from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def git_cmd(args: list[str]) -> str:
    res = run_cmd(["git", *args])
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr}")
    return res.stdout.strip()


def check_commit_exists(sha: str) -> bool:
    res = run_cmd(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
    return res.returncode == 0


def main() -> int:
    print("=== BTCETH TRADING OS: HARDENED MERGE READINESS VERIFIER ===")
    verif_started = datetime.now(timezone.utc).isoformat()
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    # 1. Verify remote reference commits
    expected_shared_sha = "5873de692b8eb7d9b7775ef3c2a2e730f9fd8088"
    expected_snapshot_sha = "5873de692b8eb7d9b7775ef3c2a2e730f9fd8088"
    expected_wip_safety_sha = "11d6e370db0d27cd635528a3c530286b28c60416"
    expected_remediation_head_sha = "6e18e19182c09066e1a0db8681cc07efa096289d"
    expected_remediation_code_sha = "c882c6ad41db0e5051e0f263ecf2b3443ebe48b3"
    p1b2_path = REPORTS / "PHASE_1B_2_ACCEPTANCE.json"
    p1b2_info = json.loads(p1b2_path.read_text(encoding="utf-8")) if p1b2_path.is_file() else {}
    expected_tested_code_sha = p1b2_info.get("tested_code_commit_sha") or "641bb5f8aae5c42ef6f774761ac44e8118c72627"
    expected_dataset_v310_sha = "a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930"

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
    checks["remediation_code_commit_exists"] = check_commit_exists(expected_remediation_code_sha)

    # 2. Hardened branch ancestry check (must descend from shared branch 5873de6)
    is_ancestor = run_cmd(["git", "merge-base", "--is-ancestor", expected_shared_sha, current_head]).returncode == 0
    checks["hardened_descends_from_shared"] = is_ancestor

    # 3. Clean tested code commit & tree verification
    tested_code_exists = check_commit_exists(expected_tested_code_sha)
    tested_tree_sha = git_cmd(["rev-parse", f"{expected_tested_code_sha}^{{tree}}"])
    # Verify no source code changes between tested code commit and HEAD (only docs/reports/tools)
    code_diff = git_cmd(["diff", expected_tested_code_sha, "HEAD", "--", "btceth-trading-os/src/"])
    checks["tested_code_commit_valid"] = tested_code_exists
    checks["zero_unverified_src_modifications"] = (len(code_diff) == 0)

    # 4. Verify all Git SHAs referenced across reports resolve locally
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
        "tested_code_commit_sha",
        "remediation_code_commit_sha",
        "remediation_branch_head_sha",
        "historical_commit",
        "hardened_commit",
        "code_commit",
        "software_commit_sha",
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

    # 5. Full pytest automated test suite check
    print("[1/5] Checking full automated test suite...")
    test_res = run_cmd([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    pytest_pass = (test_res.returncode == 0)
    checks["automated_tests_pass"] = pytest_pass
    print(f"Pytest suite: {'PASS' if pytest_pass else 'FAIL'}")

    # 6. Zero-trading security boundary check
    print("[2/5] Checking zero-trading security scan...")
    sec_res = run_cmd([sys.executable, "-m", "btceth_os.security_scan"])
    sec_pass = (sec_res.returncode == 0 and '"trading_capability": "ZERO"' in sec_res.stdout)
    checks["security_capability_zero"] = sec_pass
    print(f"Security capability zero: {'PASS' if sec_pass else 'FAIL'}")

    # 7. Milestone acceptance report checks
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

    # 8. Funding Parity mode and coverage checks
    print("[4/5] Checking funding parity evidence...")
    funding_rep = json.loads((REPORTS / "PHASE_1B_2_FUNDING_PARITY.json").read_text(encoding="utf-8"))
    checks["funding_parity_mode_live_rest"] = (funding_rep.get("funding_parity_mode") == "LIVE_REST")
    checks["funding_parity_passed"] = (funding_rep.get("funding_parity_passed") is True)
    checks["funding_parity_symbols_btc_and_eth"] = set(funding_rep.get("symbols_audited", [])) == {"BTCUSDT", "ETHUSDT"}

    # 9. Downstream hash identity verification
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
    expected_silver_sha = "b4b77ca9497759ac8ee831a7c12ac963a6c5a2309a65d19f58c2da8e8d774513"
    checks["silver_parquet_sha_matches"] = (silver_sha == expected_silver_sha)

    all_ready = all(checks.values())
    verif_status = "VERIFIED" if all_ready else "REMEDIATION_REQUIRED"

    # Compile Final Provenance Report (Section 24)
    provenance_payload = {
        "report_name": "PHASE_1B_HARDENED_FINAL_PROVENANCE",
        "generated_at_utc": verif_started,
        "readiness_status": verif_status,
        "shared_branch_name": "btceth-phase1b",
        "shared_branch_sha": shared_remote_sha,
        "hardened_branch_name": current_branch,
        "hardened_branch_sha": current_head,
        "tested_code_commit_sha": expected_tested_code_sha,
        "tested_tree_sha": tested_tree_sha,
        "remediation_code_commit_sha": expected_remediation_code_sha,
        "remediation_branch_head_sha": expected_remediation_head_sha,
        "round3b_wip_safety_sha": wip_remote_sha,
        "pre_hardening_snapshot_sha": snapshot_remote_sha,
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
        "acquisition_metrics": {
            "archive_count_verified": phase_1b2_data.get("total_archives_verified"),
            "archive_bytes_verified": phase_1b2_data.get("total_archive_bytes_verified"),
            "archive_mib_verified": phase_1b2_data.get("total_archive_mib_verified"),
            "cache_hits": phase_1b2_data.get("total_cache_hits"),
            "bytes_downloaded_this_run": phase_1b2_data.get("total_bytes_downloaded_this_run"),
        },
        "funding_parity": {
            "mode": funding_rep.get("funding_parity_mode"),
            "symbols": funding_rep.get("symbols_audited"),
            "passed": funding_rep.get("funding_parity_passed"),
        },
        "downstream_identity": {
            "dataset_v3_1_full_logical_sha": obs_v310_sha,
            "silver_parquet_sha256": silver_sha,
            "inputs_identical": downstream_rep.get("status") == "INPUTS_VERIFIED_IDENTICAL",
            "revalidation_required": downstream_rep.get("revalidation_required"),
        },
        "checks": checks,
        "details": details,
    }

    (REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE.json").write_text(
        json.dumps(provenance_payload, indent=2) + "\n"
    )

    prov_md_lines = [
        "# Phase 1B Hardened Final Provenance & Merge Readiness Report",
        "",
        f"**HARDENED_MERGE_READINESS = {verif_status}**",
        "",
        f"- **Verification Timestamp (UTC)**: `{verif_started}`",
        f"- **Shared Branch**: `btceth-phase1b` (`{shared_remote_sha}`)",
        f"- **Hardened Branch**: `{current_branch}` (`{current_head}`)",
        f"- **Tested Code Commit**: `{expected_tested_code_sha}`",
        f"- **Tested Tree SHA**: `{tested_tree_sha}`",
        f"- **Remediation Code Commit**: `{expected_remediation_code_sha}`",
        f"- **Remediation Branch Head**: `{expected_remediation_head_sha}`",
        f"- **Round 3B WIP Safety SHA**: `{wip_remote_sha}`",
        f"- **Pre-Hardening Snapshot SHA**: `{snapshot_remote_sha}`",
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
        f"- Security Boundary: `{provenance_payload['security_status']}`",
        f"- 2024 Holdout: `{provenance_payload['holdout_status']}`",
        "",
        "## Acquisition & Parity Evidence",
        "",
        f"- Total Archives Verified: `{phase_1b2_data.get('total_archives_verified')}`",
        f"- Total Archive Bytes Verified: `{phase_1b2_data.get('total_archive_bytes_verified'):,}` bytes ({phase_1b2_data.get('total_archive_mib_verified')} MiB)",
        f"- Total Cache Hits: `{phase_1b2_data.get('total_cache_hits')}`",
        f"- Bytes Downloaded This Run: `{phase_1b2_data.get('total_bytes_downloaded_this_run')}`",
        f"- Live Funding Parity Mode: `{funding_rep.get('funding_parity_mode')}` (Symbols: `{', '.join(funding_rep.get('symbols_audited', []))}`)",
        f"- Dataset v3.1.0 Full Logical SHA: `{obs_v310_sha}`",
        f"- Silver Parquet SHA: `{silver_sha}`",
        "",
        "## Mechanical Verification Checks",
        "",
    ]
    for k, v in checks.items():
        prov_md_lines.append(f"- [{'x' if v else ' '}] `{k}`")

    (REPORTS / "PHASE_1B_HARDENED_FINAL_PROVENANCE.md").write_text("\n".join(prov_md_lines) + "\n")

    print("\n=======================================================")
    print(f"HARDENED_MERGE_READINESS = {verif_status}")
    print("=======================================================")
    return 0 if all_ready else 20


if __name__ == "__main__":
    raise SystemExit(main())
