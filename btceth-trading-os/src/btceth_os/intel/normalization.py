"""Causal Normalization Policy and Fitted Scaler Metadata for INTEL-1A.

Strictly prohibits fitting scalers on the full dataset or on future observations.
Rolling normalization must use trailing history only.
Learned static scalers must record explicit fit metadata (fit_dataset, fit_start, fit_end, artifact_hash).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class ScalerMetadata:
    fit_dataset: str
    fit_start_utc: str
    fit_end_utc: str
    artifact_hash: str
    feature_version: str
    scaler_type: str
    params: Dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrailingRollingScaler:
    """Computes rolling normalization using only trailing window observations."""

    @staticmethod
    def rolling_zscore(
        series: Sequence[float], window: int = 60, min_periods: int = 20
    ) -> List[Optional[float]]:
        n = len(series)
        out: List[Optional[float]] = [None] * n
        for i in range(n):
            if i < min_periods - 1:
                continue
            start_idx = max(0, i - window + 1)
            sub = series[start_idx : i + 1]
            if len(sub) < min_periods:
                continue
            m = sum(sub) / len(sub)
            var = sum((x - m) ** 2 for x in sub) / (len(sub) - 1)
            std = math.sqrt(max(0.0, var))
            if std > 1e-12:
                out[i] = (series[i] - m) / std
            else:
                out[i] = 0.0
        return out

    @staticmethod
    def rolling_percentile(
        series: Sequence[float], window: int = 1440, min_periods: int = 60
    ) -> List[Optional[float]]:
        n = len(series)
        out: List[Optional[float]] = [None] * n
        for i in range(n):
            if i < min_periods - 1:
                continue
            start_idx = max(0, i - window + 1)
            sub = series[start_idx : i + 1]
            if len(sub) < min_periods:
                continue
            curr = series[i]
            rank = sum(1 for x in sub if x <= curr)
            out[i] = rank / len(sub)
        return out


class LearnedFeatureScaler:
    """A static scaler fit strictly on authorized historical training data."""

    def __init__(self, metadata: ScalerMetadata):
        self.metadata = metadata

    @classmethod
    def fit_min_max(
        cls,
        training_series: Sequence[float],
        fit_dataset: str,
        fit_start_utc: str,
        fit_end_utc: str,
        artifact_hash: str,
        feature_version: str = "1.0.0",
    ) -> LearnedFeatureScaler:
        if not training_series:
            raise ValueError("Cannot fit scaler on empty series")
        min_val = min(training_series)
        max_val = max(training_series)
        meta = ScalerMetadata(
            fit_dataset=fit_dataset,
            fit_start_utc=fit_start_utc,
            fit_end_utc=fit_end_utc,
            artifact_hash=artifact_hash,
            feature_version=feature_version,
            scaler_type="MIN_MAX",
            params={"min": min_val, "max": max_val},
        )
        return cls(meta)

    def transform(self, val: float) -> float:
        min_v = self.metadata.params["min"]
        max_v = self.metadata.params["max"]
        rng = max_v - min_v
        if rng <= 1e-12:
            return 0.5
        return (val - min_v) / rng
