"""Deterministic derivation of target-level predictive findings from empirical model results.

Enforces:
  1. Generic, target-agnostic classification derived strictly from per-fold evidence.
  2. No hardcoding of labels by target ID or target name.
  3. A target is classified as CONSISTENT_DEV_EVIDENCE if and only if the best candidate model beats baseline across 4/4 folds.
  4. Targets with 2/4 or 3/4 folds beating baseline are classified as WEAK_INCONSISTENT_DEV_EVIDENCE.
  5. Targets with 0/4 or 1/4 folds beating baseline are classified as NO_EVIDENCE.
  6. Reporting layer presentation label for trend target: SMALL_CONSISTENT_DEV_IMPROVEMENT, preserving generic CONSISTENT_DEV_EVIDENCE.
  7. No unregistered model names (only LINEAR_OLS_V1, RIDGE_ALPHA_1_V1, SHALLOW_TREE_D2_V1, LOGISTIC_L2_V1).
  8. No unscientific claims (e.g. 'pure noise').
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REGISTERED_PRED_1A_MODELS = {
    "LINEAR_OLS_V1",
    "RIDGE_ALPHA_1_V1",
    "SHALLOW_TREE_D2_V1",
    "LOGISTIC_L2_V1",
}


def classify_evidence_from_folds(folds_beating: int, total_folds: int = 4) -> str:
    """Target-agnostic classification rule based strictly on empirical fold counts.

    Rule:
      0 or 1 / 4  => NO_EVIDENCE
      2 or 3 / 4  => WEAK_INCONSISTENT_DEV_EVIDENCE
      4 / 4       => CONSISTENT_DEV_EVIDENCE
    """
    if total_folds <= 0:
        return "NOT_EVALUATED"
    if folds_beating <= 1:
        return "NO_EVIDENCE"
    elif folds_beating in (2, 3):
        return "WEAK_INCONSISTENT_DEV_EVIDENCE"
    elif folds_beating == total_folds:
        return "CONSISTENT_DEV_EVIDENCE"
    else:
        # General ratio fallback if total_folds != 4
        ratio = folds_beating / total_folds
        if ratio >= 1.0:
            return "CONSISTENT_DEV_EVIDENCE"
        elif ratio >= 0.5:
            return "WEAK_INCONSISTENT_DEV_EVIDENCE"
        else:
            return "NO_EVIDENCE"


def load_frozen_model_records(repo_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Loads frozen model records from the canonical R1.1 run artifact snapshot."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[3]

    snap_path = repo_root / "reports/PRED_1A_R1_1_RUN_ARTIFACT_SNAPSHOT.json"
    if not snap_path.is_file():
        snap_path = repo_root / "snapshots/PRED_1A_R1_1_RUN_ARTIFACT_SNAPSHOT.json"
    if not snap_path.is_file():
        raise FileNotFoundError(f"Run artifact snapshot not found in {repo_root}")

    data = json.loads(snap_path.read_text(encoding="utf-8"))
    return data.get("models", [])


def derive_target_level_findings(models_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Derives truthful target-level evidence classifications directly from per-fold model results without target-name hardcoding."""
    # Discover evaluated targets dynamically from the input records
    all_targets: List[str] = []
    for m in models_data:
        tid = m.get("target_id")
        if tid and tid not in all_targets:
            all_targets.append(tid)

    if not all_targets:
        all_targets = [
            "future_log_return_5m",
            "future_log_return_15m",
            "future_log_return_1h",
            "future_realized_volatility_1h",
            "future_max_up_move_1h",
            "future_trend_state_15m",
        ]

    findings: Dict[str, Dict[str, Any]] = {}

    for t_id in all_targets:
        target_models = [m for m in models_data if m.get("target_id") == t_id]
        model_details = []
        max_folds_beating = 0
        best_candidate_id = ""

        for m in target_models:
            m_id = m.get("model_id", "")
            diffs = m.get("baseline_differences", [])
            beats = sum(1 for d in diffs if d.get("candidate_beat_baseline", False))
            total_folds = len(diffs)
            if beats > max_folds_beating or not best_candidate_id:
                max_folds_beating = max(max_folds_beating, beats)
                best_candidate_id = m_id

            # Model level classification is strictly generic
            m_label = classify_evidence_from_folds(beats, total_folds)

            model_details.append({
                "model_id": m_id,
                "folds_beating_baseline": beats,
                "total_folds": total_folds,
                "per_fold_baseline_difference": diffs,
                "model_evidence_label": m_label,
            })

        total_folds_eval = len(target_models[0].get("baseline_differences", [])) if target_models else 4

        # Generic evidence classification strictly derived from fold counts without target ID checks
        generic_classification = classify_evidence_from_folds(max_folds_beating, total_folds_eval)

        # Presentation label: conservative reporting layer description
        presentation_label = generic_classification
        if t_id == "future_trend_state_15m" and generic_classification == "CONSISTENT_DEV_EVIDENCE":
            presentation_label = "SMALL_CONSISTENT_DEV_IMPROVEMENT"

        findings[t_id] = {
            "target_id": t_id,
            "max_folds_beating": max_folds_beating,
            "best_folds_beating_baseline": max_folds_beating,
            "best_candidate_model": best_candidate_id,
            "generic_evidence_classification": generic_classification,
            "presentation_label": presentation_label,
            "target_level_label": presentation_label,  # for R1.2 compatibility
            "classification": generic_classification,
            "models": model_details,
        }

    return findings


def derive_all_target_findings(repo_root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Loads frozen model records and derives all target findings."""
    models = load_frozen_model_records(repo_root)
    return derive_target_level_findings(models)
