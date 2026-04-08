"""
Modèles de données pour le moteur fiscal Fiscali.

Types de transactions et structures utilisées par le calculateur PAMP
conformément à l'article 150 VH bis du CGI.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional


class TransactionType(Enum):
    """Types de transactions crypto."""
    BUY = "buy"              # Achat crypto avec EUR
    SELL = "sell"             # Vente crypto contre EUR (cession imposable)
    CRYPTO_SWAP = "swap"     # Échange crypto-crypto (non imposable depuis 2023)
    DEPOSIT = "deposit"      # Dépôt EUR sur exchange
    WITHDRAWAL = "withdrawal"  # Retrait EUR depuis exchange
    TRANSFER = "transfer"    # Transfert entre wallets (non imposable)
    STAKING = "staking"      # Récompense de staking (BNC - hors scope MVP)
    AIRDROP = "airdrop"      # Airdrop (BNC - hors scope MVP)
    FEE = "fee"              # Frais de transaction


@dataclass
class Transaction:
    """Représente une transaction crypto individuelle."""
    date: datetime
    tx_type: TransactionType
    asset: str                          # Ex: "BTC", "ETH"
    quantity: Decimal                   # Quantité de crypto
    price_eur: Decimal                  # Prix unitaire en EUR au moment de la tx
    total_eur: Decimal                  # Montant total en EUR
    fee_eur: Decimal = Decimal("0")     # Frais en EUR
    exchange: str = ""                  # Nom de l'exchange
    tx_id: str = ""                     # ID de transaction (optionnel)
    notes: str = ""

    @property
    def net_eur(self) -> Decimal:
        """Montant net après frais."""
        if self.tx_type == TransactionType.BUY:
            return self.total_eur + self.fee_eur  # Coût total d'achat
        elif self.tx_type == TransactionType.SELL:
            return self.total_eur - self.fee_eur  # Produit net de vente
        return self.total_eur


@dataclass
class PortfolioSnapshot:
    """État du portefeuille à un instant donné."""
    date: datetime
    holdings: dict[str, Decimal] = field(default_factory=dict)  # asset -> quantity
    total_acquisition_cost: Decimal = Decimal("0")  # Prix total d'acquisition (PTA)
    total_value_eur: Decimal = Decimal("0")         # Valeur globale en EUR

    def get_quantity(self, asset: str) -> Decimal:
        return self.holdings.get(asset, Decimal("0"))

    def add_asset(self, asset: str, quantity: Decimal):
        current = self.holdings.get(asset, Decimal("0"))
        self.holdings[asset] = current + quantity

    def remove_asset(self, asset: str, quantity: Decimal):
        current = self.holdings.get(asset, Decimal("0"))
        new_qty = current - quantity
        if new_qty < Decimal("0"):
            raise ValueError(
                f"Quantité insuffisante de {asset}: "
                f"détenu={current}, demandé={quantity}"
            )
        if new_qty == Decimal("0"):
            del self.holdings[asset]
        else:
            self.holdings[asset] = new_qty


@dataclass
class CessionResult:
    """Résultat du calcul de plus/moins-value pour une cession."""
    date: datetime
    asset: str
    quantity: Decimal
    prix_cession: Decimal               # Prix de cession (net de frais)
    prix_total_acquisition: Decimal      # PTA avant cette cession
    valeur_globale_portefeuille: Decimal  # Valeur globale avant cession
    fraction_acquisition: Decimal        # PTA × (prix_cession / valeur_globale)
    plus_value: Decimal                  # Plus ou moins-value
    exchange: str = ""
    tx_id: str = ""

    @property
    def is_gain(self) -> bool:
        return self.plus_value > Decimal("0")

    @property
    def is_loss(self) -> bool:
        return self.plus_value < Decimal("0")


@dataclass
class AnnualTaxReport:
    """Rapport fiscal annuel - données pour le formulaire 2086."""
    year: int
    cessions: list[CessionResult] = field(default_factory=list)
    total_cessions_eur: Decimal = Decimal("0")   # Somme des prix de cession
    total_plus_values: Decimal = Decimal("0")     # Somme des PV positives
    total_moins_values: Decimal = Decimal("0")    # Somme des MV (négatif)
    net_plus_value: Decimal = Decimal("0")        # PV nette annuelle

    # Taux 2026
    FLAT_TAX_RATE: Decimal = Decimal("0.314")     # 31.4% (12.8% IR + 18.6% PS)
    EXEMPTION_THRESHOLD: Decimal = Decimal("305") # Seuil d'exonération

    @property
    def is_exempt(self) -> bool:
        """Exonéré si total des cessions < 305€."""
        return self.total_cessions_eur <= self.EXEMPTION_THRESHOLD

    @property
    def tax_due(self) -> Decimal:
        """Impôt dû (flat tax)."""
        if self.is_exempt or self.net_plus_value <= Decimal("0"):
            return Decimal("0")
        return (self.net_plus_value * self.FLAT_TAX_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def net_after_tax(self) -> Decimal:
        """Plus-value nette après impôt."""
        if self.net_plus_value <= Decimal("0"):
            return self.net_plus_value
        return self.net_plus_value - self.tax_due
