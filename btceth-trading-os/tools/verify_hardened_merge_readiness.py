from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


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


def compute_canonical_payload_sha256(payload: dict[str, Any]) -> str:
    clean_dict = {k: v for k, v in payload.items() if k != "provenance_payload_sha256"}
    canonical_bytes = json.dumps(clean_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def main() -> int:
    print("=== BTCETH TRADING OS: HARDENED MERGE READINESS VERIFIER V2 ===")
    verif_started = datetime.now(timezone.utc).isoformat()
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    # 1. Verify remote reference commits and branch anchors
    expected_shared_sha = "5873de692b8eb7d9b7775ef3c2a2e730f9fd8088"
    expected_snapshot_sha = "5873de692b8eb7d9b7775ef3c2a2e730f9fd8088"
    expected_wip_safety_sha = "11d6e370db0d27cd635528a3c530286b28c60416"
    expected_remediation_head_sha = "6e18e19182c09066e1a0db8681cc07efa096289d"
    expected_remediation_code_sha = "c882c6ad41db0e5051e0f263ecf2b3443ebe48b3"
    expected_tested_code_sha = "c316a0814f651aece0e4be248e0eee10ce0c18e3"
    expected_tested_tree_sha = "252d9574d9c28e9835d280a7eeade3b2528dfd5d"
    expected_dataset_v310_sha = "a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930"
    expected_silver_sha = "b4b77ca9497759ac8ee831a7c12ac963a6c5a2309a65d19f58c2da8e8d774513"

    current_branch = git_cmd(["branch", "--show-current"])
    current_head = git_cmd(["rev-parse", "HEAD"])
    shared_remote_sha = git_cmd(["rev-parse", "origin/btceth-phase1b"])
    snapshot_remote_sha = git_cmd(["rev-parse", "origin/btceth-pre-phase1b2-hardening-snapshot"])
    wip_remote_sha = git_cmd(["rev-parse", "origin/btceth-round3b-wip-safety"])
    remediation_remote_sha = git_cmd(["rev-parse", "origin/btceth-phase1b2-remediation"])

    checks["shared_branch_untouched"] = (shared_remote_sha == expected_shared_sha)
    checks["snapshot_branch_preserved"] = (snapshot_remote_sha == expected_snapshot_sha)
    checks["round3b_wip_safety_preserved"] = (wip_remote_sha == expected_wip_safety_sha)
    checks["remediation_branch_head_aligned"] = (remediation_remote_sha == expected_remediation_head_sha)

    # 2. Provenance Commit Exists & Tree Matches
    checks["base_shared_commit_resolves"] = check_commit_exists(expected_shared_sha)
    checks["remediation_code_commit_resolves"] = check_commit_exists(expected_remediation_code_sha)
    checks["remediation_branch_head_resolves"] = check_commit_exists(expected_remediation_head_sha)
    checks["snapshot_sha_resolves"] = check_commit_exists(expected_snapshot_sha)
    checks["round3b_safety_sha_resolves"] = check_commit_exists(expected_wip_safety_sha)
    checks["tested_code_commit_resolves"] = check_commit_exists(expected_tested_code_sha)

    tested_tree_sha = git_cmd(["rev-parse", f"{expected_tested_code_sha}^{{tree}}"])
    checks["tested_tree_sha_matches"] = (tested_tree_sha == expected_tested_tree_sha)

    # 3. Hardened branch ancestry check (must descend from shared branch 5873de6)
    is_ancestor = run_cmd(["git", "merge-base", "--is-ancestor", expected_shared_sha, current_head]).returncode == 0
    checks["hardened_descends_from_shared"] = is_ancestor

    # 4. Zero unverified code modifications between tested code commit and HEAD
    code_diff = git_cmd(["diff", expected_tested_code_sha, "HEAD", "--", "btceth-trading-os/src/"])
    checks["zero_unverified_src_modifications"] = (len(code_diff) == 0)

    # 5. Verify all Git SHAs referenced across reports resolve locally
    report_shas: dict[str, list[str]] = {}
    missing_shas: list[str] = []

    target_reports = [
        "PHASE_1B_2_FORWARD_PORT_AUDIT.json",
        "PHASE_1B_2_HISTORICAL_GAP_ANALYSIS.json",
        "DOWNSTREAM_HISTORICAL_DATA_IMPACT.json",
        "RESEARCH_ROUND3A_ACCEPTANCE.json",
        "PHASE_1B_2_ACCEPTANCE.json",
    ]

    commit_field_patterns = {
        "base_commit",
        "base_shared_commit_sha",
        "tested_code_commit_sha",
        "remediation_code_commit_sha",
        "remediation_branch_head_sha",
        "historical_commit",
        "hardened_commit",
        "code_commit",
        "software_commit_sha",
        "commit",
    }

    for rep_name in target_reports:
        rep_path = REPORTS / rep_name
        if not rep_path.is_file():
            missing_shas.append(f"Missing report: {rep_name}")
            continue
        try:
            data = json.loads(rep_path.read_text(encoding="utf-8"))
            shas: list[str] = []
            for k, v in data.items():
                if k in commit_field_patterns and isinstance(v, str) and len(v) == 40:
                    shas.append(v)
                    if not check_commit_exists(v):
                        missing_shas.append(f"{rep_name} -> {k}: {v}")
            report_shas[rep_name] = shas
        except Exception as e:
            missing_shas.append(f"Error reading {rep_name}: {e}")

    checks["all_report_git_shas_resolve"] = (len(missing_shas) == 0)
    details["report_shas"] = report_shas
    details["missing_shas"] = missing_shas

    # 6. Full pytest automated test suite check
    print("[1/5] Checking full automated test suite...")
    test_res = run_cmd([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    pytest_pass = (test_res.returncode == 0)
    checks["automated_tests_pass"] = pytest_pass
    print(f"Pytest suite: {'PASS' if pytest_pass else 'FAIL'}")

    # 7. Zero-trading security boundary check
    print("[2/5] Checking zero-trading security scan...")
    sec_res = run_cmd([sys.executable, "-m", "btceth_os.security_scan"])
    sec_pass = (sec_res.returncode == 0 and '"trading_capability": "ZERO"' in sec_res.stdout)
    checks["security_capability_zero"] = sec_pass
    print(f"Security capability zero: {'PASS' if sec_pass else 'FAIL'}")

    # 8. Milestone acceptance report checks
    print("[3/5] Inspecting milestone acceptance artifacts...")
    phase_1a_data = json.loads((REPORTS / "PHASE_1A_ACCEPTANCE.json").read_text(encoding="utf-8"))
    phase_1b1_data = json.loads((REPORTS / "PHASE_1B_1_ACCEPTANCE.json").read_text(encoding="utf-8"))
    phase_1b2_data = json.loads((REPORTS / "PHASE_1B_2_ACCEPTANCE.json").read_text(encoding="utf-8"))
    phase_1b3_data = json.loads((REPORTS / "PHASE_1B_3_ACCEPTANCE.json").read_text(encoding="utf-8"))
    phase_1b4_data = json.loads((REPORTS / "PHASE_1B_4_ACCEPTANCE.json").read_text(encoding="utf-8"))
    phase_1b5_data = json.loads((REPORTS / "PHASE_1B_5_ACCEPTANCE.json").read_text(encoding="utf-8"))
    round3a_data = json.loads((REPORTS / "RESEARCH_ROUND3A_ACCEPTANCE.json").read_text(encoding="utf-8"))

    checks["phase_1a_verified"] = (phase_1a_data.get("status") == "VERIFIED")
    checks["phase_1b1_verified"] = (phase_1b1_data.get("status") == "VERIFIED")
    checks["phase_1b2_verified"] = (phase_1b2_data.get("status") == "VERIFIED" and all(phase_1b2_data.get("checks", {}).values()))
    checks["phase_1b3_verified"] = (phase_1b3_data.get("status") == "VERIFIED")
    checks["phase_1b4_verified"] = (phase_1b4_data.get("status") == "VERIFIED")
    checks["phase_1b5_verified"] = (phase_1b5_data.get("status") == "VERIFIED")
    checks["round3a_verified"] = (round3a_data.get("acceptance_status") == "VERIFIED")
    checks["holdout_locked"] = (round3a_data.get("holdout_status") == "LOCKED")

    # Phase 1B.2 Clean Worktree & Dirty Paths Validation
    checks["phase1b2_working_tree_clean_before"] = (phase_1b2_data.get("working_tree_clean_before") is True)
    checks["phase1b2_dirty_paths_before_empty"] = (phase_1b2_data.get("dirty_paths_before") == [])
    checks["phase1b2_tested_code_commit_matches"] = (phase_1b2_data.get("tested_code_commit_sha") == expected_tested_code_sha)
    checks["phase1b2_tested_tree_matches"] = (phase_1b2_data.get("tested_tree_sha") == expected_tested_tree_sha)

    # 9. Funding Parity mode and coverage checks
    print("[4/5] Checking funding parity evidence...")
    funding_rep = json.loads((REPORTS / "PHASE_1B_2_FUNDING_PARITY.json").read_text(encoding="utf-8"))
    checks["funding_parity_mode_live_rest"] = (funding_rep.get("funding_parity_mode") == "LIVE_REST")
    checks["funding_parity_passed"] = (funding_rep.get("funding_parity_passed") is True)
    checks["funding_parity_symbols_btc_and_eth"] = set(funding_rep.get("symbols_audited", [])) == {"BTCUSDT", "ETHUSDT"}

    # 10. Downstream hash identity verification
    print("[5/5] Checking downstream cryptographic identity proofs...")
    downstream_rep = json.loads((REPORTS / "DOWNSTREAM_HISTORICAL_DATA_IMPACT.json").read_text(encoding="utf-8"))
    checks["downstream_inputs_identical"] = (downstream_rep.get("status") == "INPUTS_VERIFIED_IDENTICAL")
    checks["downstream_no_revalidation_required"] = (downstream_rep.get("revalidation_required") is False)

    # Check Dataset v3.1.0 logical SHA
    research_manifest = json.loads((REPORTS / "RESEARCH_ROUND3A_DATA_MANIFEST.json").read_text(encoding="utf-8"))
    obs_v310_sha = research_manifest.get("dataset_logical_sha256")
    checks["dataset_v310_full_sha_matches"] = (obs_v310_sha == expected_dataset_v310_sha)

    # Check Silver Parquet hash
    silver_files = list((ROOT / "artifacts" / "phase1b5_acceptance" / "silver").glob("*.parquet"))
    silver_sha = hashlib.sha256(silver_files[0].read_bytes()).hexdigest() if silver_files else ""
    checks["silver_parquet_sha_matches"] = (silver_sha == expected_silver_sha)

    all_ready = all(checks.values())
    verif_status = "VERIFIED" if all_ready else "REMEDIATION_REQUIRED"

    v2_json_path = REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.json"
    v2_md_path = REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE_V2.md"

    if v2_json_path.is_file() and "--force-generate" not in sys.argv:
        existing_payload = json.loads(v2_json_path.read_text(encoding="utf-8"))
        stored_sha = existing_payload.get("provenance_payload_sha256")
        computed_sha = compute_canonical_payload_sha256(existing_payload)
        payload_matches = (stored_sha == computed_sha and bool(stored_sha))
        checks["provenance_payload_sha256_matches"] = payload_matches
        payload_sha256 = stored_sha
    else:
        # Compile Final Provenance Report V2 (Non-Self-Referential Model)
        # verification_parent_head_sha: The Git HEAD existing when this report is generated
        provenance_v2_payload: dict[str, Any] = {
            "report_version": 2,
            "supersedes": "PHASE_1B_HARDENED_FINAL_PROVENANCE.json",
            "generated_at_utc": verif_started,
            "readiness_status": verif_status,
            "base_shared_commit_sha": expected_shared_sha,
            "tested_code_commit_sha": expected_tested_code_sha,
            "tested_tree_sha": expected_tested_tree_sha,
            "verification_parent_head_sha": current_head,
            "remediation_code_commit_sha": expected_remediation_code_sha,
            "remediation_branch_head_sha": expected_remediation_head_sha,
            "round3b_wip_safety_sha": expected_wip_safety_sha,
            "pre_hardening_snapshot_sha": expected_snapshot_sha,
            "working_tree_clean_before": phase_1b2_data.get("working_tree_clean_before"),
            "dirty_paths_before": phase_1b2_data.get("dirty_paths_before"),
            "milestone_statuses": {
                "all_tests_status": "PASS" if pytest_pass else "FAIL",
                "phase_1a_status": phase_1a_data.get("status"),
                "phase_1b1_status": phase_1b1_data.get("status"),
                "phase_1b2_status": phase_1b2_data.get("status"),
                "phase_1b3_status": phase_1b3_data.get("status"),
                "phase_1b4_status": phase_1b4_data.get("status"),
                "phase_1b5_status": phase_1b5_data.get("status"),
                "round3a_status": round3a_data.get("acceptance_status"),
            },
            "security_status": "ZERO" if sec_pass else "NOT_PROVEN",
            "holdout_status": round3a_data.get("holdout_status"),
            "funding_parity_mode": funding_rep.get("funding_parity_mode"),
            "funding_parity_symbols": funding_rep.get("symbols_audited"),
            "archive_count": phase_1b2_data.get("total_archives_verified"),
            "archive_bytes": phase_1b2_data.get("total_archive_bytes_verified"),
            "archive_mib": phase_1b2_data.get("total_archive_mib_verified"),
            "cache_hits": phase_1b2_data.get("total_cache_hits"),
            "silver_parquet_sha256": silver_sha,
            "dataset_v3_1_full_logical_sha": obs_v310_sha,
            "checks": checks,
            "details": details,
        }

        # Compute deterministic canonical JSON SHA-256 for the evidence payload
        payload_sha256 = compute_canonical_payload_sha256(provenance_v2_payload)
        provenance_v2_payload["provenance_payload_sha256"] = payload_sha256
        checks["provenance_payload_sha256_matches"] = True

        v2_json_path.write_text(json.dumps(provenance_v2_payload, indent=2) + "\n")

        prov_v2_md_lines = [
            "# Phase 1B Hardened Final Provenance & Merge Readiness Report V2",
            "",
            f"**HARDENED_MERGE_READINESS_V2 = {verif_status}**",
            "",
            f"- **Report Version**: `2` (supersedes `PHASE_1B_HARDENED_FINAL_PROVENANCE.json`)",
            f"- **Verification Timestamp (UTC)**: `{verif_started}`",
            f"- **Base Shared Commit**: `{expected_shared_sha}` (`btceth-phase1b`)",
            f"- **Tested Code Commit**: `{expected_tested_code_sha}`",
            f"- **Tested Tree SHA**: `{expected_tested_tree_sha}`",
            f"- **Verification Parent HEAD**: `{current_head}`",
            f"- **Remediation Code Commit**: `{expected_remediation_code_sha}`",
            f"- **Remediation Branch Head**: `{expected_remediation_head_sha}`",
            f"- **Round 3B WIP Safety SHA**: `{expected_wip_safety_sha}`",
            f"- **Pre-Hardening Snapshot SHA**: `{expected_snapshot_sha}`",
            f"- **Provenance Payload SHA-256**: `{payload_sha256}`",
            "",
            "## Clean Worktree & Environmental Proof",
            "",
            f"- **Working Tree Clean Before Phase 1B.2**: `{phase_1b2_data.get('working_tree_clean_before')}`",
            f"- **Dirty Paths Before Phase 1B.2**: `{phase_1b2_data.get('dirty_paths_before')}`",
            "",
            "## Milestone Gate Statuses",
            "",
            f"- Full Test Suite: `{'PASS' if pytest_pass else 'FAIL'}`",
            f"- Phase 1A: `{phase_1a_data.get('status')}`",
            f"- Phase 1B.1: `{phase_1b1_data.get('status')}`",
            f"- Phase 1B.2: `{phase_1b2_data.get('status')}`",
            f"- Phase 1B.3: `{phase_1b3_data.get('status')}`",
            f"- Phase 1B.4: `{phase_1b4_data.get('status')}`",
            f"- Phase 1B.5: `{phase_1b5_data.get('status')}`",
            f"- Research Round 3A: `{round3a_data.get('acceptance_status')}`",
            f"- Security Boundary: `{provenance_v2_payload['security_status']}`",
            f"- 2024 Holdout: `{provenance_v2_payload['holdout_status']}`",
            "",
            "## Acquisition & Parity Evidence",
            "",
            f"- Total Archives Verified: `{phase_1b2_data.get('total_archives_verified')}`",
            f"- Total Archive Bytes Verified: `{phase_1b2_data.get('total_archive_bytes_verified'):,}` bytes ({phase_1b2_data.get('total_archive_mib_verified')} MiB)",
            f"- Total Cache Hits: `{phase_1b2_data.get('total_cache_hits')}`",
            f"- Live Funding Parity Mode: `{funding_rep.get('funding_parity_mode')}` (Symbols: `{', '.join(funding_rep.get('symbols_audited', []))}`)",
            f"- Dataset v3.1.0 Full Logical SHA: `{obs_v310_sha}`",
            f"- Silver Parquet SHA: `{silver_sha}`",
            "",
            "## Mechanical Verification Checks",
            "",
        ]
        for k, v in checks.items():
            prov_v2_md_lines.append(f"- [{'x' if v else ' '}] `{k}`")

        v2_md_path.write_text("\n".join(prov_v2_md_lines) + "\n")

    print("\n=======================================================")
    print(f"HARDENED_MERGE_READINESS_V2 = {verif_status}")
    print("=======================================================")
    return 0 if all_ready else 20


if __name__ == "__main__":
    raise SystemExit(main())
