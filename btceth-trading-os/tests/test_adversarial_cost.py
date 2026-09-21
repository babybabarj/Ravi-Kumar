from __future__ import annotations

from decimal import Decimal
import pytest

from btceth_os.research.structural.adversarial_cost import (
    ADVERSARIAL_TIER,
    BASE_TIER,
    STRESSED_TIER,
    COST_PROFILES,
    compute_volatility_scaled_slippage,
    load_cost_profiles,
    evaluate_episodes_under_tier,
)
from btceth_os.research.structural.capital_governor import CapitalPolicy
from btceth_os.research.cost_model import DetailedCostPolicy
from btceth_os.research.structural.multi_leg_accounting import MultiLegTradeEpisode


def test_cost_profiles_loaded_from_yaml() -> None:
    """Verify that all 3 assumption tiers are loaded with correct research labels."""
    assert "BASE_RESEARCH_ASSUMPTION" in COST_PROFILES
    assert "STRESSED_RESEARCH_ASSUMPTION" in COST_PROFILES
    assert "ADVERSARIAL_RESEARCH_ASSUMPTION" in COST_PROFILES

    assert BASE_TIER.spot_taker_bps == Decimal("10.0")
    assert BASE_TIER.perp_taker_bps == Decimal("5.0")
    assert STRESSED_TIER.spot_base_slippage_bps == Decimal("5.0")
    assert ADVERSARIAL_TIER.spot_taker_bps == Decimal("20.0")
    assert ADVERSARIAL_TIER.perp_taker_bps == Decimal("10.0")


def test_scenario_slippage_volatility_scaling() -> None:
    """Test parameterized SCENARIO_SLIPPAGE_MODEL scaling."""
    base_slip = Decimal("2.0")

    # Zero vol -> base slippage
    assert compute_volatility_scaled_slippage(base_slip, Decimal("0.0")) == Decimal("2.0")

    # 1.0% hourly vol (threshold) -> 2.0 * (1 + 1) = 4.0 bps
    s_1pct = compute_volatility_scaled_slippage(base_slip, Decimal("0.01"))
    assert s_1pct == Decimal("4.0")

    # 2.0% hourly vol -> 2.0 * (1 + 2) = 6.0 bps
    s_2pct = compute_volatility_scaled_slippage(base_slip, Decimal("0.02"))
    assert s_2pct == Decimal("6.0")


def test_evaluation_under_cost_tiers_with_capital_policy() -> None:
    """Verify tier evaluation recomputes episodes and commits capital using CapitalPolicy."""
    cost = DetailedCostPolicy("SPOT", Decimal("0.0"), Decimal("0.0"), Decimal("0.0"))
    perp_cost = DetailedCostPolicy("PERP", Decimal("0.0"), Decimal("0.0"), Decimal("0.0"))

    ep = MultiLegTradeEpisode(
        episode_id="EP_COST_TEST",
        strategy_id="TEST",
        asset="BTC",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        spot_side=1,
        spot_entry_price=Decimal("50000.0"),
        spot_exit_price=Decimal("51000.0"),
        spot_quantity=Decimal("1.0"),
        perp_side=-1,
        perp_entry_price=Decimal("50000.0"),
        perp_exit_price=Decimal("51000.0"),
        perp_quantity=Decimal("1.0"),
        spot_cost_policy=cost,
        perp_cost_policy=perp_cost,
    )

    cap_pol = CapitalPolicy(starting_equity=Decimal("100000.0"))

    base_res = evaluate_episodes_under_tier([ep], BASE_TIER, capital_policy=cap_pol)
    stressed_res = evaluate_episodes_under_tier([ep], STRESSED_TIER, capital_policy=cap_pol)
    adv_res = evaluate_episodes_under_tier([ep], ADVERSARIAL_TIER, capital_policy=cap_pol)

    # Higher cost tier -> higher total costs, lower net pnl
    assert base_res["total_costs"] < stressed_res["total_costs"] < adv_res["total_costs"]
    assert base_res["period_net_pnl"] > stressed_res["period_net_pnl"] > adv_res["period_net_pnl"]
