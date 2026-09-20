from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from btceth_os.sources.binance.archive_downloader import ArchiveDownloader
from btceth_os.sources.binance.archive_planner import plan_archive_requests
from btceth_os.sources.registry import load_historical_datasets_registry


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
ARTIFACTS = ROOT / "artifacts" / "phase1b2_acceptance"


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    tests = run_command([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    (REPORTS / "PHASE_1B_2_TEST_RESULTS.txt").write_text(tests.stdout + tests.stderr)

    security = run_command([sys.executable, "-m", "btceth_os.security_scan"])
    (REPORTS / "PHASE_1B_2_SECURITY_SCAN.txt").write_text(security.stdout + security.stderr)

    checks: dict[str, object] = {
        "automated_tests_pass": tests.returncode == 0,
        "security_scan_pass": security.returncode == 0 and '"trading_capability": "ZERO"' in security.stdout,
    }
    download_result: dict[str, object] | None = None
    download_error: str | None = None
    try:
        funding = next(
            dataset
            for dataset in load_historical_datasets_registry()
            if dataset.dataset_id == "BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY"
        )
        plan = plan_archive_requests(
            funding,
            start="2024-11-01",
            end="2024-11-30",
            as_of_utc="2024-12-10T00:00:00Z",
        )
        if len(plan) != 1:
            raise RuntimeError(f"expected one monthly funding archive, got {len(plan)}")
        result = ArchiveDownloader(ARTIFACTS / "raw").download(plan[0])
        download_result = result.to_dict()
        checks["public_archive_download_pass"] = (
            result.status in {"DOWNLOADED", "EXISTING_VALID"}
            and result.physical_sha256 == result.official_checksum
            and result.local_path is not None
            and Path(result.local_path).is_file()
            and result.receipt_path is not None
            and Path(result.receipt_path).is_file()
        )
    except Exception as exc:
        download_error = f"{type(exc).__name__}: {exc}"
        checks["public_archive_download_pass"] = False

    passed = all(bool(value) for value in checks.values())
    payload = {
        "phase": "1B.2",
        "status": "VERIFIED" if passed else "REMEDIATION_REQUIRED",
        "trading_capability": "ZERO" if checks["security_scan_pass"] else "NOT_PROVEN",
        "checks": checks,
        "archive_download": download_result,
        "archive_download_error": download_error,
    }
    (REPORTS / "PHASE_1B_2_ACCEPTANCE.json").write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Phase 1B.2 Streaming Downloader Acceptance",
        "",
        f"PHASE_1B_2 = {payload['status']}",
        "",
        "## Mechanically Derived Checks",
        "",
    ]
    lines.extend(f"- [{'x' if value else ' '}] `{name}`" for name, value in checks.items())
    if download_result:
        lines.extend([
            "",
            "## Public Archive Evidence",
            "",
            f"- Status: `{download_result['status']}`",
            f"- Physical SHA-256: `{download_result['physical_sha256']}`",
            f"- Official checksum: `{download_result['official_checksum']}`",
            f"- Local RAW object: `{download_result['local_path']}`",
        ])
    if download_error:
        lines.extend(["", f"Download error: `{download_error}`"])
    (REPORTS / "PHASE_1B_2_ACCEPTANCE.md").write_text("\n".join(lines) + "\n")
    print(f"PHASE_1B_2 = {payload['status']}")
    return 0 if passed else 20


if __name__ == "__main__":
    raise SystemExit(main())
