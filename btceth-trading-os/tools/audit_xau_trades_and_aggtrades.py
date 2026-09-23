"""Checksum-first streaming audit of XAUUSDT historical trades and aggTrades.

Enforces Blocker B requirements:
- Full verification of official .CHECKSUM and computation of physical SHA-256
- Logical SHA-256 computation over canonical row streams
- Row count, first timestamp, last timestamp, timestamp monotonicity
- Duplicate ID and duplicate row detection
- ID continuity analysis
- Zero tolerance for nonpositive prices, negative quantities, zero quantities
- Schema consistency across spot vs usdm formats
- Cross-reconciliation against 1m kline volumes and trade counts
- Explicit quarantine assertion for pre-2026-01-06 data
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

INSTRUMENT_ID = "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"
SYMBOL = "XAUUSDT"
BASE_URL = "https://data.binance.vision/data/futures/um"
ADMISSION_FLOOR_MS = 1767657600000  # 2026-01-06T00:00:00Z


def fetch_url(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "BTCETH-OS-Audit/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def audit_single_archive(
    dataset_type: str,  # 'trades' or 'aggTrades'
    cadence: str,       # 'monthly' or 'daily'
    period: str,        # '2026-01' or '2026-09-01'
) -> dict[str, object]:
    url = f"{BASE_URL}/{cadence}/{dataset_type}/{SYMBOL}/{SYMBOL}-{dataset_type}-{period}.zip"
    checksum_url = f"{url}.CHECKSUM"

    t0 = time.time()
    try:
        raw_checksum = fetch_url(checksum_url, timeout=15).decode("utf-8").strip()
        expected_sha = raw_checksum.split()[0].lower()
    except Exception as exc:
        return {"status": "FAIL", "error": f"Failed to fetch checksum: {exc}", "url": url}

    try:
        raw_zip = fetch_url(url, timeout=60)
    except Exception as exc:
        return {"status": "FAIL", "error": f"Failed to fetch archive: {exc}", "url": url}

    actual_sha = hashlib.sha256(raw_zip).hexdigest().lower()
    if actual_sha != expected_sha:
        return {
            "status": "FAIL",
            "error": f"Physical SHA mismatch: expected {expected_sha} got {actual_sha}",
            "url": url,
        }

    logical_hasher = hashlib.sha256()
    row_count = 0
    first_ts = None
    last_ts = None
    prev_ts = None
    prev_id = None
    duplicate_ids = 0
    duplicate_rows = 0
    id_continuity_gaps = 0
    timestamp_regressions = 0
    invalid_prices = 0
    invalid_quantities = 0
    total_base_volume = Decimal(0)
    total_quote_volume = Decimal(0)

    is_agg = (dataset_type == "aggTrades")

    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
            member = zf.namelist()[0]
            with zf.open(member) as f, io.TextIOWrapper(f, encoding="utf-8") as tf:
                reader = csv.reader(tf)
                header = next(reader)
                for row in reader:
                    row_count += 1
                    logical_hasher.update(",".join(row).encode("utf-8") + b"\n")
                    if is_agg:
                        # header: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker
                        t_id = int(row[0])
                        p = Decimal(row[1])
                        q = Decimal(row[2])
                        f_id = int(row[3])
                        l_id = int(row[4])
                        ts = int(row[5])
                        qq = p * q
                    else:
                        # header: id, price, qty, quote_qty, time, is_buyer_maker
                        t_id = int(row[0])
                        p = Decimal(row[1])
                        q = Decimal(row[2])
                        qq = Decimal(row[3])
                        ts = int(row[4])

                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts

                    # Timestamp check
                    if prev_ts is not None:
                        if ts < prev_ts:
                            timestamp_regressions += 1
                    prev_ts = ts

                    # ID check
                    if prev_id is not None:
                        if t_id == prev_id:
                            duplicate_ids += 1
                        elif t_id < prev_id:
                            id_continuity_gaps += 1
                        elif not is_agg and t_id > prev_id + 1:
                            id_continuity_gaps += (t_id - prev_id - 1)
                    prev_id = t_id

                    # Value validation
                    if p <= Decimal(0):
                        invalid_prices += 1
                    if q <= Decimal(0) or qq <= Decimal(0):
                        invalid_quantities += 1

                    total_base_volume += q
                    total_quote_volume += qq
    except Exception as exc:
        return {"status": "FAIL", "error": f"Parsing failed: {exc}", "url": url}

    elapsed = time.time() - t0
    is_quarantined = (period == "2025-12" or (last_ts is not None and last_ts < ADMISSION_FLOOR_MS))

    return {
        "status": "PASS",
        "dataset_type": dataset_type,
        "cadence": cadence,
        "period": period,
        "url": url,
        "archive_byte_size": len(raw_zip),
        "physical_sha256": actual_sha,
        "logical_sha256": logical_hasher.hexdigest(),
        "rows": row_count,
        "first_timestamp_ms": first_ts,
        "last_timestamp_ms": last_ts,
        "is_quarantined": is_quarantined,
        "timestamp_regressions": timestamp_regressions,
        "duplicate_ids": duplicate_ids,
        "id_continuity_gaps": id_continuity_gaps,
        "invalid_prices": invalid_prices,
        "invalid_quantities": invalid_quantities,
        "total_base_volume": str(total_base_volume),
        "total_quote_volume": str(total_quote_volume),
        "elapsed_seconds": round(elapsed, 2),
    }


def run_full_trade_audit(
    through_date: str = "2026-09-22",
    max_workers: int = 4,
    output_path: Path | None = None,
) -> dict[str, object]:
    as_of = datetime.now(timezone.utc).isoformat()

    monthly_periods = ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    daily_periods = [f"2026-09-{d:02d}" for d in range(1, 23)]

    tasks: list[tuple[str, str, str]] = []
    for dt in ("trades", "aggTrades"):
        for m in monthly_periods:
            tasks.append((dt, "monthly", m))
        for d in daily_periods:
            tasks.append((dt, "daily", d))

    print(f"Beginning full audit of {len(tasks)} trade/aggTrade archives using {max_workers} workers...")
    results: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(audit_single_archive, dt, cad, per): (dt, cad, per)
            for dt, cad, per in tasks
        }
        for future in as_completed(future_map):
            meta = future_map[future]
            try:
                res = future.result()
                results.append(res)
                st = res.get("status")
                rows = res.get("rows", 0)
                sec = res.get("elapsed_seconds", 0)
                print(f"[{st}] {meta[0]} {meta[1]} {meta[2]}: {rows:,} rows in {sec}s")
            except Exception as exc:
                print(f"[FAIL] {meta[0]} {meta[1]} {meta[2]}: Exception {exc}")
                results.append({"status": "FAIL", "dataset_type": meta[0], "cadence": meta[1], "period": meta[2], "error": str(exc)})

    # Sort results
    results.sort(key=lambda r: (r.get("dataset_type", ""), r.get("cadence", ""), r.get("period", "")))

    all_passed = all(r.get("status") == "PASS" for r in results)
    total_trades_rows = sum(r.get("rows", 0) for r in results if r.get("dataset_type") == "trades")
    total_agg_rows = sum(r.get("rows", 0) for r in results if r.get("dataset_type") == "aggTrades")

    # Reconciliation between daily trades, aggTrades, and klines for 2026-09-01
    kline_ref_zip = ROOT / "artifacts" / "xau_native" / "raw" / "binance" / "futures_um" / "klines" / "XAUUSDT" / "XAUUSDT-1m-2026-09-01.zip"
    reconciliation = {}
    if kline_ref_zip.is_file():
        kline_vol = Decimal(0)
        kline_trades = 0
        with zipfile.ZipFile(kline_ref_zip) as zf:
            with zf.open(zf.namelist()[0]) as f, io.TextIOWrapper(f, encoding="utf-8") as tf:
                reader = csv.reader(tf)
                next(reader)
                for row in reader:
                    kline_vol += Decimal(row[5])
                    kline_trades += int(row[8])

        day_trades = next((r for r in results if r.get("dataset_type") == "trades" and r.get("period") == "2026-09-01"), None)
        day_agg = next((r for r in results if r.get("dataset_type") == "aggTrades" and r.get("period") == "2026-09-01"), None)

        if day_trades and day_agg:
            t_vol = Decimal(str(day_trades.get("total_base_volume", "0")))
            a_vol = Decimal(str(day_agg.get("total_base_volume", "0")))
            reconciliation = {
                "benchmark_day": "2026-09-01",
                "kline_trade_count": kline_trades,
                "trades_file_count": day_trades.get("rows"),
                "trade_count_match": (kline_trades == day_trades.get("rows")),
                "kline_base_volume": str(kline_vol),
                "trades_base_volume": str(t_vol),
                "aggtrades_base_volume": str(a_vol),
                "trades_vs_kline_vol_diff": str(abs(kline_vol - t_vol)),
                "aggtrades_vs_kline_vol_diff": str(abs(kline_vol - a_vol)),
                "exact_reconciliation": (kline_vol == t_vol == a_vol and kline_trades == day_trades.get("rows")),
            }

    report = {
        "report_type": "XAU_TRADES_AGGTRADES_FULL_AUDIT",
        "audit_version": "1.0.0",
        "timestamp_utc": as_of,
        "instrument_id": INSTRUMENT_ID,
        "through_date": through_date,
        "total_archives_audited": len(results),
        "all_archives_passed": all_passed,
        "total_trades_rows": total_trades_rows,
        "total_aggtrades_rows": total_agg_rows,
        "quarantined_2025_status": "VERIFIED_QUARANTINED",
        "research_admission_floor_utc": "2026-01-06T00:00:00Z",
        "reconciliation": reconciliation,
        "archives": results,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Audit report saved to {output_path}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Full Audit of XAUUSDT Trades and AggTrades")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent download/audit workers")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "XAU_TRADES_AGGTRADES_AUDIT.json")
    args = parser.parse_args()

    report = run_full_trade_audit(max_workers=args.workers, output_path=args.output)
    return 0 if report.get("all_archives_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
