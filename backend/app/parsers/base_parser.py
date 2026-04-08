import csv, io
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import BinaryIO
from app.services.models import Transaction

class ParseError(Exception):
    pass

class BaseParser(ABC):
    EXCHANGE_NAME: str = ""
    REQUIRED_COLUMNS: list[str] = []

    def parse_file(self, file: BinaryIO, encoding: str = "utf-8") -> list[Transaction]:
        try:
            content = file.read().decode(encoding)
        except UnicodeDecodeError:
            content = file.read().decode("utf-8-sig")
        content = content.lstrip("\ufeff")
        return self.parse_string(content)

    def parse_string(self, content: str) -> list[Transaction]:
        lines = content.strip().split("\n")
        header_line_idx = self._find_header_line(lines)
        if header_line_idx > 0:
            content = "\n".join(lines[header_line_idx:])
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames:
            cleaned = [c.strip().strip('"') for c in reader.fieldnames]
            missing = [c for c in self.REQUIRED_COLUMNS if c not in cleaned]
            if missing:
                raise ParseError(f"Colonnes manquantes dans le CSV {self.EXCHANGE_NAME}: {missing}. Colonnes trouvees: {cleaned}")
        transactions = []
        for i, row in enumerate(reader, start=2):
            try:
                row = {k.strip().strip('"'): v.strip() if v else "" for k, v in row.items() if k}
                txs = self.parse_row(row)
                if txs:
                    if isinstance(txs, list):
                        transactions.extend(txs)
                    else:
                        transactions.append(txs)
            except Exception as e:
                raise ParseError(f"Erreur ligne {i} ({self.EXCHANGE_NAME}): {e}. Donnees: {dict(row)}")
        return sorted(transactions, key=lambda t: t.date)

    def _find_header_line(self, lines: list[str]) -> int:
        for i, line in enumerate(lines):
            has_required = sum(1 for col in self.REQUIRED_COLUMNS if col.lower() in line.lower())
            if has_required >= len(self.REQUIRED_COLUMNS) // 2 + 1:
                return i
        return 0

    @abstractmethod
    def parse_row(self, row: dict) -> Transaction | list[Transaction] | None:
        ...

    @staticmethod
    def to_decimal(value: str) -> Decimal:
        if not value or value.strip() == "":
            return Decimal("0")
        value = value.strip().replace(",", "").replace(" ", "")
        try:
            return Decimal(value)
        except InvalidOperation:
            raise ParseError(f"Impossible de convertir '{value}' en nombre.")

    @staticmethod
    def parse_datetime(date_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime:
        date_str = date_str.strip().strip('"')
        for f in [fmt, "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S"]:
            try:
                return datetime.strptime(date_str, f)
            except ValueError:
                continue
        raise ParseError(f"Format de date non reconnu: '{date_str}'")
