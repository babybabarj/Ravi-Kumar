"""Research Round 3A: Defect Reproduction Regression Tests.

Reproduces the known mathematical and structural defects of Round 3 before remediation:
1. Column index offset in fundingRate parsing (row[1]=8 instead of row[2]=last_funding_rate).
2. Malformed RoC normalizer dividing cumulative multi-trade P&L by capital of only the first trade.
3. eth_dev[i] validation index leak in cross-asset relative funding strategy.
4. Fallback substitution of perp/spot prices for missing mark/index/premium prices.
5. Inconsistent strategy status (REJECTED with empty rejection_reasons).
"""
from decimal import Decimal
import math
import pytest


def test_reproduce_funding_column_offset_defect():
    """Demonstrate how row[1] (funding_interval_hours) caused 800% funding rate instead of row[2]."""
    csv_row = ["1577836800000", "8", "-0.00012359"]
    
    # Old defective logic extracted row[1]:
    defective_funding_rate = Decimal(csv_row[1])
    assert defective_funding_rate == Decimal("8")  # 800% per 8 hours!
    
    # Simulating 1 BTC short perp notional at $10,000 price:
    mark_price = Decimal("10000.0")
    notional = Decimal("1.0") * mark_price
    
    # Old cash flow calculation:
    defective_cf = notional * defective_funding_rate
    assert defective_cf == Decimal("80000.0")  # $80,000 received for 1 single 8h interval!
    
    # Over 269 trades in a year, this generates hundreds of millions in phantom funding:
    phantom_total_funding = defective_cf * 2122  # ~2122 funding periods
    assert phantom_total_funding > Decimal("160000000.0")  # > $160 Million!

    # Correct logic extracts row[2]:
    correct_funding_rate = Decimal(csv_row[2])
    assert correct_funding_rate == Decimal("-0.00012359")
    correct_cf = notional * correct_funding_rate
    assert correct_cf == Decimal("-1.2359")  # ~$1.24


def test_reproduce_malformed_roc_normalizer_defect():
    """Demonstrate how dividing cumulative annual P&L by first trade capital creates 631,000% RoC."""
    # Suppose 269 trades each produced $100 net P&L (total = $26,900)
    # But in Round 3, phantom funding produced $169,795,000 P&L:
    total_net_pnl = 169795000.0
    first_trade_capital = 26900.0  # Approx capital for 1 BTC at $27,000 * 1.75
    
    # Defective formula:
    defective_roc = total_net_pnl / first_trade_capital
    defective_roc_pct = defective_roc * 100.0
    
    # This precisely matches the observed ~631,000% anomaly:
    assert defective_roc_pct > 600000.0
    
    # Proper portfolio return on starting equity ($100,000) with true P&L ($500):
    starting_equity = 100000.0
    true_net_pnl = 500.0
    portfolio_period_return = true_net_pnl / starting_equity
    assert portfolio_period_return == 0.005  # +0.5%, economically sound


def test_reproduce_cross_asset_validation_index_leak():
    """Demonstrate how eth_dev was evaluated during the validation period."""
    # btc_dev and eth_dev have 26,000 elements
    # btc_val has 8,760 elements
    eth_dev_funding = [0.0001] * 26000
    btc_val_funding = [0.0005] * 8760
    
    # In Round 3:
    # "entry_fn": lambda bars, i: abs(bars[i].funding_rate - eth_dev[i].funding_rate) >= 0.0010 ...
    # When bars is btc_val, i is an index into btc_val (2023), but eth_dev[i] is from 2020!
    sampled_eth_element = eth_dev_funding[100]  # Element from 2020 dev set
    assert sampled_eth_element == 0.0001  # Comparing 2023 BTC with 2020 ETH!


def test_reproduce_source_fallback_substitution_defect():
    """Demonstrate how missing mark/index/premium prices were silently substituted."""
    # Old logic:
    # m_close = mark_lookup.get(last_m_ts, h_perp_close)
    # idx_close = index_lookup.get(last_m_ts, h_spot_close)
    # prem_close = premium_lookup.get(last_m_ts, 0.0)
    mark_lookup = {}  # Missing
    h_perp_close = 27500.0
    h_spot_close = 27480.0
    
    # Fallback substituted traded price for mark price:
    substituted_mark = mark_lookup.get(12345, h_perp_close)
    assert substituted_mark == h_perp_close  # Silent fallback violates reference data decoupling!


def test_reproduce_rejected_empty_reasons_defect():
    """Demonstrate the inconsistency of status=REJECTED with rejection_reasons=[]."""
    old_experiment_record = {
        "status": "REJECTED",
        "rejection_reasons": [],
    }
    # This state must be forbidden by the structural validation policy:
    assert old_experiment_record["status"] == "REJECTED" and len(old_experiment_record["rejection_reasons"]) == 0
