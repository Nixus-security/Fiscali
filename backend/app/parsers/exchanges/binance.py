from decimal import Decimal
from app.parsers.base_parser import BaseParser
from app.services.models import Transaction, TransactionType

IGNORED_OPS = {"small assets exchange bnb","distribution","referral commission","commission history","savings interest","savings purchase","savings redemption","pos savings interest","pos savings purchase","pos savings redemption","launchpool interest","super bnb mining","eth 2.0 staking","asset recovery"}

class BinanceParser(BaseParser):
    EXCHANGE_NAME = "Binance"
    REQUIRED_COLUMNS = ["UTC_Time", "Operation", "Coin", "Change"]

    def __init__(self):
        self._pending: dict[str, list[dict]] = {}

    def parse_string(self, content: str) -> list[Transaction]:
        self._pending = {}
        txs = super().parse_string(content)
        txs.extend(self._flush())
        return sorted(txs, key=lambda t: t.date)

    def parse_row(self, row: dict) -> Transaction | list[Transaction] | None:
        op = row.get("Operation","").strip().lower()
        coin = row.get("Coin","").strip().upper()
        if coin == "BETH": coin = "ETH"
        change = self.to_decimal(row.get("Change","0"))
        date = self.parse_datetime(row.get("UTC_Time",""))
        ts_key = row.get("UTC_Time","").strip()

        if op in IGNORED_OPS:
            return None

        if op == "transaction related":
            self._pending.setdefault(ts_key, []).append({"coin":coin,"change":change,"date":date})
            group = self._pending[ts_key]
            if len(group) >= 2:
                result = self._resolve(group)
                del self._pending[ts_key]
                return result
            return None

        if op in ("buy","transaction buy"):
            return Transaction(date=date, tx_type=TransactionType.BUY, asset=coin, quantity=abs(change), price_eur=Decimal("0"), total_eur=Decimal("0"), exchange=self.EXCHANGE_NAME)
        if op in ("sell","transaction sell"):
            return Transaction(date=date, tx_type=TransactionType.SELL, asset=coin, quantity=abs(change), price_eur=Decimal("0"), total_eur=abs(change), exchange=self.EXCHANGE_NAME)
        if op == "deposit":
            return Transaction(date=date, tx_type=TransactionType.DEPOSIT if coin=="EUR" else TransactionType.TRANSFER, asset=coin, quantity=abs(change), price_eur=Decimal("0"), total_eur=abs(change) if coin=="EUR" else Decimal("0"), exchange=self.EXCHANGE_NAME)
        if op == "withdrawal":
            return Transaction(date=date, tx_type=TransactionType.WITHDRAWAL if coin=="EUR" else TransactionType.TRANSFER, asset=coin, quantity=abs(change), price_eur=Decimal("0"), total_eur=abs(change) if coin=="EUR" else Decimal("0"), exchange=self.EXCHANGE_NAME)
        if op in ("staking rewards","staking"):
            return Transaction(date=date, tx_type=TransactionType.STAKING, asset=coin, quantity=abs(change), price_eur=Decimal("0"), total_eur=Decimal("0"), exchange=self.EXCHANGE_NAME)
        return None

    def _resolve(self, group):
        inc = [g for g in group if g["change"] > 0]
        out = [g for g in group if g["change"] < 0]
        if not inc or not out: return None
        txs, date = [], group[0]["date"]
        for i in inc:
            for o in out:
                if i["coin"]=="EUR":
                    txs.append(Transaction(date=date,tx_type=TransactionType.SELL,asset=o["coin"],quantity=abs(o["change"]),price_eur=(i["change"]/abs(o["change"])),total_eur=i["change"],exchange=self.EXCHANGE_NAME))
                elif o["coin"]=="EUR":
                    txs.append(Transaction(date=date,tx_type=TransactionType.BUY,asset=i["coin"],quantity=i["change"],price_eur=(abs(o["change"])/i["change"]),total_eur=abs(o["change"]),exchange=self.EXCHANGE_NAME))
                else:
                    txs.append(Transaction(date=date,tx_type=TransactionType.CRYPTO_SWAP,asset=i["coin"],quantity=i["change"],price_eur=Decimal("0"),total_eur=Decimal("0"),exchange=self.EXCHANGE_NAME))
        return txs or None

    def _flush(self):
        r = []
        for g in self._pending.values():
            if len(g)>=2:
                t = self._resolve(g)
                if t: r.extend(t)
        self._pending = {}
        return r
