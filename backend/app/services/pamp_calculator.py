"""
Moteur de calcul PAMP (Prix d'Acquisition Moyen Pondere)
========================================================

Implemente la formule de l'article 150 VH bis du Code General des Impots
pour le calcul des plus-values sur cessions d'actifs numeriques.

Formule par cession :
    PV = Prix_cession - (PTA x Prix_cession / Valeur_globale_portefeuille)

Apres chaque cession, le PTA est ajuste :
    Nouveau_PTA = Ancien_PTA - (Ancien_PTA x Prix_cession / Valeur_globale)

Regles cles :
    - Seules les cessions crypto -> EUR sont imposables
    - Echanges crypto <-> crypto NON imposables (depuis 2023)
    - Seuil : total cessions < 305 EUR/an -> exoneration
    - Flat tax 2026 : 31.4% (12.8% IR + 18.6% PS)
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional
from copy import deepcopy

from .models import (
    Transaction,
    TransactionType,
    PortfolioSnapshot,
    CessionResult,
    AnnualTaxReport,
)


class PAMPCalculatorError(Exception):
    """Erreur dans le calcul PAMP."""
    pass


class PAMPCalculator:
    """
    Calculateur de plus-values crypto selon la methode PAMP francaise.

    Usage:
        calc = PAMPCalculator()
        calc.add_transactions(transactions)
        report = calc.compute(year=2025, portfolio_values={...})
    """

    def __init__(self):
        self._transactions: list[Transaction] = []
        self._portfolio = PortfolioSnapshot(date=datetime.min)
        self._cessions: list[CessionResult] = []
        self._computed = False

    @property
    def portfolio(self) -> PortfolioSnapshot:
        return deepcopy(self._portfolio)

    @property
    def cessions(self) -> list[CessionResult]:
        return list(self._cessions)

    def add_transactions(self, transactions: list[Transaction]) -> None:
        self._transactions.extend(transactions)
        self._computed = False

    def compute(
        self,
        year: Optional[int] = None,
        portfolio_values: Optional[dict[str, dict[str, Decimal]]] = None,
    ) -> AnnualTaxReport:
        """
        Calcule les plus/moins-values pour toutes les cessions.

        Args:
            year: Si specifie, ne retourne que les cessions de cette annee.
            portfolio_values: Prix par date de cession.
                Format: {"2025-03-15": {"BTC": Decimal("85000"), ...}}
        """
        if not self._transactions:
            raise PAMPCalculatorError("Aucune transaction a traiter.")

        self._portfolio = PortfolioSnapshot(date=datetime.min)
        self._cessions = []

        sorted_txs = sorted(self._transactions, key=lambda t: t.date)

        for tx in sorted_txs:
            self._process_transaction(tx, portfolio_values or {})

        report = self._build_report(year)
        self._computed = True
        return report

    def _process_transaction(
        self,
        tx: Transaction,
        portfolio_values: dict[str, dict[str, Decimal]],
    ) -> None:
        if tx.tx_type == TransactionType.BUY:
            self._process_buy(tx)
        elif tx.tx_type == TransactionType.SELL:
            self._process_sell(tx, portfolio_values)
        elif tx.tx_type == TransactionType.CRYPTO_SWAP:
            pass  # Non imposable, TODO: mettre a jour holdings
        elif tx.tx_type in (TransactionType.DEPOSIT, TransactionType.WITHDRAWAL):
            pass
        elif tx.tx_type == TransactionType.TRANSFER:
            pass

        self._portfolio.date = tx.date

    def _process_buy(self, tx: Transaction) -> None:
        """Achat crypto avec EUR. Augmente holdings + PTA."""
        self._portfolio.add_asset(tx.asset, tx.quantity)
        cost = tx.total_eur + tx.fee_eur
        self._portfolio.total_acquisition_cost += cost

    def _process_sell(
        self,
        tx: Transaction,
        portfolio_values: dict[str, dict[str, Decimal]],
    ) -> None:
        """
        Vente crypto contre EUR (cession imposable).
        Applique la formule 150 VH bis et ajuste le PTA.
        """
        # 1. Verifier les holdings
        held = self._portfolio.get_quantity(tx.asset)
        if held < tx.quantity:
            raise PAMPCalculatorError(
                f"Cession impossible : {tx.quantity} {tx.asset} demande, "
                f"seulement {held} detenu. "
                f"Date: {tx.date.strftime('%Y-%m-%d')}, Exchange: {tx.exchange}"
            )

        # 2. Prix de cession net de frais
        prix_cession = tx.total_eur - tx.fee_eur
        if prix_cession <= Decimal("0"):
            raise PAMPCalculatorError(
                f"Prix de cession negatif ou nul apres frais. "
                f"Total: {tx.total_eur}, Frais: {tx.fee_eur}"
            )

        # 3. Valeur globale du portefeuille AVANT cession
        valeur_globale = self._compute_portfolio_value(
            tx.date, portfolio_values
        )
        if valeur_globale <= Decimal("0"):
            raise PAMPCalculatorError(
                f"Valeur globale du portefeuille <= 0 au {tx.date}."
            )

        # 4. Formule 150 VH bis
        pta = self._portfolio.total_acquisition_cost

        # Fraction du PTA imputable = PTA x (prix_cession / valeur_globale)
        fraction = (pta * prix_cession / valeur_globale).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Plus-value = prix_cession - fraction
        plus_value = (prix_cession - fraction).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # 5. Enregistrer
        cession = CessionResult(
            date=tx.date,
            asset=tx.asset,
            quantity=tx.quantity,
            prix_cession=prix_cession,
            prix_total_acquisition=pta,
            valeur_globale_portefeuille=valeur_globale,
            fraction_acquisition=fraction,
            plus_value=plus_value,
            exchange=tx.exchange,
            tx_id=tx.tx_id,
        )
        self._cessions.append(cession)

        # 6. Ajuster le PTA
        self._portfolio.total_acquisition_cost = pta - fraction

        # 7. Retirer les cryptos vendues
        self._portfolio.remove_asset(tx.asset, tx.quantity)

    def _compute_portfolio_value(
        self,
        date: datetime,
        portfolio_values: dict[str, dict[str, Decimal]],
    ) -> Decimal:
        """Calcule la valeur totale du portefeuille en EUR a une date."""
        date_key = date.strftime("%Y-%m-%d")
        prices = portfolio_values.get(date_key, {})

        if not prices and self._portfolio.holdings:
            raise PAMPCalculatorError(
                f"Prix manquants pour le {date_key}. "
                f"Assets detenus: {list(self._portfolio.holdings.keys())}. "
                f"Fournissez les prix via portfolio_values."
            )

        total = Decimal("0")
        for asset, quantity in self._portfolio.holdings.items():
            price = prices.get(asset)
            if price is None:
                raise PAMPCalculatorError(
                    f"Prix manquant pour {asset} au {date_key}."
                )
            total += quantity * price

        self._portfolio.total_value_eur = total
        return total

    def _build_report(self, year: Optional[int] = None) -> AnnualTaxReport:
        if year:
            cessions = [c for c in self._cessions if c.date.year == year]
        else:
            cessions = list(self._cessions)

        report = AnnualTaxReport(
            year=year or (cessions[0].date.year if cessions else 0),
            cessions=cessions,
        )

        for c in cessions:
            report.total_cessions_eur += c.prix_cession
            if c.is_gain:
                report.total_plus_values += c.plus_value
            else:
                report.total_moins_values += c.plus_value

        report.net_plus_value = report.total_plus_values + report.total_moins_values
        return report

    def get_portfolio_state(self) -> dict:
        return {
            "date": self._portfolio.date.isoformat(),
            "holdings": {
                asset: str(qty)
                for asset, qty in self._portfolio.holdings.items()
            },
            "total_acquisition_cost": str(self._portfolio.total_acquisition_cost),
            "total_value_eur": str(self._portfolio.total_value_eur),
        }

    def summary(self, report: AnnualTaxReport) -> str:
        """Resume lisible du rapport fiscal."""
        lines = [
            f"=== RAPPORT FISCAL {report.year} ===",
            f"",
            f"Nombre de cessions imposables : {len(report.cessions)}",
            f"Total des cessions            : {report.total_cessions_eur:>12} EUR",
            f"",
        ]

        for i, c in enumerate(report.cessions, 1):
            sign = "+" if c.is_gain else ""
            lines.append(
                f"  Cession {i}: {c.quantity} {c.asset} le {c.date.strftime('%d/%m/%Y')}"
            )
            lines.append(f"    Prix de cession          : {c.prix_cession:>12} EUR")
            lines.append(f"    PTA avant cession        : {c.prix_total_acquisition:>12} EUR")
            lines.append(f"    Valeur globale portfolio  : {c.valeur_globale_portefeuille:>12} EUR")
            lines.append(f"    Fraction d'acquisition   : {c.fraction_acquisition:>12} EUR")
            lines.append(f"    Plus/moins-value         : {sign}{c.plus_value:>11} EUR")
            lines.append("")

        lines.extend([
            f"-----------------------------------",
            f"Total plus-values            : +{report.total_plus_values:>11} EUR",
            f"Total moins-values           :  {report.total_moins_values:>11} EUR",
            f"Plus-value nette             :  {report.net_plus_value:>11} EUR",
            f"",
            f"Seuil d'exoneration (305 EUR): {'OUI' if report.is_exempt else 'NON'}",
        ])

        if not report.is_exempt and report.net_plus_value > Decimal("0"):
            ir = (report.net_plus_value * Decimal("0.128")).quantize(Decimal("0.01"))
            ps = (report.net_plus_value * Decimal("0.186")).quantize(Decimal("0.01"))
            lines.extend([
                f"",
                f"Flat tax (31.4%)             :  {report.tax_due:>11} EUR",
                f"  -> IR (12.8%)              :  {ir:>11} EUR",
                f"  -> PS (18.6%)              :  {ps:>11} EUR",
                f"",
                f"Net apres impot              :  {report.net_after_tax:>11} EUR",
            ])

        lines.append(f"")
        lines.append(f"-> Case 3AN (2042-C) : {max(report.net_plus_value, Decimal('0'))} EUR")
        lines.append(f"-> Case 3BN (2042-C) : {abs(min(report.net_plus_value, Decimal('0')))} EUR")

        return "\n".join(lines)
