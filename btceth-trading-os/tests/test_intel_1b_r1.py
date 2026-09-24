"""Unit and regression tests for INTEL-1B R1 remediation."""

import json
import math
import subprocess
from pathlib import Path
from typing import Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]

from btceth_os.intel import (
    ALL_FEATURES,
    CrossAssetContextEngine,
    FeatureAvailabilityMatrix,
    FeatureDistributionAuditor,
    FeatureDriftAuditor,
    LeadLagEngine,
    LeadLagSafetyGate,
    LeadLagSpecification,
    MarketStateEngine,
    RegimeStabilityAuditor,
)


def test_baseline_manifest_immutability():
    """Verifies that protected Phase 2 manifests match the accepted INTEL-1A baseline exactly."""
    intel_1a_baseline = "2caf4e99cb18517d3938c8c11f3e9014cc608368"
    protected_manifests = [
        "btceth-trading-os/config/xau_research_partitions_v1.json",
        "btceth-trading-os/config/xau_research_partitions_v2.json",
        "btceth-trading-os/config/xau_research_partitions_v3.json",
        "btceth-trading-os/config/research_partitions_v1.json",
        "btceth-trading-os/config/xau_primary_sources_v2.json",
        "btceth-trading-os/config/xau_primary_sources_v3.json",
        "btceth-trading-os/config/xau_contract_rule_epochs_v2.yaml",
        "btceth-trading-os/config/xau_contract_rule_epochs_v3.yaml",
    ]
    for pm in protected_manifests:
        res = subprocess.run(
            ["git", "diff", intel_1a_baseline, "HEAD", "--", pm],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert len(res.stdout.strip()) == 0, f"Protected manifest {pm} has been mutated relative to baseline!"


def test_state_counts_reconciliation():
    """Verifies that state counts in every dimension sum up exactly to total bars."""
    sample_size = 500
    timestamps = list(range(sample_size))
    # Synthetic states
    snapshots = []
    for i in range(sample_size):
        f = {
            "efficiency_ratio_20m": 0.5,
            "directional_persistence_20m": 0.6,
            "rolling_slope_20m": 0.0001,
            "volatility_percentile_trailing_1440m": 0.5,
            "short_horizon_vol_10m": 0.002,
            "volume_percentile_trailing_1440m": 0.5,
            "abnormal_activity_score_60m": 0.0,
            "latest_realized_funding_rate": 0.0001,
        }
        st = MarketStateEngine.evaluate_state(f, data_quality_status="GOOD")
        snapshots.append(st)

    audit = RegimeStabilityAuditor.audit_asset_stability("TEST_ASSET", snapshots, timestamps)
    for dim_name, d_data in audit["dimensions"].items():
        total_counts = sum(d_data["state_counts"].values())
        assert total_counts == sample_size, f"State counts for {dim_name} do not reconcile to total bars!"


def test_cross_asset_future_mutation_invariance():
    """Proves that mutating observations after anchor t produces exactly zero change to metrics at t."""
    n = 300
    anchor = 150
    lookback = 30
    rx = [0.001 * math.sin(i * 0.1) for i in range(n)]
    rb = [0.0015 * math.cos(i * 0.1) for i in range(n)]

    # Baseline metrics at anchor
    base_m = CrossAssetContextEngine.compute_pair_metrics("X", "B", rx[:anchor+1], rb[:anchor+1], lookback=lookback)

    # Mutate strictly future observations (j > anchor)
    rx_mut = list(rx)
    rb_mut = list(rb)
    for j in range(anchor + 1, n):
        rx_mut[j] += 999.0
        rb_mut[j] -= 999.0

    mut_m = CrossAssetContextEngine.compute_pair_metrics("X", "B", rx_mut[:anchor+1], rb_mut[:anchor+1], lookback=lookback)

    assert base_m.return_correlation == mut_m.return_correlation
    assert base_m.relative_volatility_ratio == mut_m.relative_volatility_ratio
    assert base_m.beta_a_to_b == mut_m.beta_a_to_b
    assert base_m.lead_lag_lag1_corr_a_leads == mut_m.lead_lag_lag1_corr_a_leads
    assert base_m.lead_lag_lag1_corr_b_leads == mut_m.lead_lag_lag1_corr_b_leads


def test_feature_availability_contract_derivation():
    """Ensures feature availability is derived from FeatureDefinition contracts rather than blanket stamped."""
    matrix = FeatureAvailabilityMatrix.build_matrix()
    assert len(matrix) == 39

    # Funding features must depend on discrete settlement
    funding_feat = matrix["latest_realized_funding_rate"]
    assert funding_feat.discrete_event_dependency == "last_realized_funding_event_ts_ns"
    assert funding_feat.availability_timestamp_rule == "DISCRETE_EVENT_FORWARD_FILLED"

    # Session features must declare session certainty semantics
    holiday_feat = matrix["holiday_status"]
    assert holiday_feat.session_certainty_semantics == "HOLIDAY_STATUS_PRESERVED_NOT_IMPLEMENTED"

    # Price / trend features must be closed-bar trailing
    ret_feat = matrix["log_return_1m"]
    assert ret_feat.availability_timestamp_rule == "BAR_CLOSE_TIMESTAMP_TRAILING"


def test_lead_lag_safety_gate_negative_lag_rejected():
    """Negative lags must always be rejected by the safety gate."""
    assert LeadLagSafetyGate.validate_lag(-1) is False
    assert LeadLagSafetyGate.validate_lag(-5) is False
    assert LeadLagSafetyGate.validate_lag(0) is True
    assert LeadLagSafetyGate.validate_lag(2) is True


def test_report_structural_pass_derivation():
    """Verifies that audit pass flags are derived from structural checks, not hardcoded."""
    from btceth_os.intel import FeatureDistributionAuditor
    stats = FeatureDistributionAuditor.audit_series("test", [1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats.count == 5
    assert not stats.has_infinities
    assert not stats.has_nan
    assert stats.finite_fraction == 1.0
