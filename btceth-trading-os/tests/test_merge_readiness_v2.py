from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_hardened_merge_readiness import (
    ROOT,
    REPORTS,
    compute_canonical_payload_sha256,
    check_tree_exists,
    check_commit_exists,
)
from tools.verify_canonical_post_merge import evaluate_canonical_post_merge


def test_positive_genuine_v2_provenance_payload_hash() -> None:
    """Positive test: genuine committed historical V2 report has exact matching canonical hash and valid payload."""
    v2_path = REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.json"
    assert v2_path.is_file(), "V2 report must exist"

    data = json.loads(v2_path.read_text(encoding="utf-8"))
    stored_sha = data.get("provenance_payload_sha256")
    expected_stored_sha = "2efaa600d09116339cc23aa633ef5e5bdb2c3acaf7904f279f8a35ae48590664"

    assert stored_sha == expected_stored_sha, f"Expected {expected_stored_sha}, got {stored_sha}"
    computed_sha = compute_canonical_payload_sha256(data)
    assert computed_sha == stored_sha, f"Computed hash {computed_sha} must equal stored hash {stored_sha}"

    # Verify historical recorded payload integrity
    assert data.get("readiness_status") == "VERIFIED"
    assert data.get("security_status") == "ZERO"
    assert data.get("holdout_status") == "LOCKED"
    assert data.get("funding_parity_mode") == "LIVE_REST"
    assert data.get("archive_count") == 15
    assert data.get("silver_parquet_sha256") == "b4b77ca9497759ac8ee831a7c12ac963a6c5a2309a65d19f58c2da8e8d774513"
    assert data.get("dataset_v3_1_full_logical_sha") == "a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930"


def test_negative_tampered_provenance_payload_fails(tmp_path: Path) -> None:
    """Negative test: tampering with any payload field without updating hash fails cryptographic check."""
    v2_path = REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.json"
    data = json.loads(v2_path.read_text(encoding="utf-8"))
    stored_sha = data.get("provenance_payload_sha256")

    # Deliberately mutate a payload value without updating provenance_payload_sha256
    data["archive_count"] = 9999
    computed_sha = compute_canonical_payload_sha256(data)

    assert computed_sha != stored_sha, "Tampered payload must not match stored hash"


def test_tree_object_verification() -> None:
    """Verify tree object existence and match against c316a0814f651aece0e4be248e0eee10ce0c18e3^{tree}."""
    expected_tree = "252d9574d9c28e9835d280a7eeade3b2528dfd5d"
    expected_code_sha = "c316a0814f651aece0e4be248e0eee10ce0c18e3"

    assert check_tree_exists(expected_tree), f"Tree object {expected_tree} must exist in Git database"

    rev_proc = subprocess.run(
        ["git", "rev-parse", f"{expected_code_sha}^{{tree}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert rev_proc.stdout.strip() == expected_tree


def test_v2_provenance_sha_references() -> None:
    """Verify all commit-like SHA references inside V2 provenance resolve in Git database."""
    v2_path = REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.json"
    data = json.loads(v2_path.read_text(encoding="utf-8"))

    commit_keys = [
        "base_shared_commit_sha",
        "tested_code_commit_sha",
        "verification_parent_head_sha",
        "remediation_code_commit_sha",
        "remediation_branch_head_sha",
        "round3b_wip_safety_sha",
        "pre_hardening_snapshot_sha",
    ]

    for k in commit_keys:
        val = data.get(k)
        assert isinstance(val, str) and len(val) == 40, f"Key {k} must be a 40-char SHA string, got {val}"
        assert check_commit_exists(val), f"Commit SHA for {k} ({val}) must exist in Git database"


def test_canonical_post_merge_readiness_positive() -> None:
    """Positive test: canonical post-merge verification passes on canonical branch."""
    all_passed, checks, status, details = evaluate_canonical_post_merge(skip_sub_tests=True)
    assert status == "VERIFIED", f"Expected VERIFIED, got {status} with checks: {checks}"
    assert all_passed is True


def test_canonical_post_merge_tamper_detection_negative(tmp_path: Path) -> None:
    """Negative test: tampering with milestone acceptance causes post-merge verifier to fail closed."""
    # Copy genuine reports to tmp dir and tamper with one
    tmp_reports = tmp_path / "reports"
    shutil.copytree(REPORTS, tmp_reports)

    tampered_p1a = tmp_reports / "PHASE_1A_ACCEPTANCE.json"
    p1a_data = json.loads(tampered_p1a.read_text(encoding="utf-8"))
    p1a_data["status"] = "TAMPERED_FAILED"
    tampered_p1a.write_text(json.dumps(p1a_data, indent=2), encoding="utf-8")

    all_passed, checks, status, details = evaluate_canonical_post_merge(
        skip_sub_tests=True,
        override_reports_dir=tmp_reports,
    )
    assert all_passed is False
    assert status == "REMEDIATION_REQUIRED"
    assert checks["PHASE_1A_PASS"] is False
