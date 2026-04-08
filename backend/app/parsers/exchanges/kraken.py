from decimal import Decimal
from app.parsers.base_parser import BaseParser
from app.services.models import Transaction, TransactionType

ASSET_MAP = {"XXBT":"BTC","XBT":"BTC","XETH":"ETH","XLTC":"LTC","XXRP":"XRP","XDOT":"DOT","DOT.S":"DOT","XXLM":"XLM","XXDG":"DOGE","XREP":"REP","XZEC":"ZEC","XXMR":"XMR","ZEUR":"EUR","ZUSD":"USD","ZGBP":"GBP","ZJPY":"JPY","ZCAD":"CAD","ZAUD":"AUD","ZCHF":"CHF","ETH2":"ETH","ETH2.S":"ETH","SOL.S":"SOL","ADA.S":"ADA","ATOM.S":"ATOM","MATIC.S":"MATIC","FLOW.S":"FLOW","KAVA.S":"KAVA","MINA.S":"MINA","LUNA2":"LUNA"}
FIAT = {"EUR","USD","GBP","JPY","CAD","AUD","CHF"}

class KrakenParser(BaseParser):
    EXCHANGE_NAME = "Kraken"
    REQUIRED_COLUMNS = ["time","type","asset","amount","fee"]

    def __init__(self):
        self._pairs: dict[str, list[dict]] = {}

    def parse_string(self, content: str) -> list[Transaction]:
        self._pairs = {}
        txs = super().parse_string(content)
        txs.extend(self._flush())
        return sorted(txs, key=lambda t: t.date)

    def parse_row(self, row: dict) -> Transaction | list[Transaction] | None:
        tt = row.get("type","").strip().lower()
        asset = self._norm(row.get("asset",""))
        amount = self.to_decimal(row.get("amount","0"))
        fee = self.to_decimal(row.get("fee","0"))
        date = self.parse_datetime(row.get("time",""))
        refid = row.get("refid","").strip()
        txid = row.get("txid","").strip()

        if tt == "trade":
            self._pairs.setdefault(refid,[]).append({"asset":asset,"amount":amount,"fee":fee,"date":date,"txid":txid})
            if len(self._pairs[refid])>=2:
                r = self._resolve(self._pairs[refid])
                del self._pairs[refid]
                return r
            return None
        if tt == "deposit":
            return Transaction(date=date,tx_type=TransactionType.DEPOSIT if asset in FIAT else TransactionType.TRANSFER,asset=asset,quantity=abs(amount),price_eur=Decimal("1") if asset=="EUR" else Decimal("0"),total_eur=abs(amount) if asset=="EUR" else Decimal("0"),fee_eur=fee,exchange=self.EXCHANGE_NAME,tx_id=txid)
        if tt == "withdrawal":
            return Transaction(date=date,tx_type=TransactionType.WITHDRAWAL if asset in FIAT else TransactionType.TRANSFER,asset=asset,quantity=abs(amount),price_eur=Decimal("1") if asset=="EUR" else Decimal("0"),total_eur=abs(amount) if asset=="EUR" else Decimal("0"),fee_eur=fee,exchange=self.EXCHANGE_NAME,tx_id=txid)
        if tt in ("staking","reward"):
            return Transaction(date=date,tx_type=TransactionType.STAKING,asset=asset,quantity=abs(amount),price_eur=Decimal("0"),total_eur=Decimal("0"),fee_eur=fee,exchange=self.EXCHANGE_NAME,tx_id=txid)
        if tt == "transfer":
            return None
        return None

    def _resolve(self, pair):
        out = [p for p in pair if p["amount"]<0]
        inc = [p for p in pair if p["amount"]>0]
        if not out or not inc: return None
        o, i, date = out[0], inc[0], pair[0]["date"]
        fee = o["fee"]+i["fee"]
        if o["asset"]=="EUR":
            return [Transaction(date=date,tx_type=TransactionType.BUY,asset=i["asset"],quantity=abs(i["amount"]),price_eur=(abs(o["amount"])/abs(i["amount"])),total_eur=abs(o["amount"]),fee_eur=fee,exchange=self.EXCHANGE_NAME,tx_id=o.get("txid",""))]
        if i["asset"]=="EUR":
            return [Transaction(date=date,tx_type=TransactionType.SELL,asset=o["asset"],quantity=abs(o["amount"]),price_eur=(abs(i["amount"])/abs(o["amount"])),total_eur=abs(i["amount"]),fee_eur=fee,exchange=self.EXCHANGE_NAME,tx_id=o.get("txid",""))]
        return [Transaction(date=date,tx_type=TransactionType.CRYPTO_SWAP,asset=i["asset"],quantity=abs(i["amount"]),price_eur=Decimal("0"),total_eur=Decimal("0"),fee_eur=fee,exchange=self.EXCHANGE_NAME,tx_id=o.get("txid",""))]

    def _flush(self):
        r = []
        for p in self._pairs.values():
            if len(p)>=2:
                t = self._resolve(p)
                if t: r.extend(t)
        self._pairs = {}
        return r

    @staticmethod
    def _norm(asset: str) -> str:
        asset = asset.strip().strip('"')
        if asset in ASSET_MAP: return ASSET_MAP[asset]
        if asset.endswith(".S"): return ASSET_MAP.get(asset[:-2], asset[:-2])
        return asset
