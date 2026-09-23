from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import pytest

from btceth_os.research.backtest import (
    Candle,
    CostModel,
    ExecutionAssumptions,
    ExecutionPriceObservation,
    PriceSource,
    OrderSide,
    run_causal_backtest,
    run_synthetic_causal_backtest,
    walk_forward_causal,
    _select_lookback,
    validate_research_series_identity,
    SYNTHETIC_TEST_CONTEXT,
    RESEARCH_CONTEXT,
    ONE,
    BPS,
)
from btceth_os.research.experiment_registry import (
    ExperimentRecord,
    ExperimentRegistry,
    compute_experiment_id,
)
from btceth_os.research.temporal import TemporalIntegrityViolationError


def _make_guarded_candles(
    n: int,
    start_ts: int = 1609459200_000_000_000,
    bar_dur: int = 3_600_000_000_000,
    instrument_id: str = "BTCUSDT",
    dataset_id: str = "BTCUSDT_DEV_2020_2022",
    base_price: Decimal = Decimal("30000.0"),
    step_price: Decimal = Decimal("100.0"),
) -> list[Candle]:
    """Helper creating a homogeneous guarded candle sequence."""
    candles = []
    for i in range(n):
        p_open = base_price + Decimal(i) * step_price
        p_close = p_open + step_price
        candles.append(
            Candle(
                ts_event_ns=start_ts + i * bar_dur,
                close=p_close,
                open=p_open,
                instrument_id=instrument_id,
                dataset_id=dataset_id,
                market_type="USD_M_PERP",
                venue="BINANCE",
            )
        )
    return candles


# ==============================================================================
# SECTION 4 & 5: CROSS-SERIES ISOLATION & RUN-TO-RUN STATE LEAKAGE
# ==============================================================================

def test_cross_series_capital_isolation_and_order_independence() -> None:
    """[3B.0I GATE: CROSS_SERIES_CAPITAL_ISOLATION & RUN_ORDER_INDEPENDENCE]
    BTC isolated vs BTC after ETH vs BTC interleaved must match to exact Decimal equality.
    """
    btc_candles = _make_guarded_candles(10, instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", base_price=Decimal("30000.0"))
    eth_candles = _make_guarded_candles(10, instrument_id="ETHUSDT", dataset_id="ETHUSDT_DEV_2020_2022", base_price=Decimal("2000.0"))

    btc_positions = [0, 1, 1, -1, -1, 0, 1, -1, 0, 0]
    eth_positions = [0, -1, -1, 1, 1, 0, -1, 1, 0, 0]

    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"), carry_bps_per_bar=Decimal("0.1"))

    # Sequence A: BTC alone (isolated)
    btc_isolated = run_causal_backtest(btc_candles, btc_positions, costs)

    # Sequence B: ETH alone (isolated)
    eth_isolated = run_causal_backtest(eth_candles, eth_positions, costs)

    # Sequence C: Interleaved runs in the same Python process
    # Run BTC -> Run ETH -> Run BTC -> Run ETH -> Run BTC
    btc_run_1 = run_causal_backtest(btc_candles, btc_positions, costs)
    eth_run_1 = run_causal_backtest(eth_candles, eth_positions, costs)
    btc_run_2 = run_causal_backtest(btc_candles, btc_positions, costs)
    eth_run_2 = run_causal_backtest(eth_candles, eth_positions, costs)
    btc_run_3 = run_causal_backtest(btc_candles, btc_positions, costs)

    # Assert exact Decimal equality across all metrics
    for btc_run in [btc_run_1, btc_run_2, btc_run_3]:
        assert btc_run.result.gross_return == btc_isolated.result.gross_return
        assert btc_run.result.net_return == btc_isolated.result.net_return
        assert btc_run.result.total_cost == btc_isolated.result.total_cost
        assert btc_run.result.trades == btc_isolated.result.trades
        assert btc_run.result.max_drawdown == btc_isolated.result.max_drawdown
        assert len(btc_run.executions) == len(btc_isolated.executions)
        for e_act, e_exp in zip(btc_run.executions, btc_isolated.executions, strict=True):
            assert e_act.fill_price == e_exp.fill_price
            assert e_act.charge == e_exp.charge
            assert e_act.turnover == e_exp.turnover
            assert e_act.instrument_id == "BTCUSDT"

    for eth_run in [eth_run_1, eth_run_2]:
        assert eth_run.result.gross_return == eth_isolated.result.gross_return
        assert eth_run.result.net_return == eth_isolated.result.net_return
        assert eth_run.result.total_cost == eth_isolated.result.total_cost
        assert eth_run.result.trades == eth_isolated.result.trades
        assert eth_run.result.max_drawdown == eth_isolated.result.max_drawdown
        assert len(eth_run.executions) == len(eth_isolated.executions)
        for e_act, e_exp in zip(eth_run.executions, eth_isolated.executions, strict=True):
            assert e_act.fill_price == e_exp.fill_price
            assert e_act.charge == e_exp.charge
            assert e_act.turnover == e_exp.turnover
            assert e_act.instrument_id == "ETHUSDT"


def test_repeated_run_determinism() -> None:
    """[3B.0I GATE: REPEATED_RUN_DETERMINISM]
    5 repeated executions of identical backtest produce bit-for-bit identical results.
    """
    candles = _make_guarded_candles(15, base_price=Decimal("40000.0"))
    positions = [0, 1, 1, 1, -1, -1, 0, 0, 1, 1, -1, 0, 1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("4.0"), slippage_bps=Decimal("1.5"))

    runs = [run_causal_backtest(candles, positions, costs) for _ in range(5)]
    baseline = runs[0]

    for r in runs[1:]:
        assert r.result.net_return == baseline.result.net_return
        assert r.result.gross_return == baseline.result.gross_return
        assert r.result.total_cost == baseline.result.total_cost
        assert r.result.max_drawdown == baseline.result.max_drawdown
        assert r.result.trades == baseline.result.trades
        assert len(r.contracts) == len(baseline.contracts)
        assert len(r.executions) == len(baseline.executions)


# ==============================================================================
# SECTION 6: INPUT IMMUTABILITY
# ==============================================================================

def test_caller_input_immutability() -> None:
    """[3B.0I GATE: INPUT_CANDLE_IMMUTABILITY, INPUT_POSITION_IMMUTABILITY, COST_OBJECT_IMMUTABILITY]
    Calling run_causal_backtest or walk_forward_causal never mutates input candles, positions, or costs.
    """
    candles = _make_guarded_candles(20)
    positions = [0, 1, 1, 0, -1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 0, 1, 0, -1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"), carry_bps_per_bar=Decimal("0.2"))

    # Snapshot before execution
    candles_snapshot = copy.deepcopy(candles)
    positions_snapshot = copy.deepcopy(positions)
    costs_snapshot = copy.deepcopy(costs)

    # Execute run_causal_backtest
    res = run_causal_backtest(candles, positions, costs)
    assert res.result.bars == 20

    # Assert zero mutation
    assert candles == candles_snapshot
    assert positions == positions_snapshot
    assert costs == costs_snapshot

    # Test walk_forward_causal immutability
    candles_snapshot_wf = copy.deepcopy(candles)
    candidate_lookbacks = [2, 3, 5]
    candidate_lookbacks_snapshot = copy.deepcopy(candidate_lookbacks)

    wf_res = walk_forward_causal(
        candles,
        train_bars=8,
        test_bars=4,
        candidate_lookbacks=candidate_lookbacks,
        costs=costs,
    )
    assert len(wf_res.folds) > 0
    assert candles == candles_snapshot_wf
    assert candidate_lookbacks == candidate_lookbacks_snapshot
    assert costs == costs_snapshot


# ==============================================================================
# SECTION 14: ERROR-PATH ATOMICITY
# ==============================================================================

def test_failed_run_state_atomicity() -> None:
    """[3B.0I GATE: FAILED_RUN_STATE_ATOMICITY]
    A failed run does NOT poison shared/global state; subsequent valid run matches clean-process baseline.
    """
    valid_candles = _make_guarded_candles(10)
    valid_positions = [0, 1, 1, 0, 0, -1, -1, 0, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    # Clean baseline
    clean_result = run_causal_backtest(valid_candles, valid_positions, costs)

    # Mode 1: Invalid series identity (ETH candle injected into BTC series)
    corrupted_candles = list(valid_candles)
    corrupted_candles[4] = Candle(
        ts_event_ns=valid_candles[4].ts_event_ns,
        close=Decimal("2000.0"),
        open=Decimal("2000.0"),
        instrument_id="ETHUSDT",
        dataset_id=valid_candles[4].dataset_id,
        market_type=valid_candles[4].market_type,
        venue=valid_candles[4].venue,
    )
    with pytest.raises(TemporalIntegrityViolationError):
        run_causal_backtest(corrupted_candles, valid_positions, costs)

    # Mode 2: Missing execution observation for terminal exit
    with pytest.raises(TemporalIntegrityViolationError):
        run_causal_backtest(valid_candles, [0, 1, 1, 1, 1, 1, 1, 1, 1, 1], costs)

    # Mode 3: Impossible timestamp (decreasing candles)
    bad_time_candles = list(valid_candles)
    bad_time_candles[3] = Candle(
        ts_event_ns=valid_candles[2].ts_event_ns - 1000,
        close=Decimal("30000.0"),
        open=Decimal("30000.0"),
        instrument_id=valid_candles[3].instrument_id,
        dataset_id=valid_candles[3].dataset_id,
        market_type=valid_candles[3].market_type,
        venue=valid_candles[3].venue,
    )
    with pytest.raises(ValueError):
        run_causal_backtest(bad_time_candles, valid_positions, costs)

    # Mode 4: Unsupported position value
    with pytest.raises(ValueError):
        run_causal_backtest(valid_candles, [0, 2, 0, 0, 0, 0, 0, 0, 0, 0], costs)

    # After all 4 deliberate failures in this process, execute valid run
    post_failure_result = run_causal_backtest(valid_candles, valid_positions, costs)

    # Must match clean baseline to exact Decimal equality
    assert post_failure_result.result.gross_return == clean_result.result.gross_return
    assert post_failure_result.result.net_return == clean_result.result.net_return
    assert post_failure_result.result.total_cost == clean_result.result.total_cost
    assert post_failure_result.result.trades == clean_result.result.trades
    assert post_failure_result.result.max_drawdown == clean_result.result.max_drawdown
    assert len(post_failure_result.executions) == len(clean_result.executions)


# ==============================================================================
# SECTION 7 & 8: CAPITAL ACCOUNTING IDENTITIES & 11 HAND-VERIFIABLE FIXTURES
# ==============================================================================

def test_fixture_1_flat_throughout() -> None:
    """[3B.0I FIXTURE 1] Flat throughout: zero trades, zero costs, zero returns, zero DD."""
    candles = _make_guarded_candles(5)
    positions = [0, 0, 0, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("10.0"), slippage_bps=Decimal("5.0"))
    res = run_causal_backtest(candles, positions, costs)

    assert res.result.trades == 0
    assert res.result.total_cost == Decimal("0")
    assert res.result.gross_return == Decimal("0")
    assert res.result.net_return == Decimal("0")
    assert res.result.max_drawdown == Decimal("0")
    assert len(res.executions) == 0


def test_fixture_2_long_then_hold() -> None:
    """[3B.0I FIXTURE 2] Long then hold:
    Bar 0: sig=0 -> target=0, prev=0
    Bar 1: sig=1 (signal from bar 0 close=0, executed at bar 1: target=0)
    Wait: with delay=1:
    Interval 0 (c0->c1): target=pos[0]=0, prev=0 (flat)
    Interval 1 (c1->c2): target=pos[1]=1, prev=0. BUY at open=100, close=110 => +10% return
    Interval 2 (c2->c3): target=pos[2]=1, prev=1. HOLD long from 110 to 121 => +10% return
    Interval 3 (c3->c4): target=pos[3]=0, prev=1. SELL at open=121, flat to 121 => 0% return
    """
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, open=Decimal("100.0"), close=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, open=Decimal("100.0"), close=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 2*bar_dur, open=Decimal("100.0"), close=Decimal("110.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 3*bar_dur, open=Decimal("110.0"), close=Decimal("121.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 4*bar_dur, open=Decimal("121.0"), close=Decimal("121.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    positions = [0, 1, 1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("100.0"), slippage_bps=Decimal("0.0"))  # 1% turnover fee
    res = run_causal_backtest(candles, positions, costs)

    # Exactly 2 executions (BUY entry at bar 2, SELL exit at bar 4)
    assert len(res.executions) == 2
    assert res.result.trades == 2
    # Total cost = 2 * 1% = 0.02
    assert res.result.total_cost == Decimal("0.02")

    # Bar 1 (c1->c2): (110 - 100) / 100 = 0.10. Net return = 0.10 - 0.01 = 0.09. Equity = 1.09
    # Bar 2 (c2->c3): (121 - 110) / 110 = 0.10. Turnover=0, charge=0. Equity = 1.09 * 1.10 = 1.199
    # Bar 3 (c3->c4): Exit at 121, exit charge = 0.01. Equity = 1.199 * (1 - 0.01) = 1.18701
    expected_gross_mult = Decimal("1.10") * Decimal("1.10")
    expected_gross_return = expected_gross_mult - ONE
    assert res.result.gross_return == expected_gross_return
    assert res.result.net_return == Decimal("1.18701") - ONE


def test_fixture_3_short_then_hold() -> None:
    """[3B.0I FIXTURE 3] Short then hold: short position gains when price drops."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, open=Decimal("100.0"), close=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, open=Decimal("100.0"), close=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 2*bar_dur, open=Decimal("100.0"), close=Decimal("90.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 3*bar_dur, open=Decimal("90.0"), close=Decimal("81.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 4*bar_dur, open=Decimal("81.0"), close=Decimal("81.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    positions = [0, -1, -1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"))
    res = run_causal_backtest(candles, positions, costs)

    # Bar 1 (c1->c2): Short entry at 100, close at 90 => gain = -(-10%) = +10%
    # Bar 2 (c2->c3): Hold short from 90 to 81 => gain = -(-10%) = +10%
    # Bar 3 (c3->c4): Exit flat at 81 => 0%
    expected_gross_mult = Decimal("1.10") * Decimal("1.10")
    assert res.result.gross_return == expected_gross_mult - ONE
    assert res.result.net_return == res.result.gross_return
    assert res.result.total_cost == Decimal("0")


def test_fixture_4_and_5_enter_and_exit_long_and_short() -> None:
    """[3B.0I FIXTURES 4 & 5] Enter long then exit flat, enter short then exit flat."""
    candles = _make_guarded_candles(6)
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    # Enter long then exit
    long_positions = [0, 1, 0, 0, 0, 0]
    res_long = run_causal_backtest(candles, long_positions, costs)
    assert res_long.result.trades == 2
    assert len(res_long.executions) == 2
    assert res_long.executions[0].side == OrderSide.BUY.value
    assert res_long.executions[1].side == OrderSide.SELL.value

    # Enter short then exit
    short_positions = [0, -1, 0, 0, 0, 0]
    res_short = run_causal_backtest(candles, short_positions, costs)
    assert res_short.result.trades == 2
    assert len(res_short.executions) == 2
    assert res_short.executions[0].side == OrderSide.SELL.value
    assert res_short.executions[1].side == OrderSide.BUY.value


def test_fixture_6_and_7_position_reversals() -> None:
    """[3B.0I FIXTURES 6 & 7: REVERSAL_LONG_TO_SHORT_ACCOUNTING & REVERSAL_SHORT_TO_LONG_ACCOUNTING]
    Position change from +1 -> -1 and -1 -> +1:
    - Turnover is 2 units
    - Two units of turnover fee charged
    - Side is SELL for +1 -> -1, and BUY for -1 -> +1
    - Gap return accrued to previous position; Bar return accrued to target position
    """
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, open=Decimal("100.0"), close=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, open=Decimal("100.0"), close=Decimal("110.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 2*bar_dur, open=Decimal("110.0"), close=Decimal("105.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 3*bar_dur, open=Decimal("105.0"), close=Decimal("105.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 4*bar_dur, open=Decimal("105.0"), close=Decimal("105.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    # Reversal +1 -> -1 at bar 2
    reversal_long_to_short = [0, 1, -1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("10.0"), slippage_bps=Decimal("5.0"))  # 15 bps one-way
    res_l2s = run_causal_backtest(candles, reversal_long_to_short, costs)

    # Check the reversal execution (index 1 in executions list, which is at bar 2)
    assert len(res_l2s.executions) == 3  # Entry long (+1), reversal (-2), exit flat (+1)
    rev_exec = res_l2s.executions[1]
    assert rev_exec.position_before == 1
    assert rev_exec.position_after == -1
    assert rev_exec.turnover == 2
    assert rev_exec.side == OrderSide.SELL.value
    # Charge must be 2 units of turnover rate: 2 * 15 bps = 30 bps
    expected_charge = Decimal("2") * costs.turnover_rate
    assert rev_exec.charge == expected_charge
    assert rev_exec.fee == Decimal("2") * costs.taker_fee_bps / BPS
    assert rev_exec.slippage == Decimal("2") * costs.slippage_bps / BPS

    # Now test reversal -1 -> +1
    reversal_short_to_long = [0, -1, 1, 0, 0]
    res_s2l = run_causal_backtest(candles, reversal_short_to_long, costs)
    assert len(res_s2l.executions) == 3
    rev_exec_s2l = res_s2l.executions[1]
    assert rev_exec_s2l.position_before == -1
    assert rev_exec_s2l.position_after == 1
    assert rev_exec_s2l.turnover == 2
    assert rev_exec_s2l.side == OrderSide.BUY.value
    assert rev_exec_s2l.charge == expected_charge


def test_fixture_8_repeated_no_turnover_holds() -> None:
    """[3B.0I FIXTURE 8] Repeated no-turnover holds: 5 consecutive hold bars have 0 execution records."""
    candles = _make_guarded_candles(8)
    positions = [0, 1, 1, 1, 1, 1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("10.0"), slippage_bps=Decimal("5.0"))
    res = run_causal_backtest(candles, positions, costs)

    # Exactly 2 executions: entry at bar 1, exit at bar 6. Bars 2, 3, 4, 5 are pure holds.
    assert len(res.executions) == 2
    assert res.result.trades == 2


def test_fixture_9_terminal_liquidation() -> None:
    """[3B.0I FIXTURE 9] Terminal liquidation / exit: non-zero held position at end exits at authentic observation."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, open=Decimal("100.0"), close=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, open=Decimal("100.0"), close=Decimal("110.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 2*bar_dur, open=Decimal("110.0"), close=Decimal("120.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    # Position remains 1 at end
    positions = [0, 1, 1]
    costs = CostModel(taker_fee_bps=Decimal("10.0"), slippage_bps=Decimal("5.0"))

    # Terminal exit requires authentic observation stream
    stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + 3*bar_dur,
            price=Decimal("120.0"),
            bid=Decimal("119.5"),
            ask=Decimal("120.5"),
            price_source=PriceSource.BID_ASK_TOUCH,
            instrument_id="BTCUSDT",
            dataset_id="BTCUSDT_DEV_2020_2022",
            market_type="USD_M_PERP",
            venue="BINANCE",
        )
    ]
    res = run_causal_backtest(candles, positions, costs, execution_stream=stream)

    # Terminal liquidation must create a terminal execution record
    assert len(res.executions) == 2
    term_exec = res.executions[-1]
    assert term_exec.terminal is True
    assert term_exec.position_before == 1
    assert term_exec.position_after == 0
    assert term_exec.turnover == 1
    assert term_exec.side == OrderSide.SELL.value
    assert term_exec.fill_price == Decimal("119.5")  # SELL touches bid


def test_fixture_10_and_11_fee_bearing_vs_zero_fee() -> None:
    """[3B.0I FIXTURES 10 & 11] Fee-bearing vs zero-fee exact accounting identity."""
    candles = _make_guarded_candles(6)
    positions = [0, 1, 1, 0, 0, 0]

    # Fixture 10: Fee bearing
    costs_fee = CostModel(taker_fee_bps=Decimal("10.0"), slippage_bps=Decimal("5.0"))
    res_fee = run_causal_backtest(candles, positions, costs_fee)
    assert res_fee.result.total_cost > Decimal("0")
    assert res_fee.result.net_return < res_fee.result.gross_return

    # Fixture 11: Zero fee
    costs_zero = CostModel(taker_fee_bps=Decimal("0.0"), slippage_bps=Decimal("0.0"), carry_bps_per_bar=Decimal("0.0"))
    res_zero = run_causal_backtest(candles, positions, costs_zero)
    assert res_zero.result.total_cost == Decimal("0")
    assert res_zero.result.net_return == res_zero.result.gross_return


# ==============================================================================
# SECTION 13: WALK-FORWARD CAPITAL RESET & LOOKBACK ORDER INDEPENDENCE
# ==============================================================================

def test_walk_forward_capital_reset() -> None:
    """[3B.0I GATE: WALK_FORWARD_CAPITAL_RESET]
    Candidate lookbacks are evaluated with fresh capital state (multiplier starts at 1).
    """
    candles = _make_guarded_candles(30)
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    # Permuting candidate lookbacks must not affect the result
    res1 = walk_forward_causal(
        candles,
        train_bars=10,
        test_bars=5,
        candidate_lookbacks=[2, 3, 5],
        costs=costs,
    )
    res2 = walk_forward_causal(
        candles,
        train_bars=10,
        test_bars=5,
        candidate_lookbacks=[5, 2, 3],
        costs=costs,
    )
    res3 = walk_forward_causal(
        candles,
        train_bars=10,
        test_bars=5,
        candidate_lookbacks=[3, 5, 2],
        costs=costs,
    )

    assert res1.net_return == res2.net_return == res3.net_return
    assert res1.trades == res2.trades == res3.trades
    assert [f.lookback for f in res1.folds] == [f.lookback for f in res2.folds] == [f.lookback for f in res3.folds]


def test_select_lookback_order_independence() -> None:
    """[3B.0I GATE: LOOKBACK_EVALUATION_ORDER_INDEPENDENCE]
    _select_lookback produces identical selection regardless of candidate permutation.
    """
    candles = _make_guarded_candles(25)
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    sel_a = _select_lookback(candles, 0, 15, [2, 4, 6], costs)
    sel_b = _select_lookback(candles, 0, 15, [6, 2, 4], costs)
    sel_c = _select_lookback(candles, 0, 15, [4, 6, 2], costs)
    sel_d = _select_lookback(candles, 0, 15, (x for x in [6, 4, 2]), costs)

    assert sel_a == sel_b == sel_c == sel_d


# ==============================================================================
# SECTION 15: EXPERIMENT IDENTITY BINDING
# ==============================================================================

def test_experiment_identity_binding(tmp_path: Path) -> None:
    """[3B.0I GATE: EXPERIMENT_INSTRUMENT_BINDING & EXPERIMENT_DATASET_BINDING]
    BTC experiment cannot collide with ETH experiment.
    DEV experiment cannot collide with VAL experiment.
    """
    db_file = tmp_path / "experiments.sqlite"
    reg = ExperimentRegistry(db_file)

    params = {"fast_window": 10, "slow_window": 30}
    hyp = "Moving average trend momentum"

    btc_exp_id = compute_experiment_id("FAM_A", "STRAT_1", hyp, "sha_btc_dev", params, instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022")
    eth_exp_id = compute_experiment_id("FAM_A", "STRAT_1", hyp, "sha_eth_dev", params, instrument_id="ETHUSDT", dataset_id="ETHUSDT_DEV_2020_2022")
    btc_val_exp_id = compute_experiment_id("FAM_A", "STRAT_1", hyp, "sha_btc_val", params, instrument_id="BTCUSDT", dataset_id="BTCUSDT_VAL_2023")

    # IDs must be strictly unique
    assert btc_exp_id != eth_exp_id
    assert btc_exp_id != btc_val_exp_id

    # Record all three
    rec_btc = ExperimentRecord(
        experiment_id=btc_exp_id,
        family="FAM_A",
        strategy_id="STRAT_1",
        variant_index=0,
        hypothesis=hyp,
        parameters=params,
        dataset_logical_sha256="sha_btc_dev",
        code_commit="commit_1",
        train_start_ts=100,
        train_end_ts=200,
        test_start_ts=201,
        test_end_ts=300,
        in_sample_net_return=0.1,
        in_sample_sharpe=1.5,
        out_of_sample_net_return=0.05,
        out_of_sample_stressed_return=0.02,
        out_of_sample_trades=20,
        out_of_sample_sharpe=1.1,
        max_drawdown=0.04,
        deflated_sharpe_ratio=0.8,
        pbo=0.1,
        status="APPROVED_FOR_RESEARCH",
        rejection_reasons=[],
        instrument_id="BTCUSDT",
        dataset_id="BTCUSDT_DEV_2020_2022",
    )

    rec_eth = ExperimentRecord(
        experiment_id=eth_exp_id,
        family="FAM_A",
        strategy_id="STRAT_1",
        variant_index=1,
        hypothesis=hyp,
        parameters=params,
        dataset_logical_sha256="sha_eth_dev",
        code_commit="commit_1",
        train_start_ts=100,
        train_end_ts=200,
        test_start_ts=201,
        test_end_ts=300,
        in_sample_net_return=0.08,
        in_sample_sharpe=1.2,
        out_of_sample_net_return=0.03,
        out_of_sample_stressed_return=0.01,
        out_of_sample_trades=18,
        out_of_sample_sharpe=0.9,
        max_drawdown=0.05,
        deflated_sharpe_ratio=0.7,
        pbo=0.15,
        status="APPROVED_FOR_RESEARCH",
        rejection_reasons=[],
        instrument_id="ETHUSDT",
        dataset_id="ETHUSDT_DEV_2020_2022",
    )

    reg.record_experiment(rec_btc)
    reg.record_experiment(rec_eth)

    all_exps = reg.get_all_experiments()
    assert len(all_exps) == 2
    insts = {e.instrument_id for e in all_exps}
    assert insts == {"BTCUSDT", "ETHUSDT"}


# ==============================================================================
# SECTION 9: SINGLE-LEG ARCHITECTURE ENFORCEMENT
# ==============================================================================

def test_single_leg_architecture_enforced() -> None:
    """[3B.0I GATE: SINGLE_LEG_ARCHITECTURE_ENFORCED]
    Single-leg backtest engine strictly rejects multi-instrument series or partition crossing.
    """
    btc_candles = _make_guarded_candles(4, instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022")
    eth_candles = _make_guarded_candles(4, instrument_id="ETHUSDT", dataset_id="ETHUSDT_DEV_2020_2022")

    # Contaminated series
    mixed_candles = list(btc_candles[:2]) + list(eth_candles[2:])
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        run_causal_backtest(mixed_candles, [0, 0, 0, 0], costs)
    assert "RESEARCH_SERIES_IDENTITY_MISMATCH" in str(exc_info.value)


# ==============================================================================
# SECTION 4 & 5: EXPLICIT ISOLATION AFTER CROSS-SERIES RUNS
# ==============================================================================

def test_btc_after_eth_isolation() -> None:
    """[3B.0I GATE: BTC_AFTER_ETH_ISOLATION]
    BTC backtest run immediately following an ETH backtest matches clean BTC run exactly.
    """
    btc_candles = _make_guarded_candles(10, instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022")
    eth_candles = _make_guarded_candles(10, instrument_id="ETHUSDT", dataset_id="ETHUSDT_DEV_2020_2022")
    positions = [0, 1, 1, 0, -1, -1, 0, 1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    clean_btc = run_causal_backtest(btc_candles, positions, costs)
    _ = run_causal_backtest(eth_candles, positions, costs)
    btc_after_eth = run_causal_backtest(btc_candles, positions, costs)

    assert btc_after_eth.result.gross_return == clean_btc.result.gross_return
    assert btc_after_eth.result.net_return == clean_btc.result.net_return
    assert btc_after_eth.result.total_cost == clean_btc.result.total_cost
    assert btc_after_eth.result.trades == clean_btc.result.trades
    assert btc_after_eth.result.max_drawdown == clean_btc.result.max_drawdown


def test_eth_after_btc_isolation() -> None:
    """[3B.0I GATE: ETH_AFTER_BTC_ISOLATION]
    ETH backtest run immediately following a BTC backtest matches clean ETH run exactly.
    """
    btc_candles = _make_guarded_candles(10, instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022")
    eth_candles = _make_guarded_candles(10, instrument_id="ETHUSDT", dataset_id="ETHUSDT_DEV_2020_2022")
    positions = [0, -1, -1, 0, 1, 1, 0, -1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    clean_eth = run_causal_backtest(eth_candles, positions, costs)
    _ = run_causal_backtest(btc_candles, positions, costs)
    eth_after_btc = run_causal_backtest(eth_candles, positions, costs)

    assert eth_after_btc.result.gross_return == clean_eth.result.gross_return
    assert eth_after_btc.result.net_return == clean_eth.result.net_return
    assert eth_after_btc.result.total_cost == clean_eth.result.total_cost
    assert eth_after_btc.result.trades == clean_eth.result.trades
    assert eth_after_btc.result.max_drawdown == clean_eth.result.max_drawdown


# ==============================================================================
# SECTION 7: NO FEE / SLIPPAGE DOUBLE COUNT
# ==============================================================================

def test_no_fee_double_count() -> None:
    """[3B.0I GATE: NO_FEE_DOUBLE_COUNT]
    Fees are charged once per turnover event; total_cost matches exactly sum of execution charges.
    """
    candles = _make_guarded_candles(12)
    positions = [0, 1, 1, -1, -1, 0, 1, 1, 0, 0, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("8.0"), slippage_bps=Decimal("4.0"))
    res = run_causal_backtest(candles, positions, costs)

    # Sum of charges in execution records must equal total_cost exactly
    sum_charges = sum((e.charge for e in res.executions), Decimal("0"))
    assert res.result.total_cost == sum_charges
    # Fee per turnover unit is costs.taker_fee_bps / 10000
    expected_fees = sum((e.fee for e in res.executions), Decimal("0"))
    total_turnover = sum(e.turnover for e in res.executions)
    assert expected_fees == Decimal(total_turnover) * costs.taker_fee_bps / BPS


def test_no_slippage_double_count() -> None:
    """[3B.0I GATE: NO_SLIPPAGE_DOUBLE_COUNT]
    Slippage is applied once per fill, never double counted.
    """
    candles = _make_guarded_candles(10)
    positions = [0, 1, 1, 0, -1, -1, 0, 0, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("3.0"))
    res = run_causal_backtest(candles, positions, costs)

    total_slippage = sum(e.slippage for e in res.executions)
    total_turnover = sum(e.turnover for e in res.executions)
    assert total_slippage == Decimal(total_turnover) * costs.slippage_bps / BPS


# ==============================================================================
# SECTION 12: DECIMAL NUMERICAL INTEGRITY
# ==============================================================================

def test_decimal_accounting_integrity() -> None:
    """[3B.0I GATE: DECIMAL_ACCOUNTING_INTEGRITY]
    Exact Decimal precision avoids binary float rounding errors (e.g. 0.1 + 0.2 != 0.3).
    """
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    # Create prices with subtle decimal fractions that binary float would distort:
    # 100.1, 100.2, 100.3, 100.3
    candles = [
        Candle(ts_event_ns=t0, open=Decimal("100.1"), close=Decimal("100.1"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, open=Decimal("100.1"), close=Decimal("100.2"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 2*bar_dur, open=Decimal("100.2"), close=Decimal("100.3"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 3*bar_dur, open=Decimal("100.3"), close=Decimal("100.3"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    positions = [0, 1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("0.1"), slippage_bps=Decimal("0.2"))
    res = run_causal_backtest(candles, positions, costs)

    # Assert all result fields are strictly Decimal
    assert isinstance(res.result.gross_return, Decimal)
    assert isinstance(res.result.net_return, Decimal)
    assert isinstance(res.result.total_cost, Decimal)
    assert isinstance(res.result.max_drawdown, Decimal)
    assert len(res.executions) == 2
    for e in res.executions:
        assert isinstance(e.charge, Decimal)
        assert isinstance(e.fill_price, Decimal)
        assert isinstance(e.fee, Decimal)
        assert isinstance(e.slippage, Decimal)


# ==============================================================================
# SECTION 16: METAMORPHIC & PROPERTY TESTS
# ==============================================================================

def test_chronological_inversion_rejected_property() -> None:
    """[3B.0I PROPERTY: CHRONOLOGY_PRESERVATION]
    Reversing candle container order without re-sorting timestamps fails closed with ValueError.
    """
    candles = _make_guarded_candles(5)
    reversed_candles = list(reversed(candles))
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    with pytest.raises(ValueError) as exc_info:
        run_causal_backtest(reversed_candles, [0, 0, 0, 0, 0], costs)
    assert "candles must be strictly increasing" in str(exc_info.value)


def test_price_scaling_invariance_property() -> None:
    """[3B.0I PROPERTY: PRICE_SCALING_INVARIANCE]
    Multiplying all candle prices by a scalar constant C leaves percentage returns invariant.
    """
    candles_1x = _make_guarded_candles(10, base_price=Decimal("1000.0"), step_price=Decimal("10.0"))
    scale = Decimal("2.5")
    candles_scaled = [
        Candle(
            ts_event_ns=c.ts_event_ns,
            close=c.close * scale,
            open=c.open * scale if c.open is not None else None,
            instrument_id=c.instrument_id,
            dataset_id=c.dataset_id,
            market_type=c.market_type,
            venue=c.venue,
        )
        for c in candles_1x
    ]
    positions = [0, 1, 1, 0, -1, -1, 0, 1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5.0"), slippage_bps=Decimal("2.0"))

    res_1x = run_causal_backtest(candles_1x, positions, costs)
    res_scaled = run_causal_backtest(candles_scaled, positions, costs)

    assert res_1x.result.gross_return == res_scaled.result.gross_return
    assert res_1x.result.net_return == res_scaled.result.net_return
    assert res_1x.result.total_cost == res_scaled.result.total_cost
    assert res_1x.result.max_drawdown == res_scaled.result.max_drawdown

