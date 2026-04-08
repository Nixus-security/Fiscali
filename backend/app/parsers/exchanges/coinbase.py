from decimal import Decimal
from app.parsers.base_parser import BaseParser
from app.services.models import Transaction, TransactionType

class CoinbaseParser(BaseParser):
    EXCHANGE_NAME = "Coinbase"
    REQUIRED_COLUMNS = ["Timestamp","Transaction Type","Asset","Quantity Transacted"]

    def parse_row(self, row: dict) -> Transaction | None:
        tt = row.get("Transaction Type","").strip().lower()
        asset = row.get("Asset","").strip().upper()
        date = self.parse_datetime(row.get("Timestamp",""))
        qty = self.to_decimal(row.get("Quantity Transacted","0"))
        spot = self.to_decimal(row.get("Spot Price at Transaction","0"))
        subtotal = self.to_decimal(row.get("Subtotal","0"))
        fees = self.to_decimal(row.get("Fees and/or Spread","0"))
        total_eur = subtotal if subtotal else (qty * spot)

        if tt == "buy":
            return Transaction(date=date,tx_type=TransactionType.BUY,asset=asset,quantity=qty,price_eur=spot,total_eur=total_eur,fee_eur=fees,exchange=self.EXCHANGE_NAME)
        if tt == "sell":
            return Transaction(date=date,tx_type=TransactionType.SELL,asset=asset,quantity=qty,price_eur=spot,total_eur=total_eur,fee_eur=fees,exchange=self.EXCHANGE_NAME)
        if tt == "convert":
            return Transaction(date=date,tx_type=TransactionType.CRYPTO_SWAP,asset=asset,quantity=qty,price_eur=spot,total_eur=total_eur,fee_eur=fees,exchange=self.EXCHANGE_NAME)
        if tt in ("send","receive"):
            return Transaction(date=date,tx_type=TransactionType.TRANSFER,asset=asset,quantity=qty,price_eur=spot,total_eur=Decimal("0"),exchange=self.EXCHANGE_NAME)
        if tt in ("staking income","rewards income","learning reward"):
            return Transaction(date=date,tx_type=TransactionType.STAKING,asset=asset,quantity=qty,price_eur=spot,total_eur=qty*spot if spot else Decimal("0"),exchange=self.EXCHANGE_NAME)
        return None
