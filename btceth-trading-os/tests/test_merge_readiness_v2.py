from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.verify_hardened_merge_readiness import (
    ROOT,
    REPORTS,
    compute_canonical_payload_sha256,
    evaluate_readiness,
    check_tree_exists,
    check_commit_exists,
)


def test_positive_genuine_v2_provenance_payload_hash() -> None:
    """Positive test: genuine committed V2 report has exact matching canonical hash."""
    v2_path = REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.json"
    assert v2_path.is_file(), "V2 report must exist"

    data = json.loads(v2_path.read_text(encoding="utf-8"))
    stored_sha = data.get("provenance_payload_sha256")
    expected_stored_sha = "2efaa600d09116339cc23aa633ef5e5bdb2c3acaf7904f279f8a35ae48590664"

    assert stored_sha == expected_stored_sha, f"Expected {expected_stored_sha}, got {stored_sha}"
    computed_sha = compute_canonical_payload_sha256(data)
    assert computed_sha == stored_sha, f"Computed hash {computed_sha} must equal stored hash {stored_sha}"

    # Evaluate using the verifier logic
    all_ready, checks, verif_status, details = evaluate_readiness(skip_sub_tests=True)
    assert checks["provenance_payload_sha256_matches"] is True
    assert verif_status == "VERIFIED"
    assert all_ready is True


def test_negative_tampered_provenance_payload_fails(tmp_path: Path) -> None:
    """Negative test: tampering with any payload field without updating hash causes failure."""
    v2_path = REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.json"
    data = json.loads(v2_path.read_text(encoding="utf-8"))

    # Deliberately mutate a payload value without updating provenance_payload_sha256
    data["archive_count"] = 9999
    tampered_file = tmp_path / "tampered_v2.json"
    tampered_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    all_ready, checks, verif_status, details = evaluate_readiness(override_v2_path=tampered_file, skip_sub_tests=True)

    assert checks["provenance_payload_sha256_matches"] is False
    assert all_ready is False
    assert verif_status == "REMEDIATION_REQUIRED"


def test_negative_cli_exit_code_on_tamper(tmp_path: Path) -> None:
    """Negative CLI test: verifier process exits non-zero when hash is tampered."""
    v2_path = REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.json"
    data = json.loads(v2_path.read_text(encoding="utf-8"))

    # Tamper a boolean check
    data["working_tree_clean_before"] = False
    tampered_file = tmp_path / "tampered_cli.json"
    tampered_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "verify_hardened_merge_readiness.py"), "--test-path", str(tampered_file), "--skip-sub-tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0, f"Expected non-zero exit code, got {proc.returncode}"
    assert "HARDENED_MERGE_READINESS_V2 = REMEDIATION_REQUIRED" in proc.stdout
    assert "provenance_payload_sha256_matches = False" in proc.stdout


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
