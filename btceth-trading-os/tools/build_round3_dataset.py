#!/usr/bin/env python3
"""Multi-year canonical research dataset compiler for BTCETH Trading OS (Research Round 3).

Ingests 48 months (2020-01 to 2023-12) of:
1. Traded Spot 1m klines
2. Traded USD-M Perp 1m klines
3. Funding rate settlements (8h)
4. Official Mark Price 1m klines
5. Official Index Price 1m klines
6. Official Premium Index 1m klines
across BTCUSDT and ETHUSDT.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq

from btceth_os.research.manifest import compute_logical_sha256

ROOT = Path(__file__).resolve().parents[1]
SILVER_V3_DIR = ROOT / "artifacts" / "research" / "silver_v3"
RAW_ZIPS_DIR = ROOT / "artifacts" / "research" / "raw_zips"
REPORTS_DIR = ROOT / "reports"

BINANCE_VISION_BASE = "https://data.binance.vision/data"


def get_git_commit() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"


def generate_month_keys(start_year_month: str, end_year_month: str) -> list[str]:
    start_y, start_m = map(int, start_year_month.split("-"))
    end_y, end_m = map(int, end_year_month.split("-"))
    months = []
    curr_y, curr_m = start_y, start_m
    while (curr_y < end_y) or (curr_y == end_y and curr_m <= end_m):
        months.append(f"{curr_y:04d}-{curr_m:02d}")
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1
    return months


def fetch_and_extract_csv(url: str, retries: int = 4) -> tuple[str, bytes]:
    """Download ZIP archive with local caching and retries; return source SHA-256 and uncompressed CSV bytes."""
    RAW_ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    # Namespace by folder to avoid collisions if filenames match
    parts = url.replace("https://data.binance.vision/data/", "").split("/")
    filename = "_".join(parts)
    local_zip = RAW_ZIPS_DIR / filename

    data: bytes | None = None
    if local_zip.exists() and local_zip.stat().st_size > 500:
        data = local_zip.read_bytes()

    if data is None:
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "btceth-trading-os/3.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                local_zip.write_bytes(data)
                break
            except Exception as e:
                last_err = e
                import time
                time.sleep(1.0 * (attempt + 1))
        if data is None:
            raise RuntimeError(f"Failed to fetch {url} after {retries} attempts: {last_err}")

    source_sha256 = hashlib.sha256(data).hexdigest()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = zf.namelist()
        csv_name = [m for m in members if m.endswith(".csv")][0]
        csv_bytes = zf.read(csv_name)
    return source_sha256, csv_bytes


def process_kline_series(
    symbol: str,
    series_category: str,  # 'spot', 'perp', 'mark', 'index', 'premium'
    months: list[str],
    max_workers: int = 8,
) -> tuple[pa.Table, list[dict[str, str | int]], dict[str, int]]:
    """Download and compile multi-year 1m series into a single Arrow Table."""
    instrument_prefix = {
        "spot": "BINANCE:SPOT:",
        "perp": "BINANCE:USD_M_PERP:",
        "mark": "BINANCE:USD_M_MARK:",
        "index": "BINANCE:USD_M_INDEX:",
        "premium": "BINANCE:USD_M_PREMIUM:",
    }[series_category]
    instrument_id = f"{instrument_prefix}{symbol}"
    print(f"[{instrument_id}] Fetching {len(months)} months ({months[0]} to {months[-1]})...")

    tasks = []
    for m in months:
        if series_category == "spot":
            url = f"{BINANCE_VISION_BASE}/spot/monthly/klines/{symbol}/1m/{symbol}-1m-{m}.zip"
        elif series_category == "perp":
            url = f"{BINANCE_VISION_BASE}/futures/um/monthly/klines/{symbol}/1m/{symbol}-1m-{m}.zip"
        elif series_category == "mark":
            url = f"{BINANCE_VISION_BASE}/futures/um/monthly/markPriceKlines/{symbol}/1m/{symbol}-1m-{m}.zip"
        elif series_category == "index":
            url = f"{BINANCE_VISION_BASE}/futures/um/monthly/indexPriceKlines/{symbol}/1m/{symbol}-1m-{m}.zip"
        elif series_category == "premium":
            url = f"{BINANCE_VISION_BASE}/futures/um/monthly/premiumIndexKlines/{symbol}/1m/{symbol}-1m-{m}.zip"
        else:
            raise ValueError(f"Unknown series category: {series_category}")
        tasks.append((m, url))

    def _fetch_one(t: tuple[str, str]) -> tuple[str, str, bytes]:
        m, url = t
        sha, b = fetch_and_extract_csv(url)
        return m, sha, b

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(_fetch_one, tasks)

    results_dict = {m: (sha, b) for m, sha, b in results}
    all_rows = []
    provenance = []

    for m in months:
        sha, csv_bytes = results_dict[m]
        reader = csv.reader(io.StringIO(csv_bytes.decode("utf-8", errors="ignore")))
        month_rows = 0
        for row in reader:
            if not row or not row[0].isdigit():
                continue
            ts_ms = int(row[0])
            all_rows.append(
                {
                    "ts_event_ns": ts_ms * 1_000_000,
                    "open": Decimal(row[1]),
                    "high": Decimal(row[2]),
                    "low": Decimal(row[3]),
                    "close": Decimal(row[4]),
                    "volume": Decimal(row[5]) if len(row) > 5 else Decimal("0"),
                    "quote_volume": Decimal(row[7]) if len(row) > 7 else Decimal("0"),
                    "trade_count": int(row[8]) if len(row) > 8 and row[8].isdigit() else 0,
                }
            )
            month_rows += 1

        provenance.append(
            {
                "period_key": m,
                "source_file_sha256": sha,
                "rows_count": month_rows,
            }
        )

    all_rows.sort(key=lambda r: r["ts_event_ns"])
    deduped_rows = []
    prev_ts = -1
    gap_count = 0
    missing_bars = 0

    for r in all_rows:
        ts = r["ts_event_ns"]
        if ts > prev_ts:
            if prev_ts > 0:
                diff_ms = (ts - prev_ts) // 1_000_000
                if diff_ms > 60_000:
                    gap_count += 1
                    missing_bars += (diff_ms // 60_000) - 1
            deduped_rows.append(r)
            prev_ts = ts

    schema = pa.schema(
        [
            ("instrument_id", pa.string()),
            ("ts_event_ns", pa.int64()),
            ("open", pa.decimal128(38, 18)),
            ("high", pa.decimal128(38, 18)),
            ("low", pa.decimal128(38, 18)),
            ("close", pa.decimal128(38, 18)),
            ("volume", pa.decimal128(38, 18)),
            ("quote_volume", pa.decimal128(38, 18)),
            ("trade_count", pa.int64()),
        ]
    )
    table = pa.Table.from_arrays(
        [
            pa.array([instrument_id] * len(deduped_rows), type=pa.string()),
            pa.array([r["ts_event_ns"] for r in deduped_rows], type=pa.int64()),
            pa.array([r["open"] for r in deduped_rows], type=pa.decimal128(38, 18)),
            pa.array([r["high"] for r in deduped_rows], type=pa.decimal128(38, 18)),
            pa.array([r["low"] for r in deduped_rows], type=pa.decimal128(38, 18)),
            pa.array([r["close"] for r in deduped_rows], type=pa.decimal128(38, 18)),
            pa.array([r["volume"] for r in deduped_rows], type=pa.decimal128(38, 18)),
            pa.array([r["quote_volume"] for r in deduped_rows], type=pa.decimal128(38, 18)),
            pa.array([r["trade_count"] for r in deduped_rows], type=pa.int64()),
        ],
        schema=schema,
    )
    gap_stats = {"gap_count": gap_count, "missing_bars": missing_bars}
    print(f"[{instrument_id}] Compiled {len(table)} bars (Gaps: {gap_count}, Missing bars: {missing_bars}).")
    return table, provenance, gap_stats


def process_funding_series(
    symbol: str,
    months: list[str],
    max_workers: int = 8,
) -> tuple[pa.Table, list[dict[str, str | int]], dict[str, int]]:
    """Download and compile multi-year funding rates into a single Arrow Table."""
    instrument_id = f"BINANCE:USD_M_PERP:{symbol}"
    print(f"[{instrument_id}] Fetching funding history across {len(months)} months...")

    tasks = []
    for m in months:
        url = f"{BINANCE_VISION_BASE}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{m}.zip"
        tasks.append((m, url))

    def _fetch_one(t: tuple[str, str]) -> tuple[str, str, bytes]:
        m, url = t
        sha, b = fetch_and_extract_csv(url)
        return m, sha, b

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(_fetch_one, tasks)

    results_dict = {m: (sha, b) for m, sha, b in results}
    all_rows = []
    provenance = []

    for m in months:
        sha, csv_bytes = results_dict[m]
        reader = csv.reader(io.StringIO(csv_bytes.decode("utf-8", errors="ignore")))
        month_rows = 0
        for row in reader:
            if not row or not row[0].isdigit():
                continue
            ts_ms = int(row[0])
            all_rows.append(
                {
                    "ts_event_ns": ts_ms * 1_000_000,
                    "funding_interval_hours": 8,
                    "funding_rate": Decimal(row[1]),
                }
            )
            month_rows += 1

        provenance.append(
            {
                "period_key": m,
                "source_file_sha256": sha,
                "rows_count": month_rows,
            }
        )

    all_rows.sort(key=lambda r: r["ts_event_ns"])
    deduped_rows = []
    prev_ts = -1
    for r in all_rows:
        if r["ts_event_ns"] > prev_ts:
            deduped_rows.append(r)
            prev_ts = r["ts_event_ns"]

    schema = pa.schema(
        [
            ("instrument_id", pa.string()),
            ("ts_event_ns", pa.int64()),
            ("funding_interval_hours", pa.int32()),
            ("funding_rate", pa.decimal128(38, 18)),
        ]
    )
    table = pa.Table.from_arrays(
        [
            pa.array([instrument_id] * len(deduped_rows), type=pa.string()),
            pa.array([r["ts_event_ns"] for r in deduped_rows], type=pa.int64()),
            pa.array([r["funding_interval_hours"] for r in deduped_rows], type=pa.int32()),
            pa.array([r["funding_rate"] for r in deduped_rows], type=pa.decimal128(38, 18)),
        ],
        schema=schema,
    )
    print(f"[{instrument_id}] Compiled {len(table)} funding events.")
    return table, provenance, {"gap_count": 0, "missing_bars": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile Research Round 3 multi-year canonical dataset.")
    parser.add_argument("--start", default="2020-01", help="Start year-month")
    parser.add_argument("--end", default="2023-12", help="End year-month (Dev + Validation only)")
    parser.add_argument("--workers", type=int, default=8, help="Download thread workers")
    args = parser.parse_args()

    months = generate_month_keys(args.start, args.end)
    print(f"[Dataset v3.0.0] Building dataset across {len(months)} months ({args.start} to {args.end})...")
    SILVER_V3_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    commit = get_git_commit()
    series_specs = [
        # (symbol, category, filename_prefix, processor)
        ("BTCUSDT", "spot", "BTCUSDT-spot-1m", "kline"),
        ("BTCUSDT", "perp", "BTCUSDT-perp-1m", "kline"),
        ("BTCUSDT", "funding", "BTCUSDT-funding", "funding"),
        ("BTCUSDT", "mark", "BTCUSDT-mark-1m", "kline"),
        ("BTCUSDT", "index", "BTCUSDT-index-1m", "kline"),
        ("BTCUSDT", "premium", "BTCUSDT-premium-1m", "kline"),
        ("ETHUSDT", "spot", "ETHUSDT-spot-1m", "kline"),
        ("ETHUSDT", "perp", "ETHUSDT-perp-1m", "kline"),
        ("ETHUSDT", "funding", "ETHUSDT-funding", "funding"),
        ("ETHUSDT", "mark", "ETHUSDT-mark-1m", "kline"),
        ("ETHUSDT", "index", "ETHUSDT-index-1m", "kline"),
        ("ETHUSDT", "premium", "ETHUSDT-premium-1m", "kline"),
    ]

    manifest_datasets = []
    hash_pairs = []

    for symbol, cat, prefix, proc in series_specs:
        target_name = f"{prefix}-{args.start}-{args.end}.parquet"
        target_path = SILVER_V3_DIR / target_name

        if proc == "kline":
            table, prov, gap_stats = process_kline_series(symbol, cat, months, max_workers=args.workers)
        else:
            table, prov, gap_stats = process_funding_series(symbol, months, max_workers=args.workers)

        pq.write_table(table, target_path, compression="snappy")
        file_sha = hashlib.sha256(target_path.read_bytes()).hexdigest()

        start_ts = table["ts_event_ns"][0].as_py()
        end_ts = table["ts_event_ns"][-1].as_py()
        row_count = len(table)

        spec_entry = {
            "dataset_id": prefix,
            "symbol": symbol,
            "category": cat,
            "period": f"{args.start} to {args.end}",
            "parquet_file": str(target_path.relative_to(ROOT)),
            "rows_count": row_count,
            "start_ts_ns": start_ts,
            "end_ts_ns": end_ts,
            "file_sha256": file_sha,
            "gap_stats": gap_stats,
            "source_files_count": len(prov),
        }
        manifest_datasets.append(spec_entry)

        key = f"{prefix}:{symbol}:{args.start}_{args.end}:{start_ts}:{end_ts}:{row_count}"
        hash_pairs.append((key, file_sha))

    logical_sha = compute_logical_sha256(hash_pairs)
    print(f"\n[Dataset v3.0.0] Compiled all 12 series! Logical SHA-256: {logical_sha}")

    manifest = {
        "manifest_version": "3.0.0",
        "dataset_name": "BTCETH_TRADING_OS_CANONICAL_V3",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_commit": commit,
        "period_start": args.start,
        "period_end": args.end,
        "total_months": len(months),
        "holdout_period": "2024-01 to 2024-11",
        "holdout_locked": True,
        "dataset_logical_sha256": logical_sha,
        "series": manifest_datasets,
    }

    manifest_file = REPORTS_DIR / "RESEARCH_ROUND3_DATA_MANIFEST.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"[Dataset v3.0.0] Wrote manifest to {manifest_file}")


if __name__ == "__main__":
    main()
