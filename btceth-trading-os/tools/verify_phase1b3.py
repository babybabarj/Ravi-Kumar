from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from btceth_os.sources.binance.archive_catalog import ArchiveCatalog
from btceth_os.sources.binance.archive_downloader import ArchiveDownloader
from btceth_os.sources.binance.archive_planner import plan_archive_requests
from btceth_os.sources.registry import load_historical_datasets_registry


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
ARTIFACTS = ROOT / "artifacts" / "phase1b3_acceptance"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    tests = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    (REPORTS / "PHASE_1B_3_TEST_RESULTS.txt").write_text(tests.stdout + tests.stderr)
    security = _run([sys.executable, "-m", "btceth_os.security_scan"])
    (REPORTS / "PHASE_1B_3_SECURITY_SCAN.txt").write_text(security.stdout + security.stderr)

    checks: dict[str, bool] = {
        "automated_tests_pass": tests.returncode == 0,
        "security_scan_pass": security.returncode == 0 and '"trading_capability": "ZERO"' in security.stdout,
    }
    evidence: dict[str, object] = {}
    error: str | None = None
    catalog: ArchiveCatalog | None = None
    try:
        funding = next(
            dataset
            for dataset in load_historical_datasets_registry()
            if dataset.dataset_id == "BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY"
        )
        plan = plan_archive_requests(funding, "2024-11-01", "2024-11-30", "2024-12-10T00:00:00Z")
        if len(plan) != 1:
            raise RuntimeError(f"expected exactly one funding archive, got {len(plan)}")
        result = ArchiveDownloader(ARTIFACTS / "raw").download(plan[0])
        catalog = ArchiveCatalog(ARTIFACTS / "archive_catalog.sqlite")
        write = catalog.record_download(result)
        rows = catalog.objects()
        checks["raw_object_catalogue_pass"] = (
            result.physical_sha256 == result.official_checksum
            and catalog.journal_mode() == "wal"
            and len(rows) == 1
            and rows[0]["physical_sha256"] == result.physical_sha256
            and rows[0]["source_url"] == result.spec.archive_url
        )
        evidence = {
            "download": result.to_dict(),
            "catalog_write": {
                "object_inserted": write.object_inserted,
                "retrieval_inserted": write.retrieval_inserted,
                "physical_sha256": write.physical_sha256,
            },
            "catalog_row": rows[0],
            "journal_mode": catalog.journal_mode(),
        }
    except Exception as exc:
        checks["raw_object_catalogue_pass"] = False
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if catalog is not None:
            catalog.close()

    verified = all(checks.values())
    payload = {
        "phase": "1B.3",
        "status": "VERIFIED" if verified else "REMEDIATION_REQUIRED",
        "trading_capability": "ZERO" if checks["security_scan_pass"] else "NOT_PROVEN",
        "checks": checks,
        "evidence": evidence,
        "error": error,
    }
    (REPORTS / "PHASE_1B_3_ACCEPTANCE.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = ["# Phase 1B.3 Historical RAW Object Catalog Acceptance", "", f"PHASE_1B_3 = {payload['status']}", ""]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in checks.items())
    if evidence:
        row = evidence["catalog_row"]
        lines.extend(["", f"- Catalog journal: `{evidence['journal_mode']}`", f"- Physical SHA-256: `{row['physical_sha256']}`"])
    if error:
        lines.extend(["", f"Error: `{error}`"])
    (REPORTS / "PHASE_1B_3_ACCEPTANCE.md").write_text("\n".join(lines) + "\n")
    print(f"PHASE_1B_3 = {payload['status']}")
    return 0 if verified else 20


if __name__ == "__main__":
    raise SystemExit(main())
