"""Versioned Feature Registry for INTEL-1A (`INTEL_FEATURESET_V1`).

Defines and catalogs all approved descriptive market intelligence features across:
1. Price Structure
2. Trend Structure
3. Volatility Structure
4. Volume / Activity
5. Funding
6. Session Context
7. Order-Flow / Microstructure

Every registered feature enforces strict causality contracts.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from btceth_os.intel.feature_contract import (
    AvailabilityTimestampRule,
    FeatureDefinition,
    MissingValuePolicy,
    NormalizationPolicy,
)

FEATURESET_V1_ID = "INTEL_FEATURESET_V1"

# 1. Price Structure Features
PRICE_STRUCTURE_FEATURES: List[FeatureDefinition] = [
    FeatureDefinition(
        feature_name="log_return_1m",
        family="price_structure",
        description="Log return of 1-minute close prices: ln(close_t / close_{t-1})",
        inputs=["close"],
        lookback=1,
        minimum_history=2,
        causality_test="test_price_log_return_causality",
    ),
    FeatureDefinition(
        feature_name="return_5m",
        family="price_structure",
        description="Percentage return over trailing 5-minute horizon",
        inputs=["close"],
        lookback=5,
        minimum_history=6,
        causality_test="test_price_return_5m_causality",
    ),
    FeatureDefinition(
        feature_name="return_15m",
        family="price_structure",
        description="Percentage return over trailing 15-minute horizon",
        inputs=["close"],
        lookback=15,
        minimum_history=16,
        causality_test="test_price_return_15m_causality",
    ),
    FeatureDefinition(
        feature_name="return_1h",
        family="price_structure",
        description="Percentage return over trailing 60-minute horizon",
        inputs=["close"],
        lookback=60,
        minimum_history=61,
        causality_test="test_price_return_1h_causality",
    ),
    FeatureDefinition(
        feature_name="rolling_high_20m",
        family="price_structure",
        description="Maximum high price over trailing 20 minutes",
        inputs=["high"],
        lookback=20,
        minimum_history=20,
        causality_test="test_rolling_extrema_causality",
    ),
    FeatureDefinition(
        feature_name="rolling_low_20m",
        family="price_structure",
        description="Minimum low price over trailing 20 minutes",
        inputs=["low"],
        lookback=20,
        minimum_history=20,
        causality_test="test_rolling_extrema_causality",
    ),
    FeatureDefinition(
        feature_name="distance_from_high_20m",
        family="price_structure",
        description="Percentage distance of current close from trailing 20m high",
        inputs=["close", "high"],
        lookback=20,
        minimum_history=20,
        causality_test="test_rolling_extrema_causality",
    ),
    FeatureDefinition(
        feature_name="distance_from_low_20m",
        family="price_structure",
        description="Percentage distance of current close from trailing 20m low",
        inputs=["close", "low"],
        lookback=20,
        minimum_history=20,
        causality_test="test_rolling_extrema_causality",
    ),
    FeatureDefinition(
        feature_name="range_location_20m",
        family="price_structure",
        description="Position of current close in trailing 20m range: (close - low_20) / (high_20 - low_20)",
        inputs=["close", "high", "low"],
        lookback=20,
        minimum_history=20,
        normalization_policy=NormalizationPolicy.BOUNDED_RATIO.value,
        causality_test="test_range_location_causality",
    ),
    FeatureDefinition(
        feature_name="parkinson_volatility_20m",
        family="price_structure",
        description="Parkinson high-low range realized volatility estimator over trailing 20 minutes",
        inputs=["high", "low"],
        lookback=20,
        minimum_history=20,
        causality_test="test_parkinson_vol_causality",
    ),
    FeatureDefinition(
        feature_name="candle_body_to_range_ratio",
        family="price_structure",
        description="Absolute candle body divided by total bar range: |close - open| / (high - low)",
        inputs=["open", "high", "low", "close"],
        lookback=1,
        minimum_history=1,
        normalization_policy=NormalizationPolicy.BOUNDED_RATIO.value,
        causality_test="test_candle_body_ratio_causality",
    ),
]

# 2. Trend Structure Features
TREND_STRUCTURE_FEATURES: List[FeatureDefinition] = [
    FeatureDefinition(
        feature_name="rolling_slope_20m",
        family="trend_structure",
        description="Linear regression slope of close prices over trailing 20 minutes normalized by price",
        inputs=["close"],
        lookback=20,
        minimum_history=20,
        causality_test="test_trend_slope_causality",
    ),
    FeatureDefinition(
        feature_name="directional_persistence_20m",
        family="trend_structure",
        description="Proportion of upward bars (close > open) in trailing 20 minutes",
        inputs=["open", "close"],
        lookback=20,
        minimum_history=20,
        normalization_policy=NormalizationPolicy.BOUNDED_RATIO.value,
        causality_test="test_directional_persistence_causality",
    ),
    FeatureDefinition(
        feature_name="efficiency_ratio_20m",
        family="trend_structure",
        description="Kaufman efficiency ratio: net price displacement divided by sum of bar-to-bar price changes",
        inputs=["close"],
        lookback=20,
        minimum_history=21,
        normalization_policy=NormalizationPolicy.BOUNDED_RATIO.value,
        causality_test="test_efficiency_ratio_causality",
    ),
    FeatureDefinition(
        feature_name="price_displacement_20m",
        family="trend_structure",
        description="Net price change over trailing 20 minutes: close_t - close_{t-20}",
        inputs=["close"],
        lookback=20,
        minimum_history=21,
        causality_test="test_price_displacement_causality",
    ),
    FeatureDefinition(
        feature_name="rolling_autocorrelation_20m",
        family="trend_structure",
        description="Lag-1 return autocorrelation over trailing 20 minutes",
        inputs=["close"],
        lookback=20,
        minimum_history=22,
        causality_test="test_autocorrelation_causality",
    ),
]

# 3. Volatility Structure Features
VOLATILITY_STRUCTURE_FEATURES: List[FeatureDefinition] = [
    FeatureDefinition(
        feature_name="short_horizon_vol_10m",
        family="volatility_structure",
        description="Sample standard deviation of 1-minute log returns over trailing 10 minutes",
        inputs=["close"],
        lookback=10,
        minimum_history=11,
        causality_test="test_short_horizon_vol_causality",
    ),
    FeatureDefinition(
        feature_name="medium_horizon_vol_60m",
        family="volatility_structure",
        description="Sample standard deviation of 1-minute log returns over trailing 60 minutes",
        inputs=["close"],
        lookback=60,
        minimum_history=61,
        causality_test="test_medium_horizon_vol_causality",
    ),
    FeatureDefinition(
        feature_name="volatility_ratio_10m_60m",
        family="volatility_structure",
        description="Ratio of short-horizon (10m) to medium-horizon (60m) realized volatility",
        inputs=["close"],
        lookback=60,
        minimum_history=61,
        causality_test="test_vol_ratio_causality",
    ),
    FeatureDefinition(
        feature_name="volatility_percentile_trailing_1440m",
        family="volatility_structure",
        description="Percentile rank of current 10m vol within trailing 1440 minutes (24h) history",
        inputs=["close"],
        lookback=1440,
        minimum_history=120,
        normalization_policy=NormalizationPolicy.TRAILING_PERCENTILE_ONLY.value,
        causality_test="test_trailing_vol_percentile_causality",
    ),
    FeatureDefinition(
        feature_name="range_expansion_contraction_ratio_20m",
        family="volatility_structure",
        description="Ratio of current bar high-low range to trailing 20m average range",
        inputs=["high", "low"],
        lookback=20,
        minimum_history=20,
        causality_test="test_range_expansion_causality",
    ),
]

# 4. Volume / Activity Features
VOLUME_ACTIVITY_FEATURES: List[FeatureDefinition] = [
    FeatureDefinition(
        feature_name="traded_volume_raw",
        family="volume_activity",
        description="Base asset volume in the current 1-minute bar",
        inputs=["volume"],
        lookback=1,
        minimum_history=1,
        causality_test="test_volume_causality",
    ),
    FeatureDefinition(
        feature_name="quote_volume_raw",
        family="volume_activity",
        description="Quote currency volume in the current 1-minute bar",
        inputs=["quote_volume"],
        lookback=1,
        minimum_history=1,
        causality_test="test_volume_causality",
    ),
    FeatureDefinition(
        feature_name="trade_count_raw",
        family="volume_activity",
        description="Count of trades executed in the current 1-minute bar",
        inputs=["trade_count"],
        lookback=1,
        minimum_history=1,
        causality_test="test_volume_causality",
    ),
    FeatureDefinition(
        feature_name="relative_activity_20m",
        family="volume_activity",
        description="Current bar volume divided by trailing 20m mean volume",
        inputs=["volume"],
        lookback=20,
        minimum_history=20,
        causality_test="test_relative_activity_causality",
    ),
    FeatureDefinition(
        feature_name="volume_percentile_trailing_1440m",
        family="volume_activity",
        description="Percentile rank of current volume within trailing 1440 minutes history",
        inputs=["volume"],
        lookback=1440,
        minimum_history=120,
        normalization_policy=NormalizationPolicy.TRAILING_PERCENTILE_ONLY.value,
        causality_test="test_trailing_volume_percentile_causality",
    ),
    FeatureDefinition(
        feature_name="abnormal_activity_score_60m",
        family="volume_activity",
        description="Trailing z-score of current bar trade count relative to trailing 60 minutes",
        inputs=["trade_count"],
        lookback=60,
        minimum_history=60,
        normalization_policy=NormalizationPolicy.TRAILING_ZSCORE_ONLY.value,
        causality_test="test_activity_score_causality",
    ),
]

# 5. Funding Features
FUNDING_FEATURES: List[FeatureDefinition] = [
    FeatureDefinition(
        feature_name="latest_realized_funding_rate",
        family="funding",
        description="Most recently settled funding event rate observed at or before current bar",
        inputs=["last_realized_funding_rate"],
        lookback=1,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_DISCRETE_EVENT_TS.value,
        causality_test="test_funding_causality_event_delay",
    ),
    FeatureDefinition(
        feature_name="time_since_last_funding_minutes",
        family="funding",
        description="Minutes elapsed since last settled funding event timestamp",
        inputs=["ts_event_ns", "last_realized_funding_event_ts_ns"],
        lookback=1,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_DISCRETE_EVENT_TS.value,
        causality_test="test_funding_causality_event_delay",
    ),
    FeatureDefinition(
        feature_name="funding_rate_trailing_average_24h",
        family="funding",
        description="Trailing average realized funding rate across observed settlement events in last 24h",
        inputs=["last_realized_funding_rate"],
        lookback=1440,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_DISCRETE_EVENT_TS.value,
        causality_test="test_funding_causality_event_delay",
    ),
    FeatureDefinition(
        feature_name="funding_sign_persistence",
        family="funding",
        description="Number of consecutive settled funding events maintaining the same sign (positive or negative)",
        inputs=["last_realized_funding_rate"],
        lookback=2880,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_DISCRETE_EVENT_TS.value,
        causality_test="test_funding_causality_event_delay",
    ),
]

# 6. Session Context Features
SESSION_CONTEXT_FEATURES: List[FeatureDefinition] = [
    FeatureDefinition(
        feature_name="underlying_session_state",
        family="session_context",
        description="Underlying reference market session state (OPEN or OFF_HOURS_INDEX_MODE)",
        inputs=["underlying_session_state"],
        lookback=1,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_SESSION_BOUNDARY.value,
        causality_test="test_session_context_causality",
    ),
    FeatureDefinition(
        feature_name="underlying_session_certainty",
        family="session_context",
        description="Certainty of underlying reference market session schedule",
        inputs=["underlying_session_certainty"],
        lookback=1,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_SESSION_BOUNDARY.value,
        causality_test="test_session_context_causality",
    ),
    FeatureDefinition(
        feature_name="holiday_status",
        family="session_context",
        description="Holiday calendar implementation status (strictly NOT_IMPLEMENTED in Phase 2)",
        inputs=["holiday_status"],
        lookback=1,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_SESSION_BOUNDARY.value,
        causality_test="test_session_context_causality",
    ),
    FeatureDefinition(
        feature_name="price_index_mode",
        family="session_context",
        description="Price index schedule mode (REGULAR_SCHEDULE_INFERRED or ORDERBOOK_EWMA_SCHEDULE_INFERRED)",
        inputs=["price_index_mode"],
        lookback=1,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_SESSION_BOUNDARY.value,
        causality_test="test_session_context_causality",
    ),
    FeatureDefinition(
        feature_name="price_index_mode_certainty",
        family="session_context",
        description="Certainty of price index mode (preserves HOLIDAY_UNKNOWN where holiday status unproven)",
        inputs=["price_index_mode_certainty"],
        lookback=1,
        minimum_history=1,
        availability_timestamp_rule=AvailabilityTimestampRule.AVAILABLE_AT_SESSION_BOUNDARY.value,
        causality_test="test_session_context_causality",
    ),
]

# 7. Order-Flow / Microstructure Features
ORDER_FLOW_FEATURES: List[FeatureDefinition] = [
    FeatureDefinition(
        feature_name="taker_buy_volume_ratio",
        family="order_flow",
        description="Ratio of taker buy volume to total volume in current 1m bar: taker_buy_vol / vol",
        inputs=["taker_buy_volume", "volume"],
        lookback=1,
        minimum_history=1,
        normalization_policy=NormalizationPolicy.BOUNDED_RATIO.value,
        causality_test="test_order_flow_causality",
    ),
    FeatureDefinition(
        feature_name="order_flow_imbalance_20m",
        family="order_flow",
        description="Trailing 20m cumulative net order flow: (sum(taker_buy) - sum(taker_sell)) / sum(volume)",
        inputs=["taker_buy_volume", "volume"],
        lookback=20,
        minimum_history=20,
        normalization_policy=NormalizationPolicy.BOUNDED_RATIO.value,
        causality_test="test_order_flow_causality",
    ),
    FeatureDefinition(
        feature_name="trade_intensity_per_volume_20m",
        family="order_flow",
        description="Ratio of trade count to traded volume: trade_count / volume over trailing 20m",
        inputs=["trade_count", "volume"],
        lookback=20,
        minimum_history=20,
        causality_test="test_order_flow_causality",
    ),
]

# Complete Master Registry
ALL_FEATURES: List[FeatureDefinition] = (
    PRICE_STRUCTURE_FEATURES
    + TREND_STRUCTURE_FEATURES
    + VOLATILITY_STRUCTURE_FEATURES
    + VOLUME_ACTIVITY_FEATURES
    + FUNDING_FEATURES
    + SESSION_CONTEXT_FEATURES
    + ORDER_FLOW_FEATURES
)

FEATURE_REGISTRY_BY_NAME: Dict[str, FeatureDefinition] = {
    f.feature_name: f for f in ALL_FEATURES
}


class FeatureRegistry:
    """Registry managing versioned features and parameter configurations for INTEL-1A."""

    def __init__(self, features: Optional[List[FeatureDefinition]] = None):
        self._features = {f.feature_name: f for f in (features or ALL_FEATURES)}
        for f in self._features.values():
            f.validate()

    @property
    def feature_set_id(self) -> str:
        return FEATURESET_V1_ID

    def get(self, feature_name: str) -> Optional[FeatureDefinition]:
        return self._features.get(feature_name)

    def list_features(self) -> List[FeatureDefinition]:
        return list(self._features.values())

    def list_feature_names(self) -> List[str]:
        return sorted(self._features.keys())

    def list_by_family(self, family: str) -> List[FeatureDefinition]:
        return [f for f in self._features.values() if f.family == family]

    def count_by_family(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for f in self._features.values():
            counts[f.family] = counts.get(f.family, 0) + 1
        return counts

    def to_manifest(self) -> dict[str, Any]:
        return {
            "feature_set_id": self.feature_set_id,
            "version": "1.0.0",
            "total_features": len(self._features),
            "family_counts": self.count_by_family(),
            "features": {name: feat.to_dict() for name, feat in sorted(self._features.items())},
        }
