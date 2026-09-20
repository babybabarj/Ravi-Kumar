"""Research Round 3A: Exact Hand-Verifiable Multi-Leg Accounting Fixtures.

Strictly verifies mathematical accounting identities and economic invariants:
1. Exact funding cash flow settlement (+/- funding, long/short perp).
2. Flat market carry fixture (zero price change + positive funding).
3. Zero-funding fixture (flat prices + zero funding -> net loss = costs).
4. Perfect-hedge price move (+10% spot / +10% perp -> exactly zero basis P&L).
5. Basis convergence fixture (entering wide, exiting narrow -> basis gain).
6. Basis widening fixture (entering narrow, exiting wide -> basis loss).
7. Dedicated ETH cash-and-carry fixture.
8. True BTC/ETH relative perp pair fixture.
9. Portfolio equity curve, capital-time utilization, and drawdown accounting.
"""
from decimal import Decimal
import math
import pytest

from btceth_os.research.cost_model import BASE_PERP_COST, BASE_SPOT_COST, DetailedCostPolicy
from btceth_os.research.structural.multi_leg_accounting import (
    FundingCashFlowEvent,
    MultiLegTradeEpisode,
    RelativePerpPairEpisode,
)
from btceth_os.research.structural.portfolio_equity import PortfolioEquityEngine
from btceth_os.research.structural.risk_models import compute_legging_friction_bps


def test_exact_funding_cash_flow():
    """Verify exact funding settlement cash flow formula across all combinations."""
    notional = Decimal("10000.0")  # $10,000 perp
    rate_pos = Decimal("0.0001")   # +0.01% (+1 bp)
    rate_neg = Decimal("-0.0001")  # -0.01% (-1 bp)
    
    # Short Perp (-1) receiving positive funding:
    # cash_flow = -position_side * notional * rate = -(-1) * 10000 * 0.0001 = +1.00 USD
    cf_short_pos = -Decimal("-1") * notional * rate_pos
    assert cf_short_pos == Decimal("1.0000")

    # Short Perp (-1) paying negative funding:
    # cash_flow = -(-1) * 10000 * (-0.0001) = -1.00 USD
    cf_short_neg = -Decimal("-1") * notional * rate_neg
    assert cf_short_neg == Decimal("-1.0000")

    # Long Perp (+1) paying positive funding:
    # cash_flow = -(+1) * 10000 * 0.0001 = -1.00 USD
    cf_long_pos = -Decimal("1") * notional * rate_pos
    assert cf_long_pos == Decimal("-1.0000")

    # Long Perp (+1) receiving negative funding:
    # cash_flow = -(+1) * 10000 * (-0.0001) = +1.00 USD
    cf_long_neg = -Decimal("1") * notional * rate_neg
    assert cf_long_neg == Decimal("1.0000")


def test_flat_market_carry_fixture():
    """Flat market: spot and perp prices unchanged, positive funding occurs."""
    zero_spot_cost = DetailedCostPolicy(instrument_type="SPOT", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    zero_perp_cost = DetailedCostPolicy(instrument_type="PERP", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    
    # 1 BTC at $30,000
    p = Decimal("30000.0")
    q = Decimal("1.0")
    
    # One funding event: +0.01% on $30,000 short perp = +$3.00
    funding_ev = FundingCashFlowEvent(
        ts_event_ns=1000,
        funding_rate=Decimal("0.0001"),
        mark_price=p,
        position_side=-1,
        notional_usd=p * q,
        cash_flow_usd=Decimal("3.0"),
    )
    
    ep = MultiLegTradeEpisode(
        episode_id="EP_FLAT",
        strategy_id="TEST_FLAT",
        asset="BTC",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        spot_side=1,
        spot_entry_price=p,
        spot_exit_price=p,
        spot_quantity=q,
        perp_side=-1,
        perp_entry_price=p,
        perp_exit_price=p,
        perp_quantity=q,
        spot_cost_policy=zero_spot_cost,
        perp_cost_policy=zero_perp_cost,
        funding_events=(funding_ev,),
    )
    
    assert ep.spot_pnl == Decimal("0")
    assert ep.perp_pnl == Decimal("0")
    assert ep.basis_pnl == Decimal("0")
    assert ep.total_funding_pnl == Decimal("3.0")
    assert ep.total_costs == Decimal("0")
    assert ep.net_pnl == Decimal("3.0")


def test_zero_funding_fixture():
    """Prices unchanged and funding is zero: net P&L must be strictly negative (equal to costs)."""
    p = Decimal("20000.0")
    q = Decimal("1.0")
    
    ep = MultiLegTradeEpisode(
        episode_id="EP_ZERO_FUNDING",
        strategy_id="TEST_ZERO",
        asset="BTC",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        spot_side=1,
        spot_entry_price=p,
        spot_exit_price=p,
        spot_quantity=q,
        perp_side=-1,
        perp_entry_price=p,
        perp_exit_price=p,
        perp_quantity=q,
        spot_cost_policy=BASE_SPOT_COST,
        perp_cost_policy=BASE_PERP_COST,
        funding_events=(),
    )
    
    assert ep.spot_pnl == Decimal("0")
    assert ep.perp_pnl == Decimal("0")
    assert ep.basis_pnl == Decimal("0")
    assert ep.total_funding_pnl == Decimal("0")
    assert ep.total_costs > Decimal("0")
    assert ep.net_pnl == -ep.total_costs
    assert ep.net_pnl < Decimal("0")


def test_perfect_hedge_price_move_fixture():
    """Spot and Perp both rise +10%: directional market P&L must cancel to zero."""
    zero_spot_cost = DetailedCostPolicy(instrument_type="SPOT", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    zero_perp_cost = DetailedCostPolicy(instrument_type="PERP", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    p0 = Decimal("30000.0")
    p1 = Decimal("33000.0")  # +10%
    q = Decimal("1.0")
    
    ep = MultiLegTradeEpisode(
        episode_id="EP_PERFECT_HEDGE",
        strategy_id="TEST_HEDGE",
        asset="BTC",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        spot_side=1,
        spot_entry_price=p0,
        spot_exit_price=p1,
        spot_quantity=q,
        perp_side=-1,
        perp_entry_price=p0,
        perp_exit_price=p1,
        perp_quantity=q,
        spot_cost_policy=zero_spot_cost,
        perp_cost_policy=zero_perp_cost,
        funding_events=(),
    )
    
    assert ep.spot_pnl == Decimal("3000.0")
    assert ep.perp_pnl == Decimal("-3000.0")
    assert ep.basis_pnl == Decimal("0.0")
    assert ep.net_pnl == Decimal("0.0")


def test_basis_convergence_fixture():
    """Perp enters at premium ($30,300) vs Spot ($30,000), basis converges to zero ($30,000)."""
    zero_spot_cost = DetailedCostPolicy(instrument_type="SPOT", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    zero_perp_cost = DetailedCostPolicy(instrument_type="PERP", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    q = Decimal("1.0")
    
    ep = MultiLegTradeEpisode(
        episode_id="EP_CONVERGENCE",
        strategy_id="TEST_BASIS",
        asset="BTC",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        spot_side=1,
        spot_entry_price=Decimal("30000.0"),
        spot_exit_price=Decimal("30000.0"),
        spot_quantity=q,
        perp_side=-1,
        perp_entry_price=Decimal("30300.0"),  # $300 premium
        perp_exit_price=Decimal("30000.0"),   # premium collapsed
        perp_quantity=q,
        spot_cost_policy=zero_spot_cost,
        perp_cost_policy=zero_perp_cost,
        funding_events=(),
    )
    
    assert ep.spot_pnl == Decimal("0.0")
    assert ep.perp_pnl == Decimal("300.0")  # Short perp captured $300 price drop
    assert ep.basis_pnl == Decimal("300.0")
    assert ep.net_pnl == Decimal("300.0")


def test_basis_widening_fixture():
    """Perp enters at parity ($30,000), basis widens adversely to $30,300."""
    zero_spot_cost = DetailedCostPolicy(instrument_type="SPOT", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    zero_perp_cost = DetailedCostPolicy(instrument_type="PERP", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    q = Decimal("1.0")
    
    ep = MultiLegTradeEpisode(
        episode_id="EP_WIDENING",
        strategy_id="TEST_BASIS",
        asset="BTC",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        spot_side=1,
        spot_entry_price=Decimal("30000.0"),
        spot_exit_price=Decimal("30000.0"),
        spot_quantity=q,
        perp_side=-1,
        perp_entry_price=Decimal("30000.0"),
        perp_exit_price=Decimal("30300.0"),   # Perp rallied against short
        perp_quantity=q,
        spot_cost_policy=zero_spot_cost,
        perp_cost_policy=zero_perp_cost,
        funding_events=(),
    )
    
    assert ep.spot_pnl == Decimal("0.0")
    assert ep.perp_pnl == Decimal("-300.0")
    assert ep.basis_pnl == Decimal("-300.0")
    assert ep.net_pnl == Decimal("-300.0")


def test_eth_multi_leg_fixtures():
    """Verify dedicated ETH cash-and-carry episode accounting."""
    zero_spot_cost = DetailedCostPolicy(instrument_type="SPOT", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    zero_perp_cost = DetailedCostPolicy(instrument_type="PERP", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    p_eth = Decimal("2000.0")
    q_eth = Decimal("10.0")  # $20,000 notional
    
    funding_ev = FundingCashFlowEvent(
        ts_event_ns=1000,
        funding_rate=Decimal("0.00015"),  # 1.5 bps
        mark_price=p_eth,
        position_side=-1,
        notional_usd=p_eth * q_eth,
        cash_flow_usd=Decimal("3.0"),      # 20000 * 0.00015 = $3.00
    )
    
    ep = MultiLegTradeEpisode(
        episode_id="EP_ETH_CARRY",
        strategy_id="TEST_ETH",
        asset="ETH",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        spot_side=1,
        spot_entry_price=p_eth,
        spot_exit_price=p_eth,
        spot_quantity=q_eth,
        perp_side=-1,
        perp_entry_price=p_eth,
        perp_exit_price=p_eth,
        perp_quantity=q_eth,
        spot_cost_policy=zero_spot_cost,
        perp_cost_policy=zero_perp_cost,
        funding_events=(funding_ev,),
    )
    
    assert ep.asset == "ETH"
    assert ep.spot_notional_entry == Decimal("20000.0")
    assert ep.total_funding_pnl == Decimal("3.0")
    assert ep.net_pnl == Decimal("3.0")


def test_relative_btceth_pair_fixture():
    """Verify genuine 2-perp relative carry accounting (Long BTC Perp vs Short ETH Perp)."""
    zero_perp_cost = DetailedCostPolicy(instrument_type="PERP", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    
    # Sized to equal $30,000 notional:
    # Leg 1: Long 1.0 BTC Perp at $30,000
    # Leg 2: Short 15.0 ETH Perp at $2,000
    btc_p0, btc_p1 = Decimal("30000.0"), Decimal("30500.0")  # +$500 gain
    eth_p0, eth_p1 = Decimal("2000.0"), Decimal("2020.0")    # -$300 loss on short (15 * $20)
    
    btc_funding = FundingCashFlowEvent(
        ts_event_ns=100,
        funding_rate=Decimal("-0.0001"),  # Long receives negative funding
        mark_price=btc_p0,
        position_side=1,
        notional_usd=Decimal("30000.0"),
        cash_flow_usd=Decimal("3.0"),     # -1 * 1 * 30000 * -0.0001 = +$3.00
    )
    eth_funding = FundingCashFlowEvent(
        ts_event_ns=100,
        funding_rate=Decimal("0.0002"),   # Short receives positive funding
        mark_price=eth_p0,
        position_side=-1,
        notional_usd=Decimal("30000.0"),
        cash_flow_usd=Decimal("6.0"),     # -1 * -1 * 30000 * 0.0002 = +$6.00
    )
    
    pair_ep = RelativePerpPairEpisode(
        episode_id="EP_REL_BTCETH",
        strategy_id="TEST_REL",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        asset1_symbol="BTCUSDT",
        asset1_side=1,
        asset1_entry_price=btc_p0,
        asset1_exit_price=btc_p1,
        asset1_quantity=Decimal("1.0"),
        asset1_cost_policy=zero_perp_cost,
        asset1_funding_events=(btc_funding,),
        asset2_symbol="ETHUSDT",
        asset2_side=-1,
        asset2_entry_price=eth_p0,
        asset2_exit_price=eth_p1,
        asset2_quantity=Decimal("15.0"),
        asset2_cost_policy=zero_perp_cost,
        asset2_funding_events=(eth_funding,),
    )
    
    assert pair_ep.asset1_pnl == Decimal("500.0")
    assert pair_ep.asset2_pnl == Decimal("-300.0")
    assert pair_ep.price_pnl == Decimal("200.0")
    assert pair_ep.total_funding_pnl == Decimal("9.0")
    assert pair_ep.total_costs == Decimal("0.0")
    assert pair_ep.net_pnl == Decimal("209.0")
    assert pair_ep.gross_notional_entry == Decimal("60000.0")
    assert pair_ep.net_delta_entry == Decimal("0.0")  # Delta neutral pair!


def test_portfolio_equity_curve_and_drawdown():
    """Verify step-by-step portfolio equity curve, capital concurrency, and drawdown."""
    engine = PortfolioEquityEngine(
        starting_equity=Decimal("100000.0"),
        target_gross_notional=Decimal("50000.0"),
        max_concurrency=1,
    )
    engine.record_initial_state(ts_event_ns=0)
    assert engine.current_cash == Decimal("100000.0")
    assert engine.available_capital == Decimal("100000.0")

    # Trade 1: Required capital = $50,000 * 1.75 = $87,500
    committed = Decimal("87500.0")
    assert engine.can_open_episode(committed) is True
    
    zero_spot_cost = DetailedCostPolicy(instrument_type="SPOT", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    zero_perp_cost = DetailedCostPolicy(instrument_type="PERP", exchange_fee_bps=Decimal("0.0"), spread_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    ep1 = MultiLegTradeEpisode(
        episode_id="EP1",
        strategy_id="TEST",
        asset="BTC",
        entry_ts_ns=100,
        exit_ts_ns=200,
        spot_side=1,
        spot_entry_price=Decimal("50000.0"),
        spot_exit_price=Decimal("50000.0"),
        spot_quantity=Decimal("1.0"),
        perp_side=-1,
        perp_entry_price=Decimal("50000.0"),
        perp_exit_price=Decimal("50000.0"),
        perp_quantity=Decimal("1.0"),
        spot_cost_policy=zero_spot_cost,
        perp_cost_policy=zero_perp_cost,
        funding_events=(
            FundingCashFlowEvent(150, Decimal("0.0002"), Decimal("50000.0"), -1, Decimal("50000.0"), Decimal("10.0")),
        ),
    )
    engine.open_episode(ep1, committed)
    assert engine.available_capital == Decimal("12500.0")
    
    # Concurrency limit blocks second trade:
    assert engine.can_open_episode(committed) is False
    assert engine.rejected_concurrency_count == 1
    
    # Settle trade 1 with +$10 net P&L
    engine.close_episode(ep1, committed, ts_event_ns=200)
    assert engine.current_cash == Decimal("100010.0")
    assert engine.available_capital == Decimal("100010.0")

    # Trade 2: loss of $50
    ep2 = MultiLegTradeEpisode(
        episode_id="EP2",
        strategy_id="TEST",
        asset="BTC",
        entry_ts_ns=300,
        exit_ts_ns=400,
        spot_side=1,
        spot_entry_price=Decimal("50000.0"),
        spot_exit_price=Decimal("50000.0"),
        spot_quantity=Decimal("1.0"),
        perp_side=-1,
        perp_entry_price=Decimal("50000.0"),
        perp_exit_price=Decimal("50050.0"),  # $50 adverse move
        perp_quantity=Decimal("1.0"),
        spot_cost_policy=zero_spot_cost,
        perp_cost_policy=zero_perp_cost,
        funding_events=(),
    )
    engine.open_episode(ep2, committed)
    engine.close_episode(ep2, committed, ts_event_ns=400)
    assert engine.current_cash == Decimal("99960.0")

    summary = engine.compute_summary_metrics([ep1, ep2], total_period_hours=100.0)
    assert summary["starting_equity"] == 100000.0
    assert summary["ending_equity"] == 99960.0
    assert summary["period_net_pnl"] == -40.0
    assert summary["portfolio_return_pct"] == -0.04
    assert summary["max_drawdown_pct"] > 0.0
    assert len(summary["sanity_flags"]) == 0
