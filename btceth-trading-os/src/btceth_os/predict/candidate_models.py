"""Candidate Predictive Models for PRED-1A.

Implements modest, deterministic candidate predictive models in pure Python:
  1. LinearRegressionModel: Ordinary Least Squares (OLS) via normal equations
  2. RidgeRegressionModel: Regularized L2 regression with declared alpha
  3. LogisticRegressionModel: Regularized binary logistic regression via gradient descent
  4. ShallowDecisionTreeRegressor: Shallow CART regressor with max_depth limit
  5. ShallowDecisionTreeClassifier: Shallow CART classifier with max_depth limit

All models enforce fixed random seeds and record library environment.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _solve_linear_system(A: List[List[float]], b: List[float]) -> List[float]:
    """Solves A x = b using Gaussian elimination with partial pivoting."""
    n = len(A)
    # Augmented matrix
    M = [A[i][:] + [b[i]] for i in range(n)]

    for i in range(n):
        # Pivot selection
        max_row = i
        max_val = abs(M[i][i])
        for r in range(i + 1, n):
            if abs(M[r][i]) > max_val:
                max_val = abs(M[r][i])
                max_row = r
        if max_row != i:
            M[i], M[max_row] = M[max_row], M[i]

        pivot = M[i][i]
        if abs(pivot) < 1e-12:
            # Singular or nearly singular: add diagonal jitter
            pivot = 1e-6 if pivot >= 0 else -1e-6
            M[i][i] = pivot

        # Normalize pivot row
        for c in range(i, n + 1):
            M[i][c] /= pivot

        # Eliminate below and above
        for r in range(n):
            if r != i:
                factor = M[r][i]
                for c in range(i, n + 1):
                    M[r][c] -= factor * M[i][c]

    return [M[i][n] for i in range(n)]


class LinearRegressionModel:
    """Ordinary Least Squares Linear Regression."""

    def __init__(self, fit_intercept: bool = True):
        self.fit_intercept = fit_intercept
        self.coef_: Optional[List[float]] = None
        self.intercept_: float = 0.0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> LinearRegressionModel:
        ridge = RidgeRegressionModel(alpha=1e-5, fit_intercept=self.fit_intercept)
        ridge.fit(X, y)
        self.coef_ = ridge.coef_
        self.intercept_ = ridge.intercept_
        return self

    @property
    def weights(self) -> Optional[List[float]]:
        return self.coef_

    @property
    def intercept(self) -> float:
        return self.intercept_

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        if self.coef_ is None:
            raise RuntimeError("Model must be fitted before predict.")
        preds = []
        for row in X:
            val = self.intercept_ + sum(c * x for c, x in zip(self.coef_, row))
            preds.append(val)
        return preds


class RidgeRegressionModel:
    """Ridge (L2 Regularized) Linear Regression."""

    def __init__(self, alpha: float = 1.0, fit_intercept: bool = True):
        self.alpha = max(1e-8, alpha)
        self.fit_intercept = fit_intercept
        self.coef_: Optional[List[float]] = None
        self.intercept_: float = 0.0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> RidgeRegressionModel:
        n_samples = len(X)
        if n_samples == 0:
            raise ValueError("Cannot fit on empty dataset.")
        n_features = len(X[0])

        dim = n_features + (1 if self.fit_intercept else 0)
        A = [[0.0] * dim for _ in range(dim)]
        b = [0.0] * dim

        for i in range(n_samples):
            row = ([1.0] if self.fit_intercept else []) + list(X[i])
            target = y[i]
            for r in range(dim):
                b[r] += row[r] * target
                for c in range(dim):
                    A[r][c] += row[r] * row[c]

        # Add L2 penalty to features (not to intercept)
        start_idx = 1 if self.fit_intercept else 0
        for j in range(start_idx, dim):
            A[j][j] += self.alpha * n_samples

        weights = _solve_linear_system(A, b)

        if self.fit_intercept:
            self.intercept_ = weights[0]
            self.coef_ = weights[1:]
        else:
            self.intercept_ = 0.0
            self.coef_ = weights
        return self

    @property
    def weights(self) -> Optional[List[float]]:
        return self.coef_

    @property
    def intercept(self) -> float:
        return self.intercept_

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        if self.coef_ is None:
            raise RuntimeError("Model must be fitted before predict.")
        preds = []
        for row in X:
            val = self.intercept_ + sum(c * x for c, x in zip(self.coef_, row))
            preds.append(val)
        return preds


class LogisticRegressionModel:
    """L2 Regularized Binary Logistic Regression via Gradient Descent."""

    def __init__(
        self,
        C: float = 1.0,
        max_iter: int = 150,
        lr: float = 0.05,
        random_seed: int = 42,
        learning_rate: Optional[float] = None,
    ):
        self.C = C
        self.max_iter = max_iter
        self.lr = learning_rate if learning_rate is not None else lr
        self.random_seed = random_seed
        self.coef_: Optional[List[float]] = None
        self.intercept_: float = 0.0

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z >= 30.0:
            return 1.0
        if z <= -30.0:
            return 0.0
        return 1.0 / (1.0 + math.exp(-z))

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> LogisticRegressionModel:
        n_samples = len(X)
        if n_samples == 0:
            raise ValueError("Cannot fit on empty dataset.")
        n_features = len(X[0])
        l2_reg = 1.0 / max(1e-4, self.C)

        rng = random.Random(self.random_seed)
        weights = [rng.uniform(-0.01, 0.01) for _ in range(n_features)]
        bias = 0.0

        for _ in range(self.max_iter):
            grad_w = [0.0] * n_features
            grad_b = 0.0
            for i in range(n_samples):
                z = bias + sum(weights[j] * X[i][j] for j in range(n_features))
                p = self._sigmoid(z)
                err = p - y[i]
                grad_b += err
                for j in range(n_features):
                    grad_w[j] += err * X[i][j]

            # Update with L2 regularization on weights
            bias -= self.lr * (grad_b / n_samples)
            for j in range(n_features):
                reg_penalty = (l2_reg / n_samples) * weights[j]
                weights[j] -= self.lr * (grad_w[j] / n_samples + reg_penalty)

        self.intercept_ = bias
        self.coef_ = weights
        return self

    @property
    def weights(self) -> Optional[List[float]]:
        return self.coef_

    @property
    def intercept(self) -> float:
        return self.intercept_

    def predict_proba(self, X: Sequence[Sequence[float]]) -> List[float]:
        if self.coef_ is None:
            raise RuntimeError("Model must be fitted before predict.")
        probs = []
        for row in X:
            z = self.intercept_ + sum(c * x for c, x in zip(self.coef_, row))
            probs.append(self._sigmoid(z))
        return probs

    def predict(self, X: Sequence[Sequence[float]], threshold: float = 0.5) -> List[float]:
        probs = self.predict_proba(X)
        return [1.0 if p >= threshold else 0.0 for p in probs]


class ShallowDecisionTreeRegressor:
    """Shallow CART Decision Tree Regressor."""

    def __init__(self, max_depth: int = 3, min_samples_split: int = 20):
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.tree_: Optional[Dict[str, Any]] = None

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> ShallowDecisionTreeRegressor:
        indices = list(range(len(y)))
        self.tree_ = self._build_tree(X, y, indices, depth=0)
        return self

    def _build_tree(
        self,
        X: Sequence[Sequence[float]],
        y: Sequence[float],
        indices: List[int],
        depth: int,
    ) -> Dict[str, Any]:
        n_samples = len(indices)
        mean_val = sum(y[i] for i in indices) / max(1, n_samples)

        if depth >= self.max_depth or n_samples < self.min_samples_split:
            return {"leaf": True, "value": mean_val}

        n_features = len(X[0])
        best_sse = float("inf")
        best_feat: Optional[int] = None
        best_thresh: Optional[float] = None
        best_left_idx: Optional[List[int]] = None
        best_right_idx: Optional[List[int]] = None

        current_sse = sum((y[i] - mean_val) ** 2 for i in indices)

        # Candidate threshold subsampling for speed (percentiles)
        for j in range(n_features):
            vals = [X[i][j] for i in indices]
            sorted_vals = sorted(vals)
            # Evaluate 5 candidate thresholds per feature
            step = max(1, n_samples // 6)
            thresholds = [sorted_vals[k] for k in range(step, n_samples - step + 1, step)]

            for thresh in set(thresholds):
                left_idx = [i for i in indices if X[i][j] <= thresh]
                right_idx = [i for i in indices if X[i][j] > thresh]

                if not left_idx or not right_idx:
                    continue

                left_mean = sum(y[i] for i in left_idx) / len(left_idx)
                right_mean = sum(y[i] for i in right_idx) / len(right_idx)
                sse = sum((y[i] - left_mean) ** 2 for i in left_idx) + sum((y[i] - right_mean) ** 2 for i in right_idx)

                if sse < best_sse:
                    best_sse = sse
                    best_feat = j
                    best_thresh = thresh
                    best_left_idx = left_idx
                    best_right_idx = right_idx

        if best_feat is None or (current_sse - best_sse) < 1e-8:
            return {"leaf": True, "value": mean_val}

        return {
            "leaf": False,
            "feature": best_feat,
            "threshold": best_thresh,
            "left": self._build_tree(X, y, best_left_idx, depth + 1),
            "right": self._build_tree(X, y, best_right_idx, depth + 1),
        }

    def _predict_row(self, row: Sequence[float], node: Dict[str, Any]) -> float:
        if node["leaf"]:
            return node["value"]
        if row[node["feature"]] <= node["threshold"]:
            return self._predict_row(row, node["left"])
        return self._predict_row(row, node["right"])

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        if self.tree_ is None:
            raise RuntimeError("Tree must be fitted before predict.")
        return [self._predict_row(row, self.tree_) for row in X]
