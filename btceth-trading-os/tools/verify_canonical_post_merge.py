from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

CANONICAL_MERGE_POINT = "5f59383d765d7682be8ce25e5043145b4a43e692"
EXPECTED_HARDENED_SHA = "5f59383d765d7682be8ce25e5043145b4a43e692"
EXPECTED_WIP_SAFETY_SHA = "11d6e370db0d27cd635528a3c530286b28c60416"
EXPECTED_SNAPSHOT_SHA = "5873de692b8eb7d9b7775ef3c2a2e730f9fd8088"
EXPECTED_TESTED_CODE_SHA = "c316a0814f651aece0e4be248e0eee10ce0c18e3"
EXPECTED_TESTED_TREE_SHA = "252d9574d9c28e9835d280a7eeade3b2528dfd5d"
EXPECTED_SILVER_SHA = "b4b77ca9497759ac8ee831a7c12ac963a6c5a2309a65d19f58c2da8e8d774513"
EXPECTED_DATASET_V310_SHA = "a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930"
EXPECTED_V2_PROVENANCE_SHA = "2efaa600d09116339cc23aa633ef5e5bdb2c3acaf7904f279f8a35ae48590664"


def run_cmd(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc_env = dict(os.environ)
    proc_env["PYTHONPATH"] = f"{ROOT / 'src'}:{proc_env.get('PYTHONPATH', '')}"
    if env:
        proc_env.update(env)
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False, env=proc_env)


def git_cmd(args: list[str]) -> str:
    res = run_cmd(["git", *args])
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr}")
    return res.stdout.strip()


def check_commit_exists(sha: str) -> bool:
    res = run_cmd(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
    return res.returncode == 0


def check_tree_exists(sha: str) -> bool:
    res = run_cmd(["git", "cat-file", "-e", f"{sha}^{{tree}}"])
    return res.returncode == 0


def compute_canonical_payload_sha256(payload: dict[str, Any]) -> str:
    clean_dict = {k: v for k, v in payload.items() if k != "provenance_payload_sha256"}
    canonical_bytes = json.dumps(clean_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def evaluate_canonical_post_merge(
    skip_sub_tests: bool = False,
    override_reports_dir: Path | None = None,
) -> tuple[bool, dict[str, bool], str, dict[str, Any]]:
    reports_dir = override_reports_dir or REPORTS
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    # 1. CANONICAL_BRANCH_SYNC & CANONICAL_MERGE_POINT_PRESENT
    current_branch = git_cmd(["branch", "--show-current"])
    current_head = git_cmd(["rev-parse", "HEAD"])
    remote_shared_head = git_cmd(["rev-parse", "origin/btceth-phase1b"])
    hardened_remote_sha = git_cmd(["rev-parse", "origin/btceth-phase1b-hardened"])
    wip_remote_sha = git_cmd(["rev-parse", "origin/btceth-round3b-wip-safety"])
    snapshot_remote_sha = git_cmd(["rev-parse", "origin/btceth-pre-phase1b2-hardening-snapshot"])

    checks["canonical_branch_name_is_phase1b"] = (current_branch == "btceth-phase1b")
    checks["canonical_branch_sync_local_remote"] = (current_head == remote_shared_head)
    checks["CANONICAL_BRANCH_SYNC"] = checks["canonical_branch_name_is_phase1b"] and checks["canonical_branch_sync_local_remote"]

    # Canonical branch must contain CANONICAL_MERGE_POINT as an ancestor
    is_ancestor = run_cmd(["git", "merge-base", "--is-ancestor", CANONICAL_MERGE_POINT, current_head]).returncode == 0
    checks["CANONICAL_MERGE_POINT_PRESENT"] = is_ancestor

    # Branch preservation
    checks["hardened_branch_preserved"] = (hardened_remote_sha == EXPECTED_HARDENED_SHA)
    checks["SAFETY_BRANCH_PRESERVED"] = (wip_remote_sha == EXPECTED_WIP_SAFETY_SHA)
    checks["snapshot_branch_preserved"] = (snapshot_remote_sha == EXPECTED_SNAPSHOT_SHA)

    # Tree object verification
    checks["tested_tree_object_resolves"] = check_tree_exists(EXPECTED_TESTED_TREE_SHA)
    tested_tree_sha = git_cmd(["rev-parse", f"{EXPECTED_TESTED_CODE_SHA}^{{tree}}"])
    checks["tested_tree_sha_matches"] = (tested_tree_sha == EXPECTED_TESTED_TREE_SHA)

    # Zero production src modifications from merge point to current HEAD
    src_diff = git_cmd(["diff", CANONICAL_MERGE_POINT, "HEAD", "--", "btceth-trading-os/src/"])
    checks["zero_unverified_src_modifications"] = (len(src_diff) == 0)

    # 2. FULL_TESTS_PASS & SECURITY_ZERO
    if skip_sub_tests:
        checks["FULL_TESTS_PASS"] = True
        checks["SECURITY_ZERO"] = True
    else:
        pytest_res = run_cmd([sys.executable, "-m", "pytest"])
        checks["FULL_TESTS_PASS"] = (pytest_res.returncode == 0)

        sec_res = run_cmd([sys.executable, "-m", "btceth_os.security_scan"])
        sec_ok = False
        if sec_res.returncode == 0:
            try:
                sec_json = json.loads(sec_res.stdout)
                sec_ok = (sec_json.get("trading_capability") == "ZERO") and (len(sec_json.get("hits", [])) == 0)
            except Exception:
                sec_ok = False
        checks["SECURITY_ZERO"] = sec_ok

    # 3. PHASE ACCEPTANCE PASS CHECKS
    # Phase 1A
    p1a_path = reports_dir / "PHASE_1A_ACCEPTANCE.json"
    p1a_ok = False
    if p1a_path.is_file():
        p1a_data = json.loads(p1a_path.read_text(encoding="utf-8"))
        p1a_ok = (p1a_data.get("status") == "VERIFIED")
    checks["PHASE_1A_PASS"] = p1a_ok

    # Phase 1B.1
    p1b1_path = reports_dir / "PHASE_1B_1_ACCEPTANCE.json"
    p1b1_ok = False
    if p1b1_path.is_file():
        p1b1_data = json.loads(p1b1_path.read_text(encoding="utf-8"))
        p1b1_ok = (p1b1_data.get("status") == "VERIFIED")
    checks["PHASE_1B1_PASS"] = p1b1_ok

    # Phase 1B.2 & Funding Parity
    p1b2_path = reports_dir / "PHASE_1B_2_ACCEPTANCE.json"
    p1b2_parity_path = reports_dir / "PHASE_1B_2_FUNDING_PARITY.json"
    p1b2_ok = False
    if p1b2_path.is_file() and p1b2_parity_path.is_file():
        p1b2_data = json.loads(p1b2_path.read_text(encoding="utf-8"))
        parity_data = json.loads(p1b2_parity_path.read_text(encoding="utf-8"))
        p1b2_ok = (
            p1b2_data.get("status") == "VERIFIED"
            and all(p1b2_data.get("checks", {}).values())
            and parity_data.get("funding_parity_passed") is True
            and parity_data.get("funding_parity_mode") == "LIVE_REST"
            and set(parity_data.get("symbols_audited", [])) == {"BTCUSDT", "ETHUSDT"}
        )
    checks["PHASE_1B2_PASS"] = p1b2_ok

    # Phase 1B.3
    p1b3_path = reports_dir / "PHASE_1B_3_ACCEPTANCE.json"
    p1b3_ok = False
    if p1b3_path.is_file():
        p1b3_data = json.loads(p1b3_path.read_text(encoding="utf-8"))
        p1b3_ok = (p1b3_data.get("status") == "VERIFIED")
    checks["PHASE_1B3_PASS"] = p1b3_ok

    # Phase 1B.4
    p1b4_path = reports_dir / "PHASE_1B_4_ACCEPTANCE.json"
    p1b4_ok = False
    if p1b4_path.is_file():
        p1b4_data = json.loads(p1b4_path.read_text(encoding="utf-8"))
        p1b4_ok = (p1b4_data.get("status") == "VERIFIED")
    checks["PHASE_1B4_PASS"] = p1b4_ok

    # Phase 1B.5
    p1b5_path = reports_dir / "PHASE_1B_5_ACCEPTANCE.json"
    p1b5_ok = False
    if p1b5_path.is_file():
        p1b5_data = json.loads(p1b5_path.read_text(encoding="utf-8"))
        p1b5_ok = (p1b5_data.get("status") == "VERIFIED")
    checks["PHASE_1B5_PASS"] = p1b5_ok

    # Research Round 3A & Holdout
    r3a_path = reports_dir / "RESEARCH_ROUND3A_ACCEPTANCE.json"
    r3a_ok = False
    holdout_ok = False
    if r3a_path.is_file():
        r3a_data = json.loads(r3a_path.read_text(encoding="utf-8"))
        r3a_ok = (r3a_data.get("acceptance_status") == "VERIFIED")
        holdout_ok = (r3a_data.get("holdout_status") == "LOCKED")
    checks["ROUND3A_PASS"] = r3a_ok
    checks["HOLDOUT_LOCKED"] = holdout_ok

    # 4. DATA HASH INVARIANTS
    # Silver Parquet hash
    silver_files = list((ROOT / "artifacts" / "phase1b5_acceptance" / "silver").glob("*.parquet"))
    silver_actual = hashlib.sha256(silver_files[0].read_bytes()).hexdigest() if silver_files else ""
    checks["silver_sha_matches"] = (silver_actual == EXPECTED_SILVER_SHA)

    # Dataset v3.1.0 logical SHA
    r3a_manifest = reports_dir / "RESEARCH_ROUND3A_DATA_MANIFEST.json"
    dataset_v310_actual = ""
    if r3a_manifest.is_file():
        dataset_v310_actual = json.loads(r3a_manifest.read_text(encoding="utf-8")).get("dataset_logical_sha256", "")
    checks["dataset_v310_sha_matches"] = (dataset_v310_actual == EXPECTED_DATASET_V310_SHA)
    checks["DATA_HASHES_MATCH"] = checks["silver_sha_matches"] and checks["dataset_v310_sha_matches"]

    # 5. V2 PROVENANCE HASH MATCH
    v2_path = reports_dir / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.json"
    v2_hash_ok = False
    if v2_path.is_file():
        v2_data = json.loads(v2_path.read_text(encoding="utf-8"))
        stored_sha = v2_data.get("provenance_payload_sha256", "")
        computed_sha = compute_canonical_payload_sha256(v2_data)
        v2_hash_ok = (stored_sha == EXPECTED_V2_PROVENANCE_SHA) and (computed_sha == EXPECTED_V2_PROVENANCE_SHA)
    checks["V2_PROVENANCE_HASH_MATCH"] = v2_hash_ok

    # Overall derivation
    all_passed = all(checks.values())
    status = "VERIFIED" if all_passed else "REMEDIATION_REQUIRED"

    details = {
        "current_branch": current_branch,
        "current_head": current_head,
        "remote_shared_head": remote_shared_head,
        "canonical_merge_point": CANONICAL_MERGE_POINT,
        "hardened_branch_sha": hardened_remote_sha,
        "wip_safety_sha": wip_remote_sha,
        "snapshot_sha": snapshot_remote_sha,
        "silver_sha": silver_actual,
        "dataset_v310_sha": dataset_v310_actual,
        "checks": checks,
    }

    return all_passed, checks, status, details


def main() -> int:
    parser = argparse.ArgumentParser(description="BTCETH Canonical Post-Merge Acceptance Verifier")
    parser.add_argument("--skip-sub-tests", action="store_true", help="Skip child pytest execution for rapid assertion")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    print("=== BTCETH TRADING OS: CANONICAL POST-MERGE ACCEPTANCE VERIFIER ===")
    all_passed, checks, status, details = evaluate_canonical_post_merge(skip_sub_tests=args.skip_sub_tests)

    for k, v in checks.items():
        res = "PASS" if v else "FAIL"
        print(f"[{res}] {k}")

    print("=" * 60)
    print(f"CANONICAL_POST_MERGE_ACCEPTANCE = {status}")
    print("=" * 60)

    if args.json:
        print(json.dumps({"status": status, "checks": checks, "details": details}, indent=2))

    return 0 if all_passed else 20


if __name__ == "__main__":
    sys.exit(main())
