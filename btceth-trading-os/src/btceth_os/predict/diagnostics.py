"""Temporal Robustness and Multiple Testing Diagnostics for PRED-1A.

Provides:
  1. Temporal Stability Evaluation across DEV folds:
     - Mean, median, min, max, standard deviation
     - Fold-by-fold sign consistency
     - Effect size vs naive baseline (absolute & relative improvement)
  2. Multiple Testing Adjustments:
     - Bonferroni correction
     - Benjamini-Hochberg False Discovery Rate (FDR)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


def evaluate_temporal_stability(
    fold_candidate_metrics: List[Dict[str, float]],
    fold_baseline_metrics: List[Dict[str, float]],
    primary_metric: str = "mae",
    higher_is_better: bool = False,
) -> Dict[str, Any]:
    """Analyzes stability of candidate model across temporal folds vs baseline."""
    n_folds = len(fold_candidate_metrics)
    if n_folds == 0:
        return {}

    candidate_vals = [f[primary_metric] for f in fold_candidate_metrics]
    baseline_vals = [f[primary_metric] for f in fold_baseline_metrics]

    cand_mean = sum(candidate_vals) / n_folds
    sorted_cand = sorted(candidate_vals)
    cand_median = sorted_cand[n_folds // 2]
    cand_min = min(candidate_vals)
    cand_max = max(candidate_vals)
    cand_std = (
        math.sqrt(sum((v - cand_mean) ** 2 for v in candidate_vals) / (n_folds - 1))
        if n_folds > 1
        else 0.0
    )

    base_mean = sum(baseline_vals) / n_folds

    # Improvements per fold
    fold_improvements = []
    superior_folds = 0
    for c, b in zip(candidate_vals, baseline_vals):
        diff = (b - c) if not higher_is_better else (c - b)
        rel_diff = diff / abs(b) if abs(b) > 1e-12 else 0.0
        is_superior = diff > 0
        if is_superior:
            superior_folds += 1
        fold_improvements.append({
            "candidate": round(c, 6),
            "baseline": round(b, 6),
            "absolute_diff": round(diff, 6),
            "relative_diff": round(rel_diff, 4),
            "is_superior": is_superior,
        })

    total_diff = (base_mean - cand_mean) if not higher_is_better else (cand_mean - base_mean)
    total_rel_diff = total_diff / abs(base_mean) if abs(base_mean) > 1e-12 else 0.0

    # Classification of evidence
    if superior_folds == 0:
        evidence_class = "NO_EVIDENCE"
    elif superior_folds < n_folds:
        evidence_class = "WEAK_INCONSISTENT_EVIDENCE"
    else:
        evidence_class = "CONSISTENT_DEV_EVIDENCE"

    return {
        "primary_metric": primary_metric,
        "higher_is_better": higher_is_better,
        "n_folds": n_folds,
        "superior_folds": superior_folds,
        "evidence_classification": evidence_class,
        "candidate_summary": {
            "mean": round(cand_mean, 6),
            "median": round(cand_median, 6),
            "min": round(cand_min, 6),
            "max": round(cand_max, 6),
            "std": round(cand_std, 6),
        },
        "baseline_mean": round(base_mean, 6),
        "overall_improvement": {
            "absolute": round(total_diff, 6),
            "relative": round(total_rel_diff, 4),
        },
        "per_fold": fold_improvements,
    }


def multiple_testing_adjustment(
    p_values: Sequence[float], alpha: float = 0.05
) -> Dict[str, Any]:
    """Applies Bonferroni and Benjamini-Hochberg FDR adjustments to an array of p-values."""
    m = len(p_values)
    if m == 0:
        return {"bonferroni_threshold": alpha, "tests": []}

    bonferroni_thresh = alpha / m

    # Benjamini-Hochberg FDR calculation
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    bh_significant = [False] * m
    bh_q_values = [1.0] * m

    # Step-up procedure
    max_k = -1
    for k in range(m - 1, -1, -1):
        rank = k + 1
        orig_idx, p_val = indexed[k]
        threshold = (rank / m) * alpha
        if p_val <= threshold:
            max_k = k
            break

    if max_k >= 0:
        for k in range(max_k + 1):
            orig_idx, _ = indexed[k]
            bh_significant[orig_idx] = True

    # Compute adjusted p-values (q-values)
    running_min = 1.0
    for k in range(m - 1, -1, -1):
        rank = k + 1
        orig_idx, p_val = indexed[k]
        q = min(1.0, (m / rank) * p_val)
        running_min = min(running_min, q)
        bh_q_values[orig_idx] = running_min

    tests_summary = []
    for i, p in enumerate(p_values):
        tests_summary.append({
            "test_index": i,
            "raw_p_value": round(p, 6),
            "raw_significant": p < alpha,
            "bonferroni_significant": p < bonferroni_thresh,
            "bh_fdr_significant": bh_significant[i],
            "bh_q_value": round(bh_q_values[i], 6),
        })

    return {
        "total_hypotheses": m,
        "nominal_alpha": alpha,
        "bonferroni_threshold": round(bonferroni_thresh, 8),
        "bonferroni_rejections": sum(1 for p in p_values if p < bonferroni_thresh),
        "bh_fdr_rejections": sum(1 for s in bh_significant if s),
        "tests": tests_summary,
    }
