from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class FeatureMetadata:
    feature_id: str
    name: str
    category: str  # price_returns, volatility, derivatives, cross_asset, time_session
    lookback_bars: int
    source_fields: tuple[str, ...]
    description: str
    point_in_time_rule: str = "available_ts <= decision_ts; strictly uses only closed bars at or prior to decision index"


class FeatureRegistry:
    """Deterministic, point-in-time feature catalog and validation registry."""

    def __init__(self) -> None:
        self._features: Dict[str, Tuple[FeatureMetadata, Callable[..., Sequence[float]]]] = {}

    def register(self, metadata: FeatureMetadata, compute_fn: Callable[..., Sequence[float]]) -> None:
        if metadata.feature_id in self._features:
            raise ValueError(f"Feature '{metadata.feature_id}' is already registered.")
        self._features[metadata.feature_id] = (metadata, compute_fn)

    def get_metadata(self, feature_id: str) -> FeatureMetadata:
        if feature_id not in self._features:
            raise KeyError(f"Feature '{feature_id}' is not registered.")
        return self._features[feature_id][0]

    def get_compute_fn(self, feature_id: str) -> Callable[..., Sequence[float]]:
        if feature_id not in self._features:
            raise KeyError(f"Feature '{feature_id}' is not registered.")
        return self._features[feature_id][1]

    def list_features(self) -> List[FeatureMetadata]:
        return [meta for meta, _ in self._features.values()]

    def compute(self, feature_id: str, *args: Any, **kwargs: Any) -> Sequence[float]:
        fn = self.get_compute_fn(feature_id)
        return fn(*args, **kwargs)


GLOBAL_FEATURE_REGISTRY = FeatureRegistry()
