"""INTEL-1 Intelligence Architecture & Reliability Package.

Provides deterministic, causal, leakage-resistant, multi-asset market intelligence:
- Dataset Access API & Append-Only Access Ledger (Holdout Firewall)
- Causal Feature Engine & Versioned Feature Registry (INTEL_FEATURESET_V1)
- Descriptive Market State Engine (5 Regime Dimensions)
- Cross-Asset Context Engine (BTC, ETH, XAU)
- Machine-Readable Non-Executable Intelligence Snapshots (V1 & V2)
- Data Quality Gate & Fail-Closed Quality Propagation Engine
- State Transition Engine & Regime Stability / Threshold Sensitivity Audits
- Lead/Lag Safety Gate & Cross-Asset Clock Alignment
- Feature Availability Matrix & Feature Quality / Redundancy / Drift Audits
- Missingness Semantics & Numeric Boundary Audits
- Multi-Timeframe Consistency Audits
"""

from btceth_os.intel.cross_asset import CrossAssetContextEngine, CrossAssetContextSnapshot
from btceth_os.intel.data_access import (
    IntelAccessDeniedError,
    IntelDatasetAccessAPI,
    audit_intel_access_ledger,
)
from btceth_os.intel.data_quality import BarDataQualityAssessment, DataQualityGate, DataQualityStatus
from btceth_os.intel.data_quality_propagation import DataQualityPropagationEngine
from btceth_os.intel.feature_availability import FeatureAvailabilityMatrix, FeatureAvailabilityRecord
from btceth_os.intel.feature_audit import (
    FeatureDistributionAuditor,
    FeatureDistributionStats,
    FeatureDriftAuditor,
    FeatureDriftRecord,
    FeaturePairRedundancy,
    FeaturePerturbationTester,
    FeatureRedundancyAuditor,
)
from btceth_os.intel.feature_contract import (
    AvailabilityTimestampRule,
    FeatureDefinition,
    MissingValuePolicy,
    NormalizationPolicy,
)
from btceth_os.intel.feature_engine import CausalFeatureEngine
from btceth_os.intel.feature_registry import (
    ALL_FEATURES,
    FEATURESET_V1_ID,
    FeatureRegistry,
)
from btceth_os.intel.lead_lag import (
    CAUSAL_LIVE_ELIGIBLE_METRICS,
    ClockAlignmentViolationError,
    CrossAssetClockAlignment,
    LeadLagEngine,
    LeadLagResult,
    LeadLagSafetyGate,
    LeadLagSpecification,
    MetricEligibilityCategory,
    NegativeLagCausalityViolationError,
    RETROSPECTIVE_RESEARCH_ONLY_METRICS,
    RetrospectiveMetricInLiveContextError,
)
from btceth_os.intel.market_state import (
    FundingRegime,
    LiquidityActivityRegime,
    MarketQualityRegime,
    MarketStateEngine,
    MarketStateSnapshot,
    TrendRegime,
    VolatilityRegime,
)
from btceth_os.intel.missingness import MissingReason, MissingValue, is_missing_value
from btceth_os.intel.multitimeframe import MultiTimeframeAuditResult, MultiTimeframeAuditor
from btceth_os.intel.normalization import LearnedFeatureScaler, TrailingRollingScaler
from btceth_os.intel.numeric_boundary import (
    NUMERIC_BOUNDARY_CATALOG,
    NumericBoundaryAuditor,
    NumericBoundaryEntry,
)
from btceth_os.intel.reproducibility import compute_feature_table_logical_hash, compute_intel_logical_hash
from btceth_os.intel.resampler import AggregatedBar, CausalResampler
from btceth_os.intel.snapshot import (
    ExecutionFieldForbiddenError,
    IntelligenceSnapshot,
    assert_no_execution_fields,
)
from btceth_os.intel.snapshot_v2 import (
    ALL_FORBIDDEN_FIELDS,
    IntelligenceSnapshotV2,
    assert_no_execution_fields_v2,
)
from btceth_os.intel.stability_audit import (
    RegimeStabilityAuditor,
    ThresholdPerturbationResult,
    ThresholdSensitivityAuditor,
    ThresholdSensitivitySummary,
)
from btceth_os.intel.state_transitions import (
    DimensionTransitionMetrics,
    StateTransitionEngine,
    StateTransitionRecord,
)

__all__ = [
    "IntelDatasetAccessAPI",
    "IntelAccessDeniedError",
    "audit_intel_access_ledger",
    "FeatureDefinition",
    "AvailabilityTimestampRule",
    "MissingValuePolicy",
    "NormalizationPolicy",
    "FeatureRegistry",
    "FEATURESET_V1_ID",
    "ALL_FEATURES",
    "CausalFeatureEngine",
    "DataQualityGate",
    "DataQualityStatus",
    "BarDataQualityAssessment",
    "DataQualityPropagationEngine",
    "MarketStateEngine",
    "MarketStateSnapshot",
    "TrendRegime",
    "VolatilityRegime",
    "LiquidityActivityRegime",
    "FundingRegime",
    "MarketQualityRegime",
    "CrossAssetContextEngine",
    "CrossAssetContextSnapshot",
    "IntelligenceSnapshot",
    "IntelligenceSnapshotV2",
    "ExecutionFieldForbiddenError",
    "assert_no_execution_fields",
    "assert_no_execution_fields_v2",
    "ALL_FORBIDDEN_FIELDS",
    "CausalResampler",
    "AggregatedBar",
    "TrailingRollingScaler",
    "LearnedFeatureScaler",
    "compute_intel_logical_hash",
    "compute_feature_table_logical_hash",
    "MissingReason",
    "MissingValue",
    "is_missing_value",
    "StateTransitionRecord",
    "DimensionTransitionMetrics",
    "StateTransitionEngine",
    "ThresholdPerturbationResult",
    "ThresholdSensitivitySummary",
    "RegimeStabilityAuditor",
    "ThresholdSensitivityAuditor",
    "MetricEligibilityCategory",
    "CAUSAL_LIVE_ELIGIBLE_METRICS",
    "RETROSPECTIVE_RESEARCH_ONLY_METRICS",
    "NegativeLagCausalityViolationError",
    "RetrospectiveMetricInLiveContextError",
    "ClockAlignmentViolationError",
    "CrossAssetClockAlignment",
    "LeadLagSpecification",
    "LeadLagResult",
    "LeadLagSafetyGate",
    "LeadLagEngine",
    "FeatureAvailabilityRecord",
    "FeatureAvailabilityMatrix",
    "NumericBoundaryEntry",
    "NUMERIC_BOUNDARY_CATALOG",
    "NumericBoundaryAuditor",
    "MultiTimeframeAuditResult",
    "MultiTimeframeAuditor",
    "FeatureDistributionStats",
    "FeaturePairRedundancy",
    "FeatureDriftRecord",
    "FeatureDistributionAuditor",
    "FeatureRedundancyAuditor",
    "FeatureDriftAuditor",
    "FeaturePerturbationTester",
]
