"""Phase 2E audit acceptance. Passing verifies the stop gate, not research readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.sources.binance.archive_paths import BinancePathError, build_archive_paths
from btceth_os.sources.registry import load_historical_datasets_registry
from tools.verify_multiasset_v12 import git, verify as verify_v12


def digest(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify(mode: str) -> tuple[dict[str, bool], dict[str, str]]:
    checks, details = verify_v12("CODE_ACCEPTANCE")
    try:
        xau_path = build_archive_paths("usdm", "trades", "XAUUSDT", "monthly", "2026-01")
        try:
            build_archive_paths("spot", "trades", "XAUUSDT", "monthly", "2026-01")
            spot_rejected = False
        except BinancePathError:
            spot_rejected = True
        checks["XAU_USDM_ONLY_ARCHIVE_PATH"] = xau_path.archive_url.startswith(
            "https://data.binance.vision/data/futures/um/monthly/trades/XAUUSDT/"
        ) and spot_rejected
        xau = load_historical_datasets_registry(ROOT / "config" / "xau_datasets.yaml")
        legacy = load_historical_datasets_registry()
        checks["SEPARATE_XAU_SOURCE_CATALOG"] = (
            len(legacy) == 20 and len(xau) == 7
            and {item.instrument for item in xau} == {"BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"}
            and xau[-1].frequency == "event" and xau[-1].daily_support == "VERIFIED_FALSE"
        )
    except (ValueError, KeyError, FileNotFoundError) as exc:
        details["xau_catalog_error"] = f"{type(exc).__name__}: {exc}"
        checks["XAU_USDM_ONLY_ARCHIVE_PATH"] = False
        checks["SEPARATE_XAU_SOURCE_CATALOG"] = False
    if mode == "FINAL_EVIDENCE_ACCEPTANCE":
        try:
            report = json.loads((ROOT / "reports" / "PHASE2E_XAU_DATA_GATE.json").read_text())
            audit_bytes = (ROOT / "reports" / "XAU_NATIVE_COVERAGE_AUDIT.json").read_bytes()
            audit = json.loads(audit_bytes)
            payload = {key: value for key, value in report.items() if key != "payload_sha256"}
            checks["EVIDENCE_PAYLOAD"] = digest(payload) == report.get("payload_sha256")
            checks["AUDIT_SOURCE_DIGEST"] = hashlib.sha256(audit_bytes).hexdigest() == report.get("audit_report_physical_sha256")
            checks["BAR_COVERAGE_AND_DAILY_REPAIR"] = (
                audit["through_utc_day"] == "2026-09-22"
                and all(item["status"] == "PASS" for item in audit["coverage"].values())
                and len(audit["daily_repair_sources"]) == 3
                and {item["period"] for item in audit["daily_repair_sources"]} == {"2026-06-29"}
                and audit["source_gap_status"] == "REPAIRED_BY_OFFICIAL_DAILY"
            )
            checks["RESEARCH_STAYS_BLOCKED"] = (
                report["status"] == "PHASE_E_BLOCKED"
                and audit["research_admission"].startswith("BLOCKED")
                and report["strategy_approved"] is False
                and report["mainnet_order_mutation"] == "DISABLED"
            )
            changed = git("diff", "--name-only", "HEAD^", "HEAD").splitlines()
            checks["TESTED_CODE_TREE"] = (
                git("rev-parse", "HEAD^") == report["tested_code_commit_sha"]
                and git("rev-parse", f"{report['tested_code_commit_sha']}^{{tree}}") == report["tested_tree_sha"]
            )
            checks["EVIDENCE_ONLY_COMMIT"] = bool(changed) and all(
                item.startswith("btceth-trading-os/reports/") for item in changed
            )
        except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
            details["evidence_error"] = f"{type(exc).__name__}: {exc}"
            for key in ("EVIDENCE_PAYLOAD", "AUDIT_SOURCE_DIGEST", "BAR_COVERAGE_AND_DAILY_REPAIR", "RESEARCH_STAYS_BLOCKED", "TESTED_CODE_TREE", "EVIDENCE_ONLY_COMMIT"):
                checks[key] = False
        checks["REMOTE_HEAD"] = git("rev-parse", "HEAD") == git("rev-parse", "origin/btceth-phase2-multiasset")
    return checks, details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("CODE_ACCEPTANCE", "FINAL_EVIDENCE_ACCEPTANCE"), required=True)
    args = parser.parse_args()
    checks, details = verify(args.mode)
    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    print(f"GATES = {sum(checks.values())}/{len(checks)}")
    print(json.dumps(details, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
