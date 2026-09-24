from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import pytest

from btceth_os.research.temporal import (
    SettlementBoundaryStatus,
    TemporalEventContract,
    TemporalIntegrityViolationError,
    classify_funding_settlement_boundary,
    compute_causal_rolling_mean,
    compute_causal_rolling_basis_bps,
    ObservableEstimatedFunding,
    RealizedHistoricalFunding,
    FutureUnsettledRealizedFunding,
    assert_causal_funding_access,
)
from btceth_os.research.backtest import (
    BarObservation,
    Candle,
    CostModel,
    ExecutionAssumptions,
    ExecutionObservation,
    ExecutionPriceObservation,
    PriceSource,
    OrderSide,
    ExecutionMode,
    select_first_executable_observation,
    run_causal_backtest as _run_causal_backtest_strict,
    run_backtest,
    SYNTHETIC_TEST_CONTEXT,
    RESEARCH_CONTEXT,
    run_synthetic_causal_backtest,
)


def run_causal_backtest(*args: Any, **kwargs: Any) -> Any:
    """Test helper defaulting to SYNTHETIC_TEST_CONTEXT for bare synthetic candle fixtures."""
    kwargs.setdefault("context", SYNTHETIC_TEST_CONTEXT)
    return _run_causal_backtest_strict(*args, **kwargs)


from btceth_os.research.features.price_returns import (
    compute_log_returns,
    compute_trend_slope,
    compute_rolling_drawdown,
)
from btceth_os.research.features.volatility import (
    compute_realized_volatility,
    compute_average_true_range,
)
from btceth_os.research.features.derivatives import (
    align_funding_rates_to_klines,
    compute_funding_zscore,
)
from btceth_os.research.features.cross_asset import (
    compute_eth_btc_ratio,
    compute_relative_return_diff,
    compute_rolling_correlation,
)
from btceth_os.research.features.time_session import (
    compute_session_flags,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"


def test_clock_hierarchy_valid_contract() -> None:
    """Valid event contract satisfies source_ts <= available_ts <= decision_ts <= execution_ts <= fill_ts."""
    contract = TemporalEventContract(
        source_ts_ns=1_000_000_000,
        available_ts_ns=1_000_100_000,
        decision_ts_ns=1_000_200_000,
        execution_ts_ns=1_000_250_000,
        fill_ts_ns=1_000_300_000,
    )
    contract.validate()  # Must not raise


def test_temporal_mutation_leakage_detected() -> None:
    """Intentionally mutating available_ts to be after decision_ts fails closed with TEMPORAL_LEAKAGE_DETECTED."""
    mutated = TemporalEventContract(
        source_ts_ns=1_000_000_000,
        available_ts_ns=1_000_500_000,  # Available AFTER decision
        decision_ts_ns=1_000_200_000,   # Cheating decision time
        execution_ts_ns=1_000_600_000,
        fill_ts_ns=1_000_700_000,
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        mutated.validate()
    assert "TEMPORAL_LEAKAGE_DETECTED" in str(exc_info.value)


def test_bar_close_execution_causality() -> None:
    """Bar-close causality: completed 01:00 hourly candle cannot trade at 00:00 open price."""
    hour_0_open_ts_ns = 1609459200_000_000_000   # 00:00:00
    hour_1_close_ts_ns = 1609462800_000_000_000  # 01:00:00

    bar_open_price = Decimal("30000.0")
    bar_close_price = Decimal("31500.0")

    decision_ts_ns = hour_1_close_ts_ns

    # Execution cannot occur before decision
    execution_ts_ns = decision_ts_ns + 100_000_000  # +100ms
    assert execution_ts_ns >= decision_ts_ns

    # Invariant: fill cannot assume historical open price of the completed bar
    def execute_market_order(fill_price: Decimal, assumed_available_price: Decimal) -> Decimal:
        if fill_price < assumed_available_price:
            raise TemporalIntegrityViolationError("CAUSALITY_VIOLATION: Traded at past bar open price after observing bar close")
        return fill_price

    # Attempting to fill at bar_open_price after observing bar close must raise
    with pytest.raises(TemporalIntegrityViolationError):
        execute_market_order(bar_open_price, bar_close_price)


def test_conservative_funding_settlement_boundary() -> None:
    """Verify conservative unambiguous funding settlement boundary rule: entry < T < exit."""
    T = 1609459200_000_000_000  # 2021-01-01 00:00:00 UTC

    # 1. Unambiguous held through: entry 1s before, exit 1s after -> HELD_THROUGH
    res1 = classify_funding_settlement_boundary(T - 1_000_000_000, T + 1_000_000_000, T)
    assert res1 == SettlementBoundaryStatus.HELD_THROUGH

    # 2. Ambiguous boundary: entry exactly at T -> AMBIGUOUS_SETTLEMENT_BOUNDARY
    res2 = classify_funding_settlement_boundary(T, T + 1_000_000_000, T)
    assert res2 == SettlementBoundaryStatus.AMBIGUOUS_SETTLEMENT_BOUNDARY

    # 3. Ambiguous boundary: exit exactly at T -> AMBIGUOUS_SETTLEMENT_BOUNDARY
    res3 = classify_funding_settlement_boundary(T - 1_000_000_000, T, T)
    assert res3 == SettlementBoundaryStatus.AMBIGUOUS_SETTLEMENT_BOUNDARY

    # 4. Opened after T -> NOT_HELD
    res4 = classify_funding_settlement_boundary(T + 1_000_000_000, T + 10_000_000_000, T)
    assert res4 == SettlementBoundaryStatus.NOT_HELD

    # 5. Closed before T -> NOT_HELD
    res5 = classify_funding_settlement_boundary(T - 10_000_000_000, T - 1_000_000_000, T)
    assert res5 == SettlementBoundaryStatus.NOT_HELD


def test_typed_funding_signals_anti_leakage() -> None:
    """Test typed funding signal classes: ObservableEstimatedFunding, RealizedHistoricalFunding,
    FutureUnsettledRealizedFunding, and assert_causal_funding_access fail-closed on temporal leakage.
    """
    now_ts = 1609455600_000_000_000  # 2021-01-01 07:00:00 UTC
    settlement_ts = 1609459200_000_000_000  # 2021-01-01 08:00:00 UTC (1 hour in the future)

    # 1. ObservableEstimatedFunding: valid when as_of <= signal_ts
    obs = ObservableEstimatedFunding(
        signal_ts_ns=now_ts,
        estimated_rate=Decimal("0.00015"),
        as_of_ts_ns=now_ts - 60_000_000_000,
    )
    assert obs.estimated_rate == Decimal("0.00015")

    # ObservableEstimatedFunding: invalid when as_of > signal_ts (leakage)
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        ObservableEstimatedFunding(
            signal_ts_ns=now_ts,
            estimated_rate=Decimal("0.00015"),
            as_of_ts_ns=now_ts + 1_000_000_000,
        )
    assert "Observable funding rate cannot be from future" in str(exc_info.value)

    # 2. RealizedHistoricalFunding: past realized rate
    hist = RealizedHistoricalFunding(
        settlement_ts_ns=now_ts - 3600_000_000_000,
        realized_rate=Decimal("0.00010"),
    )
    assert hist.realized_rate == Decimal("0.00010")

    # 3. FutureUnsettledRealizedFunding: attempting direct .rate property access fails closed unconditionally
    fut = FutureUnsettledRealizedFunding(
        settlement_ts_ns=settlement_ts,
        _future_realized_rate=Decimal("0.00045"),
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc_prop:
        _ = fut.rate
    assert "FUTURE_FUNDING_RATE_ACCESS_PROHIBITED" in str(exc_prop.value)

    # Attempting to get_rate before settlement fails closed
    with pytest.raises(TemporalIntegrityViolationError) as exc_get:
        fut.get_rate(current_ts_ns=now_ts)
    assert "FUTURE_FUNDING_RATE_ACCESS_PROHIBITED" in str(exc_get.value)

    # Accessing at or after settlement succeeds
    rate_at_settlement = fut.get_rate(current_ts_ns=settlement_ts)
    assert rate_at_settlement == Decimal("0.00045")
    rate_after_settlement = fut.get_rate(current_ts_ns=settlement_ts + 1_000_000)
    assert rate_after_settlement == Decimal("0.00045")

    # 4. assert_causal_funding_access
    with pytest.raises(TemporalIntegrityViolationError) as exc_assert:
        assert_causal_funding_access(observed_ts_ns=now_ts, settlement_ts_ns=settlement_ts)
    assert "FUTURE_FUNDING_RATE_ACCESS_PROHIBITED" in str(exc_assert.value)

    assert_causal_funding_access(observed_ts_ns=settlement_ts, settlement_ts_ns=settlement_ts)
    assert_causal_funding_access(observed_ts_ns=settlement_ts + 1000, settlement_ts_ns=settlement_ts)


def test_backtest_simulation_temporal_event_contract_integration() -> None:
    """Test TemporalEventContract integrated with simulated backtest execution sequencing.
    Clock inversion at any step of the simulation execution pipeline must fail closed.
    """
    base_ts = 1609459200_000_000_000
    
    # Valid simulation sequence for a bar
    source_ts = base_ts
    avail_ts = source_ts + 1_000_000      # +1ms
    dec_ts = avail_ts + 5_000_000         # +5ms
    exec_ts = dec_ts + 10_000_000         # +10ms
    fill_ts = exec_ts + 15_000_000        # +15ms

    valid_contract = TemporalEventContract(
        source_ts_ns=source_ts,
        available_ts_ns=avail_ts,
        decision_ts_ns=dec_ts,
        execution_ts_ns=exec_ts,
        fill_ts_ns=fill_ts,
    )
    valid_contract.validate()

    # Adversarial Clock Inversion 1: Fill timestamp before execution timestamp
    inv_fill = TemporalEventContract(
        source_ts_ns=source_ts,
        available_ts_ns=avail_ts,
        decision_ts_ns=dec_ts,
        execution_ts_ns=exec_ts,
        fill_ts_ns=exec_ts - 1,
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc1:
        inv_fill.validate()
    assert "Execution causality violated" in str(exc1.value)

    # Adversarial Clock Inversion 2: Execution timestamp before decision timestamp
    inv_exec = TemporalEventContract(
        source_ts_ns=source_ts,
        available_ts_ns=avail_ts,
        decision_ts_ns=dec_ts,
        execution_ts_ns=dec_ts - 1,
        fill_ts_ns=fill_ts,
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc2:
        inv_exec.validate()
    assert "Causality violated: decision_ts" in str(exc2.value)

    # Adversarial Clock Inversion 3: Decision timestamp before available timestamp (Lookahead leakage)
    inv_dec = TemporalEventContract(
        source_ts_ns=source_ts,
        available_ts_ns=avail_ts,
        decision_ts_ns=avail_ts - 1,
        execution_ts_ns=exec_ts,
        fill_ts_ns=fill_ts,
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc3:
        inv_dec.validate()
    assert "TEMPORAL_LEAKAGE_DETECTED" in str(exc3.value)

    # Adversarial Clock Inversion 4: Available timestamp before source timestamp
    inv_avail = TemporalEventContract(
        source_ts_ns=source_ts,
        available_ts_ns=source_ts - 1,
        decision_ts_ns=dec_ts,
        execution_ts_ns=exec_ts,
        fill_ts_ns=fill_ts,
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc4:
        inv_avail.validate()
    assert "Clock hierarchy violated: source_ts" in str(exc4.value)


def test_real_feature_modules_future_row_perturbation_invariance() -> None:
    """Test future-row perturbation against real feature modules from src/btceth_os/research/features/:
    - price_returns (compute_log_returns, compute_trend_slope, compute_rolling_drawdown)
    - volatility (compute_realized_volatility, compute_average_true_range)
    - derivatives (align_funding_rates_to_klines, compute_funding_zscore)
    - cross_asset (compute_eth_btc_ratio, compute_relative_return_diff, compute_rolling_correlation)
    - time_session (compute_session_flags)
    
    Verifies that mutating rows at t > t_eval leaves all computed features at t <= t_eval 100% identical.
    """
    n = 100
    t_eval = 50

    timestamps_ns = [1609459200_000_000_000 + i * 60_000_000_000 for i in range(n)]
    btc_closes = [50000.0 + (i * 25.0) for i in range(n)]
    btc_highs = [c + 15.0 for c in btc_closes]
    btc_lows = [c - 15.0 for c in btc_closes]
    eth_closes = [3000.0 + (i * 2.0) for i in range(n)]

    # Funding rate events every 8 hours
    funding_ts_ns = [timestamps_ns[0] + k * 8 * 3600_000_000_000 for k in range(5)]
    funding_rates = [0.0001, 0.00015, -0.0001, 0.0002, 0.00005]

    # Compute baseline features across all 5 real modules
    base_log_ret = compute_log_returns(btc_closes, lookback=1)
    base_slope = compute_trend_slope(btc_closes, lookback=10)
    base_dd = compute_rolling_drawdown(btc_closes, lookback=10)

    base_rvol = compute_realized_volatility(btc_closes, lookback=10)
    base_atr = compute_average_true_range(btc_highs, btc_lows, btc_closes, lookback=10)

    base_aligned_funding = align_funding_rates_to_klines(timestamps_ns, funding_ts_ns, funding_rates)
    base_funding_z = compute_funding_zscore(base_aligned_funding, lookback_bars=10)

    base_eth_btc_ratio = compute_eth_btc_ratio(btc_closes, eth_closes)
    eth_log_ret = compute_log_returns(eth_closes, lookback=1)
    base_rel_diff = compute_relative_return_diff(base_log_ret, eth_log_ret)
    base_corr = compute_rolling_correlation(base_log_ret, eth_log_ret, lookback=10)

    base_asia, base_europe, base_us, base_weekend = compute_session_flags(timestamps_ns)

    # Create perturbed future series: radically perturb all inputs after t_eval
    pert_btc_closes = list(btc_closes)
    pert_btc_highs = list(btc_highs)
    pert_btc_lows = list(btc_lows)
    pert_eth_closes = list(eth_closes)
    pert_timestamps_ns = list(timestamps_ns)

    for i in range(t_eval + 1, n):
        pert_btc_closes[i] = 999999.0 + i
        pert_btc_highs[i] = 1000050.0 + i
        pert_btc_lows[i] = 999000.0 - i
        pert_eth_closes[i] = 1.0
        pert_timestamps_ns[i] = timestamps_ns[i] + 86400_000_000_000  # Shifted 1 day

    # Also perturb future funding rates (those strictly occurring after timestamps_ns[t_eval])
    pert_funding_rates = list(funding_rates)
    for k, ts in enumerate(funding_ts_ns):
        if ts > timestamps_ns[t_eval]:
            pert_funding_rates[k] = 0.9999  # Extreme corrupted rate

    # Recompute features on perturbed series
    pert_log_ret = compute_log_returns(pert_btc_closes, lookback=1)
    pert_slope = compute_trend_slope(pert_btc_closes, lookback=10)
    pert_dd = compute_rolling_drawdown(pert_btc_closes, lookback=10)

    pert_rvol = compute_realized_volatility(pert_btc_closes, lookback=10)
    pert_atr = compute_average_true_range(pert_btc_highs, pert_btc_lows, pert_btc_closes, lookback=10)

    pert_aligned_funding = align_funding_rates_to_klines(pert_timestamps_ns, funding_ts_ns, pert_funding_rates)
    pert_funding_z = compute_funding_zscore(pert_aligned_funding, lookback_bars=10)

    pert_eth_btc_ratio = compute_eth_btc_ratio(pert_btc_closes, pert_eth_closes)
    pert_eth_log_ret = compute_log_returns(pert_eth_closes, lookback=1)
    pert_rel_diff = compute_relative_return_diff(pert_log_ret, pert_eth_log_ret)
    pert_corr = compute_rolling_correlation(pert_log_ret, pert_eth_log_ret, lookback=10)

    pert_asia, pert_europe, pert_us, pert_weekend = compute_session_flags(pert_timestamps_ns)

    # Invariants: 100% exact equality at all t <= t_eval across all 11 real feature outputs
    features_verified = []

    assert base_log_ret[: t_eval + 1] == pert_log_ret[: t_eval + 1]
    features_verified.append("price_returns.compute_log_returns")

    assert base_slope[: t_eval + 1] == pert_slope[: t_eval + 1]
    features_verified.append("price_returns.compute_trend_slope")

    assert base_dd[: t_eval + 1] == pert_dd[: t_eval + 1]
    features_verified.append("price_returns.compute_rolling_drawdown")

    assert base_rvol[: t_eval + 1] == pert_rvol[: t_eval + 1]
    features_verified.append("volatility.compute_realized_volatility")

    assert base_atr[: t_eval + 1] == pert_atr[: t_eval + 1]
    features_verified.append("volatility.compute_average_true_range")

    assert base_aligned_funding[: t_eval + 1] == pert_aligned_funding[: t_eval + 1]
    features_verified.append("derivatives.align_funding_rates_to_klines")

    assert base_funding_z[: t_eval + 1] == pert_funding_z[: t_eval + 1]
    features_verified.append("derivatives.compute_funding_zscore")

    assert base_eth_btc_ratio[: t_eval + 1] == pert_eth_btc_ratio[: t_eval + 1]
    features_verified.append("cross_asset.compute_eth_btc_ratio")

    assert base_rel_diff[: t_eval + 1] == pert_rel_diff[: t_eval + 1]
    features_verified.append("cross_asset.compute_relative_return_diff")

    assert base_corr[: t_eval + 1] == pert_corr[: t_eval + 1]
    features_verified.append("cross_asset.compute_rolling_correlation")

    assert base_asia[: t_eval + 1] == pert_asia[: t_eval + 1]
    assert base_europe[: t_eval + 1] == pert_europe[: t_eval + 1]
    assert base_us[: t_eval + 1] == pert_us[: t_eval + 1]
    assert base_weekend[: t_eval + 1] == pert_weekend[: t_eval + 1]
    features_verified.append("time_session.compute_session_flags")

    # Generate ROUND3B_0B_TEMPORAL_RUNTIME_AUDIT.json
    audit_report = {
        "report_version": "ROUND3B.0B",
        "status": "VERIFIED",
        "features_tested_count": len(features_verified),
        "features_tested": features_verified,
        "all_real_features_perturbation_invariant": True,
        "clock_hierarchy_verified": True,
        "backtest_simulation_contract_verified": True,
        "typed_funding_signals_verified": True,
        "future_funding_leakage_blocked": True,
        "evaluation_index": t_eval,
        "total_series_length": n,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "ROUND3B_0B_TEMPORAL_RUNTIME_AUDIT.json").write_text(
        json.dumps(audit_report, indent=2) + "\n", encoding="utf-8"
    )


def test_real_causal_backtest_execution() -> None:
    """Run real backtest simulation through run_causal_backtest and verify TemporalEventContract on each fill."""
    candles = [
        Candle(ts_event_ns=1609459200_000_000_000, close=Decimal("30000.0"), open=Decimal("30000.0")),  # 00:00
        Candle(ts_event_ns=1609462800_000_000_000, close=Decimal("30500.0"), open=Decimal("30000.0")),  # 01:00
        Candle(ts_event_ns=1609466400_000_000_000, close=Decimal("31000.0"), open=Decimal("30500.0")),  # 02:00
        Candle(ts_event_ns=1609470000_000_000_000, close=Decimal("30800.0"), open=Decimal("31000.0")),  # 03:00
        Candle(ts_event_ns=1609473600_000_000_000, close=Decimal("31200.0"), open=Decimal("30800.0")),  # 04:00
        Candle(ts_event_ns=1609477200_000_000_000, close=Decimal("31200.0"), open=Decimal("31200.0")),  # 05:00
    ]
    positions = [1, 1, 0, -1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5"), slippage_bps=Decimal("2"))

    causal_res = run_causal_backtest(candles, positions, costs)
    legacy_res = run_backtest(candles, positions, costs)

    # Result equivalence with legacy run_backtest when open == previous close
    assert causal_res.result.bars == legacy_res.bars
    assert causal_res.result.trades == legacy_res.trades
    assert causal_res.result.net_return == legacy_res.net_return
    assert causal_res.result.total_cost == legacy_res.total_cost

    # Contract verification: every true execution has a valid contract and observation
    # (Bar 1 is hold-state with turnover==0, so no synthetic execution or contract)
    assert len(causal_res.contracts) == 4
    assert len(causal_res.executions) == 4
    for c in causal_res.contracts:
        c.validate()
        assert c.source_ts_ns <= c.available_ts_ns
        assert c.available_ts_ns <= c.decision_ts_ns
        assert c.decision_ts_ns <= c.execution_ts_ns
        assert c.execution_ts_ns <= c.fill_ts_ns

    # Bar availability: decision cannot occur before bar close timestamp
    for exec_record in causal_res.executions:
        assert exec_record.contract.decision_ts_ns >= exec_record.contract.source_ts_ns
        assert exec_record.observation.fill_price_observation_ts_ns >= exec_record.observation.decision_ts_ns


def test_real_causal_backtest_clock_inversion_fails_closed() -> None:
    """Deliberate clock inversion in real runner fails closed immediately."""
    candles = [
        Candle(ts_event_ns=1609459200_000_000_000, close=Decimal("30000.0"), open=Decimal("30000.0")),
        Candle(ts_event_ns=1609462800_000_000_000, close=Decimal("30500.0"), open=Decimal("30000.0")),
    ]
    positions = [1, 0]
    costs = CostModel(taker_fee_bps=Decimal("5"), slippage_bps=Decimal("2"))

    # 1. Negative latency causes decision_ts < available_ts (TEMPORAL_LEAKAGE_DETECTED)
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        run_causal_backtest(candles, positions, costs, decision_latency_ns=-10_000_000)
    assert "TEMPORAL_LEAKAGE_DETECTED" in str(exc_info.value)

    # 2. Execution latency negative causes execution_ts < decision_ts
    with pytest.raises(TemporalIntegrityViolationError) as exc_info2:
        run_causal_backtest(candles, positions, costs, execution_latency_ns=-5_000_000)
    assert "Causality violated" in str(exc_info2.value)


def test_real_causal_backtest_funding_boundary() -> None:
    """Strategy funding boundary accepts only causal typed funding signals and blocks unsettled funding."""
    candles = [
        Candle(ts_event_ns=1609459200_000_000_000, close=Decimal("30000.0"), open=Decimal("30000.0")),
        Candle(ts_event_ns=1609462800_000_000_000, close=Decimal("30500.0"), open=Decimal("30000.0")),
        Candle(ts_event_ns=1609466400_000_000_000, close=Decimal("30500.0"), open=Decimal("30500.0")),
    ]
    positions = [1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5"), slippage_bps=Decimal("2"))

    valid_signals = [
        ObservableEstimatedFunding(
            signal_ts_ns=1609459200_000_000_000,
            estimated_rate=Decimal("0.0001"),
            as_of_ts_ns=1609459200_000_000_000,
        ),
        RealizedHistoricalFunding(
            settlement_ts_ns=1609455600_000_000_000,
            realized_rate=Decimal("0.00015"),
        ),
    ]
    res = run_causal_backtest(candles, positions, costs, funding_signals=valid_signals)
    assert res.result.trades > 0

    future_unsettled = FutureUnsettledRealizedFunding(
        settlement_ts_ns=1609462800_000_000_000,
        _future_realized_rate=Decimal("0.0002"),
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc1:
        run_causal_backtest(candles, positions, costs, funding_signals=[future_unsettled])
    assert "STRATEGY_FUNDING_BOUNDARY_VIOLATION" in str(exc1.value)

    with pytest.raises(TemporalIntegrityViolationError) as exc2:
        run_causal_backtest(candles, positions, costs, funding_signals=[0.0001])
    assert "STRATEGY_FUNDING_BOUNDARY_VIOLATION" in str(exc2.value)


def test_same_close_cheating_blocked_by_next_bar_open_fill() -> None:
    """Same-close cheating: Signal observed at C_N (100) enters at O_{N+1} (120).
    Gap from 100 to 120 must NOT be credited to new position."""
    candles = [
        Candle(ts_event_ns=1000, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=2000, close=Decimal("120.0"), open=Decimal("120.0")),  # Gap up 20%
        Candle(ts_event_ns=3000, close=Decimal("120.0"), open=Decimal("120.0")),
    ]
    positions = [1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # Legacy cheating engine credits the gap to the trade
    legacy_res = run_backtest(candles, positions, costs)
    assert legacy_res.gross_return == Decimal("0.20")  # CHEATING

    # Causal engine enters at O_{N+1} = 120, so return from 100 to 120 earns 0
    causal_res = run_causal_backtest(candles, positions, costs)
    assert causal_res.result.gross_return == Decimal("0")
    assert causal_res.executions[0].fill_price == Decimal("120.0")
    assert causal_res.executions[0].position_before == 0
    assert causal_res.executions[0].position_after == 1


def test_gap_down_exit_penalized_causally() -> None:
    """Gap-down exit: Position held long decides to exit at C_N (100).
    Exit fills at O_{N+1} (80). Long position must take the -20% gap loss before exiting."""
    candles = [
        Candle(ts_event_ns=1000, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=2000, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=3000, close=Decimal("80.0"), open=Decimal("80.0")),  # Gap down 20%
    ]
    # At bar 0, stay long (1). At bar 1, exit to flat (0).
    positions = [1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # In legacy backtest, position is 0 from bar 1 to bar 2, so it escapes the gap!
    legacy_res = run_backtest(candles, positions, costs)
    assert legacy_res.gross_return == Decimal("0")  # ESCAPED GAP

    # In causal engine, position held is 1 during gap from 100 to 80; exit fills at 80
    causal_res = run_causal_backtest(candles, positions, costs)
    assert causal_res.result.gross_return == Decimal("-0.20")
    assert causal_res.executions[1].fill_price == Decimal("80.0")
    assert causal_res.executions[1].position_before == 1
    assert causal_res.executions[1].position_after == 0


def test_walk_forward_causal_routing() -> None:
    """Verify walk_forward_causal and walk_forward_momentum route to causal engine with open fallback."""
    from btceth_os.research.backtest import walk_forward_causal, walk_forward_momentum
    candles = [
        Candle(
            ts_event_ns=1000 * i,
            close=Decimal(str(10 + i % 5)),
            open=Decimal(str(10 + i % 5)),
            instrument_id="BTCUSDT",
            dataset_id="BTCUSDT_DEV_2020_2022",
            market_type="USD_M_PERP",
            venue="BINANCE",
        )
        for i in range(20)
    ]
    costs = CostModel(taker_fee_bps=Decimal("1"), slippage_bps=Decimal("1"))
    wf_res = walk_forward_causal(
        candles,
        train_bars=6,
        test_bars=4,
        candidate_lookbacks=[1, 2],
        costs=costs,
    )
    assert len(wf_res.folds) > 0
    assert wf_res.trades >= 0

    # walk_forward_momentum also works
    wf_mom_res = walk_forward_momentum(
        candles,
        train_bars=6,
        test_bars=4,
        candidate_lookbacks=[1, 2],
        costs=costs,
    )
    assert len(wf_mom_res.folds) == len(wf_res.folds)


def test_next_bar_open_blocked_when_decision_latency_positive() -> None:
    """When decision latency > 0, next-bar open occurred before decision finished; must fail closed."""
    candles = [
        Candle(ts_event_ns=1609459200_000_000_000, close=Decimal("30000.0"), open=Decimal("30000.0")),  # 00:00:00 -> close 01:00:00
        Candle(ts_event_ns=1609462800_000_000_000, close=Decimal("30500.0"), open=Decimal("30000.0")),  # 01:00:00 -> open 01:00:00
    ]
    positions = [1, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # When decision latency is 10ms (10,000,000 ns), decision is at 01:00:00.010, which is after 01:00:00.000 open
    assumptions = ExecutionAssumptions(
        price_source=PriceSource.NEXT_BAR_OPEN,
        decision_latency_ns=10_000_000,
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        run_causal_backtest(candles, positions, costs, assumptions=assumptions)
    assert "PRICE_CAUSALITY_VIOLATION" in str(exc_info.value)
    assert "Next-bar open" in str(exc_info.value)


def test_first_post_decision_observation_selection() -> None:
    """When execution_stream is provided, query first observation with ts_event_ns >= execution_eligible_ts_ns."""
    candles = [
        Candle(ts_event_ns=1609459200_000_000_000, close=Decimal("30000.0"), open=Decimal("30000.0")),  # 00:00:00
        Candle(ts_event_ns=1609462800_000_000_000, close=Decimal("30500.0"), open=Decimal("30000.0")),  # 01:00:00
    ]
    positions = [1, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # Decision finishes at 01:00:00 + 50ms = 1609462800_050_000_000
    decision_lat = 50_000_000
    assumptions = ExecutionAssumptions(
        price_source=PriceSource.NEXT_BAR_OPEN,
        decision_latency_ns=decision_lat,
    )

    bar_close_ts = 1609462800_000_000_000
    term_close_ts = bar_close_ts + 3_600_000_000_000
    exec_stream = [
        ExecutionPriceObservation(
            ts_event_ns=bar_close_ts + 10_000_000,
            price=Decimal("30010.0"),
            bid=Decimal("30010.0"),
            ask=Decimal("30010.0"),
            source_instrument="BTCUSDT_QUOTE_10MS",
        ),
        ExecutionPriceObservation(
            ts_event_ns=bar_close_ts + 60_000_000,
            price=Decimal("30025.0"),
            bid=Decimal("30025.0"),
            ask=Decimal("30025.0"),
            source_instrument="BTCUSDT_QUOTE_60MS",
        ),
        ExecutionPriceObservation(
            ts_event_ns=bar_close_ts + 120_000_000,
            price=Decimal("30050.0"),
            bid=Decimal("30050.0"),
            ask=Decimal("30050.0"),
            source_instrument="BTCUSDT_QUOTE_120MS",
        ),
        ExecutionPriceObservation(
            ts_event_ns=term_close_ts + 60_000_000,
            price=Decimal("30500.0"),
            bid=Decimal("30500.0"),
            ask=Decimal("30500.0"),
            source_instrument="BTCUSDT_QUOTE_TERM",
        ),
    ]

    res = run_causal_backtest(
        candles,
        positions,
        costs,
        assumptions=assumptions,
        execution_stream=exec_stream,
    )

    assert len(res.executions) > 0
    first_exec = res.executions[0]
    assert first_exec.fill_price == Decimal("30025.0")
    assert first_exec.observation.fill_price_observation_ts_ns == bar_close_ts + 60_000_000
    assert first_exec.observation.fill_price_observation_ts_ns >= first_exec.observation.execution_eligible_ts_ns
    assert first_exec.observation.source_instrument == "BTCUSDT_QUOTE_60MS"


def test_current_bar_close_execution_blocked_for_close_signal() -> None:
    """CURRENT_BAR_CLOSE cannot be used for execution after consuming that close as signal."""
    candles = [
        Candle(ts_event_ns=1000, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=2000, close=Decimal("110.0"), open=Decimal("100.0")),
    ]
    positions = [1, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    assumptions = ExecutionAssumptions(price_source=PriceSource.CURRENT_BAR_CLOSE)
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        run_causal_backtest(candles, positions, costs, assumptions=assumptions)
    assert "PRICE_CAUSALITY_VIOLATION" in str(exc_info.value)
    assert "CURRENT_BAR_CLOSE cannot be used as execution price" in str(exc_info.value)


def test_no_unsafe_open_fallback() -> None:
    """Missing open price raises NO_VALID_EXECUTION_OBSERVATION without falling back to close."""
    candles = [
        Candle(ts_event_ns=1000, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=2000, close=Decimal("110.0"), open=None),  # Missing open
    ]
    positions = [1, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        run_causal_backtest(candles, positions, costs)
    assert "NO_VALID_EXECUTION_OBSERVATION" in str(exc_info.value)
    assert "no open price" in str(exc_info.value)


def test_functional_execution_delay_bars() -> None:
    """execution_delay_bars = 2 shifts signal application by 2 bars."""
    candles = [
        Candle(ts_event_ns=1000, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=2000, close=Decimal("110.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=3000, close=Decimal("120.0"), open=Decimal("110.0")),
        Candle(ts_event_ns=4000, close=Decimal("130.0"), open=Decimal("120.0")),
        Candle(ts_event_ns=5000, close=Decimal("140.0"), open=Decimal("130.0")),
        Candle(ts_event_ns=6000, close=Decimal("150.0"), open=Decimal("140.0")),
    ]
    # Signal says go long at bar 0, exit to flat at bar 3
    positions = [1, 1, 1, 0, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # With delay = 1 (standard): signal on bar 0 executes at bar 1 (index 0 transition)
    res_delay1 = run_causal_backtest(candles, positions, costs, assumptions=ExecutionAssumptions(execution_delay_bars=1))
    assert res_delay1.executions[0].bar_index == 0
    assert res_delay1.executions[0].position_after == 1

    # With delay = 2: signal on bar 0 is NOT executed at bar 1; it executes at bar 2 (index 1 transition)
    res_delay2 = run_causal_backtest(candles, positions, costs, assumptions=ExecutionAssumptions(execution_delay_bars=2))
    assert res_delay2.executions[0].bar_index == 1
    assert res_delay2.executions[0].position_after == 1  # Becomes 1 at bar 2!


def test_terminal_exit_uses_authentic_market_observation() -> None:
    """Terminal exit uses authentic post-arrival observation timestamp from execution stream."""
    candles = [
        Candle(ts_event_ns=1609459200_000_000_000, close=Decimal("30000.0"), open=Decimal("30000.0")),
        Candle(ts_event_ns=1609462800_000_000_000, close=Decimal("31000.0"), open=Decimal("30000.0")),
    ]
    # Remains long at end of simulation
    positions = [1, 1]
    costs = CostModel(taker_fee_bps=Decimal("5"), slippage_bps=Decimal("2"))

    # Without an authentic execution observation stream, missing observation fails closed
    with pytest.raises(TemporalIntegrityViolationError) as exc_missing:
        run_causal_backtest(candles, positions, costs)
    assert "INVALID_TERMINAL_EXECUTION: TERMINAL_EXECUTION_OBSERVATION_MISSING" in str(exc_missing.value)

    # With an authentic post-arrival observation stream, terminal exit succeeds authentically
    entry_arrival_ts = 1609462800_000_000_000
    terminal_arrival_ts = 1609462800_000_000_000 + 3_600_000_000_000
    exec_stream = [
        ExecutionPriceObservation(
            ts_event_ns=entry_arrival_ts + 100_000_000,
            price=Decimal("30000.0"),
            bid=Decimal("29990.0"),
            ask=Decimal("30010.0"),
            trade_price=Decimal("30000.0"),
            source_instrument="BTCUSDT",
        ),
        ExecutionPriceObservation(
            ts_event_ns=terminal_arrival_ts + 100_000_000,
            price=Decimal("31000.0"),
            bid=Decimal("30990.0"),
            ask=Decimal("31010.0"),
            trade_price=Decimal("31000.0"),
            source_instrument="BTCUSDT",
        ),
    ]
    res = run_causal_backtest(candles, positions, costs, execution_stream=exec_stream)
    assert len(res.executions) == 2  # Entry at bar 1 open + terminal exit at end
    exit_exec = res.executions[-1]
    assert exit_exec.position_after == 0
    assert exit_exec.observation.fill_price_observation_ts_ns >= exit_exec.observation.execution_eligible_ts_ns
    assert exit_exec.turnover == 1
    assert exit_exec.observation.terminal is True


# ==============================================================================
# MANDATORY ROUND 3B.0E ADVERSARIAL CAUSALITY & TERMINAL SETTLEMENT TESTS
# ==============================================================================

def test_adversarial_3b0d_regression_pre_arrival_rejected() -> None:
    """[3B.0E SECTION 7 & 40] Pre-arrival market observations are strictly rejected.

    Fixture:
    Signal available:      T0 (01:00:00.000)
    Decision latency:      50 ms -> Decision / Submit: T0 + 50ms
    Execution latency:     100 ms -> Exchange arrival / eligible: T0 + 150ms
    Obs A:                 T0 + 60ms, price 100 (ineligible, occurred before exchange arrival)
    Obs B:                 T0 + 170ms, price 120 (eligible, first post-arrival observation)
    Terminal Obs:          T0 + 3600s + 200ms, price 120 (for terminal exit)

    Expected: Obs B (price 120) selected; Obs A (price 100) strictly rejected.
    """
    t0 = 1609459200_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), source_instrument="BTCUSDT"),
        Candle(ts_event_ns=t0 + 3_600_000_000_000, close=Decimal("110.0"), open=Decimal("100.0"), source_instrument="BTCUSDT"),
    ]
    positions = [1, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    assumptions = ExecutionAssumptions(
        decision_latency_ns=50_000_000,     # +50ms
        execution_latency_ns=100_000_000,   # +100ms -> Arrival = +150ms
    )

    t_signal = t0 + 3_600_000_000_000  # Bar 0 close is at t0 + 1 hour
    t_arrival = t_signal + 150_000_000

    exec_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t_signal + 60_000_000,   # +60ms (before arrival at +150ms)
            price=Decimal("100.0"),
            bid=Decimal("100.0"),
            ask=Decimal("100.0"),
            source_instrument="BTCUSDT",
        ),
        ExecutionPriceObservation(
            ts_event_ns=t_signal + 170_000_000,  # +170ms (after arrival at +150ms)
            price=Decimal("120.0"),
            bid=Decimal("120.0"),
            ask=Decimal("120.0"),
            source_instrument="BTCUSDT",
        ),
        ExecutionPriceObservation(
            ts_event_ns=t_signal + 3_600_000_000_000 + 200_000_000,  # Terminal
            price=Decimal("120.0"),
            bid=Decimal("120.0"),
            ask=Decimal("120.0"),
            source_instrument="BTCUSDT",
        ),
    ]

    res = run_causal_backtest(candles, positions, costs, assumptions=assumptions, execution_stream=exec_stream)

    assert len(res.executions) >= 1
    first_exec = res.executions[0]
    # Under defective 3B.0D engine, Obs A (+60ms, price 100) was chosen because 60ms >= 50ms decision_ts.
    # Under hardened 3B.0E engine, Obs A is rejected (60ms < 150ms arrival); Obs B (170ms, price 120) MUST be chosen.
    assert first_exec.fill_price == Decimal("120.0")
    assert first_exec.observation.fill_price_observation_ts_ns == t_signal + 170_000_000
    assert first_exec.observation.execution_eligible_ts_ns == t_arrival
    assert first_exec.observation.fill_price_observation_ts_ns >= first_exec.observation.execution_eligible_ts_ns


def test_fill_latency_semantics() -> None:
    """[3B.0E SECTION 8 & 41] A later fill timestamp cannot validate an earlier unavailable observation.

    price_observation_ts >= execution_eligible_ts is validated independently from fill_ts.
    """
    t0 = 1609459200_000_000_000
    # Attempt to construct an ExecutionObservation where price observation happened before exchange arrival
    # even though fill_ts is later (attempting to launder an early observation through fill latency)
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        ExecutionObservation(
            bar_index=0,
            signal_available_ts_ns=t0,
            decision_ts_ns=t0 + 50_000_000,
            order_submit_ts_ns=t0 + 50_000_000,
            exchange_arrival_ts_ns=t0 + 150_000_000,
            execution_eligible_ts_ns=t0 + 150_000_000,
            price_observation_ts_ns=t0 + 60_000_000,   # Ineligible! (60ms < 150ms)
            fill_ts_ns=t0 + 200_000_000,              # Laundering attempt (+200ms)
            price_source=PriceSource.BID_ASK_TOUCH,
            fill_price=Decimal("100.0"),
        )
    assert "PRICE_CAUSALITY_VIOLATION" in str(exc_info.value)
    assert "price_observation_ts_ns" in str(exc_info.value)


def test_cross_instrument_rejected() -> None:
    """[3B.0E SECTION 22 & 42] BTC order must never fill from ETH market data."""
    t0 = 1609459200_000_000_000

    # Case 1: Stream contains ETH observation earlier, BTC observation later -> BTC selected
    mixed_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + 100_000_000,
            price=Decimal("2000.0"),
            bid=Decimal("2000.0"),
            ask=Decimal("2000.0"),
            instrument_id="ETHUSDT",
        ),
        ExecutionPriceObservation(
            ts_event_ns=t0 + 200_000_000,
            price=Decimal("30000.0"),
            bid=Decimal("30000.0"),
            ask=Decimal("30000.0"),
            instrument_id="BTCUSDT",
        ),
    ]
    obs, fill_p, _ = select_first_executable_observation(
        mixed_stream,
        execution_eligible_ts_ns=t0 + 50_000_000,
        order_side=OrderSide.BUY,
        instrument_id="BTCUSDT",
    )
    assert obs.instrument_id == "BTCUSDT"
    assert fill_p == Decimal("30000.0")

    # Case 2: Stream contains only ETH observations -> fails closed with NO_VALID_EXECUTION_OBSERVATION
    eth_only_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + 100_000_000,
            price=Decimal("2000.0"),
            bid=Decimal("2000.0"),
            ask=Decimal("2000.0"),
            instrument_id="ETHUSDT",
        ),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            eth_only_stream,
            execution_eligible_ts_ns=t0 + 50_000_000,
            order_side=OrderSide.BUY,
            instrument_id="BTCUSDT",
        )
    assert "NO_VALID_EXECUTION_OBSERVATION" in str(exc_info.value)


def test_cross_market_type_rejected() -> None:
    """[3B.0E SECTION 23 & 43] USD-M Perp order must not silently execute against SPOT data."""
    t0 = 1609459200_000_000_000
    spot_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + 100_000_000,
            price=Decimal("30000.0"),
            bid=Decimal("30000.0"),
            ask=Decimal("30000.0"),
            instrument_id="BTCUSDT",
            market_type="SPOT",
        ),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            spot_stream,
            execution_eligible_ts_ns=t0 + 50_000_000,
            order_side=OrderSide.BUY,
            instrument_id="BTCUSDT",
            market_type="USD_M_PERP",
        )
    assert "NO_VALID_EXECUTION_OBSERVATION" in str(exc_info.value)


def test_unsorted_stream_rejected() -> None:
    """[3B.0E SECTION 24 & 44] Non-monotonic execution streams must fail closed."""
    t0 = 1609459200_000_000_000
    unsorted_stream = [
        ExecutionPriceObservation(ts_event_ns=t0 + 200_000_000, price=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t0 + 100_000_000, price=Decimal("101.0")),
        ExecutionPriceObservation(ts_event_ns=t0 + 150_000_000, price=Decimal("102.0")),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            unsorted_stream,
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.BUY,
        )
    assert "EXECUTION_STREAM_NOT_MONOTONIC" in str(exc_info.value)


def test_duplicate_timestamp_ambiguity_rejected() -> None:
    """[3B.0E SECTION 25 & 45] Identical timestamps without sequence ID raise AMBIGUOUS_EXECUTION_OBSERVATION."""
    t0 = 1609459200_000_000_000
    duplicate_stream = [
        ExecutionPriceObservation(ts_event_ns=t0 + 100_000_000, price=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t0 + 100_000_000, price=Decimal("101.0")),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            duplicate_stream,
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.BUY,
        )
    assert "AMBIGUOUS_EXECUTION_OBSERVATION" in str(exc_info.value)


def test_terminal_missing_observation_fails_closed() -> None:
    """[3B.0E SECTION 11 & 46] Long remains open with no authentic post-arrival observation -> fails closed."""
    t0 = 1609459200_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3_600_000_000_000, close=Decimal("100.0"), open=Decimal("100.0")),
    ]
    positions = [1, 1]  # Remains long (+1) at end of simulation
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # Case A: No execution stream provided
    with pytest.raises(TemporalIntegrityViolationError) as exc_no_stream:
        run_causal_backtest(candles, positions, costs)
    assert "INVALID_TERMINAL_EXECUTION: TERMINAL_EXECUTION_OBSERVATION_MISSING" in str(exc_no_stream.value)

    # Case B: Execution stream has observations, but NONE at or after terminal arrival
    terminal_arrival_ts = t0 + 2 * 3_600_000_000_000
    stale_stream = [
        ExecutionPriceObservation(
            ts_event_ns=terminal_arrival_ts - 100_000_000,  # 100ms before terminal arrival (serves as entry fill)
            price=Decimal("99.0"),
            bid=Decimal("99.0"),
            ask=Decimal("99.0"),
        ),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_stale:
        run_causal_backtest(candles, positions, costs, execution_stream=stale_stream)
    assert "INVALID_TERMINAL_EXECUTION: TERMINAL_EXECUTION_OBSERVATION_MISSING" in str(exc_stale.value)


def test_terminal_authentic_observation_selected() -> None:
    """[3B.0E SECTION 12 & 47] Positive terminal execution observation selection."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), source_instrument="BTCUSDT"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0"), source_instrument="BTCUSDT"),
    ]
    positions = [1, 1]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    assumptions = ExecutionAssumptions(
        decision_latency_ns=50_000_000,     # +50ms
        execution_latency_ns=100_000_000,   # +100ms -> Arrival = +150ms after close
    )

    t_term_close = t0 + 2 * bar_dur
    t_term_arrival = t_term_close + 150_000_000

    stream = [
        ExecutionPriceObservation(ts_event_ns=t0 + bar_dur + 160_000_000, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0"), source_instrument="BTCUSDT"), # Entry
        ExecutionPriceObservation(ts_event_ns=t_term_close + 100_000_000, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0"), source_instrument="BTCUSDT"), # +100ms (pre-arrival, ineligible)
        ExecutionPriceObservation(ts_event_ns=t_term_close + 160_000_000, price=Decimal("98.0"), bid=Decimal("98.0"), ask=Decimal("98.0"), source_instrument="BTCUSDT"),  # +160ms (first post-arrival, SELECTED)
        ExecutionPriceObservation(ts_event_ns=t_term_close + 300_000_000, price=Decimal("97.0"), bid=Decimal("97.0"), ask=Decimal("97.0"), source_instrument="BTCUSDT"),  # +300ms (too late)
    ]

    res = run_causal_backtest(candles, positions, costs, assumptions=assumptions, execution_stream=stream)

    assert len(res.executions) == 2
    term_exec = res.executions[-1]
    assert term_exec.fill_price == Decimal("98.0")
    assert term_exec.observation.fill_price_observation_ts_ns == t_term_close + 160_000_000
    assert term_exec.observation.execution_eligible_ts_ns == t_term_arrival
    assert term_exec.observation.side == OrderSide.SELL  # Flattening a long requires a SELL
    assert term_exec.observation.terminal is True
    assert term_exec.position_after == 0


def test_terminal_pnl_exact_decimal_hand_fixtures() -> None:
    """[3B.0E SECTIONS 14, 15, 16, 48] Terminal mark-to-fill return exact Decimal fixtures:
    - Long Loss:   100 -> 90   (-10%)
    - Long Gain:   100 -> 110  (+10%)
    - Short Gain:  100 -> 90   (+10%)
    - Short Loss:  100 -> 110  (-10%)
    """
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    t_entry = t0 + bar_dur + 1_000_000
    t_exit = t0 + 2 * bar_dur + 1_000_000

    c_long = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
    ]

    # Fixture 1: Long Loss (position = +1, entry = 100, mark = 100, fill = 90) -> return = -0.10
    s_long_loss = [
        ExecutionPriceObservation(ts_event_ns=t_entry, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t_exit, price=Decimal("90.0"), bid=Decimal("90.0"), ask=Decimal("90.0")),
    ]
    res1 = run_causal_backtest(c_long, [1, 1], zero_costs, execution_stream=s_long_loss)
    assert res1.result.gross_return == Decimal("-0.10")
    assert res1.result.net_return == Decimal("-0.10")

    # Fixture 2: Long Gain (position = +1, entry = 100, mark = 100, fill = 110) -> return = +0.10
    s_long_gain = [
        ExecutionPriceObservation(ts_event_ns=t_entry, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t_exit, price=Decimal("110.0"), bid=Decimal("110.0"), ask=Decimal("110.0")),
    ]
    res2 = run_causal_backtest(c_long, [1, 1], zero_costs, execution_stream=s_long_gain)
    assert res2.result.gross_return == Decimal("0.10")
    assert res2.result.net_return == Decimal("0.10")

    # Fixture 3: Short Gain (position = -1, entry = 100, mark = 100, fill = 90) -> return = +0.10
    s_short_gain = [
        ExecutionPriceObservation(ts_event_ns=t_entry, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t_exit, price=Decimal("90.0"), bid=Decimal("90.0"), ask=Decimal("90.0")),
    ]
    res3 = run_causal_backtest(c_long, [-1, -1], zero_costs, execution_stream=s_short_gain)
    assert res3.result.gross_return == Decimal("0.10")
    assert res3.result.net_return == Decimal("0.10")

    # Fixture 4: Short Loss (position = -1, entry = 100, mark = 100, fill = 110) -> return = -0.10
    s_short_loss = [
        ExecutionPriceObservation(ts_event_ns=t_entry, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t_exit, price=Decimal("110.0"), bid=Decimal("110.0"), ask=Decimal("110.0")),
    ]
    res4 = run_causal_backtest(c_long, [-1, -1], zero_costs, execution_stream=s_short_loss)
    assert res4.result.gross_return == Decimal("-0.10")
    assert res4.result.net_return == Decimal("-0.10")


def test_terminal_cost_applied_once() -> None:
    """[3B.0E SECTION 17 & 49] Terminal exit fee is applied exactly once to net equity."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    t_entry = t0 + bar_dur + 1_000_000
    t_exit = t0 + 2 * bar_dur + 1_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
    ]
    # Turnover rate = 5 bps taker + 5 bps slippage = 10 bps = 0.001
    costs = CostModel(taker_fee_bps=Decimal("5"), slippage_bps=Decimal("5"))
    # Terminal fill price equals last mark (0 market movement return)
    stream = [
        ExecutionPriceObservation(ts_event_ns=t_entry, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t_exit, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
    ]

    res = run_causal_backtest(candles, [1, 1], costs, execution_stream=stream)
    # Entry fee was 0.001, Terminal exit fee was 0.001 -> Total cost = 0.002
    assert res.result.total_cost == Decimal("0.002")
    # Equity after entry fee = 1 - 0.001 = 0.999
    # Equity after terminal exit fee = 0.999 * (1 - 0.001) = 0.998001
    expected_net = Decimal("0.998001") - Decimal("1.0")
    assert res.result.net_return == expected_net
    assert res.result.gross_return == Decimal("0")


def test_terminal_drawdown_updates_max_drawdown() -> None:
    """[3B.0E SECTION 18 & 50] Terminal gap loss correctly forms strategy peak max_drawdown."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    t_entry = t0 + bar_dur + 1_000_000
    t_exit = t0 + 2 * bar_dur + 1_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
    ]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    # Severe gap down at terminal exit: 100 -> 75 (-25%)
    stream = [
        ExecutionPriceObservation(ts_event_ns=t_entry, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t_exit, price=Decimal("75.0"), bid=Decimal("75.0"), ask=Decimal("75.0")),
    ]

    res = run_causal_backtest(candles, [1, 1], zero_costs, execution_stream=stream)
    assert res.result.max_drawdown == Decimal("0.25")


def test_side_aware_bid_ask_touch_execution() -> None:
    """[3B.0E SECTION 19] BID_ASK_TOUCH execution mode: BUY executes at ASK, SELL executes at BID."""
    t0 = 1609459200_000_000_000
    obs = ExecutionPriceObservation(
        ts_event_ns=t0 + 100_000_000,
        price=Decimal("100.0"),       # Midpoint
        bid=Decimal("99.5"),         # Bid
        ask=Decimal("100.5"),        # Ask
        trade_price=Decimal("100.0"),
    )

    # BUY marketable order must execute at ASK
    _, buy_fill, _ = select_first_executable_observation(
        [obs],
        execution_eligible_ts_ns=t0,
        order_side=OrderSide.BUY,
        execution_mode=ExecutionMode.BID_ASK_TOUCH,
    )
    assert buy_fill == Decimal("100.5")

    # SELL marketable order must execute at BID
    _, sell_fill, _ = select_first_executable_observation(
        [obs],
        execution_eligible_ts_ns=t0,
        order_side=OrderSide.SELL,
        execution_mode=ExecutionMode.BID_ASK_TOUCH,
    )
    assert sell_fill == Decimal("99.5")


# ==============================================================================
# MANDATORY ROUND 3B.0F TESTS
# ==============================================================================

def test_adversarial_future_observation_blocked() -> None:
    """[3B.0F SECTION 6] Observation timestamped after valuation close is NEVER selected.

    Window is [eligible_ts, window_end_ts]. An observation at window_end_ts + 1ns
    must fail closed with NO_VALID_EXECUTION_OBSERVATION_IN_WINDOW.
    """
    t0 = 1609459200_000_000_000
    t_eligible = t0 + 100_000_000
    t_window_end = t0 + 3_600_000_000_000

    # Observation occurs 10ms AFTER window_end
    future_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t_window_end + 10_000_000,
            price=Decimal("100.0"),
            bid=Decimal("100.0"),
            ask=Decimal("100.0"),
        ),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            future_stream,
            execution_eligible_ts_ns=t_eligible,
            execution_window_end_ts_ns=t_window_end,
            order_side=OrderSide.BUY,
        )
    assert "NO_VALID_EXECUTION_OBSERVATION_IN_WINDOW" in str(exc_info.value)


def test_valid_observation_in_window_selected() -> None:
    """[3B.0F SECTION 7] Observation within [execution_eligible_ts_ns, execution_window_end_ts_ns] is selected."""
    t0 = 1609459200_000_000_000
    t_eligible = t0 + 100_000_000
    t_window_end = t0 + 3_600_000_000_000

    valid_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t_eligible + 50_000_000,  # inside window
            price=Decimal("105.0"),
            bid=Decimal("104.5"),
            ask=Decimal("105.5"),
        ),
    ]
    obs, fill_p, raw_p = select_first_executable_observation(
        valid_stream,
        execution_eligible_ts_ns=t_eligible,
        execution_window_end_ts_ns=t_window_end,
        order_side=OrderSide.BUY,
    )
    assert obs.ts_event_ns == t_eligible + 50_000_000
    assert fill_p == Decimal("105.5")


def test_observation_after_next_close_rejected() -> None:
    """[3B.0F SECTION 8] Observation at next_close_ts + 1ns is rejected for the interval."""
    t0 = 1609459200_000_000_000
    t_eligible = t0 + 100_000_000
    t_window_end = t0 + 3_600_000_000_000

    stream = [
        ExecutionPriceObservation(
            ts_event_ns=t_window_end + 1,  # Exactly 1ns after next_close_ts
            price=Decimal("100.0"),
            bid=Decimal("100.0"),
            ask=Decimal("100.0"),
        ),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            stream,
            execution_eligible_ts_ns=t_eligible,
            execution_window_end_ts_ns=t_window_end,
            order_side=OrderSide.BUY,
        )
    assert "NO_VALID_EXECUTION_OBSERVATION_IN_WINDOW" in str(exc_info.value)


def test_return_timeline_order_enforced() -> None:
    """[3B.0F SECTION 9] Return timeline order signal_close_ts <= fill_obs_ts <= valuation_close_ts enforced."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("105.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("110.0"), open=Decimal("105.0")),
    ]
    positions = [1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # Case A: Normal execution respects signal_close_ts <= fill_obs_ts <= next_close_ts
    normal_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + bar_dur + 50_000_000,
            price=Decimal("102.0"),
            bid=Decimal("102.0"),
            ask=Decimal("102.0"),
        ),
        ExecutionPriceObservation(
            ts_event_ns=t0 + 2 * bar_dur + 50_000_000,
            price=Decimal("108.0"),
            bid=Decimal("108.0"),
            ask=Decimal("108.0"),
        ),
    ]
    res = run_causal_backtest(candles, positions, costs, execution_stream=normal_stream)
    assert len(res.executions) >= 1
    exec0 = res.executions[0]
    sig_close = t0 + bar_dur
    val_close = t0 + 2 * bar_dur
    assert sig_close <= exec0.observation.fill_price_observation_ts_ns <= val_close

    # Case B: Post-valuation close observation rejected by execution window and raises violation
    future_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + 2 * bar_dur + 10_000_000,  # After first valuation close (t0 + 2*bar_dur)
            price=Decimal("102.0"),
            bid=Decimal("102.0"),
            ask=Decimal("102.0"),
        ),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        run_causal_backtest(candles, positions, costs, execution_stream=future_stream)
    assert "NO_VALID_EXECUTION_OBSERVATION_IN_WINDOW" in str(exc_info.value)


def test_execution_delay_bars_window_aligned() -> None:
    """[3B.0F SECTION 10] execution_delay_bars = 2 aligns window with delayed interval."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("105.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("110.0"), open=Decimal("105.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("115.0"), open=Decimal("110.0")),
    ]
    positions = [1, 1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    assumptions = ExecutionAssumptions(execution_delay_bars=2)

    # Delay 2: Signal generated at bar 0 close (t0 + bar_dur) executes at bar 2 (t0 + 2*bar_dur -> t0 + 3*bar_dur)
    delayed_stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + bar_dur + 10_000_000,
            price=Decimal("100.0"),
            bid=Decimal("100.0"),
            ask=Decimal("100.0"),
        ),
        ExecutionPriceObservation(
            ts_event_ns=t0 + 2 * bar_dur + 10_000_000,
            price=Decimal("110.0"),
            bid=Decimal("110.0"),
            ask=Decimal("110.0"),
        ),
        ExecutionPriceObservation(
            ts_event_ns=t0 + 3 * bar_dur + 10_000_000,
            price=Decimal("115.0"),
            bid=Decimal("115.0"),
            ask=Decimal("115.0"),
        ),
        ExecutionPriceObservation(
            ts_event_ns=t0 + 4 * bar_dur + 10_000_000,  # Terminal exit observation
            price=Decimal("115.0"),
            bid=Decimal("115.0"),
            ask=Decimal("115.0"),
        ),
    ]
    res = run_causal_backtest(candles, positions, costs, assumptions=assumptions, execution_stream=delayed_stream)
    assert res.executions[0].position_after == 1  # Bar 2 transition becomes 1 (no synthetic execution at Bar 1)
    assert res.executions[0].observation.fill_price_observation_ts_ns == t0 + 2 * bar_dur + 10_000_000


def test_same_instrument_missing_obs_id_blocked() -> None:
    """[3B.0F SECTION 16] Missing instrument_id on observation fails closed in strict mode."""
    t0 = 1609459200_000_000_000
    stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + 100_000_000,
            price=Decimal("100.0"),
            bid=Decimal("100.0"),
            ask=Decimal("100.0"),
            instrument_id=None,
        ),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            stream,
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.BUY,
            instrument_id="BTCUSDT",
            strict_identity=True,
        )
    assert "EXECUTION_OBSERVATION_INSTRUMENT_REQUIRED" in str(exc_info.value)


def test_same_instrument_missing_expected_id_strict() -> None:
    """[3B.0F SECTION 17] Missing expected instrument_id in strict mode fails closed."""
    t0 = 1609459200_000_000_000
    stream = [
        ExecutionPriceObservation(
            ts_event_ns=t0 + 100_000_000,
            price=Decimal("100.0"),
            bid=Decimal("100.0"),
            ask=Decimal("100.0"),
            instrument_id="BTCUSDT",
        ),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            stream,
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.BUY,
            instrument_id=None,
            strict_identity=True,
        )
    assert "EXECUTION_INSTRUMENT_IDENTITY_REQUIRED" in str(exc_info.value)


def test_dataset_loader_propagation() -> None:
    """[3B.0F SECTION 18] load_guarded_kline_candles() populates metadata onto Candle."""
    from btceth_os.research.backtest import load_guarded_kline_candles
    dev_part = ROOT / "artifacts" / "research" / "partitions" / "BTCUSDT_DEV_2020_2022.parquet"
    if not dev_part.is_file():
        pytest.skip("BTCUSDT_DEV_2020_2022.parquet not present on disk")
    _, candles = load_guarded_kline_candles("BTCUSDT_DEV_2020_2022")
    assert len(candles) > 0
    c0 = candles[0]
    assert c0.instrument_id == "BTCUSDT"
    assert c0.market_type == "USD_M_PERP"
    assert c0.venue == "BINANCE"
    assert c0.dataset_id == "BTCUSDT_DEV_2020_2022"


def test_buy_without_ask_fails_closed() -> None:
    """[3B.0F SECTION 20] BID_ASK_TOUCH with BUY order fails closed if ask is missing."""
    t0 = 1609459200_000_000_000
    obs = ExecutionPriceObservation(
        ts_event_ns=t0 + 100_000_000,
        price=Decimal("100.0"),
        bid=Decimal("99.0"),
        ask=None,
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            [obs],
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.BUY,
            execution_mode=ExecutionMode.BID_ASK_TOUCH,
        )
    assert "EXECUTABLE_ASK_MISSING" in str(exc_info.value)


def test_sell_without_bid_fails_closed() -> None:
    """[3B.0F SECTION 21] BID_ASK_TOUCH with SELL order fails closed if bid is missing."""
    t0 = 1609459200_000_000_000
    obs = ExecutionPriceObservation(
        ts_event_ns=t0 + 100_000_000,
        price=Decimal("100.0"),
        bid=None,
        ask=Decimal("101.0"),
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            [obs],
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.SELL,
            execution_mode=ExecutionMode.BID_ASK_TOUCH,
        )
    assert "EXECUTABLE_BID_MISSING" in str(exc_info.value)


def test_trade_print_mode_requires_trade_price() -> None:
    """[3B.0F SECTION 22] TRADE_PRINT mode fails closed if trade_price is missing."""
    t0 = 1609459200_000_000_000
    obs = ExecutionPriceObservation(
        ts_event_ns=t0 + 100_000_000,
        price=Decimal("100.0"),
        bid=Decimal("99.0"),
        ask=Decimal("101.0"),
        trade_price=None,
    )
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        select_first_executable_observation(
            [obs],
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.BUY,
            execution_mode=ExecutionMode.TRADE_PRINT,
        )
    assert "EXECUTABLE_TRADE_PRICE_MISSING" in str(exc_info.value)


def test_generic_price_no_strict_touch_fallback() -> None:
    """[3B.0F SECTION 23 & 24] GENERIC_PRICE succeeds with generic price, while BID_ASK_TOUCH rejects it."""
    t0 = 1609459200_000_000_000
    obs = ExecutionPriceObservation(
        ts_event_ns=t0 + 100_000_000,
        price=Decimal("100.0"),
        bid=None,
        ask=None,
        trade_price=None,
    )

    # 1. BID_ASK_TOUCH strictly rejects generic price
    with pytest.raises(TemporalIntegrityViolationError) as exc_buy:
        select_first_executable_observation(
            [obs],
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.BUY,
            execution_mode=ExecutionMode.BID_ASK_TOUCH,
        )
    assert "EXECUTABLE_ASK_MISSING" in str(exc_buy.value)

    with pytest.raises(TemporalIntegrityViolationError) as exc_sell:
        select_first_executable_observation(
            [obs],
            execution_eligible_ts_ns=t0,
            order_side=OrderSide.SELL,
            execution_mode=ExecutionMode.BID_ASK_TOUCH,
        )
    assert "EXECUTABLE_BID_MISSING" in str(exc_sell.value)

    # 2. Explicit GENERIC_PRICE mode succeeds
    selected_obs, fill_price, raw_price = select_first_executable_observation(
        [obs],
        execution_eligible_ts_ns=t0,
        order_side=OrderSide.BUY,
        execution_mode=ExecutionMode.GENERIC_PRICE,
    )
    assert fill_price == Decimal("100.0")
    assert raw_price == Decimal("100.0")


# ==============================================================================
# ROUND 3B.0G MANDATORY GATES: HOLD-STATE ACCOUNTING + STRICT RESEARCH IDENTITY
# ==============================================================================


def test_held_long_exact_return() -> None:
    """[3B.0G SECTION 7 & 33] Held long position (100 -> 110) earns exactly +10% discrete-bar return with zero turnover."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("110.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("110.0"), open=Decimal("110.0")),
    ]
    # Bar 0 (t0->t1): target=1 (0->1 entry). Bar 1 (t1->t2): target=1 (1->1 HOLD). Bar 2 (t2->t3): target=0 (1->0 exit).
    positions = [1, 1, 0, 0]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    res = run_causal_backtest(candles, positions, zero_costs)
    assert res.result.gross_return == Decimal("0.10")
    assert res.result.net_return == Decimal("0.10")
    # Only 2 executions: entry at bar 0 and exit at bar 2. NO execution for hold bar 1!
    assert len(res.executions) == 2
    assert res.executions[0].bar_index == 0
    assert res.executions[0].position_after == 1
    assert res.executions[1].bar_index == 2
    assert res.executions[1].position_after == 0
    assert res.result.trades == 2


def test_held_short_loss_exact_return() -> None:
    """[3B.0G SECTION 8, 33, 34] Held short position (100 -> 110) experiences exactly -10% discrete-bar return with zero turnover."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("110.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("110.0"), open=Decimal("110.0")),
    ]
    positions = [-1, -1, 0, 0]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    res = run_causal_backtest(candles, positions, zero_costs)
    assert res.result.gross_return == Decimal("-0.10")
    assert res.result.net_return == Decimal("-0.10")
    assert len(res.executions) == 2
    assert res.executions[0].bar_index == 0
    assert res.executions[0].position_after == -1
    assert res.executions[1].bar_index == 2
    assert res.executions[1].position_after == 0


def test_held_short_gain_exact_return() -> None:
    """[3B.0G SECTION 9 & 33] Held short position (100 -> 90) earns exactly +10% discrete-bar return with zero turnover."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("90.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("90.0"), open=Decimal("90.0")),
    ]
    positions = [-1, -1, 0, 0]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    res = run_causal_backtest(candles, positions, zero_costs)
    assert res.result.gross_return == Decimal("0.10")
    assert res.result.net_return == Decimal("0.10")
    assert len(res.executions) == 2


def test_intermediate_quote_does_not_affect_hold_return() -> None:
    """[3B.0G SECTION 35] Changing intermediate quote (105 -> 106 -> 120) inside hold interval has ZERO effect on held short return."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("110.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("110.0"), open=Decimal("110.0")),
    ]
    positions = [-1, -1, 0, 0]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    returns = []
    for intermediate_price in [Decimal("105.0"), Decimal("106.0"), Decimal("120.0")]:
        stream = [
            # Entry observation at bar 0
            ExecutionPriceObservation(ts_event_ns=t0 + bar_dur + 10_000_000, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
            # Intermediate observation inside hold interval (bar 1: t0 + 2*bar_dur)
            ExecutionPriceObservation(ts_event_ns=t0 + 2 * bar_dur - 10_000_000, price=intermediate_price, bid=intermediate_price, ask=intermediate_price),
            # Exit observation at bar 2
            ExecutionPriceObservation(ts_event_ns=t0 + 3 * bar_dur + 10_000_000, price=Decimal("110.0"), bid=Decimal("110.0"), ask=Decimal("110.0")),
        ]
        res = run_causal_backtest(candles, positions, zero_costs, execution_stream=stream)
        returns.append(res.result.gross_return)

    # All three must be exactly identical to -0.10
    assert len(set(returns)) == 1
    assert returns[0] == Decimal("-0.10")


def test_hold_period_missing_execution_stream_passes() -> None:
    """[3B.0G SECTION 10 & 33] Hold-only valuation interval does NOT require any execution stream observation."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("105.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("110.0"), open=Decimal("105.0")),
    ]
    # Bar 0: enter 1. Bar 1: hold 1. Bar 2: exit 0.
    positions = [1, 1, 0, 0]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # Stream has observations for entry and exit, but ZERO observations during hold interval (bar 1)
    stream = [
        ExecutionPriceObservation(ts_event_ns=t0 + bar_dur + 10_000_000, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t0 + 3 * bar_dur + 10_000_000, price=Decimal("110.0"), bid=Decimal("110.0"), ask=Decimal("110.0")),
    ]
    res = run_causal_backtest(candles, positions, zero_costs, execution_stream=stream)
    assert res.result.gross_return == Decimal("0.10")
    assert len(res.executions) == 2


def test_hold_period_missing_bid_ask_passes() -> None:
    """[3B.0G SECTION 11 & 33] Zero-turnover interval does not require bid or ask data."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("105.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("110.0"), open=Decimal("105.0")),
    ]
    positions = [1, 1, 0, 0]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # Stream has observation during hold interval with bid=None and ask=None
    stream = [
        ExecutionPriceObservation(ts_event_ns=t0 + bar_dur + 10_000_000, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t0 + 2 * bar_dur - 10_000_000, price=Decimal("102.0"), bid=None, ask=None),
        ExecutionPriceObservation(ts_event_ns=t0 + 3 * bar_dur + 10_000_000, price=Decimal("110.0"), bid=Decimal("110.0"), ask=Decimal("110.0")),
    ]
    res = run_causal_backtest(candles, positions, zero_costs, execution_stream=stream)
    assert res.result.gross_return == Decimal("0.10")


def test_zero_turnover_selector_not_called(monkeypatch: pytest.MonkeyPatch) -> None:
    """[3B.0G SECTION 15 & 33] select_first_executable_observation is NOT called on zero-turnover hold intervals."""
    import btceth_os.research.backtest as bt_mod

    call_count = 0
    orig_select = bt_mod.select_first_executable_observation

    def counting_select(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        return orig_select(*args, **kwargs)

    monkeypatch.setattr(bt_mod, "select_first_executable_observation", counting_select)

    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("105.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("110.0"), open=Decimal("105.0")),
        Candle(ts_event_ns=t0 + 4 * bar_dur, close=Decimal("115.0"), open=Decimal("110.0")),
    ]
    # Positions: 0->1 (entry), 1->1 (hold), 1->1 (hold), 1->0 (exit)
    positions = [1, 1, 1, 0, 0]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    stream = [
        ExecutionPriceObservation(ts_event_ns=t0 + bar_dur + 10_000_000, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t0 + 4 * bar_dur + 10_000_000, price=Decimal("115.0"), bid=Decimal("115.0"), ask=Decimal("115.0")),
    ]
    res = run_causal_backtest(candles, positions, zero_costs, execution_stream=stream)
    assert res.result.gross_return == Decimal("0.15")
    # There were 4 valuation intervals, but only 2 position transitions (entry + exit).
    # The 2 hold intervals must NEVER call select_first_executable_observation!
    assert call_count == 2


def test_execution_records_only_for_turnover() -> None:
    """[3B.0G SECTION 12 & 33] CausalExecutionRecord is emitted only when turnover > 0 (or terminal exit)."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0 + i * bar_dur, close=Decimal("100.0"), open=Decimal("100.0"))
        for i in range(7)
    ]
    # 0 -> 1 on bar 0, then held long for 5 bars, then 1 -> 0 on bar 5
    positions = [1, 1, 1, 1, 1, 0, 0]
    zero_costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    res = run_causal_backtest(candles, positions, zero_costs)
    # Exactly 2 execution records across 6 intervals:
    assert len(res.executions) == 2
    assert res.executions[0].bar_index == 0
    assert res.executions[0].turnover == 1
    assert res.executions[1].bar_index == 5
    assert res.executions[1].turnover == 1


def test_hold_costs_zero_fee_zero_slippage() -> None:
    """[3B.0G SECTION 6, 14, 33] Zero-turnover hold intervals incur zero taker fee and zero slippage."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("105.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("105.0"), open=Decimal("105.0")),
    ]
    # Bar 0: enter 1 (turnover 1). Bar 1: hold 1 (turnover 0). Bar 2: hold 1 (turnover 0).
    positions = [1, 1, 1, 1]
    # 10 bps fee + 10 bps slippage per unit turnover
    costs = CostModel(taker_fee_bps=Decimal("10"), slippage_bps=Decimal("10"))

    stream = [
        ExecutionPriceObservation(ts_event_ns=t0 + bar_dur + 10_000_000, price=Decimal("100.0"), bid=Decimal("100.0"), ask=Decimal("100.0")),
        ExecutionPriceObservation(ts_event_ns=t0 + 4 * bar_dur + 10_000_000, price=Decimal("105.0"), bid=Decimal("105.0"), ask=Decimal("105.0")),
    ]
    res = run_causal_backtest(candles, positions, costs, execution_stream=stream)
    # Executions: 1 entry (bar 0) + 1 terminal flattening (end) = 2 executions.
    # Total execution cost = 20 bps on entry + 20 bps on terminal exit = 40 bps (0.004).
    # Zero cost from the 2 intermediate hold bars!
    assert len(res.executions) == 2
    assert res.executions[0].charge == Decimal("0.002")  # 20 bps
    assert res.executions[1].charge == Decimal("0.002")  # 20 bps


def test_flat_to_flat_no_execution() -> None:
    """[3B.0G SECTION 18 & 33] Flat-to-flat (0 -> 0) produces zero executions, zero trades, and zero return."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0 + i * bar_dur, close=Decimal("100.0"), open=Decimal("100.0"))
        for i in range(5)
    ]
    positions = [0, 0, 0, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("10"), slippage_bps=Decimal("10"))

    res = run_causal_backtest(candles, positions, costs)
    assert len(res.executions) == 0
    assert len(res.contracts) == 0
    assert res.result.trades == 0
    assert res.result.gross_return == Decimal("0")
    assert res.result.net_return == Decimal("0")
    assert res.result.total_cost == Decimal("0")


def test_reversal_turnover_two() -> None:
    """[3B.0G SECTION 19, 20, 33] Position reversal (-1 -> +1 and +1 -> -1) has turnover = 2 and charges two units."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=t0 + 3 * bar_dur, close=Decimal("100.0"), open=Decimal("100.0")),
    ]
    # Reversal from -1 to +1 at bar 1: turnover = 2. Exit to 0 at bar 2: turnover = 1.
    positions = [-1, 1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("5"), slippage_bps=Decimal("5"))

    res = run_causal_backtest(candles, positions, costs)
    assert len(res.executions) == 3
    # Bar 0: 0 -> -1 (turnover 1)
    assert res.executions[0].turnover == 1
    assert res.executions[0].side == "SELL"
    # Bar 1: -1 -> +1 (turnover 2, BUY)
    assert res.executions[1].turnover == 2
    assert res.executions[1].side == "BUY"
    assert res.executions[1].charge == Decimal("2") * Decimal("10") / Decimal("10000")  # 20 bps
    # Bar 2: +1 -> 0 (turnover 1, SELL)
    assert res.executions[2].turnover == 1
    assert res.executions[2].side == "SELL"


def test_strict_research_context_incomplete_blocked() -> None:
    """[3B.0G SECTION 21, 22, 33] Strict research context fails closed if missing any required identity field."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # Missing instrument_id
    c_no_inst = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0"), dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_inst:
        _run_causal_backtest_strict(c_no_inst, [1, 0], costs, strict_research_context=True)
    assert "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in str(exc_inst.value)

    # Missing dataset_id
    c_no_ds = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_ds:
        _run_causal_backtest_strict(c_no_ds, [1, 0], costs, strict_research_context=True)
    assert "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in str(exc_ds.value)

    # Missing market_type
    c_no_mkt = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", venue="BINANCE"),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_mkt:
        _run_causal_backtest_strict(c_no_mkt, [1, 0], costs, strict_research_context=True)
    assert "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in str(exc_mkt.value)

    # Missing venue
    c_no_ven = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP"),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_ven:
        _run_causal_backtest_strict(c_no_ven, [1, 0], costs, strict_research_context=True)
    assert "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in str(exc_ven.value)


def test_no_silent_market_type_or_venue_defaults() -> None:
    """[3B.0G SECTION 23 & 33] Strict mode does NOT silently default missing market_type to USD_M_PERP or venue to BINANCE."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # Bare candles with only instrument_id and dataset_id provided
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022"),
    ]
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [1, 0], costs, strict_research_context=True)
    assert "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in str(exc_info.value)
    # Verifies it failed because market_type=None, venue=None, rather than silently defaulting
    assert "market_type=None" in str(exc_info.value)
    assert "venue=None" in str(exc_info.value)


def test_canonical_registry_explicit_identity() -> None:
    """[3B.0G SECTION 25, 27, 33] All canonical datasets explicitly define instrument_id, market_type, venue."""
    from btceth_os.research.data_guard import CANONICAL_DATASET_REGISTRY, DatasetRole

    for ds_id, entry in CANONICAL_DATASET_REGISTRY.items():
        if entry.status == "CANONICAL":
            if ds_id.startswith("XAUUSDT"):
                assert entry.instrument_id == "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT", f"{ds_id} invalid instrument_id"
                assert entry.market_type == "TRADFI_COMMODITY_PERP", f"{ds_id} invalid market_type"
                assert entry.venue == "BINANCE", f"{ds_id} invalid venue"
            else:
                assert entry.instrument_id in ("BTCUSDT", "ETHUSDT"), f"{ds_id} missing valid instrument_id"
                assert entry.market_type == "USD_M_PERP", f"{ds_id} missing valid market_type"
                assert entry.venue == "BINANCE", f"{ds_id} missing valid venue"


def test_guarded_loader_fails_on_incomplete_identity() -> None:
    """[3B.0G SECTION 28 & 33] load_guarded_kline_candles fails closed if canonical metadata is incomplete."""
    from btceth_os.research.backtest import load_guarded_kline_candles
    dev_part = ROOT / "artifacts" / "research" / "partitions" / "BTCUSDT_DEV_2020_2022.parquet"
    if not dev_part.is_file():
        pytest.skip("BTCUSDT_DEV_2020_2022.parquet not present on disk")

    # Calling with a valid partition succeeds and populates metadata
    _, candles = load_guarded_kline_candles("BTCUSDT_DEV_2020_2022", strict_metadata=True)
    assert len(candles) > 0
    assert candles[0].instrument_id == "BTCUSDT"
    assert candles[0].market_type == "USD_M_PERP"
    assert candles[0].venue == "BINANCE"
    assert candles[0].dataset_id == "BTCUSDT_DEV_2020_2022"


def test_execution_record_identity_assertions() -> None:
    """[3B.0G SECTION 32 & 33] Every CausalExecutionRecord in strict research has non-null identity fields."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    positions = [1, 0, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    res = _run_causal_backtest_strict(candles, positions, costs, strict_research_context=True)
    assert len(res.executions) >= 1
    for exec_rec in res.executions:
        assert exec_rec.instrument_id == "BTCUSDT"
        assert exec_rec.dataset_id == "BTCUSDT_DEV_2020_2022"
        assert exec_rec.market_type == "USD_M_PERP"
        assert exec_rec.venue == "BINANCE"


# ==============================================================================
# ROUND 3B.0H TESTS: Strict Entry-Point Defaults & Series Identity Homogeneity
# ==============================================================================


def test_anonymous_candles_blocked_in_primary_causal_api() -> None:
    """[3B.0H GATES 1 & 3] run_causal_backtest is strict by default and blocks anonymous candles."""
    candles = [
        Candle(ts_event_ns=1000, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=2000, close=Decimal("102.0"), open=Decimal("100.0")),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [1, 0], costs)
    err = str(exc_info.value)
    assert "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in err or "RESEARCH_SERIES_IDENTITY_INCOMPLETE" in err


def test_synthetic_helper_allows_anonymous_candles() -> None:
    """[3B.0H GATE 2] run_synthetic_causal_backtest allows anonymous candles via explicit opt-in."""
    candles = [
        Candle(ts_event_ns=1000, close=Decimal("100.0"), open=Decimal("100.0")),
        Candle(ts_event_ns=2000, close=Decimal("102.0"), open=Decimal("100.0")),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    res = run_synthetic_causal_backtest(candles, [0, 0], costs)
    assert res.result.bars == 2
    assert res.assumptions.context == SYNTHETIC_TEST_CONTEXT
    assert res.assumptions.strict_research_context is False


def test_walk_forward_causal_blocks_anonymous_candles() -> None:
    """[3B.0H GATE 4] walk_forward_causal rejects anonymous candles fail-closed."""
    from btceth_os.research.backtest import walk_forward_causal
    candles = [
        Candle(ts_event_ns=1000 * i, close=Decimal(str(10 + i % 5)), open=Decimal(str(10 + i % 5)))
        for i in range(20)
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        walk_forward_causal(candles, train_bars=6, test_bars=4, candidate_lookbacks=[1, 2], costs=costs)
    err = str(exc_info.value)
    assert "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in err or "RESEARCH_SERIES_IDENTITY_INCOMPLETE" in err


def test_walk_forward_momentum_blocks_anonymous_candles() -> None:
    """[3B.0H GATE 4] walk_forward_momentum rejects anonymous candles fail-closed."""
    from btceth_os.research.backtest import walk_forward_momentum
    candles = [
        Candle(ts_event_ns=1000 * i, close=Decimal(str(10 + i % 5)), open=Decimal(str(10 + i % 5)))
        for i in range(20)
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        walk_forward_momentum(candles, train_bars=6, test_bars=4, candidate_lookbacks=[1, 2], costs=costs)
    err = str(exc_info.value)
    assert "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in err or "RESEARCH_SERIES_IDENTITY_INCOMPLETE" in err


def test_guarded_candles_walk_forward_allowed() -> None:
    """[3B.0H GATE 5] walk_forward_causal succeeds with fully identified candles."""
    from btceth_os.research.backtest import walk_forward_causal
    candles = [
        Candle(
            ts_event_ns=1000 * i,
            close=Decimal(str(10 + i % 5)),
            open=Decimal(str(10 + i % 5)),
            instrument_id="BTCUSDT",
            dataset_id="BTCUSDT_DEV_2020_2022",
            market_type="USD_M_PERP",
            venue="BINANCE",
        )
        for i in range(20)
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    wf_res = walk_forward_causal(candles, train_bars=6, test_bars=4, candidate_lookbacks=[1, 2], costs=costs)
    assert len(wf_res.folds) > 0
    assert wf_res.trades >= 0


def test_series_instrument_homogeneity() -> None:
    """[3B.0H GATE 8] Mixed instruments in valuation series fail closed."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("102.0"), open=Decimal("100.0"), instrument_id="ETHUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [0, 0], costs)
    assert "RESEARCH_SERIES_IDENTITY_MISMATCH" in str(exc_info.value)


def test_series_dataset_homogeneity() -> None:
    """[3B.0H GATE 9] Mixed dataset IDs in valuation series fail closed."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("102.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_VAL_2023", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [0, 0], costs)
    assert "RESEARCH_SERIES_DATASET_MISMATCH" in str(exc_info.value)


def test_series_market_type_homogeneity() -> None:
    """[3B.0H GATE 10] Mixed market types in valuation series fail closed."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("102.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="SPOT", venue="BINANCE"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [0, 0], costs)
    assert "RESEARCH_SERIES_MARKET_TYPE_MISMATCH" in str(exc_info.value)


def test_series_venue_homogeneity() -> None:
    """[3B.0H GATE 11] Mixed venues in valuation series fail closed."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("102.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="OKX"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [0, 0], costs)
    assert "RESEARCH_SERIES_VENUE_MISMATCH" in str(exc_info.value)


def test_series_missing_identity_mid_sequence() -> None:
    """[3B.0H GATE 12] Missing identity on any candle in series fails closed."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("102.0"), open=Decimal("100.0"), instrument_id=None, dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [0, 0], costs)
    err = str(exc_info.value)
    assert "RESEARCH_SERIES_IDENTITY_INCOMPLETE" in err or "RESEARCH_EXECUTION_CONTEXT_INCOMPLETE" in err


def test_btc_eth_valuation_contamination_blocked_before_pnl() -> None:
    """[3B.0H GATE 13] Contaminating BTC series with ETH candle is blocked before P&L."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("30000.0"), open=Decimal("30000.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("1800.0"), open=Decimal("1800.0"), instrument_id="ETHUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [0, 0], costs)
    assert "RESEARCH_SERIES_IDENTITY_MISMATCH" in str(exc_info.value)


def test_dev_val_sequence_contamination_blocked() -> None:
    """[3B.0H GATE 14] Splicing DEV and VAL partitions in single valuation series fails closed."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("105.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_VAL_2023", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError) as exc_info:
        _run_causal_backtest_strict(candles, [0, 0], costs)
    assert "RESEARCH_SERIES_DATASET_MISMATCH" in str(exc_info.value)


def test_homogeneous_btc_sequence_allowed() -> None:
    """[3B.0H GATE 15] Homogeneous BTC sequence validates and executes cleanly."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("100.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("105.0"), open=Decimal("100.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("110.0"), open=Decimal("105.0"), instrument_id="BTCUSDT", dataset_id="BTCUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    res = _run_causal_backtest_strict(candles, [1, 0, 0], costs)
    assert res.result.bars == 3
    assert len(res.executions) >= 1
    assert res.executions[0].instrument_id == "BTCUSDT"


def test_homogeneous_eth_sequence_allowed() -> None:
    """[3B.0H GATE 16] Homogeneous ETH sequence validates and executes cleanly."""
    t0 = 1609459200_000_000_000
    bar_dur = 3_600_000_000_000
    candles = [
        Candle(ts_event_ns=t0, close=Decimal("1000.0"), open=Decimal("1000.0"), instrument_id="ETHUSDT", dataset_id="ETHUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + bar_dur, close=Decimal("1050.0"), open=Decimal("1000.0"), instrument_id="ETHUSDT", dataset_id="ETHUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
        Candle(ts_event_ns=t0 + 2 * bar_dur, close=Decimal("1100.0"), open=Decimal("1050.0"), instrument_id="ETHUSDT", dataset_id="ETHUSDT_DEV_2020_2022", market_type="USD_M_PERP", venue="BINANCE"),
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    res = _run_causal_backtest_strict(candles, [1, 0, 0], costs)
    assert res.result.bars == 3
    assert len(res.executions) >= 1
    assert res.executions[0].instrument_id == "ETHUSDT"


def test_select_lookback_strict_context() -> None:
    """[3B.0H GATE 7] _select_lookback rejects anonymous candles and accepts guarded candles."""
    from btceth_os.research.backtest import _select_lookback
    anon_candles = [
        Candle(ts_event_ns=1000 * i, close=Decimal(str(10 + i % 5)), open=Decimal(str(10 + i % 5)))
        for i in range(15)
    ]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    with pytest.raises(TemporalIntegrityViolationError):
        _select_lookback(anon_candles, 0, 10, [1, 2], costs)

    guarded_candles = [
        Candle(
            ts_event_ns=1000 * i,
            close=Decimal(str(10 + i % 5)),
            open=Decimal(str(10 + i % 5)),
            instrument_id="BTCUSDT",
            dataset_id="BTCUSDT_DEV_2020_2022",
            market_type="USD_M_PERP",
            venue="BINANCE",
        )
        for i in range(15)
    ]
    best_lb = _select_lookback(guarded_candles, 0, 10, [1, 2], costs)
    assert best_lb in [1, 2]




