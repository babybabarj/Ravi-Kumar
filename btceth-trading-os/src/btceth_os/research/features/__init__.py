from __future__ import annotations

from .registry import FeatureMetadata, FeatureRegistry, GLOBAL_FEATURE_REGISTRY
from .price_returns import (
    compute_log_returns,
    compute_trend_slope,
    compute_breakout_distance,
    compute_normalized_range_position,
    compute_rolling_drawdown,
)
from .volatility import (
    compute_realized_volatility,
    compute_parkinson_volatility,
    compute_garman_klass_volatility,
    compute_average_true_range,
    compute_range_compression_ratio,
)
from .derivatives import (
    align_funding_rates_to_klines,
    compute_funding_zscore,
    compute_funding_percentile,
    compute_minutes_to_funding,
)
from .cross_asset import (
    compute_eth_btc_ratio,
    compute_relative_return_diff,
    compute_rolling_correlation,
    compute_ratio_zscore,
)
from .time_session import (
    timestamp_to_session_info,
    compute_session_flags,
)

__all__ = [
    "FeatureMetadata",
    "FeatureRegistry",
    "GLOBAL_FEATURE_REGISTRY",
    "compute_log_returns",
    "compute_trend_slope",
    "compute_breakout_distance",
    "compute_normalized_range_position",
    "compute_rolling_drawdown",
    "compute_realized_volatility",
    "compute_parkinson_volatility",
    "compute_garman_klass_volatility",
    "compute_average_true_range",
    "compute_range_compression_ratio",
    "align_funding_rates_to_klines",
    "compute_funding_zscore",
    "compute_funding_percentile",
    "compute_minutes_to_funding",
    "compute_eth_btc_ratio",
    "compute_relative_return_diff",
    "compute_rolling_correlation",
    "compute_ratio_zscore",
    "timestamp_to_session_info",
    "compute_session_flags",
]
