from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from btceth_os.sources.binance.archive_downloader import ArchiveDownloader
from btceth_os.sources.binance.archive_parser import iter_bronze_records
from btceth_os.sources.binance.archive_planner import plan_archive_requests
from btceth_os.sources.binance.historical_silver import write_historical_silver
from btceth_os.sources.registry import load_historical_datasets_registry


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
ARTIFACTS = ROOT / "artifacts" / "phase1b5_acceptance"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    tests = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    security = _run([sys.executable, "-m", "btceth_os.security_scan"])
    (REPORTS / "PHASE_1B_5_TEST_RESULTS.txt").write_text(tests.stdout + tests.stderr)
    (REPORTS / "PHASE_1B_5_SECURITY_SCAN.txt").write_text(security.stdout + security.stderr)
    checks: dict[str, bool] = {
        "automated_tests_pass": tests.returncode == 0,
        "security_scan_pass": security.returncode == 0 and '"trading_capability": "ZERO"' in security.stdout,
    }
    evidence: dict[str, object] = {}
    error: str | None = None
    try:
        funding = next(d for d in load_historical_datasets_registry() if d.dataset_id == "BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY")
        plan = plan_archive_requests(funding, "2024-11-01", "2024-11-30", "2024-12-10T00:00:00Z")
        if len(plan) != 1:
            raise RuntimeError(f"expected one funding archive, got {len(plan)}")
        result = ArchiveDownloader(ARTIFACTS / "raw").download(plan[0])
        if result.local_path is None or result.physical_sha256 is None:
            raise RuntimeError("verified RAW archive has no local path or physical SHA-256")
        records = list(iter_bronze_records(result.local_path, funding))
        silver_path = ARTIFACTS / "silver" / f"funding-{result.physical_sha256}.parquet"
        if not silver_path.exists():
            _, findings = write_historical_silver(records, silver_path, result.physical_sha256)
        else:
            findings = []
        table = pq.read_table(silver_path)
        checks["public_archive_to_silver_pass"] = (
            bool(records)
            and table.num_rows == len(records)
            and table.schema.field("funding_rate").type == pa.decimal128(38, 18)
            and table.column("source_object_sha256")[0].as_py() == result.physical_sha256
            and table.column("source_row_number")[0].as_py() >= 1
        )
        evidence = {
            "download": result.to_dict(),
            "parsed_rows": len(records),
            "silver_path": str(silver_path),
            "silver_rows": table.num_rows,
            "silver_schema": str(table.schema),
            "quality_findings": [finding.__dict__ for finding in findings],
        }
    except Exception as exc:
        checks["public_archive_to_silver_pass"] = False
        error = f"{type(exc).__name__}: {exc}"

    verified = all(checks.values())
    payload = {
        "phase": "1B.5",
        "status": "VERIFIED" if verified else "REMEDIATION_REQUIRED",
        "trading_capability": "ZERO" if checks["security_scan_pass"] else "NOT_PROVEN",
        "checks": checks,
        "evidence": evidence,
        "error": error,
    }
    (REPORTS / "PHASE_1B_5_ACCEPTANCE.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = ["# Phase 1B.5 Historical Silver Acceptance", "", f"PHASE_1B_5 = {payload['status']}", ""]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in checks.items())
    if evidence:
        lines.extend(["", f"- Parsed rows: `{evidence['parsed_rows']}`", f"- Silver rows: `{evidence['silver_rows']}`"])
    if error:
        lines.extend(["", f"Error: `{error}`"])
    (REPORTS / "PHASE_1B_5_ACCEPTANCE.md").write_text("\n".join(lines) + "\n")
    print(f"PHASE_1B_5 = {payload['status']}")
    return 0 if verified else 20


if __name__ == "__main__":
    raise SystemExit(main())
