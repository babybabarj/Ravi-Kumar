"""Causal Feature Contract and Definition Schema for INTEL-1A.

Every feature in the intelligence architecture must satisfy strict causality:
feature_at_time_t uses ONLY information available at or before t.
No future bars, no centered rolling windows, no full-dataset scaling.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, List, Mapping, Optional, Sequence


class AvailabilityTimestampRule(str, Enum):
    AVAILABLE_AT_BAR_CLOSE_T = "AVAILABLE_AT_BAR_CLOSE_T"
    AVAILABLE_AT_DISCRETE_EVENT_TS = "AVAILABLE_AT_DISCRETE_EVENT_TS"
    AVAILABLE_AT_SESSION_BOUNDARY = "AVAILABLE_AT_SESSION_BOUNDARY"


class MissingValuePolicy(str, Enum):
    EMIT_NULL_IF_INSUFFICIENT_HISTORY = "EMIT_NULL_IF_INSUFFICIENT_HISTORY"
    EMIT_UNKNOWN_LABEL = "EMIT_UNKNOWN_LABEL"
    FORWARD_FILL_LAST_KNOWN_ONLY = "FORWARD_FILL_LAST_KNOWN_ONLY"
    FAIL_CLOSED = "FAIL_CLOSED"


class NormalizationPolicy(str, Enum):
    RAW_VALUE = "RAW_VALUE"
    BOUNDED_RATIO = "BOUNDED_RATIO"
    TRAILING_PERCENTILE_ONLY = "TRAILING_PERCENTILE_ONLY"
    TRAILING_ZSCORE_ONLY = "TRAILING_ZSCORE_ONLY"
    TRAILING_MIN_MAX_ONLY = "TRAILING_MIN_MAX_ONLY"


@dataclass(frozen=True)
class FeatureDefinition:
    feature_name: str
    family: str
    description: str
    inputs: List[str]
    lookback: int
    minimum_history: int
    publication_delay_ns: int = 0
    availability_timestamp_rule: str = AvailabilityTimestampRule.AVAILABLE_AT_BAR_CLOSE_T.value
    missing_value_policy: str = MissingValuePolicy.EMIT_NULL_IF_INSUFFICIENT_HISTORY.value
    normalization_policy: str = NormalizationPolicy.RAW_VALUE.value
    causality_test: str = "test_causal_no_future_leakage"
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if not self.feature_name:
            raise ValueError("FeatureDefinition requires non-empty feature_name")
        if self.lookback < 0:
            raise ValueError(f"Feature {self.feature_name} lookback cannot be negative: {self.lookback}")
        if self.minimum_history < 0:
            raise ValueError(
                f"Feature {self.feature_name} minimum_history ({self.minimum_history}) cannot be negative"
            )
        if not self.inputs:
            raise ValueError(f"Feature {self.feature_name} must declare at least one input field")
