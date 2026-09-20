from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from btceth_os.sources.binance.archive_downloader import ArchiveDownloader
from btceth_os.sources.binance.archive_parser import iter_bronze_records
from btceth_os.sources.binance.archive_planner import plan_archive_requests
from btceth_os.sources.registry import load_historical_datasets_registry

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
ARTIFACTS = ROOT / "artifacts" / "phase1b4_acceptance"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    tests = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    security = _run([sys.executable, "-m", "btceth_os.security_scan"])
    (REPORTS / "PHASE_1B_4_TEST_RESULTS.txt").write_text(tests.stdout + tests.stderr)
    (REPORTS / "PHASE_1B_4_SECURITY_SCAN.txt").write_text(security.stdout + security.stderr)
    checks = {
        "automated_tests_pass": tests.returncode == 0,
        "security_scan_pass": security.returncode == 0 and '"trading_capability": "ZERO"' in security.stdout,
    }
    evidence: dict[str, object] = {}
    error = None
    try:
        funding = next(d for d in load_historical_datasets_registry() if d.dataset_id == "BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY")
        plan = plan_archive_requests(funding, "2024-11-01", "2024-11-30", "2024-12-10T00:00:00Z")
        result = ArchiveDownloader(ARTIFACTS / "raw").download(plan[0])
        records = list(iter_bronze_records(Path(result.local_path), funding))
        checks["public_archive_parse_pass"] = bool(records) and all(r.source_ts_unit == "ms" for r in records)
        evidence = {"download": result.to_dict(), "parsed_rows": len(records), "first_record": records[0].__dict__}
    except Exception as exc:
        checks["public_archive_parse_pass"] = False
        error = f"{type(exc).__name__}: {exc}"
    verified = all(checks.values())
    payload = {"phase": "1B.4", "status": "VERIFIED" if verified else "REMEDIATION_REQUIRED", "trading_capability": "ZERO" if checks["security_scan_pass"] else "NOT_PROVEN", "checks": checks, "evidence": evidence, "error": error}
    (REPORTS / "PHASE_1B_4_ACCEPTANCE.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = ["# Phase 1B.4 Bronze Parser Acceptance", "", f"PHASE_1B_4 = {payload['status']}", ""]
    lines.extend(f"- [{'x' if value else ' '}] `{key}`" for key, value in checks.items())
    if evidence:
        lines.append(f"- Parsed rows: `{evidence['parsed_rows']}`")
    if error:
        lines.append(f"- Error: `{error}`")
    (REPORTS / "PHASE_1B_4_ACCEPTANCE.md").write_text("\n".join(lines) + "\n")
    print(f"PHASE_1B_4 = {payload['status']}")
    return 0 if verified else 20


if __name__ == "__main__":
    raise SystemExit(main())
