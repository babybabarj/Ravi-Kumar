"""INTEL-1A Intelligence Architecture Foundation Package.

Provides deterministic, causal, leakage-resistant, multi-asset market intelligence:
- Dataset Access API & Append-Only Access Ledger (Holdout Firewall)
- Causal Feature Engine & Versioned Feature Registry (INTEL_FEATURESET_V1)
- Descriptive Market State Engine (5 Regime Dimensions)
- Cross-Asset Context Engine (BTC, ETH, XAU)
- Machine-Readable Non-Executable Intelligence Snapshots
- Data Quality Gate
- Causal Timeframe Resampler
- Normalization Policy
- Deterministic Logical Hashing
"""

from btceth_os.intel.cross_asset import CrossAssetContextEngine, CrossAssetContextSnapshot
from btceth_os.intel.data_access import (
    IntelAccessDeniedError,
    IntelDatasetAccessAPI,
    audit_intel_access_ledger,
)
from btceth_os.intel.data_quality import BarDataQualityAssessment, DataQualityGate, DataQualityStatus
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
from btceth_os.intel.market_state import (
    FundingRegime,
    LiquidityActivityRegime,
    MarketQualityRegime,
    MarketStateEngine,
    MarketStateSnapshot,
    TrendRegime,
    VolatilityRegime,
)
from btceth_os.intel.normalization import LearnedFeatureScaler, TrailingRollingScaler
from btceth_os.intel.reproducibility import compute_feature_table_logical_hash, compute_intel_logical_hash
from btceth_os.intel.resampler import AggregatedBar, CausalResampler
from btceth_os.intel.snapshot import (
    ExecutionFieldForbiddenError,
    IntelligenceSnapshot,
    assert_no_execution_fields,
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
    "ExecutionFieldForbiddenError",
    "assert_no_execution_fields",
    "CausalResampler",
    "AggregatedBar",
    "TrailingRollingScaler",
    "LearnedFeatureScaler",
    "compute_intel_logical_hash",
    "compute_feature_table_logical_hash",
]
