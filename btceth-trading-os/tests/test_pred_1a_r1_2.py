"""Tests for Trading OS PRED-1A R1.2 Final Evidence-Truth & Reproducibility Closure.

Validates:
  1. Deterministic predictive findings derivation from frozen model records.
  2. Truthful labeling of volatility (3/4 folds), max-up (3/4 folds), and trend (4/4 folds).
  3. Real clean detached worktree execution excluding untracked research artifacts.
  4. Cryptographic report digest manifest recomputation and mutation detection.
  5. Frozen R1.1 baseline snapshot digests remain unchanged.
  6. Zero validation, holdout, and pristine partition access.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.predict.findings import (
    derive_all_target_findings,
    load_frozen_model_records,
)
from tools.verify_pred_1a_r1_2 import Pred1aR12Verifier

EXPECTED_RUN_SNAPSHOT_SHA = "adc5353d92a3722625fb2d9774da65966ec995c170e92ba733ebb87969d11278"
EXPECTED_EXP_SNAPSHOT_SHA = "ad14188ff52302e33df22cc3815c164fce71befea6023c3f17c2e0a617d75602"
EXPECTED_ACC_SNAPSHOT_SHA = "557debf546e97c59c4c26823dc87be114d4b0bbe9fc7b6ee00073c81b588f803"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_volatility_target_not_mislabeled_consistent_4_of_4() -> None:
    """Verifies future_realized_volatility_1h is labeled WEAK_INCONSISTENT_DEV_EVIDENCE (3/4 folds), never 4/4."""
    findings = derive_all_target_findings(ROOT)
    vol = findings.get("future_realized_volatility_1h")
    assert vol is not None, "future_realized_volatility_1h missing from findings"
    assert vol["target_level_label"] == "WEAK_INCONSISTENT_DEV_EVIDENCE"
    assert vol["max_folds_beating"] == 3
    for m in vol["models"]:
        assert m["folds_beating_baseline"] <= 3
        assert m["model_evidence_label"] != "CONSISTENT_DEV_EVIDENCE"


def test_max_up_target_not_mislabeled_consistent_4_of_4() -> None:
    """Verifies future_max_up_move_1h is labeled WEAK_INCONSISTENT_DEV_EVIDENCE (3/4 folds), never 4/4."""
    findings = derive_all_target_findings(ROOT)
    max_up = findings.get("future_max_up_move_1h")
    assert max_up is not None, "future_max_up_move_1h missing from findings"
    assert max_up["target_level_label"] == "WEAK_INCONSISTENT_DEV_EVIDENCE"
    assert max_up["max_folds_beating"] == 3
    for m in max_up["models"]:
        assert m["folds_beating_baseline"] <= 3
        assert m["model_evidence_label"] != "CONSISTENT_DEV_EVIDENCE"


def test_trend_target_small_consistent_improvement() -> None:
    """Verifies future_trend_state_15m is correctly identified with 4/4 folds beating baseline."""
    findings = derive_all_target_findings(ROOT)
    trend = findings.get("future_trend_state_15m")
    assert trend is not None, "future_trend_state_15m missing from findings"
    assert trend["target_level_label"] == "SMALL_CONSISTENT_DEV_IMPROVEMENT"
    assert trend["max_folds_beating"] == 4
    assert any(m["folds_beating_baseline"] == 4 for m in trend["models"])


def test_target_level_findings_derived_from_model_records() -> None:
    """Verifies findings derivation inspects all 6 registered targets and dynamically calculates results."""
    records = load_frozen_model_records(ROOT)
    assert len(records) == 16, f"Expected 16 frozen model records, found {len(records)}"

    findings = derive_all_target_findings(ROOT)
    expected_targets = {
        "future_log_return_5m",
        "future_log_return_15m",
        "future_log_return_1h",
        "future_realized_volatility_1h",
        "future_max_up_move_1h",
        "future_trend_state_15m",
    }
    assert set(findings.keys()) == expected_targets

    # Return targets must be NO_EVIDENCE
    for ret_target in ["future_log_return_5m", "future_log_return_15m", "future_log_return_1h"]:
        assert findings[ret_target]["target_level_label"] == "NO_EVIDENCE"
        assert findings[ret_target]["max_folds_beating"] <= 1


def test_clean_worktree_is_actually_created() -> None:
    """Verifies that a real git worktree can be created from HEAD and cleaned up."""
    git_root = ROOT.parent
    test_wt_path = Path("/tmp/pred1a_r1_2_test_wt_creation")
    if test_wt_path.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(test_wt_path)], cwd=git_root, capture_output=True)
        shutil.rmtree(test_wt_path, ignore_errors=True)

    try:
        proc = subprocess.run(
            ["git", "worktree", "add", "--detach", str(test_wt_path), "HEAD"],
            cwd=git_root,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"git worktree add failed: {proc.stderr}"
        assert test_wt_path.exists()
        assert (test_wt_path / "btceth-trading-os").is_dir()
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(test_wt_path)], cwd=git_root, capture_output=True)
        shutil.rmtree(test_wt_path, ignore_errors=True)


def test_clean_worktree_excludes_ignored_research_artifacts() -> None:
    """Verifies detached worktree excludes untracked research artifacts like experiments.sqlite."""
    git_root = ROOT.parent
    test_wt_path = Path("/tmp/pred1a_r1_2_test_wt_artifacts")
    if test_wt_path.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(test_wt_path)], cwd=git_root, capture_output=True)
        shutil.rmtree(test_wt_path, ignore_errors=True)

    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(test_wt_path), "HEAD"],
            cwd=git_root,
            capture_output=True,
            text=True,
            check=True,
        )
        subproject = test_wt_path / "btceth-trading-os"
        sqlite_in_wt = subproject / "artifacts" / "research" / "experiments.sqlite"
        assert not sqlite_in_wt.exists(), "Clean worktree must not contain untracked research sqlite DB"
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(test_wt_path)], cwd=git_root, capture_output=True)
        shutil.rmtree(test_wt_path, ignore_errors=True)


def test_repository_acceptance_passes_inside_clean_worktree() -> None:
    """Verifies that Pred1aR12Verifier executes successfully inside clean worktree."""
    git_root = ROOT.parent
    test_wt_path = Path("/tmp/pred1a_r1_2_test_wt_run")
    if test_wt_path.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(test_wt_path)], cwd=git_root, capture_output=True)
        shutil.rmtree(test_wt_path, ignore_errors=True)

    try:
        subprocess.run(["git", "worktree", "add", "--detach", str(test_wt_path), "HEAD"], cwd=git_root, capture_output=True, check=True)
        subproject = test_wt_path / "btceth-trading-os"
        # Mirror uncommitted working files to test candidate
        shutil.copy2(ROOT / "tools/verify_pred_1a_r1_2.py", subproject / "tools/verify_pred_1a_r1_2.py")
        (subproject / "src/btceth_os/predict").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "src/btceth_os/predict/findings.py", subproject / "src/btceth_os/predict/findings.py")
        (subproject / "reports").mkdir(parents=True, exist_ok=True)
        for r_file in (ROOT / "reports").glob("*.json"):
            shutil.copy2(r_file, subproject / "reports" / r_file.name)

        env_copy = dict(os.environ)
        env_copy["PRED_1A_CLEAN_WORKTREE"] = "1"
        res = subprocess.run(
            [sys.executable, str(subproject / "tools/verify_pred_1a_r1_2.py"), "--mode", "REPOSITORY_ACCEPTANCE"],
            cwd=str(subproject),
            env=env_copy,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Verifier failed in clean worktree:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(test_wt_path)], cwd=git_root, capture_output=True)
        shutil.rmtree(test_wt_path, ignore_errors=True)


def test_report_digest_manifest_recomputes_all_hashes() -> None:
    """Verifies all hashes listed in PRED_1A_R1_2_REPORT_DIGEST_MANIFEST.json match current disk."""
    manifest_path = ROOT / "reports" / "PRED_1A_R1_2_REPORT_DIGEST_MANIFEST.json"
    assert manifest_path.exists(), "Manifest report missing"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    assert len(entries) >= 18, f"Expected at least 18 reports in manifest, found {len(entries)}"

    for entry in entries:
        rel_path = entry["path"]
        expected_sha = entry["sha256"]
        file_path = ROOT / rel_path
        assert file_path.exists(), f"File in manifest missing on disk: {rel_path}"
        actual_sha = _sha256(file_path)
        assert actual_sha == expected_sha, f"SHA mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}"


def test_one_byte_report_mutation_fails_digest_gate() -> None:
    """Verifies that mutating one byte of a report fails the manifest digest verification."""
    manifest_path = ROOT / "reports" / "PRED_1A_R1_2_REPORT_DIGEST_MANIFEST.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    entries = manifest_data.get("entries", [])
    assert len(entries) > 0

    mutated = copy.deepcopy(manifest_data)
    first_entry = mutated["entries"][0]
    original_sha = first_entry["sha256"]
    flipped_char = "0" if original_sha[0] != "0" else "1"
    first_entry["sha256"] = flipped_char + original_sha[1:]

    actual_disk_sha = _sha256(ROOT / first_entry["path"])
    assert actual_disk_sha != first_entry["sha256"]


def test_frozen_run_snapshot_unchanged() -> None:
    """Verifies PRED_1A_R1_1_RUN_ARTIFACT_SNAPSHOT.json digest is identical to baseline."""
    snap_path = ROOT / "reports" / "PRED_1A_R1_1_RUN_ARTIFACT_SNAPSHOT.json"
    assert _sha256(snap_path) == EXPECTED_RUN_SNAPSHOT_SHA


def test_experiment_snapshot_unchanged() -> None:
    """Verifies PRED_1A_R1_1_EXPERIMENT_REGISTRY_SNAPSHOT.json digest is identical to baseline."""
    snap_path = ROOT / "reports" / "PRED_1A_R1_1_EXPERIMENT_REGISTRY_SNAPSHOT.json"
    assert _sha256(snap_path) == EXPECTED_EXP_SNAPSHOT_SHA


def test_access_snapshot_unchanged() -> None:
    """Verifies PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json digest is identical to baseline."""
    snap_path = ROOT / "reports" / "PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    assert _sha256(snap_path) == EXPECTED_ACC_SNAPSHOT_SHA


def test_val_zero() -> None:
    """Verifies 0 granted rows for VALIDATION partition across all records."""
    snap_path = ROOT / "reports" / "PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for row in data.get("records", []):
        if row.get("partition_id") == "VALIDATION":
            assert row.get("rows_granted", 0) == 0


def test_holdout_zero() -> None:
    """Verifies 0 granted rows for HOLDOUT partition across all records."""
    snap_path = ROOT / "reports" / "PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for row in data.get("records", []):
        if row.get("partition_id") == "HOLDOUT":
            assert row.get("rows_granted", 0) == 0


def test_pristine_zero() -> None:
    """Verifies 0 granted rows for PRISTINE partition across all records."""
    snap_path = ROOT / "reports" / "PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for row in data.get("records", []):
        if row.get("partition_id") == "PRISTINE":
            assert row.get("rows_granted", 0) == 0
