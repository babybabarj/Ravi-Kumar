from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

root = Path.cwd()
parent_git = root.parent
reports = root / "reports"
reports.mkdir(exist_ok=True)

test_exit = int(os.environ.get("TEST_EXIT", "0"))
security_exit = int(os.environ.get("SECURITY_EXIT", "0"))

checks: dict[str, dict[str, object]] = {}

# 1. Git Baseline Checks
def git_cmd(args: list[str]) -> str:
    try:
        res = subprocess.run(["git", *args], cwd=parent_git, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"ERROR: {e}"

current_branch = git_cmd(["branch", "--show-current"])
checks["git_current_branch"] = {
    "expected": "btceth-phase1b",
    "observed": current_branch,
    "pass": current_branch == "btceth-phase1b",
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

remote_branch_exists = subprocess.run(
    ["git", "rev-parse", "--verify", "origin/btceth-phase1b"],
    cwd=parent_git, capture_output=True
).returncode == 0
remote_head = git_cmd(["rev-parse", "origin/btceth-phase1b"])
checks["git_remote_branch_aligned"] = {
    "remote_branch_exists": remote_branch_exists,
    "pass": remote_branch_exists and (local_head == remote_head),
}

git_status = git_cmd(["status", "--porcelain"])
tracked_diff = git_cmd(["diff", "HEAD", "--", ":!reports/PHASE_1B_0_*", ":!reports/SECURITY_SCAN*"])
checks["git_tracked_clean"] = {
    "observed_diff_length": len(tracked_diff),
    "pass": len(tracked_diff) == 0,
}

# 2. Automated Tests & Security Scan
checks["automated_tests_pass"] = {
    "expected_exit": 0,
    "observed_exit": test_exit,
    "pass": test_exit == 0,
}

security_txt = (reports / "PHASE_1B_0_SECURITY_SCAN.txt").read_text() if (reports / "PHASE_1B_0_SECURITY_SCAN.txt").exists() else ""
sec_json_zero = False
try:
    sec_data = json.loads(security_txt)
    sec_json_zero = sec_data.get("trading_capability") == "ZERO" and len(sec_data.get("hits", [])) == 0
except Exception:
    pass

sec_pass = (security_exit == 0) and (sec_json_zero or "TRADING CAPABILITY = ZERO" in security_txt or '"trading_capability": "ZERO"' in security_txt)

checks["security_scan_pass"] = {
    "expected_exit": 0,
    "observed_exit": security_exit,
    "trading_capability_zero": sec_json_zero or "TRADING CAPABILITY = ZERO" in security_txt or '"trading_capability": "ZERO"' in security_txt,
    "pass": sec_pass,
}

# 3. Required File Existence Checks
required_files = [
    "THIRD_PARTY_NOTICES.md",
    "config/historical_datasets.yaml",
    "reports/PHASE_1A_BASELINE.md",
    "reports/OPEN_SOURCE_SOURCE_MANIFEST.md",
    "reports/OPEN_SOURCE_SOURCE_MANIFEST.json",
    "reports/PASSIVBOT_PHASE1B_REUSE_MAP.md",
    "reports/PHASE_1B_0_INCONSISTENCIES.md",
    "src/btceth_os/identity/hashes.py",
    "src/btceth_os/identity/provenance.py",
    "src/btceth_os/quality/contracts.py",
    "src/btceth_os/sources/registry.py",
    "tests/test_phase1b_0.py",
]

missing_files = [f for f in required_files if not (root / f).is_file()]
checks["required_files_exist"] = {
    "expected_files_count": len(required_files),
    "missing_files": missing_files,
    "pass": len(missing_files) == 0,
}

# 4. Open-Source Archive Hashing & License Verification
manifest_path = reports / "OPEN_SOURCE_SOURCE_MANIFEST.json"
archive_results: list[dict[str, object]] = []
archive_all_ok = True

if manifest_path.is_file():
    manifest_data = json.loads(manifest_path.read_text())
    for item in manifest_data.get("archives", []):
        z_path = Path(item["absolute_source_path"])
        item_ok = True
        err = None
        recomputed_sha = None

        if not z_path.is_file():
            item_ok = False
            err = "file_missing"
        elif z_path.stat().st_size != item["size_bytes"]:
            item_ok = False
            err = f"size_mismatch: expected {item['size_bytes']}, got {z_path.stat().st_size}"
        else:
            with open(z_path, "rb") as f:
                recomputed_sha = hashlib.file_digest(f, "sha256").hexdigest()
            if recomputed_sha != item["sha256"]:
                item_ok = False
                err = f"sha256_mismatch: expected {item['sha256']}, got {recomputed_sha}"
            else:
                try:
                    with zipfile.ZipFile(z_path) as z:
                        namelist = z.namelist()
                        if item["license_file_path"] not in namelist:
                            item_ok = False
                            err = f"license_file_missing_in_zip: {item['license_file_path']}"
                except Exception as ex:
                    item_ok = False
                    err = f"zip_read_error: {ex}"

        if not item_ok:
            archive_all_ok = False

        archive_results.append({
            "project": item["project"],
            "path": str(z_path),
            "expected_sha": item["sha256"],
            "recomputed_sha": recomputed_sha,
            "error": err,
            "pass": item_ok,
        })
else:
    archive_all_ok = False

checks["open_source_archives_verified"] = {
    "archive_count": len(archive_results),
    "all_passed": archive_all_ok,
    "archives": archive_results,
    "pass": archive_all_ok and len(archive_results) == 8,
}

# 5. Historical Dataset Registry Contract Checks
from btceth_os.sources.registry import load_historical_datasets_registry

reg_ok = True
reg_errors: list[str] = []
try:
    datasets = load_historical_datasets_registry()
    if len(datasets) < 14:
        reg_ok = False
        reg_errors.append(f"insufficient_datasets: expected >= 14, got {len(datasets)}")

    for d in datasets:
        if d.archive_support_status != "UNVERIFIED_SOURCE_PATH":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: expected UNVERIFIED_SOURCE_PATH, got {d.archive_support_status}")
        if d.daily_support != "UNVERIFIED":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: daily_support not UNVERIFIED")
        if d.monthly_support != "UNVERIFIED":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: monthly_support not UNVERIFIED")
        if d.checksum_support != "UNVERIFIED":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: checksum_support not UNVERIFIED")

        if d.market == "spot":
            policy = d.source_timestamp_policy
            if policy.get("type") != "date_versioned":
                reg_ok = False
                reg_errors.append(f"{d.dataset_id}: Spot timestamp policy must be date_versioned")
        elif d.market == "usdm":
            policy = d.source_timestamp_policy
            if policy.get("type") != "unverified":
                reg_ok = False
                reg_errors.append(f"{d.dataset_id}: USD-M timestamp policy must be independent unverified")

        if "PREMIUM" in d.dataset_id and d.source_dataset_name != "premiumPriceKlines":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: expected premiumPriceKlines, got {d.source_dataset_name}")

        if "FUNDING" in d.dataset_id and d.raw_format != "UNVERIFIED":
            reg_ok = False
            reg_errors.append(f"{d.dataset_id}: funding history raw_format must be UNVERIFIED")

except Exception as ex:
    reg_ok = False
    reg_errors.append(f"registry_load_error: {ex}")

checks["dataset_registry_contracts_pass"] = {
    "dataset_count": len(datasets) if "datasets" in locals() else 0,
    "errors": reg_errors,
    "pass": reg_ok,
}

# 6. Evaluate Overall Gate
criteria = {
    "git_current_branch": bool(checks["git_current_branch"]["pass"]),
    "git_descends_from_verified_1a": bool(checks["git_descends_from_verified_1a"]["pass"]),
    "git_phase1a_branch_untouched": bool(checks["git_phase1a_branch_untouched"]["pass"]),
    "git_remote_branch_aligned": bool(checks["git_remote_branch_aligned"]["pass"]),
    "git_tracked_clean": bool(checks["git_tracked_clean"]["pass"]),
    "automated_tests_pass": bool(checks["automated_tests_pass"]["pass"]),
    "security_scan_pass": bool(checks["security_scan_pass"]["pass"]),
    "required_files_exist": bool(checks["required_files_exist"]["pass"]),
    "open_source_archives_verified": bool(checks["open_source_archives_verified"]["pass"]),
    "dataset_registry_contracts_pass": bool(checks["dataset_registry_contracts_pass"]["pass"]),
}

all_passed = all(criteria.values())
status = "VERIFIED" if all_passed else "REMEDIATION_REQUIRED"

acceptance_json = {
    "phase": "1B.0",
    "status": status,
    "trading_capability": "ZERO" if criteria["security_scan_pass"] else "NOT_PROVEN",
    "criteria": criteria,
    "checks": checks,
}
(reports / "PHASE_1B_0_ACCEPTANCE.json").write_text(json.dumps(acceptance_json, indent=2))

md = [
    "# Phase 1B.0 Foundation, Provenance & Source Freeze Acceptance",
    "",
    f"PHASE_1B_0 = {status}",
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
    "## Open-Source Archive Verification Summary",
    "",
    "| Project | Path | Recomputed SHA-256 | Status |",
    "|---|---|---|---|",
])
for ar in archive_results:
    sha_display = ar.get("recomputed_sha") or "N/A"
    md.append(f"| {ar['project']} | `{ar['path']}` | `{sha_display[:16]}...` | {'PASS' if ar['pass'] else 'FAIL: ' + str(ar['error'])} |")

md.extend([
    "",
    "## Final Status",
    "",
    f"STATUS = {status}",
    f"NEXT = {'PHASE 1B.1 (PENDING REVIEW)' if all_passed else 'REMEDIATE FAILED ITEMS'}",
])
(reports / "PHASE_1B_0_ACCEPTANCE.md").write_text("\n".join(md) + "\n")

print("\n================ FINAL ================")
print(f"PHASE_1B_0 = {status}")
print(f"TRADING CAPABILITY = {'ZERO' if criteria['security_scan_pass'] else 'NOT PROVEN'}")
print(f"LOCAL HEAD = {local_head}")
print(f"ORIGIN HEAD = {remote_head}")
if not all_passed:
    failed = [name for name, passed in criteria.items() if not passed]
    print("FAILED CRITERIA =", ", ".join(failed))
print(f"NEXT = {'PHASE 1B.1 (PENDING REVIEW)' if all_passed else 'REMEDIATE FAILED ITEMS'}")
print("Reports:", reports)
raise SystemExit(0 if all_passed else 20)
