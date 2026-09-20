"""Unit tests for multi-leg carry accounting, signed funding cash flows, and capital normalization."""
from decimal import Decimal
import pytest

from btceth_os.research.cost_model import BASE_PERP_COST, BASE_SPOT_COST, compute_funding_cash_flow
from btceth_os.research.structural.capital_model import (
    CapitalRequirementPolicy,
    calculate_total_committed_capital,
    compute_capital_normalized_metrics,
    compute_round_trip_breakeven_bps,
)
from btceth_os.research.structural.intent import LegIntent, MultiLegStrategyIntent
from btceth_os.research.structural.multi_leg_accounting import (
    FundingCashFlowEvent,
    MultiLegTradeEpisode,
)


def test_spot_no_funding_rule():
    """Spot leg must NEVER generate funding cash flows."""
    assert BASE_SPOT_COST.include_funding is False
    # Spot position has 0 funding regardless of rate
    spot_cf = compute_funding_cash_flow(position=0, funding_rate=Decimal("0.0010"))
    assert spot_cf == Decimal("0")


def test_funding_cash_flow_signs():
    """Perpetual funding sign semantics according to Binance USD-M rules."""
    rate_pos = Decimal("0.0005")  # +5 bps (crowded longs pay shorts)
    rate_neg = Decimal("-0.0005") # -5 bps (crowded shorts pay longs)

    # Long Perp (+1)
    # Pays positive funding (cash flow negative)
    assert compute_funding_cash_flow(position=1, funding_rate=rate_pos) == Decimal("-0.0005")
    # Receives negative funding (cash flow positive)
    assert compute_funding_cash_flow(position=1, funding_rate=rate_neg) == Decimal("0.0005")

    # Short Perp (-1)
    # Receives positive funding (cash flow positive)
    assert compute_funding_cash_flow(position=-1, funding_rate=rate_pos) == Decimal("0.0005")
    # Pays negative funding (cash flow negative)
    assert compute_funding_cash_flow(position=-1, funding_rate=rate_neg) == Decimal("-0.0005")


def test_multi_leg_delta_neutral_pnl_decomposition():
    """Verify that a perfect hedge removes directional market risk, leaving basis + funding - friction."""
    # Scenario:
    # Buy 1 BTC Spot at $30,000
    # Short 1 BTC Perp at $30,050 (Basis = +$50)
    # Market moves up violently to $40,000 spot, $40,010 perp (Basis compresses to +$10)
    # 3 funding payments occurred at mark price $35,000 with +0.02% (+2 bps) each
    
    funding_events = (
        FundingCashFlowEvent(
            ts_event_ns=1000,
            funding_rate=Decimal("0.0002"),
            mark_price=Decimal("35000"),
            position_side=-1,  # Short perp
            notional_usd=Decimal("35000"),
            cash_flow_usd=Decimal("7.0"),  # 35,000 * 0.0002 = +$7.00
        ),
        FundingCashFlowEvent(
            ts_event_ns=2000,
            funding_rate=Decimal("0.0002"),
            mark_price=Decimal("35000"),
            position_side=-1,
            notional_usd=Decimal("35000"),
            cash_flow_usd=Decimal("7.0"),
        ),
        FundingCashFlowEvent(
            ts_event_ns=3000,
            funding_rate=Decimal("0.0002"),
            mark_price=Decimal("35000"),
            position_side=-1,
            notional_usd=Decimal("35000"),
            cash_flow_usd=Decimal("7.0"),
        ),
    )

    episode = MultiLegTradeEpisode(
        episode_id="EP_TEST_001",
        strategy_id="STRUCT_A_BTC_SPOT_PERP_CARRY",
        asset="BTC",
        entry_ts_ns=0,
        exit_ts_ns=24 * 3_600_000_000_000,  # 24 hours
        spot_side=1,
        spot_entry_price=Decimal("30000"),
        spot_exit_price=Decimal("40000"),
        spot_quantity=Decimal("1.0"),
        perp_side=-1,
        perp_entry_price=Decimal("30050"),
        perp_exit_price=Decimal("40010"),
        perp_quantity=Decimal("1.0"),
        spot_cost_policy=BASE_SPOT_COST,
        perp_cost_policy=BASE_PERP_COST,
        funding_events=funding_events,
    )

    # Spot P&L: 1.0 * (40,000 - 30,000) = +$10,000.00
    assert episode.spot_pnl == Decimal("10000.0")
    # Perp P&L: -1.0 * (40,010 - 30,050) = -$9,960.00
    assert episode.perp_pnl == Decimal("-9960.0")
    # Basis P&L: $10,000 - $9,960 = +$40.00 (basis compressed from $50 to $10)
    assert episode.basis_pnl == Decimal("40.0")
    # Funding P&L: 3 * $7 = +$21.00
    assert episode.total_funding_pnl == Decimal("21.0")

    # Costs: Spot fees (10 bps each way) + Perp fees (5 bps each way) + slippage
    assert episode.spot_fees > Decimal("0")
    assert episode.perp_fees > Decimal("0")
    assert episode.net_pnl == episode.basis_pnl + episode.total_funding_pnl - episode.total_costs


def test_return_on_capital_denominator():
    """Capital normalization must include spot notional, perp margin, and safety buffer."""
    spot_notional = Decimal("100000.0")  # $100,000 spot
    perp_notional = Decimal("100000.0")  # $100,000 perp
    policy = CapitalRequirementPolicy(
        spot_capital_fraction=Decimal("1.00"),
        perp_margin_fraction=Decimal("0.50"),   # 2x leverage on perp
        safety_buffer_fraction=Decimal("0.25"), # 25% buffer
    )
    total_committed = calculate_total_committed_capital(spot_notional, perp_notional, policy)
    # $100k + (0.50 + 0.25) * $100k = $175,000
    assert total_committed == Decimal("175000.0")

    # Gross exposure is $200,000
    gross_exposure = spot_notional + perp_notional
    assert gross_exposure == Decimal("200000.0")


def test_round_trip_breakeven_bps():
    # Base: Spot (10 fee + 5 slip = 15 one-way = 30 RT) + Perp (5 fee + 5 slip = 10 one-way = 20 RT) = 50 bps RT
    be = compute_round_trip_breakeven_bps(
        spot_fee_bps=Decimal("10.0"),
        spot_slip_bps=Decimal("5.0"),
        perp_fee_bps=Decimal("5.0"),
        perp_slip_bps=Decimal("5.0"),
    )
    assert be == Decimal("50.0")


def test_multi_leg_strategy_intent_creation():
    intent = MultiLegStrategyIntent(
        strategy_id="STRUCT_A_BTC_SPOT_PERP_CARRY",
        target_hedge_ratio=Decimal("1.0"),
        leg_1=LegIntent(market="BINANCE:SPOT", symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=Decimal("1.5")),
        leg_2=LegIntent(market="BINANCE:USD_M_PERP", symbol="BTCUSDT", side="SELL", order_type="MARKET", quantity=Decimal("1.5"), role="HEDGE"),
        max_legging_delay_ms=500,
        max_delta_mismatch_usd=Decimal("250.0"),
    )
    d = intent.to_dict()
    assert d["strategy_id"] == "STRUCT_A_BTC_SPOT_PERP_CARRY"
    assert d["leg_1"]["side"] == "BUY"
    assert d["leg_2"]["side"] == "SELL"
    assert d["atomicity_policy"] == "ALL_OR_CANCEL_HEDGE"
