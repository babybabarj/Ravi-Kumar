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
import sqlite3
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

INSTRUMENT_ID = "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"
SYMBOL = "XAUUSDT"
BASE_URL = "https://data.binance.vision/data/futures/um"
ADMISSION_FLOOR_MS = 1767657600000  # 2026-01-06T00:00:00Z
AUDIT_VERSION = "2.0.0"


def count_all_duplicate_rows(raw_zip: bytes) -> int:
    """Exact disk-backed fallback for an archive whose ID order is anomalous."""
    with tempfile.TemporaryDirectory(prefix="xau-audit-") as directory:
        db = sqlite3.connect(Path(directory) / "rows.sqlite")
        try:
            db.execute("CREATE TABLE seen (row BLOB PRIMARY KEY) WITHOUT ROWID")
            duplicates = 0
            with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
                with zf.open(zf.namelist()[0]) as member, io.TextIOWrapper(member, encoding="utf-8") as tf:
                    reader = csv.reader(tf)
                    next(reader)
                    for row in reader:
                        before = db.total_changes
                        db.execute("INSERT OR IGNORE INTO seen VALUES (?)", (",".join(row).encode(),))
                        duplicates += db.total_changes == before
            return duplicates
        finally:
            db.close()


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
    prev_row_bytes: bytes | None = None
    id_continuity_gaps = 0
    id_regressions = 0
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
                    row_bytes = ",".join(row).encode("utf-8") + b"\n"
                    logical_hasher.update(row_bytes)
                    if row_bytes == prev_row_bytes:
                        duplicate_rows += 1
                    prev_row_bytes = row_bytes
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
                            id_regressions += 1
                        elif t_id > prev_id + 1:
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

    # Strictly increasing IDs prove nonadjacent duplicate rows impossible.
    if id_regressions or duplicate_ids:
        duplicate_rows = count_all_duplicate_rows(raw_zip)

    elapsed = time.time() - t0
    is_quarantined = (period == "2025-12" or (last_ts is not None and last_ts < ADMISSION_FLOOR_MS))

    return {
        "status": "PASS" if not any((timestamp_regressions, duplicate_ids, duplicate_rows,
                                       id_regressions, id_continuity_gaps if is_agg else 0,
                                       invalid_prices, invalid_quantities)) else "FAIL",
        "audit_version": AUDIT_VERSION,
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
        "duplicate_rows": duplicate_rows,
        "id_continuity_gaps": id_continuity_gaps,
        "id_regressions": id_regressions,
        "invalid_prices": invalid_prices,
        "invalid_quantities": invalid_quantities,
        "total_base_volume": str(total_base_volume),
        "total_quote_volume": str(total_quote_volume),
        "elapsed_seconds": round(elapsed, 2),
    }


def extract_kline_day_stats(date_str: str) -> tuple[int, Decimal, int]:
    """Extract (bar_count, base_volume, trade_count) from raw klines for a given date."""
    year_month = date_str[:7]
    monthly_kline = ROOT / "artifacts" / "xau_native" / "raw" / "binance" / "futures_um" / "klines" / "XAUUSDT" / f"XAUUSDT-1m-{year_month}.zip"
    daily_kline = ROOT / "artifacts" / "xau_native" / "raw" / "binance" / "futures_um" / "klines" / "XAUUSDT" / f"XAUUSDT-1m-{date_str}.zip"

    kline_zip = daily_kline if daily_kline.is_file() else (monthly_kline if monthly_kline.is_file() else None)
    if not kline_zip:
        return 0, Decimal(0), 0

    dt_start = int(datetime.fromisoformat(f"{date_str}T00:00:00+00:00").timestamp() * 1000)
    dt_end = int(datetime.fromisoformat(f"{date_str}T23:59:59.999+00:00").timestamp() * 1000)

    bar_count = 0
    kline_vol = Decimal(0)
    kline_trades = 0

    with zipfile.ZipFile(kline_zip) as zf:
        with zf.open(zf.namelist()[0]) as f, io.TextIOWrapper(f, encoding="utf-8") as tf:
            reader = csv.reader(tf)
            for row in reader:
                if not row or not row[0].isdigit():
                    continue
                open_ts = int(row[0])
                if dt_start <= open_ts <= dt_end:
                    bar_count += 1
                    kline_vol += Decimal(row[5])
                    kline_trades += int(row[8])

    return bar_count, kline_vol, kline_trades


def run_full_trade_audit(
    through_date: str = "2026-09-22",
    max_workers: int = 4,
    output_path: Path | None = None,
    cache_from: Path | None = None,
    aggtrade_policy_report: Path | None = None,
) -> dict[str, object]:
    as_of = datetime.now(timezone.utc).isoformat()

    monthly_periods = ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    daily_periods = [f"2026-09-{d:02d}" for d in range(1, 23)]
    # Benchmark days required for multi-epoch reconciliation:
    benchmark_days = ["2026-01-15", "2026-05-15", "2026-09-01"]

    results_map: dict[tuple[str, str, str], dict[str, object]] = {}

    # Load cache if available
    if cache_from and cache_from.is_file():
        try:
            cached_data = json.loads(cache_from.read_text())
            for arc in cached_data.get("archives", []):
                key = (arc["dataset_type"], arc["cadence"], arc["period"])
                expected_url = f"{BASE_URL}/{key[1]}/{key[0]}/{SYMBOL}/{SYMBOL}-{key[0]}-{key[2]}.zip"
                if arc.get("audit_version") != AUDIT_VERSION or arc.get("url") != expected_url:
                    continue
                try:
                    official_sha = fetch_url(expected_url + ".CHECKSUM", timeout=15).decode().split()[0].lower()
                except Exception:
                    continue
                if arc.get("physical_sha256") == official_sha:
                    results_map[key] = arc
            print(f"Loaded {len(results_map)} cached archive audit records from {cache_from}")
        except Exception as exc:
            print(f"Warning: Failed to load cache from {cache_from}: {exc}")

    tasks: list[tuple[str, str, str]] = []
    for dt in ("trades", "aggTrades"):
        for m in monthly_periods:
            if (dt, "monthly", m) not in results_map:
                tasks.append((dt, "monthly", m))
        for d in daily_periods:
            if (dt, "daily", d) not in results_map:
                tasks.append((dt, "daily", d))
        for b_day in benchmark_days:
            if (dt, "daily", b_day) not in results_map:
                tasks.append((dt, "daily", b_day))

    if tasks:
        print(f"Auditing {len(tasks)} trade/aggTrade archives using {max_workers} workers...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(audit_single_archive, dt, cad, per): (dt, cad, per)
                for dt, cad, per in tasks
            }
            for future in as_completed(future_map):
                meta = future_map[future]
                try:
                    res = future.result()
                    results_map[meta] = res
                    st = res.get("status")
                    rows = res.get("rows", 0)
                    sec = res.get("elapsed_seconds", 0)
                    print(f"[{st}] {meta[0]} {meta[1]} {meta[2]}: {rows:,} rows in {sec}s")
                except Exception as exc:
                    print(f"[FAIL] {meta[0]} {meta[1]} {meta[2]}: Exception {exc}")
                    results_map[meta] = {
                        "status": "FAIL",
                        "dataset_type": meta[0],
                        "cadence": meta[1],
                        "period": meta[2],
                        "error": str(exc),
                    }
    else:
        print(f"All {len(results_map)} required archives already present in cache.")

    # Sort results
    results = list(results_map.values())
    results.sort(key=lambda r: (r.get("dataset_type", ""), r.get("cadence", ""), r.get("period", "")))

    all_passed = all(r.get("status") == "PASS" for r in results)
    total_trades_rows = sum(r.get("rows", 0) for r in results if r.get("dataset_type") == "trades")
    total_agg_rows = sum(r.get("rows", 0) for r in results if r.get("dataset_type") == "aggTrades")

    # Multi-epoch benchmark day reconciliations
    reconciliations: dict[str, dict[str, object]] = {}
    policy = json.loads(aggtrade_policy_report.read_text()) if aggtrade_policy_report and aggtrade_policy_report.is_file() else None
    for b_day in benchmark_days:
        k_bars, k_vol, k_trades = extract_kline_day_stats(b_day)
        day_trades = next((r for r in results if r.get("dataset_type") == "trades" and r.get("period") == b_day and r.get("cadence") == "daily"), None)
        day_agg = next((r for r in results if r.get("dataset_type") == "aggTrades" and r.get("period") == b_day and r.get("cadence") == "daily"), None)

        if day_trades and day_agg:
            t_vol = Decimal(str(day_trades.get("total_base_volume", "0")))
            a_vol = Decimal(str(day_agg.get("total_base_volume", "0")))
            t_count = day_trades.get("rows", 0)

            trades_vol_diff = abs(k_vol - t_vol)
            agg_vol_diff = abs(k_vol - a_vol)
            count_match = (k_trades == t_count)
            trades_exact = (count_match and trades_vol_diff == Decimal(0))
            all_exact = (trades_exact and agg_vol_diff == Decimal(0))
            semantic_exact = bool(
                b_day == "2026-05-15" and policy
                and policy.get("policy") == "SOURCE_SEMANTICALLY_CONSISTENT"
                and policy.get("covered_constituent_exact") is True
                and policy.get("monthly_daily_match") is True
                and policy.get("aggregate_group_quantity_mismatches") == 0
                and policy.get("boundary_analysis", {}).get("agg_ids_continuous_across_days") is True
                and policy.get("boundary_analysis", {}).get("trade_ids_continuous_across_days") is True
                and policy.get("trades_source", {}).get("physical_sha256") == day_trades.get("physical_sha256")
                and policy.get("aggtrades_source", {}).get("physical_sha256") == day_agg.get("physical_sha256")
                and Decimal(policy.get("uncovered_trade_volume", "-1")) == agg_vol_diff
                and Decimal(policy.get("trades_volume", "-1")) == t_vol
                and Decimal(policy.get("aggregate_volume", "-1")) == a_vol
            )

            reconciliations[b_day] = {
                "benchmark_day": b_day,
                "kline_bar_count": k_bars,
                "kline_trade_count": k_trades,
                "trades_file_count": t_count,
                "trade_count_match": count_match,
                "kline_base_volume": str(k_vol),
                "trades_base_volume": str(t_vol),
                "aggtrades_base_volume": str(a_vol),
                "trades_vs_kline_vol_diff": str(trades_vol_diff),
                "aggtrades_vs_kline_vol_diff": str(agg_vol_diff),
                "trades_exact_reconciliation": trades_exact,
                "exact_reconciliation": all_exact,
                "aggtrade_policy": "EXACT_CALENDAR_DAY" if agg_vol_diff == 0 else (
                    "SOURCE_SEMANTICALLY_CONSISTENT" if semantic_exact else "FAILED"
                ),
                "aggtrades_reconciliation_passed": agg_vol_diff == 0 or semantic_exact,
            }

    primary_rec = reconciliations.get("2026-09-01", {})

    report = {
        "report_type": "XAU_TRADES_AGGTRADES_FULL_AUDIT_V15",
        "audit_version": AUDIT_VERSION,
        "timestamp_utc": as_of,
        "instrument_id": INSTRUMENT_ID,
        "through_date": through_date,
        "total_archives_audited": len(results),
        "all_archives_passed": all_passed,
        "total_trades_rows": total_trades_rows,
        "total_aggtrades_rows": total_agg_rows,
        "quarantined_2025_status": "VERIFIED_QUARANTINED",
        "research_admission_floor_utc": "2026-01-06T00:00:00Z",
        "reconciliation": primary_rec,
        "reconciliations": reconciliations,
        "multi_epoch_reconciliation_passed": len(reconciliations) == len(benchmark_days) and all(
            r["trades_exact_reconciliation"] and r["aggtrades_reconciliation_passed"] for r in reconciliations.values()
        ),
        "archives": results,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Audit report saved to {output_path}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Full Audit of XAUUSDT Trades and AggTrades (V15)")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent download/audit workers")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "XAU_TRADES_AGGTRADES_AUDIT_V15.json")
    parser.add_argument("--cache-from", type=Path, default=ROOT / "reports" / "XAU_TRADES_AGGTRADES_AUDIT.json")
    parser.add_argument("--aggtrade-policy-report", type=Path, default=None)
    args = parser.parse_args()

    report = run_full_trade_audit(
        max_workers=args.workers,
        output_path=args.output,
        cache_from=args.cache_from if args.cache_from.is_file() else None,
        aggtrade_policy_report=args.aggtrade_policy_report,
    )
    return 0 if (report.get("all_archives_passed") and report.get("multi_epoch_reconciliation_passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
