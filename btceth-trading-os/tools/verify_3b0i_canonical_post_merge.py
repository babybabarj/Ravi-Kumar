"""Verifier for current canonical post-merge state following Round 3B.0I acceptance.

Verifies:
- Current canonical HEAD == fb2d2c1f25f199ea040212fe683e64776754b805
- Canonical tag btceth-reliability-3b0i-canonical-2026-09-23 resolves to canonical HEAD
- Reliability evidence branch matches canonical HEAD
- Tested commit parent (4612bb0e6cdc64b9f28a352d213305e7ffb692a2) preserved
- Tested tree SHA (e4859f17d25d31d12f31e2116c3c740259e244f1) preserved
- Evidence payload hash matches ROUND3B_0I acceptance report
- WIP safety branch (11d6e370db0d27cd635528a3c530286b28c60416) preserved
- BTC/ETH holdout remains locked with 0 allowed accesses
- Zero shadow/paper promotions
- Security clean (trading capability ZERO, 0 hits)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.research.data_guard import verify_access_ledger_integrity
from btceth_os.research.promotion_state import inspect_promotion_state

EXPECTED_CANONICAL_SHA = "fb2d2c1f25f199ea040212fe683e64776754b805"
EXPECTED_TESTED_PARENT_SHA = "4612bb0e6cdc64b9f28a352d213305e7ffb692a2"
EXPECTED_TESTED_TREE_SHA = "e4859f17d25d31d12f31e2116c3c740259e244f1"
EXPECTED_WIP_SAFETY_SHA = "11d6e370db0d27cd635528a3c530286b28c60416"
EXPECTED_CANONICAL_TAG = "btceth-reliability-3b0i-canonical-2026-09-23"
EXPECTED_0I_PAYLOAD_SHA = "5bf089f4a14a888089cb610aae58cd0eed15c09340bbeff7856da22d83dd6346"


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def run_python(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def compute_payload_sha256(report: dict[str, Any]) -> str:
    clean = {k: v for k, v in report.items() if k != "acceptance_payload_sha256"}
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluate() -> tuple[dict[str, bool], dict[str, Any]]:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    # 1. Canonical baseline
    try:
        remote_canonical = git("rev-parse", "origin/btceth-phase1b")
        checks["CURRENT_CANONICAL_BASELINE"] = remote_canonical == EXPECTED_CANONICAL_SHA
        details["remote_canonical"] = remote_canonical
    except Exception as exc:
        checks["CURRENT_CANONICAL_BASELINE"] = False
        details["remote_canonical_error"] = str(exc)

    # 2. Canonical snapshot tag
    try:
        tag_commit = git("rev-parse", f"{EXPECTED_CANONICAL_TAG}^{{commit}}")
        checks["CANONICAL_TAG_VERIFIED"] = tag_commit == EXPECTED_CANONICAL_SHA
        details["tag_commit"] = tag_commit
    except Exception as exc:
        checks["CANONICAL_TAG_VERIFIED"] = False
        details["tag_error"] = str(exc)

    # 3. Accepted reliability branch
    try:
        reliability_sha = git("rev-parse", "origin/btceth-round3b-reliability")
        checks["RELIABILITY_BRANCH_MATCHES"] = reliability_sha == EXPECTED_CANONICAL_SHA
        details["reliability_sha"] = reliability_sha
    except Exception as exc:
        checks["RELIABILITY_BRANCH_MATCHES"] = False
        details["reliability_error"] = str(exc)

    # 4. Tested commit parent
    try:
        parent_sha = git("rev-parse", f"{EXPECTED_CANONICAL_SHA}^")
        checks["TESTED_PARENT_PRESERVED"] = parent_sha == EXPECTED_TESTED_PARENT_SHA
        details["parent_sha"] = parent_sha
    except Exception as exc:
        checks["TESTED_PARENT_PRESERVED"] = False
        details["parent_error"] = str(exc)

    # 5. Tested tree SHA
    try:
        tree_sha = git("rev-parse", f"{EXPECTED_TESTED_PARENT_SHA}^{{tree}}")
        checks["TESTED_TREE_PRESERVED"] = tree_sha == EXPECTED_TESTED_TREE_SHA
        details["tree_sha"] = tree_sha
    except Exception as exc:
        checks["TESTED_TREE_PRESERVED"] = False
        details["tree_error"] = str(exc)

    # 6. Evidence payload hash
    try:
        report_path = ROOT / "reports" / "ROUND3B_0I_RELIABILITY_ACCEPTANCE.json"
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        payload_sha = compute_payload_sha256(report_data)
        checks["EVIDENCE_PAYLOAD_HASH_PRESERVED"] = (
            payload_sha == EXPECTED_0I_PAYLOAD_SHA
            and report_data.get("acceptance_payload_sha256") == EXPECTED_0I_PAYLOAD_SHA
        )
        details["payload_sha"] = payload_sha
    except Exception as exc:
        checks["EVIDENCE_PAYLOAD_HASH_PRESERVED"] = False
        details["payload_error"] = str(exc)

    # 7. WIP safety branch preserved
    try:
        wip_sha = git("rev-parse", "origin/btceth-round3b-wip-safety")
        checks["WIP_SAFETY_PRESERVED"] = wip_sha == EXPECTED_WIP_SAFETY_SHA
        details["wip_sha"] = wip_sha
    except Exception as exc:
        checks["WIP_SAFETY_PRESERVED"] = False
        details["wip_error"] = str(exc)

    # 8. Holdout locked
    try:
        ledger_ok, count, _, ledger = verify_access_ledger_integrity()
        checks["HOLDOUT_LOCKED"] = (
            ledger_ok
            and count > 0
            and ledger.get("allowed_holdout_accesses") == 0
        )
        details["holdout_entries"] = count
    except Exception as exc:
        checks["HOLDOUT_LOCKED"] = False
        details["holdout_error"] = str(exc)

    # 9. Zero promotions
    try:
        prom = inspect_promotion_state()
        checks["ZERO_PROMOTIONS"] = (
            prom.status == "VERIFIED"
            and prom.persistent_approved_shadow == 0
            and prom.persistent_approved_paper == 0
            and prom.runtime_approved_shadow == 0
            and prom.runtime_approved_paper == 0
        )
        details["total_experiments"] = prom.persistent_total_experiments
    except Exception as exc:
        checks["ZERO_PROMOTIONS"] = False
        details["promotion_error"] = str(exc)

    # 10. Security scan zero
    try:
        sec = run_python("-m", "btceth_os.security_scan")
        scan = json.loads(sec.stdout)
        checks["SECURITY_CLEAN"] = (
            sec.returncode == 0
            and scan.get("trading_capability") == "ZERO"
            and scan.get("hits") == []
        )
    except Exception as exc:
        checks["SECURITY_CLEAN"] = False
        details["security_error"] = str(exc)

    return checks, details


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify 3B.0I Canonical Post-Merge State")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    checks, details = evaluate()
    all_passed = all(checks.values())
    status = "VERIFIED" if all_passed else "REMEDIATION_REQUIRED"

    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    print(f"GATES = {sum(checks.values())}/{len(checks)}")
    print(f"CANONICAL_POST_MERGE_STATUS = {status}")

    if args.json:
        print(json.dumps({"status": status, "checks": checks, "details": details}, indent=2, sort_keys=True))

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
