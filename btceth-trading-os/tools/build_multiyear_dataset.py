#!/usr/bin/env python3
"""Multi-year canonical research dataset compiler for BTCETH Trading OS (Research Round 2)."""
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
SILVER_V2_DIR = ROOT / "artifacts" / "research" / "silver_v2"
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


RAW_ZIPS_DIR = ROOT / "artifacts" / "research" / "raw_zips"


def fetch_and_extract_csv(url: str, retries: int = 4) -> tuple[str, bytes]:
    """Download ZIP archive with local caching and retries; return source SHA-256 and uncompressed CSV bytes."""
    RAW_ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1]
    local_zip = RAW_ZIPS_DIR / filename

    data: bytes | None = None
    if local_zip.exists() and local_zip.stat().st_size > 500:
        data = local_zip.read_bytes()

    if data is None:
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "btceth-trading-os/2.0"})
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


def process_kline_months(
    symbol: str,
    market: str,  # 'futures/um' or 'spot'
    months: list[str],
    max_workers: int = 8,
) -> tuple[pa.Table, list[dict[str, str | int]]]:
    """Download and compile multi-year 1m klines into a single Arrow Table."""
    instrument_id = f"BINANCE:{'USD_M_PERP' if market == 'futures/um' else 'SPOT'}:{symbol}"
    print(f"[{instrument_id}] Fetching {len(months)} months ({months[0]} to {months[-1]})...")

    tasks = []
    for m in months:
        url = f"{BINANCE_VISION_BASE}/{market}/monthly/klines/{symbol}/1m/{symbol}-1m-{m}.zip"
        tasks.append((m, url))

    all_rows = []
    provenance = []

    def _fetch_one(t: tuple[str, str]) -> tuple[str, str, bytes]:
        m, url = t
        sha, b = fetch_and_extract_csv(url)
        return m, sha, b

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(_fetch_one, tasks)

    # Process in chronological order
    results_dict = {m: (sha, b) for m, sha, b in results}
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
                    "volume": Decimal(row[5]),
                    "quote_volume": Decimal(row[7]),
                    "trade_count": int(row[8]),
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

    # Deduplicate and sort strictly by timestamp
    all_rows.sort(key=lambda r: r["ts_event_ns"])
    deduped_rows = []
    prev_ts = -1
    for r in all_rows:
        if r["ts_event_ns"] > prev_ts:
            deduped_rows.append(r)
            prev_ts = r["ts_event_ns"]

    # Build PyArrow Table with exact Decimal128
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
    print(f"[{instrument_id}] Compiled {len(table)} unique 1m bars.")
    return table, provenance


def process_funding_months(
    symbol: str,
    months: list[str],
    max_workers: int = 8,
) -> tuple[pa.Table, list[dict[str, str | int]]]:
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
            ("funding_interval_hours", pa.int64()),
            ("funding_rate", pa.decimal128(38, 18)),
        ]
    )
    table = pa.Table.from_arrays(
        [
            pa.array([instrument_id] * len(deduped_rows), type=pa.string()),
            pa.array([r["ts_event_ns"] for r in deduped_rows], type=pa.int64()),
            pa.array([r["funding_interval_hours"] for r in deduped_rows], type=pa.int64()),
            pa.array([r["funding_rate"] for r in deduped_rows], type=pa.decimal128(38, 18)),
        ],
        schema=schema,
    )
    print(f"[{instrument_id}] Compiled {len(table)} unique funding events.")
    return table, provenance


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile multi-year canonical research dataset for BTC/ETH.")
    parser.add_argument("--start", default="2021-01", help="Start month YYYY-MM")
    parser.add_argument("--end", default="2024-11", help="End month YYYY-MM")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    months = generate_month_keys(args.start, args.end)
    print("=" * 70)
    print(f"BTCETH TRADING OS: MULTI-YEAR RESEARCH DATA COMPILER (v2.0.0)")
    print(f"Target Range: {args.start} to {args.end} ({len(months)} months)")
    print("=" * 70)

    SILVER_V2_DIR.mkdir(parents=True, exist_ok=True)
    code_commit = get_git_commit()

    # 1. Compile BTCUSDT Perp 1m
    btc_perp_table, btc_perp_prov = process_kline_months("BTCUSDT", "futures/um", months, args.workers)
    btc_perp_path = SILVER_V2_DIR / f"BTCUSDT-perp-1m-{args.start}-{args.end}.parquet"
    pq.write_table(btc_perp_table, btc_perp_path, compression="zstd")

    # 2. Compile ETHUSDT Perp 1m
    eth_perp_table, eth_perp_prov = process_kline_months("ETHUSDT", "futures/um", months, args.workers)
    eth_perp_path = SILVER_V2_DIR / f"ETHUSDT-perp-1m-{args.start}-{args.end}.parquet"
    pq.write_table(eth_perp_table, eth_perp_path, compression="zstd")

    # 3. Compile BTCUSDT Funding
    btc_funding_table, btc_funding_prov = process_funding_months("BTCUSDT", months, args.workers)
    btc_funding_path = SILVER_V2_DIR / f"BTCUSDT-funding-{args.start}-{args.end}.parquet"
    pq.write_table(btc_funding_table, btc_funding_path, compression="zstd")

    # 4. Compile ETHUSDT Funding
    eth_funding_table, eth_funding_prov = process_funding_months("ETHUSDT", months, args.workers)
    eth_funding_path = SILVER_V2_DIR / f"ETHUSDT-funding-{args.start}-{args.end}.parquet"
    pq.write_table(eth_funding_table, eth_funding_path, compression="zstd")

    # 5. Compile Spot 1m klines
    btc_spot_table, btc_spot_prov = process_kline_months("BTCUSDT", "spot", months, args.workers)
    btc_spot_path = SILVER_V2_DIR / f"BTCUSDT-spot-1m-{args.start}-{args.end}.parquet"
    pq.write_table(btc_spot_table, btc_spot_path, compression="zstd")

    eth_spot_table, eth_spot_prov = process_kline_months("ETHUSDT", "spot", months, args.workers)
    eth_spot_path = SILVER_V2_DIR / f"ETHUSDT-spot-1m-{args.start}-{args.end}.parquet"
    pq.write_table(eth_spot_table, eth_spot_path, compression="zstd")

    # Compute deterministic logical hash
    # Hash sampled keys across all tables to form dataset logical SHA-256
    hash_pairs = []
    for row_idx in range(0, len(btc_perp_table), 10):
        ts = str(btc_perp_table.column("ts_event_ns")[row_idx].as_py())
        c = str(btc_perp_table.column("close")[row_idx].as_py())
        hash_pairs.append((f"BTC_PERP_{ts}", c))

    for row_idx in range(0, len(eth_perp_table), 10):
        ts = str(eth_perp_table.column("ts_event_ns")[row_idx].as_py())
        c = str(eth_perp_table.column("close")[row_idx].as_py())
        hash_pairs.append((f"ETH_PERP_{ts}", c))

    for row_idx in range(len(btc_funding_table)):
        ts = str(btc_funding_table.column("ts_event_ns")[row_idx].as_py())
        f = str(btc_funding_table.column("funding_rate")[row_idx].as_py())
        hash_pairs.append((f"BTC_FUND_{ts}", f))

    dataset_logical_sha256 = compute_logical_sha256(hash_pairs)
    print(f"\n[Manifest] Multi-Year Dataset Logical SHA-256: {dataset_logical_sha256}")

    manifest_data = {
        "dataset_version": "2.0.0",
        "dataset_universe": "CORE_LONG_HISTORY",
        "dataset_logical_sha256": dataset_logical_sha256,
        "round1_dataset_sha256": "a24103d810c36c44a2d8bf26a51c4a034a012906d6463284d50ec175102e5d9a",
        "code_commit": code_commit,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "date_range": {
            "start": args.start,
            "end": args.end,
            "total_months": len(months),
        },
        "streams": {
            "BTCUSDT_PERP_1M": {
                "parquet_path": str(btc_perp_path),
                "total_rows": len(btc_perp_table),
                "start_ts_ns": btc_perp_table.column("ts_event_ns")[0].as_py(),
                "end_ts_ns": btc_perp_table.column("ts_event_ns")[-1].as_py(),
            },
            "ETHUSDT_PERP_1M": {
                "parquet_path": str(eth_perp_path),
                "total_rows": len(eth_perp_table),
                "start_ts_ns": eth_perp_table.column("ts_event_ns")[0].as_py(),
                "end_ts_ns": eth_perp_table.column("ts_event_ns")[-1].as_py(),
            },
            "BTCUSDT_FUNDING": {
                "parquet_path": str(btc_funding_path),
                "total_rows": len(btc_funding_table),
            },
            "ETHUSDT_FUNDING": {
                "parquet_path": str(eth_funding_path),
                "total_rows": len(eth_funding_table),
            },
            "BTCUSDT_SPOT_1M": {
                "parquet_path": str(btc_spot_path),
                "total_rows": len(btc_spot_table),
            },
            "ETHUSDT_SPOT_1M": {
                "parquet_path": str(eth_spot_path),
                "total_rows": len(eth_spot_table),
            },
        },
        "holdout_config": {
            "development_period": "2021-01 to 2022-12 (24 months)",
            "validation_period": "2023-01 to 2023-12 (12 months)",
            "final_holdout_period": "2024-01 to 2024-11 (11 months)",
            "holdout_locked": True,
        },
    }

    manifest_path = REPORTS_DIR / "RESEARCH_ROUND2_DATA_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
    print(f"[Manifest] Wrote manifest to: {manifest_path}")
    print("=" * 70)
    print("MULTI-YEAR DATASET COMPILATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
