"""Model Calibration and Reliability Diagnostics for PRED-1A.

Evaluates probabilistic predictions:
  - Reliability bins
  - Observed positive frequency vs mean predicted probability
  - Brier score decomposition
  - Strictly research diagnostic (never interpreted as trade win-rate)
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def evaluate_calibration(
    y_true: Sequence[float],
    y_prob: Sequence[float],
    n_bins: int = 5,
) -> Dict[str, Any]:
    """Computes reliability calibration table across quantile or equal-width bins."""
    n = len(y_true)
    if n == 0:
        return {"brier_score": 0.0, "bins": []}

    brier = sum((p - y) ** 2 for y, p in zip(y_true, y_prob)) / n
    bin_width = 1.0 / n_bins
    bins_data: List[Dict[str, Any]] = []

    for b in range(n_bins):
        lower = b * bin_width
        upper = (b + 1) * bin_width if b < n_bins - 1 else 1.000001
        indices = [i for i, p in enumerate(y_prob) if lower <= p < upper]
        count = len(indices)
        if count > 0:
            mean_pred = sum(y_prob[i] for i in indices) / count
            obs_freq = sum(y_true[i] for i in indices) / count
        else:
            mean_pred = (lower + upper) / 2.0
            obs_freq = 0.0

        bins_data.append({
            "bin_index": b + 1,
            "bin_lower": round(lower, 2),
            "bin_upper": round(upper if upper <= 1.0 else 1.0, 2),
            "count": count,
            "mean_predicted_probability": round(mean_pred, 4),
            "observed_positive_frequency": round(obs_freq, 4),
            "calibration_error": round(abs(mean_pred - obs_freq), 4),
        })

    # Expected Calibration Error (ECE)
    ece = sum(b["count"] * b["calibration_error"] for b in bins_data) / max(1, n)

    return {
        "brier_score": round(brier, 6),
        "expected_calibration_error": round(ece, 4),
        "bins_evaluated": n_bins,
        "bins": bins_data,
    }
