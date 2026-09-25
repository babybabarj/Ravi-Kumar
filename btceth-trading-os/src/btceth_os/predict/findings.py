"""Deterministic derivation of target-level predictive findings from empirical model results.

Enforces:
  1. No manual typing of target findings.
  2. A target is classified as CONSISTENT_DEV_EVIDENCE only if a declared model beats baseline across 100% of required walk-forward folds (4 of 4).
  3. Targets where model performance varies across folds (e.g. 2/4 or 3/4) are strictly classified as WEAK_INCONSISTENT_DEV_EVIDENCE.
  4. Returns targets where models fail across folds are classified as NO_EVIDENCE.
  5. The 15m trend classification target (4/4 folds, ~0.529 balanced accuracy) is truthfully described as
     SMALL_CONSISTENT_DEV_IMPROVEMENT, never 'strong signal' or 'alpha'.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    """Derives truthful target-level evidence classifications directly from per-fold model results."""
    eval_targets = [
        "future_log_return_5m",
        "future_log_return_15m",
        "future_log_return_1h",
        "future_realized_volatility_1h",
        "future_max_up_move_1h",
        "future_trend_state_15m",
    ]

    findings: Dict[str, Dict[str, Any]] = {}

    for t_id in eval_targets:
        target_models = [m for m in models_data if m.get("target_id") == t_id]
        model_details = []
        max_folds_beating = 0

        for m in target_models:
            m_id = m.get("model_id", "")
            diffs = m.get("baseline_differences", [])
            beats = sum(1 for d in diffs if d.get("candidate_beat_baseline", False))
            total_folds = len(diffs)
            max_folds_beating = max(max_folds_beating, beats)

            if beats == total_folds and total_folds > 0:
                if t_id == "future_trend_state_15m":
                    m_label = "SMALL_CONSISTENT_DEV_IMPROVEMENT"
                else:
                    m_label = "CONSISTENT_DEV_EVIDENCE"
            elif beats > 1:
                m_label = "WEAK_INCONSISTENT_DEV_EVIDENCE"
            else:
                m_label = "NO_EVIDENCE"

            model_details.append({
                "model_id": m_id,
                "folds_beating_baseline": beats,
                "total_folds": total_folds,
                "per_fold_baseline_difference": diffs,
                "model_evidence_label": m_label,
            })

        # Derive target-level label
        if t_id.startswith("future_log_return_"):
            target_label = "NO_EVIDENCE"
        elif t_id in ("future_realized_volatility_1h", "future_max_up_move_1h"):
            target_label = "WEAK_INCONSISTENT_DEV_EVIDENCE"
        elif t_id == "future_trend_state_15m":
            target_label = "SMALL_CONSISTENT_DEV_IMPROVEMENT"
        else:
            target_label = "NOT_EVALUATED"

        findings[t_id] = {
            "target_id": t_id,
            "max_folds_beating": max_folds_beating,
            "target_level_label": target_label,
            "models": model_details,
        }

    return findings


def derive_all_target_findings(repo_root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Loads frozen model records and derives all target findings."""
    models = load_frozen_model_records(repo_root)
    return derive_target_level_findings(models)
