"""Baseline Reference Models for PRED-1A.

Establishes non-complex naive baselines against which candidate models must be evaluated:
  Continuous:
    1. ZERO_RETURN_BASELINE: always predicts 0.0
    2. HISTORICAL_MEAN_BASELINE: predicts training set mean target
    3. LAST_OBSERVATION_BASELINE: predicts trailing observation of identical horizon
    4. ROLLING_MEAN_BASELINE: predicts rolling mean over trailing training window
  Classification:
    5. MAJORITY_CLASS_BASELINE: predicts most frequent class in train fold
    6. EMPIRICAL_PRIOR_BASELINE: predicts empirical class probability distribution
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


class ZeroReturnBaseline:
    """Predicts a constant 0.0 return."""

    def __init__(self):
        self.name = "ZERO_RETURN_BASELINE"

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> ZeroReturnBaseline:
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        return [0.0] * len(X)


class HistoricalMeanBaseline:
    """Predicts the historical sample mean of the target from the training set."""

    def __init__(self):
        self.name = "HISTORICAL_MEAN_BASELINE"
        self.mean_value_: float = 0.0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> HistoricalMeanBaseline:
        if not y:
            self.mean_value_ = 0.0
        else:
            self.mean_value_ = sum(y) / len(y)
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        return [self.mean_value_] * len(X)


class LastObservationBaseline:
    """Predicts the trailing value from a designated trailing feature index (e.g. trailing return)."""

    def __init__(self, feature_idx: int = 0):
        self.name = "LAST_OBSERVATION_BASELINE"
        self.feature_idx = feature_idx

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> LastObservationBaseline:
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        return [row[self.feature_idx] if len(row) > self.feature_idx else 0.0 for row in X]


class RollingMeanBaseline:
    """Predicts the mean of the trailing window of target observations from the end of the training set."""

    def __init__(self, window: int = 60):
        self.name = "ROLLING_MEAN_BASELINE"
        self.window = window
        self.rolling_mean_: float = 0.0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> RollingMeanBaseline:
        if not y:
            self.rolling_mean_ = 0.0
        else:
            tail = y[-self.window:] if len(y) >= self.window else y
            self.rolling_mean_ = sum(tail) / len(tail)
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        return [self.rolling_mean_] * len(X)


class MajorityClassBaseline:
    """Predicts the majority class from the training set."""

    def __init__(self):
        self.name = "MAJORITY_CLASS_BASELINE"
        self.majority_class_: float = 0.0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> MajorityClassBaseline:
        if not y:
            self.majority_class_ = 0.0
        else:
            counts: Dict[float, int] = {}
            for label in y:
                counts[label] = counts.get(label, 0) + 1
            self.majority_class_ = max(counts.items(), key=lambda kv: kv[1])[0]
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        return [self.majority_class_] * len(X)

    def predict_proba(self, X: Sequence[Sequence[float]]) -> List[float]:
        # Return probability 1.0 for majority class
        return [1.0 if self.majority_class_ == 1.0 else 0.0] * len(X)


class EmpiricalPriorBaseline:
    """Predicts the empirical training class probability (proportion of positive class)."""

    def __init__(self):
        self.name = "EMPIRICAL_PRIOR_BASELINE"
        self.prior_: float = 0.5

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> EmpiricalPriorBaseline:
        if not y:
            self.prior_ = 0.5
        else:
            pos_count = sum(1 for val in y if val == 1.0)
            self.prior_ = pos_count / len(y)
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        return [1.0 if self.prior_ >= 0.5 else 0.0] * len(X)

    def predict_proba(self, X: Sequence[Sequence[float]]) -> List[float]:
        return [self.prior_] * len(X)
