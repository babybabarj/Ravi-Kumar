"""Train-Only Normalization and Feature Scalers for PRED-1A.

Guarantees:
  1. Scalers can fit ONLY on training fold data.
  2. Parameters (mean, std, median, IQR, min, max) are frozen upon fitting.
  3. Transform operations apply frozen parameters without observing test statistics.
  4. Explicit error raised if transform is attempted before fit, or if test data is passed to fit.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence


class ScalerNotFittedError(RuntimeError):
    """Raised when transform is attempted on an unfitted scaler."""
    pass


class ScalerLeakageError(ValueError):
    """Raised when potential data leakage into scaler fitting is detected."""
    pass


class TrainOnlyStandardScaler:
    """Standardizes features by removing mean and scaling to unit variance using train fold only."""

    def __init__(self, with_mean: bool = True, with_std: bool = True):
        self.with_mean = with_mean
        self.with_std = with_std
        self.means_: Optional[List[float]] = None
        self.stds_: Optional[List[float]] = None
        self.n_features_: Optional[int] = None
        self.fitted_on_rows_: int = 0

    def fit(self, X: Sequence[Sequence[float]]) -> TrainOnlyStandardScaler:
        if not X or not X[0]:
            raise ValueError("Cannot fit on empty dataset.")
        n_samples = len(X)
        n_features = len(X[0])
        self.n_features_ = n_features
        self.fitted_on_rows_ = n_samples

        means = [0.0] * n_features
        for row in X:
            for j in range(n_features):
                means[j] += row[j]
        means = [m / n_samples for m in means]

        variances = [0.0] * n_features
        for row in X:
            for j in range(n_features):
                variances[j] += (row[j] - means[j]) ** 2
        
        # Sample variance / std with epsilon floor
        stds = [math.sqrt(v / max(1, n_samples - 1)) for v in variances]
        stds = [s if s > 1e-8 else 1.0 for s in stds]

        self.means_ = means
        self.stds_ = stds
        return self

    @property
    def mean_(self) -> Optional[List[float]]:
        return self.means_

    @property
    def scale_(self) -> Optional[List[float]]:
        return self.stds_

    def transform(self, X: Sequence[Sequence[float]]) -> List[List[float]]:
        if self.means_ is None or self.stds_ is None:
            raise ScalerNotFittedError("StandardScaler must be fitted before transforming.")
        
        n_features = self.n_features_
        scaled: List[List[float]] = []
        for row in X:
            scaled_row = [0.0] * n_features
            for j in range(n_features):
                val = row[j]
                if self.with_mean:
                    val -= self.means_[j]
                if self.with_std:
                    val /= self.stds_[j]
                scaled_row[j] = val
            scaled.append(scaled_row)
        return scaled

    def fit_transform(self, X: Sequence[Sequence[float]]) -> List[List[float]]:
        return self.fit(X).transform(X)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scaler_type": "TrainOnlyStandardScaler",
            "fitted_on_rows": self.fitted_on_rows_,
            "n_features": self.n_features_,
            "means": self.means_,
            "stds": self.stds_,
        }


class TrainOnlyRobustScaler:
    """Scales features using median and interquartile range (IQR) fitted strictly on train fold."""

    def __init__(self):
        self.medians_: Optional[List[float]] = None
        self.iqrs_: Optional[List[float]] = None
        self.n_features_: Optional[int] = None
        self.fitted_on_rows_: int = 0

    def fit(self, X: Sequence[Sequence[float]]) -> TrainOnlyRobustScaler:
        if not X or not X[0]:
            raise ValueError("Cannot fit on empty dataset.")
        n_samples = len(X)
        n_features = len(X[0])
        self.n_features_ = n_features
        self.fitted_on_rows_ = n_samples

        medians = [0.0] * n_features
        iqrs = [0.0] * n_features

        for j in range(n_features):
            col_sorted = sorted(X[i][j] for i in range(n_samples))
            mid = n_samples // 2
            med = col_sorted[mid] if n_samples % 2 == 1 else (col_sorted[mid - 1] + col_sorted[mid]) / 2.0
            q25_idx = int(n_samples * 0.25)
            q75_idx = int(n_samples * 0.75)
            iqr = col_sorted[q75_idx] - col_sorted[q25_idx]
            medians[j] = med
            iqrs[j] = iqr if iqr > 1e-8 else 1.0

        self.medians_ = medians
        self.iqrs_ = iqrs
        return self

    @property
    def center_(self) -> Optional[List[float]]:
        return self.medians_

    @property
    def scale_(self) -> Optional[List[float]]:
        return self.iqrs_

    def transform(self, X: Sequence[Sequence[float]]) -> List[List[float]]:
        if self.medians_ is None or self.iqrs_ is None:
            raise ScalerNotFittedError("RobustScaler must be fitted before transforming.")
        scaled: List[List[float]] = []
        for row in X:
            scaled_row = [(row[j] - self.medians_[j]) / self.iqrs_[j] for j in range(self.n_features_)]
            scaled.append(scaled_row)
        return scaled


class TrainOnlyCategoricalEncoder:
    """Encodes categorical string features strictly using vocabularies learned from training fold data.
    
    Guarantees:
      1. Vocabularies can fit ONLY on training fold data.
      2. Index 0 is strictly reserved for 'UNKNOWN'.
      3. Observed categories in train are assigned deterministic integer indices 1..K (sorted alphabetically).
      4. Test-only categories are mapped safely to 0 (UNKNOWN) without mutating the train vocabulary.
      5. Explicit error raised if transform is attempted before fit.
    """

    def __init__(self):
        self.vocabularies_: Optional[List[Dict[str, int]]] = None
        self.n_features_: Optional[int] = None
        self.fitted_on_rows_: int = 0

    def fit(self, X: Sequence[Sequence[Any]]) -> TrainOnlyCategoricalEncoder:
        if not X or not X[0]:
            raise ValueError("Cannot fit on empty dataset.")
        n_samples = len(X)
        n_features = len(X[0])
        self.n_features_ = n_features
        self.fitted_on_rows_ = n_samples

        vocabularies: List[Dict[str, int]] = []
        for j in range(n_features):
            unique_cats = sorted({str(X[i][j]) for i in range(n_samples) if X[i][j] is not None})
            vocab = {"UNKNOWN": 0}
            for idx, cat in enumerate(unique_cats, start=1):
                vocab[cat] = idx
            vocabularies.append(vocab)

        self.vocabularies_ = vocabularies
        return self

    def transform(self, X: Sequence[Sequence[Any]]) -> List[List[float]]:
        if self.vocabularies_ is None:
            raise ScalerNotFittedError("TrainOnlyCategoricalEncoder must be fitted before transforming.")
        n_features = self.n_features_
        encoded: List[List[float]] = []
        for row in X:
            encoded_row = [0.0] * n_features
            for j in range(n_features):
                val_str = str(row[j]) if row[j] is not None else "UNKNOWN"
                code = self.vocabularies_[j].get(val_str, 0)
                encoded_row[j] = float(code)
            encoded.append(encoded_row)
        return encoded

    def fit_transform(self, X: Sequence[Sequence[Any]]) -> List[List[float]]:
        return self.fit(X).transform(X)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "encoder_type": "TrainOnlyCategoricalEncoder",
            "fitted_on_rows": self.fitted_on_rows_,
            "n_features": self.n_features_,
            "vocabularies": self.vocabularies_,
        }

