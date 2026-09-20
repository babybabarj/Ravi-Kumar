from __future__ import annotations

from decimal import Decimal
import pytest

from btceth_os.research.cost_model import (
    BASE_PERP_COST,
    BASE_SPOT_COST,
    STRESSED_PERP_COST,
    compute_funding_cash_flow,
)


def test_hand_calculated_turnover_rates():
    # Base Perp: 5 fee + 1 spread + 4 slippage = 10 bps one-way
    assert BASE_PERP_COST.total_turnover_rate == Decimal("0.0010")

    # Stressed Perp: 10 fee + 3 spread + 12 slippage = 25 bps one-way
    assert STRESSED_PERP_COST.total_turnover_rate == Decimal("0.0025")

    # Base Spot: 10 fee + 1 spread + 4 slippage = 15 bps one-way
    assert BASE_SPOT_COST.total_turnover_rate == Decimal("0.0015")
    assert not BASE_SPOT_COST.include_funding


def test_binance_funding_cash_flow_directions():
    # Positive funding rate (+1 bp = +0.0001)
    rate_pos = Decimal("0.0001")

    # Long pays positive funding
    cf_long_pos = compute_funding_cash_flow(position=1, funding_rate=rate_pos)
    assert cf_long_pos == Decimal("-0.0001")

    # Short receives positive funding
    cf_short_pos = compute_funding_cash_flow(position=-1, funding_rate=rate_pos)
    assert cf_short_pos == Decimal("0.0001")

    # Negative funding rate (-2.5 bps = -0.00025)
    rate_neg = Decimal("-0.00025")

    # Long receives negative funding
    cf_long_neg = compute_funding_cash_flow(position=1, funding_rate=rate_neg)
    assert cf_long_neg == Decimal("0.00025")

    # Short pays negative funding
    cf_short_neg = compute_funding_cash_flow(position=-1, funding_rate=rate_neg)
    assert cf_short_neg == Decimal("-0.00025")

    # Flat position has zero cash flow
    cf_flat = compute_funding_cash_flow(position=0, funding_rate=rate_pos)
    assert cf_flat == Decimal("0")
