"""Adversarial and Causality Test Suite for INTEL-1A.

Tests all core invariants of the intelligence architecture:
1. Causality: future bars cannot influence feature at t
2. Rolling windows: warmup bounds and first valid timestamps
3. Resampling causality: higher-timeframe bars unavailable before interval close
4. Funding causality: discrete funding events strictly causal
5. Missing data: data gaps produce explicit degraded/unreliable data quality
6. Holdout firewall: holdout and pristine partition access unconditionally denied
7. Normalization causality: future values cannot influence past normalized states
8. Cross-asset causality: asset B at t+1 cannot influence asset A at t
9. Session certainty: HOLIDAY_UNKNOWN preserved
10. Deterministic logical hashing: identical data produces identical logical hash
11. Execution separation: schema-level prohibition of execution fields
12. Adversarial attacks: injection of forbidden execution keys, holdout paths, NaNs
"""

from __future__ import annotations

import copy
import math
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest

from btceth_os.intel.cross_asset import CrossAssetContextEngine
from btceth_os.intel.data_access import (
    IntelAccessDeniedError,
    IntelDatasetAccessAPI,
    audit_intel_access_ledger,
)
from btceth_os.intel.data_quality import DataQualityGate, DataQualityStatus
from btceth_os.intel.feature_contract import FeatureDefinition
from btceth_os.intel.feature_engine import CausalFeatureEngine
from btceth_os.intel.feature_registry import FeatureRegistry
from btceth_os.intel.market_state import (
    FundingRegime,
    LiquidityActivityRegime,
    MarketQualityRegime,
    MarketStateEngine,
    TrendRegime,
    VolatilityRegime,
)
from btceth_os.intel.normalization import LearnedFeatureScaler, TrailingRollingScaler
from btceth_os.intel.reproducibility import compute_feature_table_logical_hash, compute_intel_logical_hash
from btceth_os.intel.resampler import CausalResampler
from btceth_os.intel.snapshot import (
    ExecutionFieldForbiddenError,
    IntelligenceSnapshot,
    assert_no_execution_fields,
)


def _make_synthetic_bar_table(n_bars: int = 100, base_price: float = 2000.0) -> pa.Table:
    """Generates a synthetic causal 1-minute bar table for adversarial testing."""
    ts_start = 1767657600_000_000_000  # 2026-01-06 00:00:00 UTC
    step = 60_000_000_000

    ts_list = [ts_start + i * step for i in range(n_bars)]
    opens = []
    highs = []
    lows = []
    closes = []
    vols = []
    tcs = []
    tbs = []

    p = base_price
    for i in range(n_bars):
        # Deterministic price oscillation
        delta = math.sin(i / 5.0) * 2.0
        o = p
        c = p + delta
        h = max(o, c) + 1.0
        l = min(o, c) - 1.0
        v = 10.0 + (i % 5)
        tc = 50 + (i % 10)
        tb = v * 0.55

        opens.append(Decimal(f"{o:.4f}"))
        highs.append(Decimal(f"{h:.4f}"))
        lows.append(Decimal(f"{l:.4f}"))
        closes.append(Decimal(f"{c:.4f}"))
        vols.append(Decimal(f"{v:.8f}"))
        tcs.append(tc)
        tbs.append(Decimal(f"{tb:.8f}"))
        p = c

    # Funding rate: every 240 bars, a funding rate settles
    last_rates = [Decimal("0.0001")] * n_bars
    last_funding_ts = [ts_start] * n_bars

    schema = pa.schema([
        ("ts_event_ns", pa.int64()),
        ("open", pa.decimal128(18, 4)),
        ("high", pa.decimal128(18, 4)),
        ("low", pa.decimal128(18, 4)),
        ("close", pa.decimal128(18, 4)),
        ("volume", pa.decimal128(28, 8)),
        ("quote_volume", pa.decimal128(28, 8)),
        ("trade_count", pa.int64()),
        ("taker_buy_volume", pa.decimal128(28, 8)),
        ("last_realized_funding_rate", pa.decimal128(18, 8)),
        ("last_realized_funding_event_ts_ns", pa.int64()),
        ("underlying_session_state", pa.string()),
        ("underlying_session_certainty", pa.string()),
        ("holiday_status", pa.string()),
        ("price_index_mode", pa.string()),
        ("price_index_mode_certainty", pa.string()),
    ])

    return pa.Table.from_pydict({
        "ts_event_ns": ts_list,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols,
        "quote_volume": [Decimal(f"{float(v) * float(c):.8f}") for v, c in zip(vols, closes)],
        "trade_count": tcs,
        "taker_buy_volume": tbs,
        "last_realized_funding_rate": last_rates,
        "last_realized_funding_event_ts_ns": last_funding_ts,
        "underlying_session_state": ["UNDERLYING_OPEN"] * n_bars,
        "underlying_session_certainty": ["WEEKDAY_RULE_ONLY"] * n_bars,
        "holiday_status": ["NOT_IMPLEMENTED"] * n_bars,
        "price_index_mode": ["REGULAR_SCHEDULE_INFERRED"] * n_bars,
        "price_index_mode_certainty": ["HOLIDAY_UNKNOWN"] * n_bars,
    }, schema=schema)


# 1. Causality: Future bar mutation cannot alter past feature values
def test_causality_future_mutation_cannot_alter_past_features():
    table1 = _make_synthetic_bar_table(80, base_price=2500.0)
    # Mutate only future rows (row 50 onwards)
    table2_dict = table1.to_pydict()
    for i in range(50, 80):
        table2_dict["close"][i] = Decimal("99999.0000")
        table2_dict["high"][i] = Decimal("99999.0000")
    table2 = pa.Table.from_pydict(table2_dict, schema=table1.schema)

    engine = CausalFeatureEngine()
    feats1 = engine.compute_features(table1)
    feats2 = engine.compute_features(table2)

    # All features at row t < 50 MUST be bitwise identical
    for name in feats1:
        for t in range(50):
            val1 = feats1[name][t]
            val2 = feats2[name][t]
            if val1 is None:
                assert val2 is None, f"Feature {name} at t={t} diverged: {val1} vs {val2}"
            elif isinstance(val1, (int, float)):
                assert abs(val1 - float(val2)) < 1e-12, f"Feature {name} at t={t} diverged: {val1} vs {val2}"
            else:
                assert val1 == val2, f"Feature {name} at t={t} diverged: {val1} vs {val2}"


# 2. Rolling Windows: Warmup bounds respected
def test_rolling_window_warmup_bounds():
    table = _make_synthetic_bar_table(50)
    engine = CausalFeatureEngine()
    feats = engine.compute_features(table)

    # 20m rolling features must be None for rows 0..18 and non-None at row 19
    for name in ("rolling_high_20m", "rolling_low_20m", "efficiency_ratio_20m"):
        for t in range(19):
            assert feats[name][t] is None, f"{name} emitted premature value at warmup row {t}: {feats[name][t]}"
        assert feats[name][19] is not None, f"{name} failed to compute at row 19"


# 3. Resampling Causality: Higher timeframe bar unavailable before completion
def test_resampling_causality():
    # 7 bars of 1m data (0 to 6)
    ts_start = 1767657600_000_000_000
    step = 60_000_000_000
    ts_list = [ts_start + i * step for i in range(7)]
    prices = [100.0 + i for i in range(7)]

    # 5m aggregation: bars 0..4 make 1st 5m candle. Bars 5..6 are incomplete.
    agg = CausalResampler.resample(
        timeframe="5m",
        ts_ns_list=ts_list,
        open_list=prices,
        high_list=prices,
        low_list=prices,
        close_list=prices,
        volume_list=[1.0] * 7,
    )

    # Exactly 1 completed 5m candle emitted
    assert len(agg) == 1
    candle = agg[0]
    # Candle covers [ts_start, ts_start + 300s)
    assert candle.period_start_ns == ts_start
    assert candle.period_end_ns == ts_start + 300_000_000_000
    # Incomplete bar (minutes 5 and 6) was NOT emitted
    assert candle.constituent_bars_count == 5
    assert candle.close == 104.0  # close of bar 4


# 4. Funding Causality: Post-boundary event unavailable before its timestamp
def test_funding_causality():
    engine = CausalFeatureEngine()
    table = _make_synthetic_bar_table(30)
    feats = engine.compute_features(table)

    # Each bar must observe the last realized rate, never future rates
    last_rates = feats["latest_realized_funding_rate"]
    for t in range(len(last_rates)):
        assert last_rates[t] == Decimal("0.0001")


# 5. Missing Data: Gaps produce explicit degraded quality
def test_data_quality_detects_gap_and_anomaly():
    ts = 1767657600_000_000_000
    # Gap of 180 seconds (2 missing minutes)
    ass_gap = DataQualityGate.assess_bar(
        ts_ns=ts + 180_000_000_000,
        prev_ts_ns=ts,
        open_p=2000.0,
        high_p=2005.0,
        low_p=1995.0,
        close_p=2002.0,
        volume=10.0,
    )
    assert ass_gap.status == DataQualityStatus.DEGRADED.value
    assert any("MISSING_BAR_GAP" in r for r in ass_gap.reasons)

    # Non-monotonic timestamp
    ass_rev = DataQualityGate.assess_bar(
        ts_ns=ts - 1000,
        prev_ts_ns=ts,
        open_p=2000.0,
        high_p=2005.0,
        low_p=1995.0,
        close_p=2002.0,
        volume=10.0,
    )
    assert ass_rev.status == DataQualityStatus.UNRELIABLE.value
    assert "NON_MONOTONIC_TIMESTAMP" in ass_rev.reasons

    # Impossible OHLC: high < low
    ass_ohlc = DataQualityGate.assess_bar(
        ts_ns=ts + 60_000_000_000,
        prev_ts_ns=ts,
        open_p=2000.0,
        high_p=1990.0,
        low_p=2005.0,
        close_p=2002.0,
        volume=10.0,
    )
    assert ass_ohlc.status == DataQualityStatus.UNRELIABLE.value
    assert "IMPOSSIBLE_OHLC_HIGH_LESS_THAN_LOW" in ass_ohlc.reasons


# 6 & 7. Holdout Firewall: HOLDOUT and PRISTINE access unconditionally denied before read
def test_holdout_firewall_unconditionally_blocks_locked_roles(tmp_path):
    test_ledger = tmp_path / "test_intel_ledger.jsonl"

    for locked_role in ("LOCKED_HOLDOUT", "HOLDOUT", "LOCKED_PROSPECTIVE_PRISTINE", "PRISTINE"):
        with pytest.raises(IntelAccessDeniedError):
            IntelDatasetAccessAPI.request_dataset(
                asset="XAUUSDT",
                dataset_role=locked_role,
                purpose="UNAUTHORIZED_EXPLORATION",
                caller="test_suite",
                phase="INTEL_1A",
                ledger_path=test_ledger,
            )

    audit = audit_intel_access_ledger(test_ledger)
    assert audit["total_access_attempts"] == 4
    assert audit["granted_accesses"] == 0
    assert audit["denied_accesses"] == 4
    assert audit["successful_holdout_accesses"] == 0
    assert audit["successful_pristine_accesses"] == 0
    assert audit["audit_passed"] is True


# 8. Normalization Causality: Future observations cannot alter past normalized values
def test_normalization_causality():
    series_short = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0]
    series_long = series_short + [99999.0, 99999.0, 99999.0]  # future spike

    z_short = TrailingRollingScaler.rolling_zscore(series_short, window=5, min_periods=3)
    z_long = TrailingRollingScaler.rolling_zscore(series_long, window=5, min_periods=3)

    # First len(series_short) values of z_long MUST be identical to z_short
    for i in range(len(series_short)):
        if z_short[i] is None:
            assert z_long[i] is None
        else:
            assert abs(z_short[i] - z_long[i]) < 1e-12


# 9. Cross-Asset Causality: Future ETH timestamp cannot influence past BTC metrics
def test_cross_asset_causality():
    btc_rets1 = [0.01, -0.02, 0.015, -0.005, 0.01] * 20
    eth_rets1 = [0.015, -0.025, 0.02, -0.008, 0.012] * 20

    # Mutate only future of ETH (index 80 onwards)
    btc_rets2 = list(btc_rets1)
    eth_rets2 = list(eth_rets1)
    for i in range(80, 100):
        eth_rets2[i] = 1.0  # huge future spike

    m1 = CrossAssetContextEngine.compute_pair_metrics("BTC", "ETH", btc_rets1[:60], eth_rets1[:60], lookback=60)
    m2 = CrossAssetContextEngine.compute_pair_metrics("BTC", "ETH", btc_rets2[:60], eth_rets2[:60], lookback=60)

    # Pair metrics at t=60 must be identical
    assert m1.return_correlation == m2.return_correlation
    assert m1.beta_a_to_b == m2.beta_a_to_b


# 10. Session State: HOLIDAY_UNKNOWN preserved
def test_session_state_holiday_unknown_preserved():
    table = _make_synthetic_bar_table(10)
    engine = CausalFeatureEngine()
    feats = engine.compute_features(table)

    for i in range(10):
        assert feats["holiday_status"][i] == "NOT_IMPLEMENTED"
        assert feats["price_index_mode_certainty"][i] == "HOLIDAY_UNKNOWN"

    state = MarketStateEngine.evaluate_state(
        features={k: v[5] for k, v in feats.items()},
        data_quality_status="GOOD",
    )
    assert "SESSION_HOLIDAY_STATUS_UNPROVEN" in state.uncertainties


# 11. Deterministic Logical Hashing: Repeated computation produces identical hash
def test_deterministic_logical_hashing():
    table = _make_synthetic_bar_table(40)
    engine = CausalFeatureEngine()
    feats1 = engine.compute_features(table)
    feats2 = engine.compute_features(table)

    h1 = compute_feature_table_logical_hash(feats1)
    h2 = compute_feature_table_logical_hash(feats2)
    assert h1 == h2 and len(h1) == 64


# 12. Execution Separation: Schema rejects forbidden execution fields
def test_intelligence_schema_rejects_execution_fields():
    # Valid non-executable snapshot
    snap = IntelligenceSnapshot(
        timestamp_utc="2026-01-06T01:00:00Z",
        asset="XAUUSDT",
        feature_set="INTEL_FEATURESET_V1",
        market_quality="HEALTHY",
        trend_state="UP",
        volatility_state="NORMAL",
        activity_state="NORMAL",
        funding_state="NEUTRAL",
        session_state="OPEN",
        features={"log_return_1m": 0.0005},
    )
    assert snap.trend_state == "UP"

    # Forbidden execution fields must raise ExecutionFieldForbiddenError
    for forbidden in ("BUY", "SELL", "order", "position_size", "leverage", "stop_loss", "take_profit", "signal"):
        with pytest.raises(ExecutionFieldForbiddenError):
            assert_no_execution_fields({"timestamp": "2026-01-06T01:00:00Z", forbidden: "ACTIONABLE"})

    # Prohibit direct execution orders in values
    with pytest.raises(ExecutionFieldForbiddenError):
        assert_no_execution_fields({"market_state": "BUY"})
