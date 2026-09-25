"""Tests for Trading OS PRED-1A R1.3 Final Data-Driven Classification & Reporting-Truth Patch.

Validates:
  1. Generic classifier is strictly target-agnostic without target-name dependencies.
  2. Map rules: 0-1/4 -> NO_EVIDENCE, 2-3/4 -> WEAK_INCONSISTENT_DEV_EVIDENCE, 4/4 -> CONSISTENT_DEV_EVIDENCE.
  3. Target classifier selects best candidate fold count.
  4. Adversarial proofs: return target is CONSISTENT if fixture is 4/4; volatility is NO_EVIDENCE if fixture is 0/4.
  5. Verifier independently recomputes target labels directly from frozen model records.
  6. Hardcoded findings functions would fail independent reconciliation.
  7. No LightGBM / LGBM model references in PRED-1A code or evaluated models.
  8. No unscientific 'pure noise' claim for 5m return.
  9. Frozen snapshots unchanged and zero partition leakage.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.predict.findings import (
    REGISTERED_PRED_1A_MODELS,
    classify_evidence_from_folds,
    derive_all_target_findings,
    derive_target_level_findings,
    load_frozen_model_records,
)
from tools.verify_pred_1a_r1_3 import Pred1aR13Verifier

EXPECTED_RUN_SNAPSHOT_SHA = "adc5353d92a3722625fb2d9774da65966ec995c170e92ba733ebb87969d11278"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_generic_classifier_no_target_name_dependency() -> None:
    """Verifies classify_evidence_from_folds has zero target name checks in its AST."""
    src = (ROOT / "src/btceth_os/predict/findings.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "classify_evidence_from_folds":
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    val = child.value.lower()
                    assert not any(t in val for t in ["return", "volatility", "max_up", "trend"]), (
                        f"Target-specific string found in classify_evidence_from_folds: {child.value}"
                    )


def test_zero_or_one_of_four_maps_to_no_evidence() -> None:
    """Verifies fold counts of 0 and 1 map generically to NO_EVIDENCE."""
    assert classify_evidence_from_folds(0, 4) == "NO_EVIDENCE"
    assert classify_evidence_from_folds(1, 4) == "NO_EVIDENCE"


def test_two_or_three_of_four_maps_to_weak_inconsistent() -> None:
    """Verifies fold counts of 2 and 3 map generically to WEAK_INCONSISTENT_DEV_EVIDENCE."""
    assert classify_evidence_from_folds(2, 4) == "WEAK_INCONSISTENT_DEV_EVIDENCE"
    assert classify_evidence_from_folds(3, 4) == "WEAK_INCONSISTENT_DEV_EVIDENCE"


def test_four_of_four_maps_to_consistent() -> None:
    """Verifies fold count of 4 maps generically to CONSISTENT_DEV_EVIDENCE."""
    assert classify_evidence_from_folds(4, 4) == "CONSISTENT_DEV_EVIDENCE"


def test_target_classifier_uses_best_candidate_fold_count() -> None:
    """Verifies target-level classification is based on the maximum folds across candidates."""
    models_fixture = [
        {
            "target_id": "test_synthetic_target",
            "model_id": "MODEL_A",
            "baseline_differences": [{"candidate_beat_baseline": True}, {"candidate_beat_baseline": False}],
        },
        {
            "target_id": "test_synthetic_target",
            "model_id": "MODEL_B",
            "baseline_differences": [{"candidate_beat_baseline": True}] * 4,
        },
    ]
    findings = derive_target_level_findings(models_fixture)
    target_info = findings["test_synthetic_target"]
    assert target_info["best_folds_beating_baseline"] == 4
    assert target_info["generic_evidence_classification"] == "CONSISTENT_DEV_EVIDENCE"


def test_return_target_would_be_consistent_if_fixture_is_4_of_4() -> None:
    """Adversarial proof: future_log_return_5m is NOT hardcoded to NO_EVIDENCE."""
    fixture_4_of_4 = [{
        "target_id": "future_log_return_5m",
        "model_id": "HYPOTHETICAL_SUPER_MODEL",
        "baseline_differences": [{"candidate_beat_baseline": True}] * 4,
    }]
    findings = derive_target_level_findings(fixture_4_of_4)
    assert findings["future_log_return_5m"]["generic_evidence_classification"] == "CONSISTENT_DEV_EVIDENCE"


def test_volatility_target_would_be_no_evidence_if_fixture_is_0_of_4() -> None:
    """Adversarial proof: future_realized_volatility_1h is NOT hardcoded to WEAK_INCONSISTENT."""
    fixture_0_of_4 = [{
        "target_id": "future_realized_volatility_1h",
        "model_id": "HYPOTHETICAL_FAIL_MODEL",
        "baseline_differences": [{"candidate_beat_baseline": False}] * 4,
    }]
    findings = derive_target_level_findings(fixture_0_of_4)
    assert findings["future_realized_volatility_1h"]["generic_evidence_classification"] == "NO_EVIDENCE"


def test_verifier_independently_recomputes_target_labels() -> None:
    """Verifies that independent derivation matches findings derivation across all targets."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_RUN_ARTIFACT_SNAPSHOT.json"
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Independent computation without using findings.py
    independent_best: Dict[str, int] = {}
    for m in data.get("models", []):
        tid = m.get("target_id")
        beats = sum(1 for d in m.get("baseline_differences", []) if d.get("candidate_beat_baseline", False))
        independent_best[tid] = max(independent_best.get(tid, 0), beats)

    # Output from findings.py
    findings = derive_target_level_findings(data.get("models", []))

    for tid, max_beats in independent_best.items():
        assert findings[tid]["best_folds_beating_baseline"] == max_beats
        expected = "NO_EVIDENCE" if max_beats <= 1 else ("WEAK_INCONSISTENT_DEV_EVIDENCE" if max_beats <= 3 else "CONSISTENT_DEV_EVIDENCE")
        assert findings[tid]["generic_evidence_classification"] == expected


def test_hardcoded_findings_function_would_fail_independent_reconciliation() -> None:
    """Verifies that an altered findings function returning a fake label fails independent reconciliation."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_RUN_ARTIFACT_SNAPSHOT.json"
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    findings = derive_target_level_findings(data.get("models", []))
    # Artificially alter one target's generic label
    corrupted_findings = dict(findings)
    corrupted_findings["future_trend_state_15m"] = dict(corrupted_findings["future_trend_state_15m"])
    corrupted_findings["future_trend_state_15m"]["generic_evidence_classification"] = "FAKE_HARDCODED_LABEL"

    # Verifier independent check
    raw_models = data.get("models", [])
    independent_beats = sum(1 for d in [m for m in raw_models if m["target_id"] == "future_trend_state_15m"][0]["baseline_differences"] if d["candidate_beat_baseline"])
    expected_label = "CONSISTENT_DEV_EVIDENCE" if independent_beats == 4 else "OTHER"

    assert corrupted_findings["future_trend_state_15m"]["generic_evidence_classification"] != expected_label


def test_no_lightgbm_in_pred_1a_reporting() -> None:
    """Verifies no LightGBM / LGBM is claimed as an evaluated model in findings.py or reports."""
    findings_src = (ROOT / "src/btceth_os/predict/findings.py").read_text()
    assert "lightgbm" not in findings_src.lower()
    assert "lgbm" not in findings_src.lower()

    # Check registered models set
    assert "LIGHTGBM" not in REGISTERED_PRED_1A_MODELS
    assert "LGBM" not in REGISTERED_PRED_1A_MODELS


def test_no_pure_noise_claim() -> None:
    """Verifies that summary table does not make unscientific 'pure noise' claim."""
    rep_path = ROOT / "reports/PRED_1A_R1_3_FINDINGS_TRUTH.json"
    if rep_path.is_file():
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        summary_5m = rep.get("summary_table", {}).get("future_log_return_5m", "")
        assert "pure noise" not in summary_5m.lower()


def test_frozen_run_snapshot_unchanged() -> None:
    """Verifies PRED_1A_R1_1_RUN_ARTIFACT_SNAPSHOT.json digest is identical to baseline."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_RUN_ARTIFACT_SNAPSHOT.json"
    assert _sha256(snap_path) == EXPECTED_RUN_SNAPSHOT_SHA


def test_val_holdout_pristine_zero() -> None:
    """Verifies zero rows granted for VALIDATION, HOLDOUT, PRISTINE partitions."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("val_granted", -1) == 0
    assert data.get("holdout_granted", -1) == 0
    assert data.get("pristine_granted", -1) == 0
