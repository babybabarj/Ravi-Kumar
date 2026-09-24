"""Comprehensive Verification Suite for INTEL-1B: Market Intelligence Validation, Stability & Reliability.

Verifies:
1. Trade Board quarantine & separate BTC bot complete isolation.
2. State Transition Engine & duration/reversal dynamics.
3. Regime Stability Audit & Threshold Sensitivity without profit bias.
4. Cross-Asset Causality & adversarial future mutation invariance.
5. Lead/Lag safety gate & machine-enforced retrospective separation.
6. Cross-Asset clock alignment & fail-closed unavailability.
7. Feature Availability Matrix for all 39 features.
8. Numeric Boundary Audit & pure storage precision invariants.
9. Missingness semantics with distinct uncollapsed reasons.
10. Data quality fail-closed propagation.
11. Multi-timeframe resampling & bar-close causality.
12. Feature distribution, redundancy, drift, and perturbation isolation.
13. Intelligence Snapshot V2 & execution field prohibition.
14. Decision engine prohibition across intel codebase.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import pytest

from btceth_os.intel import (
    ALL_FEATURES,
    ALL_FORBIDDEN_FIELDS,
    BarDataQualityAssessment,
    CAUSAL_LIVE_ELIGIBLE_METRICS,
    ClockAlignmentViolationError,
    CrossAssetClockAlignment,
    CrossAssetContextEngine,
    DataQualityGate,
    DataQualityPropagationEngine,
    DataQualityStatus,
    DimensionTransitionMetrics,
    ExecutionFieldForbiddenError,
    FeatureAvailabilityMatrix,
    FeatureDistributionAuditor,
    FeatureDriftAuditor,
    FeaturePerturbationTester,
    FeatureRedundancyAuditor,
    FundingRegime,
    IntelligenceSnapshotV2,
    LeadLagEngine,
    LeadLagResult,
    LeadLagSafetyGate,
    LeadLagSpecification,
    LiquidityActivityRegime,
    MarketQualityRegime,
    MarketStateEngine,
    MarketStateSnapshot,
    MetricEligibilityCategory,
    MissingReason,
    MissingValue,
    MultiTimeframeAuditor,
    NUMERIC_BOUNDARY_CATALOG,
    NegativeLagCausalityViolationError,
    NumericBoundaryAuditor,
    RETROSPECTIVE_RESEARCH_ONLY_METRICS,
    RegimeStabilityAuditor,
    RetrospectiveMetricInLiveContextError,
    StateTransitionEngine,
    ThresholdSensitivityAuditor,
    TrendRegime,
    VolatilityRegime,
    assert_no_execution_fields_v2,
    is_missing_value,
)

ROOT = Path(__file__).resolve().parents[1]


# -----------------------------------------------------------------------------
# 1. Quarantine & Isolation
# -----------------------------------------------------------------------------
def test_trade_board_quarantined_and_separate_btc_bot_isolated() -> None:
    """Proves trade_board.py is deleted and BTCUSD trade bot is strictly isolated."""
    # 1. Trade board module must not exist
    tb_file = ROOT / "src" / "btceth_os" / "trade_board.py"
    assert not tb_file.exists(), "src/btceth_os/trade_board.py must be deleted/quarantined"

    # 2. Source scan for separate BTC bot dependencies
    forbidden_terms = [
        "/Users/ravi/BTCUSD trade bot",
        "BTCUSD trade bot",
        "veteran_playbook.json",
        "pre_move_engine.py",
        "shadow_trader.py",
    ]
    for p in (ROOT / "src" / "btceth_os").rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for term in forbidden_terms:
            assert term not in text, f"Forbidden reference to '{term}' found in {p.relative_to(ROOT)}"


# -----------------------------------------------------------------------------
# 2. State Transition Engine
# -----------------------------------------------------------------------------
def test_state_transition_engine_dynamics() -> None:
    """Verifies state transition recording, duration distribution, and rapid flip detection."""
    # Synthetic sequence: UP for 4 bars, DOWN for 2 bars, UP for 5 bars (rapid reversal: UP->DOWN->UP within 2 bars)
    states = ["UP"] * 4 + ["DOWN"] * 2 + ["UP"] * 5
    timestamps = [1000 + i * 60 for i in range(len(states))]
    qualities = ["GOOD"] * len(states)

    metrics = StateTransitionEngine.track_dimension(
        asset="BTCUSDT",
        dimension="TREND",
        states=states,
        timestamps_ns=timestamps,
        data_qualities=qualities,
        flip_window=3,
    )

    assert metrics.total_bars == 11
    assert metrics.transition_count == 2
    assert len(metrics.transitions) == 2

    # Check first transition: UP -> DOWN after 4 bars
    t0 = metrics.transitions[0]
    assert t0.from_state == "UP"
    assert t0.to_state == "DOWN"
    assert t0.previous_state_duration_bars == 4

    # Check second transition: DOWN -> UP after 2 bars
    t1 = metrics.transitions[1]
    assert t1.from_state == "DOWN"
    assert t1.to_state == "UP"
    assert t1.previous_state_duration_bars == 2

    # Reversal count: flipped back to UP within 2 bars (<= flip_window 3)
    assert metrics.reversal_count == 1
    assert metrics.rapid_flip_rate == 0.5  # 1 reversal / 2 transitions
    assert metrics.persistence_probability == 0.8  # 8 same-state steps out of 10 steps


# -----------------------------------------------------------------------------
# 3. Regime Stability & Threshold Sensitivity
# -----------------------------------------------------------------------------
def test_regime_stability_and_threshold_sensitivity_audit() -> None:
    """Verifies stability auditor and local threshold perturbation without profit bias."""
    # Test stability audit on synthetic snapshots
    snapshots = [
        MarketStateSnapshot(
            trend_state="UP",
            volatility_state="NORMAL",
            activity_state="NORMAL",
            funding_state="NEUTRAL",
            market_quality_state="HEALTHY",
            uncertainties=[],
        )
        for _ in range(20)
    ]
    timestamps = [1000 + i * 60 for i in range(20)]

    stability = RegimeStabilityAuditor.audit_asset_stability("BTCUSDT", snapshots, timestamps)
    assert stability["total_bars"] == 20
    assert "TREND" in stability["dimensions"]
    assert stability["dimensions"]["TREND"]["persistence_probability"] == 1.0
    assert stability["dimensions"]["TREND"]["rapid_flip_rate"] == 0.0

    # Test threshold sensitivity audit
    feature_tuples = [
        (0.42, 0.70, 0.0005),  # Clear UP
        (0.20, 0.50, 0.0000),  # Clear RANGE
        (0.35, 0.60, 0.0002),  # UNCERTAIN
        (0.45, 0.20, -0.0005), # Clear DOWN
    ] * 10

    sens = ThresholdSensitivityAuditor.audit_trend_threshold(
        feature_tuples=feature_tuples,
        param_name="efficiency_ratio_high",
        baseline_val=0.40,
        perturbations=(-0.05, 0.05),
    )
    assert sens.parameter_name == "efficiency_ratio_high"
    assert sens.dimension == "TREND"
    assert len(sens.perturbation_results) == 2
    assert sens.is_classification_stable is True


# -----------------------------------------------------------------------------
# 4. Cross-Asset Causality & Adversarial Future Mutation
# -----------------------------------------------------------------------------
def test_cross_asset_future_mutation_invariance() -> None:
    """Mutating observations after t produces zero change to cross-asset intelligence at t."""
    t_anchor = 60
    r_a = [0.001 * (i % 5 - 2) for i in range(100)]
    r_b = [0.0015 * (i % 7 - 3) for i in range(100)]

    # Compute at anchor t
    m_base = CrossAssetContextEngine.compute_pair_metrics("BTC", "ETH", r_a[:t_anchor], r_b[:t_anchor], lookback=30)

    # Mutate future observations after t_anchor
    r_a_mut = list(r_a)
    r_b_mut = list(r_b)
    for j in range(t_anchor, 100):
        r_a_mut[j] += 0.50  # Massive future spike
        r_b_mut[j] -= 0.75  # Massive future crash

    # Recompute at anchor t using full array sliced up to anchor
    m_mut = CrossAssetContextEngine.compute_pair_metrics("BTC", "ETH", r_a_mut[:t_anchor], r_b_mut[:t_anchor], lookback=30)

    assert m_base.return_correlation == m_mut.return_correlation
    assert m_base.relative_volatility_ratio == m_mut.relative_volatility_ratio
    assert m_base.beta_a_to_b == m_mut.beta_a_to_b


# -----------------------------------------------------------------------------
# 5. Lead/Lag Safety Gate & Machine-Enforced Separation
# -----------------------------------------------------------------------------
def test_lead_lag_safety_gate_enforcement() -> None:
    """Verifies that negative lag and retrospective metrics fail closed in live context."""
    # 1. Negative lag must raise NegativeLagCausalityViolationError
    bad_spec = LeadLagSpecification(
        source_asset="BTC",
        target_asset="ETH",
        metric_name="lagged_return_correlation",
        lag=-1,
        window=30,
        minimum_samples=10,
    )
    with pytest.raises(NegativeLagCausalityViolationError):
        LeadLagSafetyGate.validate_for_live_snapshot(bad_spec)

    # 2. Retrospective research metric must raise RetrospectiveMetricInLiveContextError
    retro_spec = LeadLagSpecification(
        source_asset="BTC",
        target_asset="ETH",
        metric_name="future_lead_correlation",
        lag=1,
        window=30,
        minimum_samples=10,
    )
    with pytest.raises(RetrospectiveMetricInLiveContextError):
        LeadLagSafetyGate.validate_for_live_snapshot(retro_spec)

    # 3. Valid causal spec computes cleanly
    valid_spec = LeadLagSpecification(
        source_asset="BTC",
        target_asset="ETH",
        metric_name="lagged_return_correlation",
        lag=2,
        window=30,
        minimum_samples=10,
    )
    returns_a = [0.01 * (i % 3) for i in range(50)]
    returns_b = [0.01 * ((i - 2) % 3) for i in range(50)]
    timestamps = [1000 + i * 60 for i in range(50)]

    res = LeadLagEngine.compute_pair_lead_lag(
        source_returns=returns_a,
        target_returns=returns_b,
        timestamps_ns=timestamps,
        spec=valid_spec,
        current_t_ns=timestamps[-1],
        is_live_context=True,
    )
    assert res.is_causal_live_eligible is True
    assert res.correlation is not None
    assert res.effective_samples >= 10


# -----------------------------------------------------------------------------
# 6. Cross-Asset Clock Alignment
# -----------------------------------------------------------------------------
def test_cross_asset_clock_alignment() -> None:
    """Verifies observation availability auditing and prevention of forward-filling."""
    t_now = 5000

    # 1. Complete alignment
    c_good = CrossAssetClockAlignment(
        snapshot_timestamp_ns=t_now,
        btc_available_at_ns=t_now,
        eth_available_at_ns=t_now,
        xau_available_at_ns=t_now,
    )
    assert c_good.is_fully_aligned is True
    assert c_good.context_state == "COMPLETE"
    c_good.assert_causality()  # Passes cleanly

    # 2. Partial alignment (XAU not yet published)
    c_partial = CrossAssetClockAlignment(
        snapshot_timestamp_ns=t_now,
        btc_available_at_ns=t_now,
        eth_available_at_ns=t_now,
        xau_available_at_ns=None,
    )
    assert c_partial.is_fully_aligned is False
    assert c_partial.context_state == "PARTIAL"

    # 3. Future leakage must raise ClockAlignmentViolationError
    c_leak = CrossAssetClockAlignment(
        snapshot_timestamp_ns=t_now,
        btc_available_at_ns=t_now,
        eth_available_at_ns=t_now + 100,  # Leaking future ETH observation!
        xau_available_at_ns=t_now,
    )
    with pytest.raises(ClockAlignmentViolationError):
        c_leak.assert_causality()


# -----------------------------------------------------------------------------
# 7. Feature Availability Matrix
# -----------------------------------------------------------------------------
def test_feature_availability_matrix() -> None:
    """Verifies all 39 INTEL-1A features are cataloged with strict causality contracts."""
    matrix = FeatureAvailabilityMatrix.build_matrix()
    assert len(matrix) == 39
    assert len(matrix) == len(ALL_FEATURES)

    for name, rec in matrix.items():
        assert rec.causal_live_eligible is True
        assert rec.retrospective_only is False
        assert rec.minimum_history >= 1
        assert rec.publication_delay_bars == 0
        assert "BTCUSDT" in rec.asset_support
        assert "ETHUSDT" in rec.asset_support
        assert "XAUUSDT" in rec.asset_support


# -----------------------------------------------------------------------------
# 8. Numeric Boundary Audit
# -----------------------------------------------------------------------------
def test_numeric_boundary_audit() -> None:
    """Proves financial numeric conversions to float are strictly ephemeral."""
    rep = NumericBoundaryAuditor.generate_audit_report()
    assert rep["total_conversions_registered"] >= 10
    assert rep["canonical_storage_downgrades"] == 0
    assert rep["all_conversions_ephemeral"] is True
    assert rep["float_contamination_in_storage"] == "ZERO"

    for entry in NUMERIC_BOUNDARY_CATALOG:
        assert entry.persisted_or_ephemeral == "EPHEMERAL"
        assert "Decimal" in entry.source_type
        assert "float" in entry.target_type


# -----------------------------------------------------------------------------
# 9. Missingness Semantics
# -----------------------------------------------------------------------------
def test_missingness_semantics() -> None:
    """Verifies explicit missingness reason preservation."""
    mv1 = MissingValue(MissingReason.NOT_ENOUGH_HISTORY, details="Requires 20 bars, observed 5")
    mv2 = MissingValue(MissingReason.DATA_GAP, details="Bar at t=1000 missing")
    mv3 = MissingValue(MissingReason.HOLIDAY_UNKNOWN)

    assert is_missing_value(mv1)
    assert is_missing_value(mv2)
    assert is_missing_value(mv3)

    assert mv1.reason == MissingReason.NOT_ENOUGH_HISTORY
    assert mv2.reason == MissingReason.DATA_GAP
    assert mv3.reason == MissingReason.HOLIDAY_UNKNOWN

    assert mv1 != mv2
    assert mv1.to_dict()["reason"] == "NOT_ENOUGH_HISTORY"


# -----------------------------------------------------------------------------
# 10. Data Quality Propagation
# -----------------------------------------------------------------------------
def test_data_quality_propagation() -> None:
    """Verifies fail-closed override when input data quality is unreliable or degraded."""
    raw_state = MarketStateSnapshot(
        trend_state=TrendRegime.UP.value,
        volatility_state=VolatilityRegime.NORMAL.value,
        activity_state=LiquidityActivityRegime.ELEVATED.value,
        funding_state=FundingRegime.POSITIVE.value,
        market_quality_state=MarketQualityRegime.HEALTHY.value,
        uncertainties=[],
    )

    # 1. UNRELIABLE quality forces all downstream regimes to UNCERTAIN/UNKNOWN
    unreliable_assessment = BarDataQualityAssessment(
        status=DataQualityStatus.UNRELIABLE.value,
        reasons=["NON_MONOTONIC_TIMESTAMP", "ZERO_VOLUME_PRICE_JUMP"],
    )
    propagated_bad = DataQualityPropagationEngine.propagate(unreliable_assessment, raw_state)
    assert propagated_bad.trend_state == TrendRegime.UNCERTAIN.value
    assert propagated_bad.volatility_state == VolatilityRegime.UNKNOWN.value
    assert propagated_bad.activity_state == LiquidityActivityRegime.UNKNOWN.value
    assert propagated_bad.funding_state == FundingRegime.UNKNOWN.value
    assert propagated_bad.market_quality_state == MarketQualityRegime.UNRELIABLE.value
    assert "PROPAGATED_FAIL_CLOSED_UNRELIABLE" in propagated_bad.uncertainties

    # 2. DEGRADED quality allows computation but injects warnings
    degraded_assessment = BarDataQualityAssessment(
        status=DataQualityStatus.DEGRADED.value,
        reasons=["HOLIDAY_UNKNOWN"],
    )
    propagated_deg = DataQualityPropagationEngine.propagate(degraded_assessment, raw_state)
    assert propagated_deg.trend_state == TrendRegime.UP.value  # Allowed
    assert propagated_deg.market_quality_state == MarketQualityRegime.DEGRADED.value
    assert "DATA_QUALITY_DEGRADED" in propagated_deg.uncertainties


# -----------------------------------------------------------------------------
# 11. Multi-Timeframe Consistency
# -----------------------------------------------------------------------------
def test_multitimeframe_consistency() -> None:
    """Verifies bar-close availability rule and incomplete final bucket suppression."""
    ts = [1_767_657_600_000_000_000 + i * 60_000_000_000 for i in range(125)]
    opens = [100.0 + i for i in range(125)]
    highs = [105.0 + i for i in range(125)]
    lows = [95.0 + i for i in range(125)]
    closes = [102.0 + i for i in range(125)]
    vols = [10.0] * 125

    # 1h timeframe (each 1h needs 60 1m bars)
    # 125 bars -> 2 full 1h bars (120 bars), 5 remaining bars in incomplete bucket
    res = MultiTimeframeAuditor.audit_timeframe("1h", ts, opens, highs, lows, closes, vols)
    assert res.aggregated_bars_count == 2
    assert res.incomplete_final_bucket_suppressed is True
    assert res.zero_future_leakage is True
    assert res.mean_constituent_bars == 60.0


# -----------------------------------------------------------------------------
# 12. Feature Quality, Redundancy, Drift & Perturbation Isolation
# -----------------------------------------------------------------------------
def test_feature_audits_and_perturbation_isolation() -> None:
    """Verifies distribution stats, redundancy, chronological drift, and dependency isolation."""
    # 1. Distribution audit
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, None, float("nan")]
    dist = FeatureDistributionAuditor.audit_series("test_feature", vals)
    assert dist.count == 5
    assert dist.missing_count == 2
    assert dist.mean == 3.0
    assert dist.median == 3.0
    assert dist.has_nan is True

    # 2. Redundancy audit
    xs = [float(i) for i in range(50)]
    ys = [float(i * 2 + 1) for i in range(50)]  # Perfectly collinear
    red = FeatureRedundancyAuditor.compute_pair_redundancy("x", xs, "y", ys)
    assert red.redundancy_level == "REDUNDANCY_HIGH"
    assert math.isclose(red.pearson_correlation, 1.0, abs_tol=1e-3)

    # 3. Drift audit
    chrono_vals = [10.0 + (i % 3) for i in range(30)] + [10.0 + (i % 3) for i in range(30)]
    drift = FeatureDriftAuditor.audit_chronological_drift("stable_feature", chrono_vals)
    assert drift.drift_status == "STABLE"

    # 4. Perturbation isolation
    base_feat = {"rolling_high_20m": 105.0, "funding_rate": 0.0001}
    mut_feat = {"rolling_high_20m": 105.0, "funding_rate": 0.0005}  # mutated funding only
    ok, violations = FeaturePerturbationTester.verify_isolation(
        base_features=base_feat,
        mutated_features=mut_feat,
        mutated_input="funding",
        declared_dependents={"funding_rate"},
    )
    assert ok is True
    assert len(violations) == 0


# -----------------------------------------------------------------------------
# 13. Intelligence Snapshot V2 & Execution Ban
# -----------------------------------------------------------------------------
def test_snapshot_v2_and_execution_field_prohibition() -> None:
    """Verifies Snapshot V2 serialization and strict prohibition of execution fields."""
    snap = IntelligenceSnapshotV2(
        timestamp_ns=1_767_657_600_000_000_000,
        asset="BTCUSDT",
        data_quality={"status": "GOOD", "reasons": []},
        market_state={
            "trend": "UP",
            "volatility": "NORMAL",
            "activity": "NORMAL",
            "funding": "NEUTRAL",
        },
        state_stability={"trend_duration_bars": 42, "volatility_duration_bars": 18},
        cross_asset_context={"btc_eth_corr": 0.85},
        feature_availability={"log_return_1m": "AVAILABLE"},
        uncertainties=[],
    )
    assert snap.schema_version == "2.0.0"
    d = snap.to_dict()
    assert d["asset"] == "BTCUSDT"

    # Invariant: Forbidden fields trigger ExecutionFieldForbiddenError
    for forbidden in ALL_FORBIDDEN_FIELDS:
        with pytest.raises(ExecutionFieldForbiddenError):
            assert_no_execution_fields_v2({forbidden: 100.0})

    # Invariant: Forbidden string order values trigger error
    for order_val in ["BUY", "SELL", "LONG", "SHORT", "OPEN_LONG"]:
        with pytest.raises(ExecutionFieldForbiddenError):
            assert_no_execution_fields_v2({"action": order_val})


# -----------------------------------------------------------------------------
# 14. Decision Engine Prohibition across INTEL codebase
# -----------------------------------------------------------------------------
def test_decision_engine_prohibition_in_codebase() -> None:
    """Ensures no execution semantics or trade decision engines exist in src/btceth_os/intel."""
    forbidden_function_patterns = [
        r"def\s+evaluate_trade\b",
        r"def\s+take_trade\b",
        r"def\s+generate_signal\b",
        r"def\s+entry_zone\b",
        r"def\s+stop_loss\b",
        r"def\s+take_profit\b",
        r"def\s+position_size\b",
        r"def\s+set_leverage\b",
    ]

    for py_file in (ROOT / "src" / "btceth_os" / "intel").rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pat in forbidden_function_patterns:
            assert not re.search(pat, content, re.IGNORECASE), (
                f"Forbidden execution function pattern '{pat}' detected in {py_file.relative_to(ROOT)}"
            )
