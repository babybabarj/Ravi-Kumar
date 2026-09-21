"""Research Round 3B: Capital Concurrency & Multi-Strategy Adversarial Tests.

Verifies:
1. Fixed pool of $10,000 initial capital.
2. Strategy-level capital allocation must sum <= 1.0 (or <= $10,000).
   If Strategy A requests $6,000 and Strategy B requests $6,000, rejects or scales down.
3. Concurrent Episode Tests:
   - 1 episode active -> capital used <= $10,000.
   - 2 episodes active -> combined margin + notional <= $10,000.
   - 5 episodes active -> total margin required <= available cash.
   - Total capital requested > available equity -> FAIL_CLOSED_CAPITAL_EXHAUSTION.
4. Unallocated cash earns zero return.
5. Max concurrency limits strictly enforced.
"""
from decimal import Decimal
import pytest

from btceth_os.research.cost_model import DetailedCostPolicy
from btceth_os.research.structural.multi_leg_accounting import MultiLegTradeEpisode
from btceth_os.research.structural.portfolio_equity import (
    CapitalExhaustionError,
    PortfolioEquityEngine,
    allocate_multi_strategy_capital,
)


def _make_dummy_episode(ep_id: str, notional: Decimal = Decimal("2000.0")) -> MultiLegTradeEpisode:
    cost = DetailedCostPolicy(
        instrument_type="SPOT",
        exchange_fee_bps=Decimal("0.0"),
        spread_bps=Decimal("0.0"),
        slippage_bps=Decimal("0.0"),
    )
    perp_cost = DetailedCostPolicy(
        instrument_type="PERP",
        exchange_fee_bps=Decimal("0.0"),
        spread_bps=Decimal("0.0"),
        slippage_bps=Decimal("0.0"),
    )
    # qty = 1, price = notional / 2 for spot and perp
    half = notional / Decimal("2.0")
    return MultiLegTradeEpisode(
        episode_id=ep_id,
        strategy_id="TEST_CONCURRENCY",
        asset="BTC",
        entry_ts_ns=1_000_000_000,
        exit_ts_ns=2_000_000_000,
        spot_side=1,
        spot_entry_price=half,
        spot_exit_price=half,
        spot_quantity=Decimal("1.0"),
        perp_side=-1,
        perp_entry_price=half,
        perp_exit_price=half,
        perp_quantity=Decimal("1.0"),
        spot_cost_policy=cost,
        perp_cost_policy=perp_cost,
    )


def test_strategy_level_capital_allocation_exhaustion():
    """Verify that concurrent strategy requests exceeding $10,000 fail closed or scale down."""
    total_capital = Decimal("10000.0")
    # Strategy A requests $6,000, Strategy B requests $6,000 (total $12,000 > $10,000)
    allocations = {
        "STRATEGY_A": Decimal("6000.0"),
        "STRATEGY_B": Decimal("6000.0"),
    }

    # REJECT policy must raise CapitalExhaustionError
    with pytest.raises(CapitalExhaustionError, match="FAIL_CLOSED_CAPITAL_EXHAUSTION"):
        allocate_multi_strategy_capital(allocations, total_capital=total_capital, policy="REJECT")

    # SCALE_DOWN policy scales proportionally to fit exactly $10,000
    scaled = allocate_multi_strategy_capital(allocations, total_capital=total_capital, policy="SCALE_DOWN")
    assert sum(scaled.values()) == total_capital
    assert scaled["STRATEGY_A"] == Decimal("5000.0")
    assert scaled["STRATEGY_B"] == Decimal("5000.0")


def test_single_episode_capital_bound():
    """1 episode active -> capital used <= $10,000."""
    engine = PortfolioEquityEngine(
        starting_equity=Decimal("10000.0"),
        max_concurrency=1,
    )
    engine.record_initial_state(ts_event_ns=0)
    assert engine.available_capital == Decimal("10000.0")

    ep = _make_dummy_episode("EP1", Decimal("8000.0"))
    committed = Decimal("8000.0")
    assert engine.can_open_episode(committed) is True
    engine.allocate_episode(ep, committed)

    assert engine.current_committed_capital == Decimal("8000.0")
    assert engine.available_capital == Decimal("2000.0")
    assert engine.current_committed_capital <= Decimal("10000.0")


def test_two_concurrent_episodes_capital_bound():
    """2 episodes active -> combined margin + notional <= $10,000."""
    engine = PortfolioEquityEngine(
        starting_equity=Decimal("10000.0"),
        max_concurrency=2,
    )
    engine.record_initial_state(ts_event_ns=0)

    ep1 = _make_dummy_episode("EP1", Decimal("4500.0"))
    ep2 = _make_dummy_episode("EP2", Decimal("4500.0"))
    ep3_excess = _make_dummy_episode("EP3", Decimal("4500.0"))

    # Allocate EP1: committed $4,500
    engine.allocate_episode(ep1, Decimal("4500.0"))
    assert engine.available_capital == Decimal("5500.0")

    # Allocate EP2: committed $4,500 (total $9,000 <= $10,000)
    engine.allocate_episode(ep2, Decimal("4500.0"))
    assert engine.current_committed_capital == Decimal("9000.0")
    assert engine.available_capital == Decimal("1000.0")

    # Attempt EP3: requires $4,500 > available $1,000 -> must fail closed
    assert engine.can_open_episode(Decimal("4500.0")) is False
    with pytest.raises(CapitalExhaustionError, match="FAIL_CLOSED_CAPITAL_EXHAUSTION"):
        engine.allocate_episode(ep3_excess, Decimal("4500.0"))


def test_five_concurrent_episodes_exhaustion_boundary():
    """5 episodes active -> total margin required <= available cash, 6th rejected."""
    engine = PortfolioEquityEngine(
        starting_equity=Decimal("10000.0"),
        max_concurrency=5,
    )
    engine.record_initial_state(ts_event_ns=0)

    # 5 episodes of $2,000 each = $10,000 total
    episodes = [_make_dummy_episode(f"EP_{i}", Decimal("2000.0")) for i in range(5)]
    for i, ep in enumerate(episodes):
        assert engine.can_open_episode(Decimal("2000.0")) is True
        engine.allocate_episode(ep, Decimal("2000.0"))
        assert engine.current_committed_capital == Decimal(f"{(i + 1) * 2000}.0")

    assert engine.current_committed_capital == Decimal("10000.0")
    assert engine.available_capital == Decimal("0.0")

    # 6th episode must fail closed due to both capital and max_concurrency exhaustion
    ep_extra = _make_dummy_episode("EP_EXTRA", Decimal("100.0"))
    assert engine.can_open_episode(Decimal("100.0")) is False
    with pytest.raises(CapitalExhaustionError, match="FAIL_CLOSED_CAPITAL_EXHAUSTION"):
        engine.allocate_episode(ep_extra, Decimal("100.0"))


def test_unallocated_cash_earns_zero():
    """Verify unallocated cash in pool earns exactly zero return."""
    engine = PortfolioEquityEngine(
        starting_equity=Decimal("10000.0"),
        max_concurrency=2,
    )
    engine.record_initial_state(ts_event_ns=0)

    # Allocate $3,000 for an episode, leaving $7,000 unallocated
    ep = _make_dummy_episode("EP_FLAT", Decimal("3000.0"))
    engine.allocate_episode(ep, Decimal("3000.0"))
    
    # Close episode with zero PnL
    engine.close_episode(ep, Decimal("3000.0"), ts_event_ns=3_600_000_000_000)

    metrics = engine.compute_summary_metrics([ep], total_period_hours=1.0)
    assert engine.current_cash == Decimal("10000.0")
    assert metrics["period_net_pnl"] == 0.0
    assert metrics["portfolio_return_pct"] == 0.0
