"""
Tests du moteur PAMP - scenarios reels de calcul fiscal crypto.

Chaque test reproduit un scenario concret d'investisseur et verifie
que le calcul est conforme a la formule 150 VH bis du CGI.
"""

import pytest
from decimal import Decimal
from datetime import datetime

import sys
sys.path.insert(0, "/home/claude/fiscali/backend")

from app.services.models import Transaction, TransactionType, AnnualTaxReport
from app.services.pamp_calculator import PAMPCalculator, PAMPCalculatorError


# ─── Helpers ───

def tx(date_str, tx_type, asset, qty, price, total, fee="0", exchange="Binance"):
    """Shortcut pour creer une transaction."""
    return Transaction(
        date=datetime.strptime(date_str, "%Y-%m-%d"),
        tx_type=TransactionType(tx_type),
        asset=asset,
        quantity=Decimal(str(qty)),
        price_eur=Decimal(str(price)),
        total_eur=Decimal(str(total)),
        fee_eur=Decimal(str(fee)),
        exchange=exchange,
    )


# ═══ TEST 1 : Scenario simple ═══
# Achat 1 BTC a 20 000 EUR, revente a 30 000 EUR
# PV = 30000 - (20000 x 30000/30000) = 30000 - 20000 = 10 000 EUR

class TestSimpleBuyAndSell:
    def setup_method(self):
        self.calc = PAMPCalculator()

    def test_single_buy_sell(self):
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 1, 20000, 20000),
            tx("2025-06-15", "sell", "BTC", 1, 30000, 30000),
        ]
        prices = {
            "2025-06-15": {"BTC": Decimal("30000")},
        }

        self.calc.add_transactions(transactions)
        report = self.calc.compute(year=2025, portfolio_values=prices)

        assert len(report.cessions) == 1
        c = report.cessions[0]
        assert c.prix_cession == Decimal("30000")
        assert c.plus_value == Decimal("10000.00")
        assert c.is_gain is True

    def test_tax_calculation(self):
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 1, 20000, 20000),
            tx("2025-06-15", "sell", "BTC", 1, 30000, 30000),
        ]
        prices = {"2025-06-15": {"BTC": Decimal("30000")}}

        self.calc.add_transactions(transactions)
        report = self.calc.compute(year=2025, portfolio_values=prices)

        # 10000 x 31.4% = 3140 EUR
        assert report.tax_due == Decimal("3140.00")
        assert report.net_after_tax == Decimal("6860.00")


# ═══ TEST 2 : Scenario multi-achats (PTA moyen) ═══
# Achat 1 BTC a 20 000 + Achat 0.5 BTC a 30 000
# PTA total = 35 000 EUR pour 1.5 BTC
# Vente 0.5 BTC quand portfolio vaut 45 000 EUR
# Prix cession = 15 000 EUR
# PV = 15000 - (35000 x 15000/45000) = 15000 - 11666.67 = 3333.33 EUR

class TestMultipleBuys:
    def test_averaged_acquisition_cost(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 1,   20000, 20000),
            tx("2025-03-01", "buy",  "BTC", 0.5, 30000, 15000),
            tx("2025-06-15", "sell", "BTC", 0.5, 30000, 15000),
        ]
        prices = {
            "2025-06-15": {"BTC": Decimal("30000")},  # 1.5 BTC x 30000 = 45000
        }

        calc.add_transactions(transactions)
        report = calc.compute(year=2025, portfolio_values=prices)

        c = report.cessions[0]
        assert c.prix_cession == Decimal("15000")
        assert c.prix_total_acquisition == Decimal("35000")
        assert c.valeur_globale_portefeuille == Decimal("45000")
        # fraction = 35000 * 15000/45000 = 11666.67
        assert c.fraction_acquisition == Decimal("11666.67")
        # PV = 15000 - 11666.67 = 3333.33
        assert c.plus_value == Decimal("3333.33")


# ═══ TEST 3 : Moins-value ═══
# Achat 1 BTC a 40 000 EUR, vente a 25 000 EUR (marche baissier)

class TestLoss:
    def test_capital_loss(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 1, 40000, 40000),
            tx("2025-06-15", "sell", "BTC", 1, 25000, 25000),
        ]
        prices = {"2025-06-15": {"BTC": Decimal("25000")}}

        calc.add_transactions(transactions)
        report = calc.compute(year=2025, portfolio_values=prices)

        c = report.cessions[0]
        assert c.plus_value == Decimal("-15000.00")
        assert c.is_loss is True
        assert report.tax_due == Decimal("0")


# ═══ TEST 4 : Multi-assets (BTC + ETH) ═══
# Le PTA est global (tous assets confondus), c'est la regle francaise

class TestMultiAssets:
    def test_portfolio_wide_pta(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 1,   20000, 20000),
            tx("2025-02-01", "buy",  "ETH", 10,  2000,  20000),
            # PTA total = 40 000 EUR
            # Vente 5 ETH quand BTC=25000, ETH=2500
            # Valeur globale = 1*25000 + 10*2500 = 50 000
            # Prix cession = 5*2500 = 12 500
            tx("2025-06-15", "sell", "ETH", 5, 2500, 12500),
        ]
        prices = {
            "2025-06-15": {"BTC": Decimal("25000"), "ETH": Decimal("2500")},
        }

        calc.add_transactions(transactions)
        report = calc.compute(year=2025, portfolio_values=prices)

        c = report.cessions[0]
        assert c.asset == "ETH"
        assert c.prix_cession == Decimal("12500")
        assert c.prix_total_acquisition == Decimal("40000")
        assert c.valeur_globale_portefeuille == Decimal("50000")
        # fraction = 40000 * 12500/50000 = 10000
        assert c.fraction_acquisition == Decimal("10000.00")
        # PV = 12500 - 10000 = 2500
        assert c.plus_value == Decimal("2500.00")


# ═══ TEST 5 : Cessions multiples dans l'annee (PTA s'ajuste) ═══

class TestMultipleSales:
    def test_pta_adjusts_after_each_sale(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 2, 20000, 40000),
            # PTA = 40 000
            # Vente 1 : 1 BTC a 30 000, portefeuille = 2*30000 = 60 000
            tx("2025-03-15", "sell", "BTC", 1, 30000, 30000),
            # Vente 2 : 0.5 BTC a 35 000, portefeuille restant = 1*35000 = 35 000
            tx("2025-06-15", "sell", "BTC", 0.5, 35000, 17500),
        ]
        prices = {
            "2025-03-15": {"BTC": Decimal("30000")},
            "2025-06-15": {"BTC": Decimal("35000")},
        }

        calc.add_transactions(transactions)
        report = calc.compute(year=2025, portfolio_values=prices)

        # Cession 1: PV = 30000 - (40000 * 30000/60000) = 30000 - 20000 = 10000
        c1 = report.cessions[0]
        assert c1.plus_value == Decimal("10000.00")
        assert c1.fraction_acquisition == Decimal("20000.00")

        # Apres cession 1, PTA = 40000 - 20000 = 20000
        # Cession 2: PV = 17500 - (20000 * 17500/35000) = 17500 - 10000 = 7500
        c2 = report.cessions[1]
        assert c2.prix_total_acquisition == Decimal("20000")
        assert c2.plus_value == Decimal("7500.00")

        # Total
        assert report.net_plus_value == Decimal("17500.00")
        assert report.total_cessions_eur == Decimal("47500")


# ═══ TEST 6 : Exemption sous 305 EUR ═══

class TestExemption:
    def test_below_threshold(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 0.01, 20000, 200),
            tx("2025-06-15", "sell", "BTC", 0.01, 25000, 250),
        ]
        prices = {"2025-06-15": {"BTC": Decimal("25000")}}

        calc.add_transactions(transactions)
        report = calc.compute(year=2025, portfolio_values=prices)

        assert report.total_cessions_eur == Decimal("250")
        assert report.is_exempt is True
        assert report.tax_due == Decimal("0")


# ═══ TEST 7 : Frais deduits ═══

class TestFees:
    def test_fees_deducted_from_sale(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 1, 20000, 20000, fee="50"),
            # PTA = 20000 + 50 = 20050
            tx("2025-06-15", "sell", "BTC", 1, 30000, 30000, fee="100"),
            # Prix cession net = 30000 - 100 = 29900
        ]
        prices = {"2025-06-15": {"BTC": Decimal("30000")}}

        calc.add_transactions(transactions)
        report = calc.compute(year=2025, portfolio_values=prices)

        c = report.cessions[0]
        assert c.prix_cession == Decimal("29900")
        # PTA = 20050 (achat + frais d'achat)
        assert c.prix_total_acquisition == Decimal("20050")
        # fraction = 20050 * 29900/30000 = 19983.17
        # PV = 29900 - 19983.17 = 9916.83
        assert c.plus_value == Decimal("9916.83")


# ═══ TEST 8 : Erreurs ═══

class TestErrors:
    def test_sell_more_than_held(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 0.5, 20000, 10000),
            tx("2025-06-15", "sell", "BTC", 1,   30000, 30000),
        ]
        prices = {"2025-06-15": {"BTC": Decimal("30000")}}
        calc.add_transactions(transactions)

        with pytest.raises(PAMPCalculatorError, match="Cession impossible"):
            calc.compute(portfolio_values=prices)

    def test_missing_prices(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 1, 20000, 20000),
            tx("2025-06-15", "sell", "BTC", 1, 30000, 30000),
        ]
        calc.add_transactions(transactions)

        with pytest.raises(PAMPCalculatorError, match="Prix manquants"):
            calc.compute(portfolio_values={})

    def test_no_transactions(self):
        calc = PAMPCalculator()
        with pytest.raises(PAMPCalculatorError, match="Aucune transaction"):
            calc.compute()


# ═══ TEST 9 : Compensation PV / MV dans l'annee ═══

class TestCompensation:
    def test_gains_offset_losses(self):
        calc = PAMPCalculator()
        transactions = [
            tx("2025-01-15", "buy",  "BTC", 2, 30000, 60000),
            # Vente 1 a perte : 1 BTC a 20 000, portfolio = 2*20000 = 40000
            tx("2025-03-15", "sell", "BTC", 1, 20000, 20000),
            # Vente 2 en gain : 1 BTC a 50 000, portfolio = 1*50000 = 50000
            tx("2025-09-15", "sell", "BTC", 1, 50000, 50000),
        ]
        prices = {
            "2025-03-15": {"BTC": Decimal("20000")},
            "2025-09-15": {"BTC": Decimal("50000")},
        }

        calc.add_transactions(transactions)
        report = calc.compute(year=2025, portfolio_values=prices)

        # Cession 1: PV = 20000 - (60000 * 20000/40000) = 20000 - 30000 = -10000
        assert report.cessions[0].plus_value == Decimal("-10000.00")

        # Apres cession 1: PTA = 60000 - 30000 = 30000
        # Cession 2: PV = 50000 - (30000 * 50000/50000) = 50000 - 30000 = 20000
        assert report.cessions[1].plus_value == Decimal("20000.00")

        # Net: 20000 - 10000 = 10000
        assert report.net_plus_value == Decimal("10000.00")
        assert report.total_plus_values == Decimal("20000.00")
        assert report.total_moins_values == Decimal("-10000.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
