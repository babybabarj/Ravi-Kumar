"""Predictive Research Metrics and Performance Firewall for PRED-1A.

Permitted Research Metrics:
  Continuous:
    - MAE
    - RMSE
    - R2
    - Pearson Correlation
    - Spearman Rank Correlation
    - Directional Sign Accuracy
  Classification:
    - Accuracy
    - Balanced Accuracy
    - Precision
    - Recall
    - F1 Score
    - Brier Score
    - Log Loss

FORBIDDEN PERFORMANCE METRICS:
  PRED-1A strictly prohibits calculation of:
    pnl, p&l, sharpe, sortino, cagr, profit_factor, win_rate,
    expectancy, trade_count, drawdown, portfolio_return, kelly, leverage.
  Any calculation or dict containing these keys raises ForbiddenMetricError.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


FORBIDDEN_METRIC_KEYWORDS = {
    "PNL", "P&L", "SHARPE", "SORTINO", "CAGR", "PROFIT_FACTOR",
    "WIN_RATE", "EXPECTANCY", "TRADE_COUNT", "DRAWDOWN",
    "PORTFOLIO_RETURN", "KELLY", "LEVERAGE",
    "TARGET_ENTRY", "STOP_LOSS", "TAKE_PROFIT", "ENTRY_ZONE", "TRADE_CONFIDENCE",
}


class ForbiddenMetricError(ValueError):
    """Raised when trading/strategy performance metrics are illicitly computed."""
    pass


def assert_no_forbidden_metrics(metrics: Dict[str, Any]) -> None:
    """Verifies that no trading performance metrics exist in the metrics dictionary."""
    for key in metrics:
        key_upper = key.upper()
        for kw in FORBIDDEN_METRIC_KEYWORDS:
            if kw in key_upper:
                raise ForbiddenMetricError(
                    f"Forbidden trading performance metric '{key}' detected in predictive research: {kw}"
                )


def mean_absolute_error(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    n = len(y_true)
    if n == 0:
        return 0.0
    return sum(abs(yt - yp) for yt, yp in zip(y_true, y_pred)) / n


def root_mean_squared_error(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    n = len(y_true)
    if n == 0:
        return 0.0
    mse = sum((yt - yp) ** 2 for yt, yp in zip(y_true, y_pred)) / n
    return math.sqrt(mse)


def r2_score(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    n = len(y_true)
    if n < 2:
        return 0.0
    mean_y = sum(y_true) / n
    ss_tot = sum((yt - mean_y) ** 2 for yt in y_true)
    if ss_tot < 1e-12:
        return 0.0
    ss_res = sum((yt - yp) ** 2 for yt, yp in zip(y_true, y_pred))
    return 1.0 - (ss_res / ss_tot)


def pearson_correlation(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    n = len(y_true)
    if n < 2:
        return 0.0
    mean_t = sum(y_true) / n
    mean_p = sum(y_pred) / n
    cov = sum((yt - mean_t) * (yp - mean_p) for yt, yp in zip(y_true, y_pred))
    var_t = sum((yt - mean_t) ** 2 for yt in y_true)
    var_p = sum((yp - mean_p) ** 2 for yp in y_pred)
    denom = math.sqrt(var_t * var_p)
    if denom < 1e-12:
        return 0.0
    return cov / denom


def _rankdata(vals: Sequence[float]) -> List[float]:
    """Assigns average ranks to ties."""
    n = len(vals)
    indexed = sorted(enumerate(vals), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    n = len(y_true)
    if n < 2:
        return 0.0
    rank_t = _rankdata(y_true)
    rank_p = _rankdata(y_pred)
    return pearson_correlation(rank_t, rank_p)


def directional_sign_accuracy(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    n = len(y_true)
    if n == 0:
        return 0.0
    matches = 0
    for yt, yp in zip(y_true, y_pred):
        sign_t = 1 if yt > 0 else (-1 if yt < 0 else 0)
        sign_p = 1 if yp > 0 else (-1 if yp < 0 else 0)
        if sign_t == sign_p:
            matches += 1
    return matches / n


def brier_score(y_true: Sequence[float], y_prob: Sequence[float]) -> float:
    n = len(y_true)
    if n == 0:
        return 0.0
    return sum((prob - yt) ** 2 for yt, prob in zip(y_true, y_prob)) / n


def log_loss(y_true: Sequence[float], y_prob: Sequence[float], eps: float = 1e-15) -> float:
    n = len(y_true)
    if n == 0:
        return 0.0
    total = 0.0
    for yt, prob in zip(y_true, y_prob):
        p = max(eps, min(1.0 - eps, prob))
        total += yt * math.log(p) + (1.0 - yt) * math.log(1.0 - p)
    return -total / n


def binary_classification_metrics(
    y_true: Sequence[float],
    y_prob: Sequence[float],
    threshold: float = 0.5,
) -> Dict[str, float]:
    n = len(y_true)
    if n == 0:
        return {}

    tp = fp = tn = fn = 0
    for yt, prob in zip(y_true, y_prob):
        pred_label = 1 if prob >= threshold else 0
        true_label = int(yt)
        if true_label == 1 and pred_label == 1:
            tp += 1
        elif true_label == 0 and pred_label == 1:
            fp += 1
        elif true_label == 0 and pred_label == 0:
            tn += 1
        elif true_label == 1 and pred_label == 0:
            fn += 1

    accuracy = (tp + tn) / n
    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    balanced_acc = (sensitivity + specificity) / 2.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = sensitivity
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    brier = brier_score(y_true, y_prob)
    ll = log_loss(y_true, y_prob)

    metrics = {
        "accuracy": accuracy,
        "balanced_accuracy": balanced_acc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "brier_score": brier,
        "log_loss": ll,
    }
    assert_no_forbidden_metrics(metrics)
    return metrics


def continuous_prediction_metrics(
    y_true: Sequence[float], y_pred: Sequence[float]
) -> Dict[str, float]:
    metrics = {
        "mae": mean_absolute_error(y_true, y_pred),
        "rmse": root_mean_squared_error(y_true, y_pred),
        "r2": r2_score(y_true, y_pred),
        "pearson_corr": pearson_correlation(y_true, y_pred),
        "spearman_corr": spearman_correlation(y_true, y_pred),
        "directional_accuracy": directional_sign_accuracy(y_true, y_pred),
    }
    assert_no_forbidden_metrics(metrics)
    return metrics


# Aliases
calculate_continuous_metrics = continuous_prediction_metrics
calculate_binary_metrics = binary_classification_metrics

