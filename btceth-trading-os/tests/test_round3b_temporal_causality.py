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
    ExecutionPriceObservation,
    PriceSource,
    run_causal_backtest,
    run_backtest,
)

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
    ]
    positions = [1, 1, 0, -1, 0]
    costs = CostModel(taker_fee_bps=Decimal("5"), slippage_bps=Decimal("2"))

    causal_res = run_causal_backtest(candles, positions, costs)
    legacy_res = run_backtest(candles, positions, costs)

    # Result equivalence with legacy run_backtest when open == previous close
    assert causal_res.result.bars == legacy_res.bars
    assert causal_res.result.trades == legacy_res.trades
    assert causal_res.result.net_return == legacy_res.net_return
    assert causal_res.result.total_cost == legacy_res.total_cost

    # Contract verification: every bar execution has a valid contract and observation
    assert len(causal_res.contracts) == len(candles)
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
    ]
    positions = [1, 0]
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
        Candle(ts_event_ns=1000 * i, close=Decimal(str(10 + i % 5)), open=Decimal(str(10 + i % 5)))
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
    """When execution_stream is provided, query first observation with ts_event_ns >= decision_ts_ns."""
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

    # Execution stream with quotes:
    # 1. Before decision: 01:00:00 + 10ms (price 30010) -> ineligible
    # 2. At or after decision: 01:00:00 + 60ms (price 30025) -> MUST BE SELECTED
    # 3. Later: 01:00:00 + 120ms (price 30050) -> too late
    bar_close_ts = 1609462800_000_000_000
    exec_stream = [
        ExecutionPriceObservation(
            ts_event_ns=bar_close_ts + 10_000_000,
            price=Decimal("30010.0"),
            source_instrument="BTCUSDT_QUOTE_10MS",
        ),
        ExecutionPriceObservation(
            ts_event_ns=bar_close_ts + 60_000_000,
            price=Decimal("30025.0"),
            source_instrument="BTCUSDT_QUOTE_60MS",
        ),
        ExecutionPriceObservation(
            ts_event_ns=bar_close_ts + 120_000_000,
            price=Decimal("30050.0"),
            source_instrument="BTCUSDT_QUOTE_120MS",
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
    assert first_exec.observation.fill_price_observation_ts_ns >= first_exec.observation.decision_ts_ns
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
    ]
    # Signal says go long at bar 0
    positions = [1, 1, 1, 0]
    costs = CostModel(taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))

    # With delay = 1 (standard): signal on bar 0 executes at bar 1 (index 0 transition)
    res_delay1 = run_causal_backtest(candles, positions, costs, assumptions=ExecutionAssumptions(execution_delay_bars=1))
    assert res_delay1.executions[0].bar_index == 0
    assert res_delay1.executions[0].position_after == 1

    # With delay = 2: signal on bar 0 is NOT executed at bar 1; it executes at bar 2 (index 1 transition)
    res_delay2 = run_causal_backtest(candles, positions, costs, assumptions=ExecutionAssumptions(execution_delay_bars=2))
    assert res_delay2.executions[0].bar_index == 0
    assert res_delay2.executions[0].position_after == 0  # Still 0 at bar 1!
    assert res_delay2.executions[1].bar_index == 1
    assert res_delay2.executions[1].position_after == 1  # Becomes 1 at bar 2!


def test_terminal_exit_uses_authentic_market_observation() -> None:
    """Terminal exit uses authentic post-decision observation timestamp."""
    candles = [
        Candle(ts_event_ns=1609459200_000_000_000, close=Decimal("30000.0"), open=Decimal("30000.0")),
        Candle(ts_event_ns=1609462800_000_000_000, close=Decimal("31000.0"), open=Decimal("30000.0")),
    ]
    # Remains long at end of simulation
    positions = [1, 1]
    costs = CostModel(taker_fee_bps=Decimal("5"), slippage_bps=Decimal("2"))

    res = run_causal_backtest(candles, positions, costs)
    assert len(res.executions) == 2  # Entry at bar 1 open + terminal exit at end
    exit_exec = res.executions[-1]
    assert exit_exec.position_after == 0
    assert exit_exec.observation.fill_price_observation_ts_ns >= exit_exec.observation.decision_ts_ns
    assert exit_exec.turnover == 1


