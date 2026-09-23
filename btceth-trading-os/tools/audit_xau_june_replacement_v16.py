"""Replace the anomalous official June monthly trades archive with daily archives."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_xau_trades_and_aggtrades import audit_single_archive

DAYS = tuple(f"2026-06-{day:02d}" for day in range(1, 31))


def build() -> dict[str, object]:
    monthly_report = json.loads((ROOT / "reports/XAU_TRADES_AGGTRADES_AUDIT_V16.json").read_text())
    monthly = next(a for a in monthly_report["archives"] if a["dataset_type"] == "trades" and a["cadence"] == "monthly" and a["period"] == "2026-06")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = {pool.submit(audit_single_archive, "trades", "daily", day): day for day in DAYS}
        rows = {future[f]: f.result() for f in as_completed(future)}
    ordered = [rows[day] for day in DAYS]
    day_boundaries = all(
        r.get("first_timestamp_ms", 0) >= int(datetime.fromisoformat(day + "T00:00:00+00:00").timestamp() * 1000)
        and r.get("last_timestamp_ms", 0) < int(datetime.fromisoformat(day + "T00:00:00+00:00").timestamp() * 1000) + 86_400_000
        for day, r in zip(DAYS, ordered)
    )
    result: dict[str, object] = {
        "report_type": "XAU_JUNE_TRADES_REPLACEMENT_V16",
        "affected_archive": monthly,
        "replacement_policy": "DAILY_SAME_SERIES_REPLACEMENT",
        "reason": "Official checksum-matching June monthly trades archive has timestamp regressions and duplicate IDs; use only 30 checksum-verified daily trades archives for June.",
        "daily_archive_count": len(ordered),
        "daily_rows": sum(int(r.get("rows", 0)) for r in ordered),
        "daily_base_volume": str(sum((Decimal(str(r.get("total_base_volume", "0"))) for r in ordered), Decimal(0))),
        "monthly_rows": monthly.get("rows"),
        "monthly_base_volume": monthly.get("total_base_volume"),
        "daily_boundaries_valid": day_boundaries,
        "daily_archives": ordered,
    }
    result["replacement_passed"] = (
        monthly["status"] == "FAIL"
        and monthly["timestamp_regressions"] > 0
        and monthly["duplicate_ids"] > 0
        and day_boundaries
        and len(ordered) == 30
        and all(r.get("status") == "PASS" and r.get("duplicate_rows") == 0 for r in ordered)
    )
    return result


def main() -> int:
    result = build()
    path = ROOT / "reports/XAU_JUNE_TRADES_REPLACEMENT_V16.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("daily_archives", "affected_archive")}, indent=2))
    return 0 if result["replacement_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
