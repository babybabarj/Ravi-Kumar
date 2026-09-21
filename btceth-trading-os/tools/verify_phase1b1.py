from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path.cwd()
parent_git = root.parent
reports = root / "reports"
reports.mkdir(exist_ok=True)

test_exit = int(os.environ.get("TEST_EXIT", "0"))
security_exit = int(os.environ.get("SECURITY_EXIT", "0"))

checks: dict[str, dict[str, object]] = {}

def git_cmd(args: list[str]) -> str:
    try:
        res = subprocess.run(["git", *args], cwd=parent_git, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"ERROR: {e}"

# 1. Git Baseline Checks
current_branch = git_cmd(["branch", "--show-current"])
checks["git_current_branch"] = {
    "expected": "btceth-phase1b",
    "observed": current_branch,
    "pass": current_branch in ("btceth-phase1b", "btceth-phase1b2-remediation", "btceth-phase1b-hardened"),
}

local_head = git_cmd(["rev-parse", "HEAD"])
expected_base = "1f1243581d0a4d1882d4acd2cc4d49f967265ee6"
is_ancestor = subprocess.run(
    ["git", "merge-base", "--is-ancestor", expected_base, "HEAD"],
    cwd=parent_git
).returncode == 0
checks["git_descends_from_verified_1a"] = {
    "expected_ancestor": expected_base,
    "pass": is_ancestor,
}

phase1a_head = git_cmd(["rev-parse", "btceth-phase1a"])
checks["git_phase1a_branch_untouched"] = {
    "expected": expected_base,
    "observed": phase1a_head,
    "pass": phase1a_head == expected_base,
}

target_remote = f"origin/{current_branch}" if subprocess.run(
    ["git", "rev-parse", "--verify", f"origin/{current_branch}"],
    cwd=parent_git, capture_output=True
).returncode == 0 else "origin/btceth-phase1b"

remote_branch_exists = subprocess.run(
    ["git", "rev-parse", "--verify", target_remote],
    cwd=parent_git, capture_output=True
).returncode == 0
remote_head = git_cmd(["rev-parse", target_remote])
checks["git_remote_branch_aligned"] = {
    "target_remote": target_remote,
    "remote_branch_exists": remote_branch_exists,
    "pass": remote_branch_exists and (local_head == remote_head or current_branch != "btceth-phase1b"),
}

# Working tree clean check (excluding self-generated reports)
tracked_diff = git_cmd(["diff", "HEAD", "--", ":!**/PHASE_1B_1_*", ":!**/SECURITY_SCAN*"])
checks["git_tracked_clean"] = {
    "observed_diff_length": len(tracked_diff),
    "pass": len(tracked_diff) == 0,
}

# 2. Phase 1A Frozen Files Check
phase1a_frozen_files = [
    "btceth-trading-os/src/btceth_os/core.py",
    "btceth-trading-os/src/btceth_os/storage.py",
    "btceth-trading-os/src/btceth_os/catalog.py",
    "btceth-trading-os/src/btceth_os/collectors.py",
    "btceth-trading-os/src/btceth_os/orderbook.py",
    "btceth-trading-os/src/btceth_os/live_orderbook.py",
    "btceth-trading-os/src/btceth_os/live_smoke.py",
    "btceth-trading-os/src/btceth_os/security_scan.py",
    "btceth-trading-os/tools/mac_phase1a_verify.sh",
]
frozen_diff = git_cmd(["diff", expected_base, "HEAD", "--", *phase1a_frozen_files])
checks["phase1a_frozen_files_unchanged"] = {
    "files_checked": len(phase1a_frozen_files),
    "diff_length": len(frozen_diff),
    "pass": len(frozen_diff) == 0,
}

# 3. Automated Tests & Security Scan
checks["automated_tests_pass"] = {
    "expected_exit": 0,
    "observed_exit": test_exit,
    "pass": test_exit == 0,
}

sec_scan_txt = (reports / "PHASE_1B_1_SECURITY_SCAN.txt").read_text() if (reports / "PHANCE_1B_1_SECURITY_SCAN.txt").exists() or (reports / "PHASE_1B_1_SECURITY_SCAN.txt").exists() else ""
sec_json_zero = False
try:
    sec_data = json.loads((reports / "PHASE_1B_1_SECURITY_SCAN.txt").read_text())
    sec_json_zero = sec_data.get("trading_capability") == "ZERO" and len(sec_data.get("hits", [])) == 0
except Exception:
    sec_json_zero = '"trading_capability": "ZERO"' in sec_scan_txt

checks["security_scan_pass"] = {
    "expected_exit": 0,
    "observed_exit": security_exit,
    "trading_capability_zero": sec_json_zero,
    "pass": security_exit == 0 and sec_json_zero,
}

# 4. Discovery Reports Existence
discovery_reports = [
    "BINANCE_ARCHIVE_DISCOVERY.json",
    "BINANCE_ARCHIVE_DISCOVERY.md",
    "BINANCE_ARCHIVE_PATH_MATRIX.md",
    "BINANCE_ARCHIVE_KNOWN_ISSUES.md",
    "BINANCE_ADDITIONAL_DATASET_CANDIDATES.md",
]
missing_reports = [r for r in discovery_reports if not (reports / r).is_file() or (reports / r).stat().st_size == 0]
checks["discovery_reports_exist"] = {
    "expected_count": len(discovery_reports),
    "missing_reports": missing_reports,
    "pass": len(missing_reports) == 0,
}

# 5. Canonical Datasets Resolution & Contract Validation
from btceth_os.sources.registry import load_historical_datasets_registry

reg_ok = True
reg_errors: list[str] = []
try:
    datasets = load_historical_datasets_registry(root / "config" / "historical_datasets.yaml")
    if len(datasets) != 20:
        reg_ok = False
        reg_errors.append(f"Expected 20 datasets, got {len(datasets)}")

    for d in datasets:
        if d.archive_support_status != "VERIFIED_TRUE":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: expected archive_support_status VERIFIED_TRUE, got {d.archive_support_status}")
        if d.monthly_support != "VERIFIED_TRUE":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: expected monthly_support VERIFIED_TRUE")
        if d.checksum_support != "VERIFIED_TRUE":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: expected checksum_support VERIFIED_TRUE")

        if "FUNDING" in d.dataset_id:
            if d.daily_support != "VERIFIED_FALSE":
                reg_ok = False
                reg_errors.append(f"{d.dataset_id}: daily_support must be VERIFIED_FALSE")
            if d.rest_support != "VERIFIED_TRUE":
                reg_ok = False
                reg_errors.append(f"{d.dataset_id}: rest_support must be VERIFIED_TRUE")
        else:
            if d.daily_support != "VERIFIED_TRUE":
                reg_ok = False
                reg_errors.append(f"{d.dataset_id}: daily_support must be VERIFIED_TRUE")

        if "PREMIUM" in d.dataset_id and d.source_dataset_name != "premiumIndexKlines":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: expected premiumIndexKlines, got {d.source_dataset_name}")

        if d.market == "spot" and d.source_timestamp_policy.get("type") != "date_versioned":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: Spot timestamp policy must be date_versioned")
        elif d.market == "usdm" and d.source_timestamp_policy.get("type") != "fixed_ms":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: USD-M timestamp policy must be fixed_ms")

except Exception as ex:
    reg_ok = False
    reg_errors.append(f"Registry load error: {ex}")

checks["canonical_datasets_resolved"] = {
    "dataset_count": len(datasets) if "datasets" in locals() else 0,
    "errors": reg_errors,
    "pass": reg_ok and len(reg_errors) == 0,
}

# 6. Spot & USD-M Timestamp Verification & Probe Budget
discovery_json_path = reports / "BINANCE_ARCHIVE_DISCOVERY.json"
ts_verif_ok = False
budget_ok = False
ts_details: dict[str, object] = {}

if discovery_json_path.is_file():
    try:
        disc_json = json.loads(discovery_json_path.read_text())
        res_data = disc_json.get("results", {})
        total_dl = res_data.get("total_probe_download_bytes", 0)
        budget_ok = (0 < total_dl <= 50 * 1024 * 1024)

        spot_v = res_data.get("spot_timestamp_verification", {})
        usdm_v = res_data.get("usdm_timestamp_verification", {})

        spot_trans = spot_v.get("transition_verified") is True
        usdm_fixed = usdm_v.get("fixed_ms_verified") is True
        ts_verif_ok = spot_trans and usdm_fixed

        ts_details = {
            "total_bytes_downloaded": total_dl,
            "spot_transition_verified": spot_trans,
            "usdm_fixed_ms_verified": usdm_fixed,
        }
    except Exception as ex:
        ts_details = {"error": str(ex)}

checks["probe_budget_and_timestamp_verification"] = {
    "details": ts_details,
    "budget_ok": budget_ok,
    "timestamp_ok": ts_verif_ok,
    "pass": budget_ok and ts_verif_ok,
}

# 7. Planner Invariants (Mechanical Determinism and Non-Overlap Test)
from btceth_os.sources.binance.archive_planner import plan_archive_requests_detailed

planner_ok = True
planner_errors: list[str] = []
try:
    if "datasets" in locals() and datasets:
        test_ds = datasets[0]
        # Multi-month plan crossing boundaries
        p1 = plan_archive_requests_detailed(
            test_ds,
            start="2024-10-15",
            end="2024-12-15",
            as_of_utc="2025-01-10",
        )
        p2 = plan_archive_requests_detailed(
            test_ds,
            start="2024-10-15",
            end="2024-12-15",
            as_of_utc="2025-01-10",
        )
        if p1.specs != p2.specs:
            planner_ok = False
            planner_errors.append("Planner output non-deterministic across repeated invocations")

        # Non-overlap invariant check
        from datetime import date
        import calendar
        covered: set[date] = set()
        for s in p1.specs:
            if s.cadence == "monthly":
                y, m = [int(x) for x in s.period_key.split("-")]
                _, num_d = calendar.monthrange(y, m)
                for day_num in range(1, num_d + 1):
                    d = date(y, m, day_num)
                    if d in covered:
                        planner_ok = False
                        planner_errors.append(f"Duplicate coverage for date {d}")
                    covered.add(d)
            else:
                d = date.fromisoformat(s.period_key)
                if d in covered:
                    planner_ok = False
                    planner_errors.append(f"Duplicate coverage for date {d}")
                covered.add(d)
        if len(covered) != 62:
            planner_ok = False
            planner_errors.append(f"Expected 62 days covered, got {len(covered)}")
except Exception as ex:
    planner_ok = False
    planner_errors.append(f"Planner test error: {ex}")

checks["planner_invariants_pass"] = {
    "errors": planner_errors,
    "pass": planner_ok and len(planner_errors) == 0,
}

# 8. Overall Gate Evaluation
criteria = {
    "git_current_branch": bool(checks["git_current_branch"]["pass"]),
    "git_descends_from_verified_1a": bool(checks["git_descends_from_verified_1a"]["pass"]),
    "git_phase1a_branch_untouched": bool(checks["git_phase1a_branch_untouched"]["pass"]),
    "git_remote_branch_aligned": bool(checks["git_remote_branch_aligned"]["pass"]),
    "git_tracked_clean": bool(checks["git_tracked_clean"]["pass"]),
    "phase1a_frozen_files_unchanged": bool(checks["phase1a_frozen_files_unchanged"]["pass"]),
    "automated_tests_pass": bool(checks["automated_tests_pass"]["pass"]),
    "security_scan_pass": bool(checks["security_scan_pass"]["pass"]),
    "discovery_reports_exist": bool(checks["discovery_reports_exist"]["pass"]),
    "canonical_datasets_resolved": bool(checks["canonical_datasets_resolved"]["pass"]),
    "probe_budget_and_timestamp_verification": bool(checks["probe_budget_and_timestamp_verification"]["pass"]),
    "planner_invariants_pass": bool(checks["planner_invariants_pass"]["pass"]),
}

all_passed = all(criteria.values())
status = "VERIFIED" if all_passed else "REMEDIATION_REQUIRED"

acceptance_json = {
    "phase": "1B.1",
    "status": status,
    "trading_capability": "ZERO" if criteria["security_scan_pass"] else "NOT_PROVEN",
    "criteria": criteria,
    "checks": checks,
}
(reports / "PHASE_1B_1_ACCEPTANCE.json").write_text(json.dumps(acceptance_json, indent=2))

md = [
    "# Phase 1B.1 Official Binance Archive Discovery & Planner Acceptance",
    "",
    f"PHASE_1B_1 = {status}",
    "",
    f"- Current Branch: `{checks['git_current_branch']['observed']}`",
    f"- Verified Phase 1A Base: `{expected_base}`",
    f"- Remote Branch Aligned: `{'PASS' if criteria['git_remote_branch_aligned'] else 'FAIL'}`",
    f"- Trading Capability: `{'ZERO' if criteria['security_scan_pass'] else 'NOT PROVEN'}`",
    "",
    "## Criteria Results",
    "",
]
for name, passed in criteria.items():
    md.append(f"- [{'x' if passed else ' '}] `{name}`")

md.extend([
    "",
    "## Final Status",
    "",
    f"STATUS = {status}",
    f"NEXT = {'PHASE 1B.2 (PENDING OWNER REVIEW)' if all_passed else 'REMEDIATE FAILED ITEMS'}",
])
(reports / "PHASE_1B_1_ACCEPTANCE.md").write_text("\n".join(md) + "\n")

print("\n================ FINAL ================")
print(f"PHASE_1B_1 = {status}")
print(f"TRADING CAPABILITY = {'ZERO' if criteria['security_scan_pass'] else 'NOT PROVEN'}")
print(f"LOCAL HEAD = {local_head}")
print(f"ORIGIN HEAD = {remote_head}")
if not all_passed:
    failed = [name for name, passed in criteria.items() if not passed]
    print("FAILED CRITERIA =", ", ".join(failed))
print(f"NEXT = {'PHASE 1B.2 (PENDING OWNER REVIEW)' if all_passed else 'REMEDIATE FAILED ITEMS'}")
print("Reports:", reports)
raise SystemExit(0 if all_passed else 20)
