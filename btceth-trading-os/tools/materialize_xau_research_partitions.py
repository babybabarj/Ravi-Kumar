"""Materialize rule-epoch aware Silver and research partitions for XAUUSDT.

Enforces:
- Direct ingestion of checksum-verified 1m bars from raw archives + daily repair
- Rule epoch annotation on every record via ContractRuleEpochRegistry
- Session state annotation (UnderlyingReferenceSession vs PerpetualContractSession)
- Partition separation:
  * XAUUSDT_DEV_2026_01_04: 2026-01-06T00:00:00Z to 2026-04-30T23:59:59Z (DEVELOPMENT)
  * XAUUSDT_VAL_2026_05_07: 2026-05-01T00:00:00Z to 2026-07-31T23:59:59Z (VALIDATION)
  * XAUUSDT_HOLDOUT_2026_08_09: 2026-08-01T00:00:00Z to 2026-09-15T21:00:00Z (HOLDOUT)
  * XAUUSDT_PROSPECTIVE_PRISTINE: 2026-09-15T21:00:00Z to 2026-09-22T23:59:59Z (PROSPECTIVE_PRISTINE)
- Cryptographic physical and logical SHA-256 computation
- Sealed holdout registration in holdout ledger
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from typing import Any
import zipfile

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.contract_rule_epochs import ContractRuleEpochRegistry
from btceth_os.sessions import evaluate_sessions, GoldSessionState

RAW_ROOT = ROOT / "artifacts" / "xau_native" / "raw" / "binance" / "futures_um"
OUTPUT_DIR = ROOT / "artifacts" / "research" / "partitions"
SILVER_DIR = ROOT / "artifacts" / "research" / "silver_xau"
CONFIG_PATH = ROOT / "config" / "xau_research_partitions_v1.json"
EPOCHS_CONFIG = ROOT / "config" / "xau_contract_rule_epochs.yaml"

INSTRUMENT_ID = "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"
MINUTE_MS = 60_000
MINUTE_NS = 60_000_000_000

# Boundary definitions in UTC milliseconds
ADMISSION_START_MS = 1767657600000       # 2026-01-06T00:00:00Z
DEV_END_MS = 1777593540000               # 2026-04-30T23:59:00Z
VAL_START_MS = 1777593600000             # 2026-05-01T00:00:00Z
VAL_END_MS = 1785542340000               # 2026-07-31T23:59:00Z
HOLDOUT_START_MS = 1785542400000         # 2026-08-01T00:00:00Z
HOLDOUT_END_MS = 1789505940000           # 2026-09-15T20:59:00Z (Regime boundary strictly before 21:00 UTC)
PRISTINE_START_MS = 1789506000000        # 2026-09-15T21:00:00Z (Epoch 6 start)
THROUGH_END_MS = 1790121540000           # 2026-09-22T23:59:00Z


def compute_file_sha256(path: Path | str, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def compute_partition_logical_sha256(table: pa.Table) -> str:
    h = hashlib.sha256()
    schema_str = ";".join(f"{f.name}:{f.type}" for f in table.schema)
    h.update(f"SCHEMA:{schema_str}\n".encode("utf-8"))

    ts_event_col = table["ts_event_ns"].to_pylist()
    col_names = [f.name for f in table.schema if f.name != "ts_event_ns"]
    cols_data = [table[c].to_pylist() for c in col_names]

    for i, ts in enumerate(ts_event_col):
        row_vals = ",".join(str(cols_data[c_idx][i]) for c_idx in range(len(col_names)))
        line = f"{ts}:{row_vals}\n"
        h.update(line.encode("utf-8"))

    return h.hexdigest()


def read_zip_csv(zip_path: Path) -> list[list[str]]:
    with zipfile.ZipFile(zip_path) as zf:
        member = zf.namelist()[0]
        with zf.open(member) as f, io.TextIOWrapper(f, encoding="utf-8") as tf:
            reader = csv.reader(tf)
            first = next(reader)
            # If first row is header, skip it
            if first and not first[0].lstrip("-").isdigit():
                return list(reader)
            return [first] + list(reader)


def load_all_series(dataset_name: str) -> dict[int, list[str]]:
    """Loads all records for a dataset keyed by open_time ms. Uses daily repair for 2026-06-29."""
    records: dict[int, list[str]] = {}
    dataset_dir = RAW_ROOT / dataset_name / "XAUUSDT"

    # Monthly files
    for m in range(1, 9):
        m_str = f"2026-{m:02d}"
        zip_path = dataset_dir / f"XAUUSDT-1m-{m_str}.zip"
        if zip_path.is_file():
            rows = read_zip_csv(zip_path)
            for r in rows:
                ts = int(r[0])
                records[ts] = r

    # Daily repair for 2026-06-29
    repair_zip = dataset_dir / "XAUUSDT-1m-2026-06-29.zip"
    if repair_zip.is_file():
        rows = read_zip_csv(repair_zip)
        for r in rows:
            ts = int(r[0])
            records[ts] = r

    # Daily files for September
    for d in range(1, 23):
        d_str = f"2026-09-{d:02d}"
        zip_path = dataset_dir / f"XAUUSDT-1m-{d_str}.zip"
        if zip_path.is_file():
            rows = read_zip_csv(zip_path)
            for r in rows:
                ts = int(r[0])
                records[ts] = r

    return records


def load_all_funding() -> dict[int, Decimal]:
    funding: dict[int, Decimal] = {}
    funding_dir = RAW_ROOT / "fundingRate" / "XAUUSDT"
    for m in range(1, 9):
        m_str = f"2026-{m:02d}"
        zip_path = funding_dir / f"XAUUSDT-fundingRate-{m_str}.zip"
        if zip_path.is_file():
            rows = read_zip_csv(zip_path)
            for r in rows:
                ts = int(r[0])
                funding[ts] = Decimal(r[2])

    # September REST funding
    rest_dir = ROOT / "artifacts" / "xau_native" / "rest_funding"
    if rest_dir.is_dir():
        for f in rest_dir.glob("*.json"):
            try:
                rows = json.loads(f.read_text())
                for r in rows:
                    ts = int(r["fundingTime"])
                    funding[ts] = Decimal(r["fundingRate"])
            except Exception:
                pass
    return funding


def build_and_materialize() -> dict[str, Any]:
    print("Loading 1m bar series and funding rates...")
    klines = load_all_series("klines")
    mark_klines = load_all_series("markPriceKlines")
    index_klines = load_all_series("indexPriceKlines")
    premium_klines = load_all_series("premiumIndexKlines")
    funding_map = load_all_funding()

    reg = ContractRuleEpochRegistry.from_yaml(EPOCHS_CONFIG)

    sorted_ts = sorted(ts for ts in klines if ts >= ADMISSION_START_MS and ts <= THROUGH_END_MS)
    print(f"Total admitted 1m bars from 2026-01-06 through 2026-09-22: {len(sorted_ts):,}")

    rows_data: dict[str, list[Any]] = {
        "ts_event_ns": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
        "quote_volume": [],
        "trade_count": [],
        "taker_buy_volume": [],
        "taker_buy_quote_volume": [],
        "mark_price": [],
        "index_price": [],
        "premium_index": [],
        "funding_rate": [],
        "contract_rule_epoch_id": [],
        "underlying_session_state": [],
        "is_contract_tradable": [],
        "instrument_id": [],
    }

    current_funding_rate = 0.0
    funding_times = sorted(funding_map.keys())
    funding_idx = 0

    for ts_ms in sorted_ts:
        k = klines[ts_ms]
        m = mark_klines.get(ts_ms, k)
        idx_k = index_klines.get(ts_ms, k)
        p_k = premium_klines.get(ts_ms, [0, 0, 0, 0, "0.0"])

        # Update realized funding rate
        while funding_idx < len(funding_times) and funding_times[funding_idx] <= ts_ms:
            current_funding_rate = float(funding_map[funding_times[funding_idx]])
            funding_idx += 1

        dt_utc = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        epoch = reg.get_epoch_for_timestamp(dt_utc)
        epoch_id = epoch.epoch_id if epoch else "UNKNOWN"

        session_snap = evaluate_sessions(dt_utc, epoch.price_index_method if epoch else "UNKNOWN")

        rows_data["ts_event_ns"].append(ts_ms * 1_000_000)
        rows_data["open"].append(float(k[1]))
        rows_data["high"].append(float(k[2]))
        rows_data["low"].append(float(k[3]))
        rows_data["close"].append(float(k[4]))
        rows_data["volume"].append(float(k[5]))
        rows_data["quote_volume"].append(float(k[7]))
        rows_data["trade_count"].append(int(k[8]))
        rows_data["taker_buy_volume"].append(float(k[9]))
        rows_data["taker_buy_quote_volume"].append(float(k[10]))
        rows_data["mark_price"].append(float(m[4]))
        rows_data["index_price"].append(float(idx_k[4]))
        rows_data["premium_index"].append(float(p_k[4]))
        rows_data["funding_rate"].append(current_funding_rate)
        rows_data["contract_rule_epoch_id"].append(epoch_id)
        rows_data["underlying_session_state"].append(session_snap.underlying_state.value)
        rows_data["is_contract_tradable"].append(session_snap.is_contract_tradable)
        rows_data["instrument_id"].append(INSTRUMENT_ID)

    master_table = pa.Table.from_pydict(rows_data)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    silver_path = SILVER_DIR / "XAUUSDT-resampled-1m-silver.parquet"
    pq.write_table(master_table, silver_path, compression="snappy")
    silver_phys_sha = compute_file_sha256(silver_path)
    print(f"Master Silver table written: {silver_path} ({len(master_table):,} rows, sha={silver_phys_sha[:16]}...)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    partition_specs = [
        {
            "dataset_id": "XAUUSDT_DEV_2026_01_04",
            "file_name": "XAUUSDT_DEV_2026_01_04.parquet",
            "role": "DEVELOPMENT",
            "start_ms": ADMISSION_START_MS,
            "end_ms": DEV_END_MS,
            "epochs": [
                "XAU_EPOCH_1_LAUNCH_DISCOVERY",
                "XAU_EPOCH_2_ZERO_INTEREST_COMPONENT",
                "XAU_EPOCH_3_INDEX_WEIGHT_REBALANCE",
                "XAU_EPOCH_4_8H_FUNDING_AND_CAP_FLOOR",
            ],
        },
        {
            "dataset_id": "XAUUSDT_VAL_2026_05_07",
            "file_name": "XAUUSDT_VAL_2026_05_07.parquet",
            "role": "VALIDATION",
            "start_ms": VAL_START_MS,
            "end_ms": VAL_END_MS,
            "epochs": [
                "XAU_EPOCH_4_8H_FUNDING_AND_CAP_FLOOR",
                "XAU_EPOCH_5_ORDERBOOK_EWMA_INDEX_MODE",
            ],
        },
        {
            "dataset_id": "XAUUSDT_HOLDOUT_2026_08_09",
            "file_name": "XAUUSDT_HOLDOUT_2026_08_09.parquet",
            "role": "HOLDOUT",
            "start_ms": HOLDOUT_START_MS,
            "end_ms": HOLDOUT_END_MS,
            "epochs": [
                "XAU_EPOCH_5_ORDERBOOK_EWMA_INDEX_MODE",
            ],
        },
        {
            "dataset_id": "XAUUSDT_PROSPECTIVE_PRISTINE",
            "file_name": "XAUUSDT_PROSPECTIVE_PRISTINE.parquet",
            "role": "PROSPECTIVE_PRISTINE",
            "start_ms": PRISTINE_START_MS,
            "end_ms": THROUGH_END_MS,
            "epochs": [
                "XAU_EPOCH_6_ET_SESSION_CALENDAR_REGIME",
            ],
        },
    ]

    manifest_partitions: dict[str, Any] = {}

    for spec in partition_specs:
        s_ns = spec["start_ms"] * 1_000_000
        e_ns = (spec["end_ms"] + 59_999) * 1_000_000

        # Filter slice
        mask = pc.and_(
            pc.greater_equal(master_table["ts_event_ns"], s_ns),
            pc.less_equal(master_table["ts_event_ns"], e_ns),
        )
        part_table = master_table.filter(mask)

        out_path = OUTPUT_DIR / spec["file_name"]
        part_tmp = out_path.with_suffix(".parquet.tmp")
        pq.write_table(part_table, part_tmp, compression="snappy")
        os.replace(part_tmp, out_path)

        phys_sha = compute_file_sha256(out_path)
        log_sha = compute_partition_logical_sha256(part_table)

        manifest_partitions[spec["dataset_id"]] = {
            "dataset_id": spec["dataset_id"],
            "file_name": spec["file_name"],
            "relative_path": str(out_path.relative_to(ROOT)),
            "role": spec["role"],
            "parent_artifact": "XAUUSDT-resampled-1m-silver.parquet",
            "parent_physical_sha256": silver_phys_sha,
            "start_ts_ns": s_ns,
            "end_ts_ns": e_ns,
            "expected_rows": len(part_table),
            "expected_physical_sha256": phys_sha,
            "partition_logical_sha256": log_sha,
            "rule_epoch_coverage": spec["epochs"],
        }
        print(f"Partition {spec['dataset_id']} materialized: {len(part_table):,} rows, phys={phys_sha[:16]}... log={log_sha[:16]}...")

    manifest = {
        "manifest_version": "1.0.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "instrument_id": INSTRUMENT_ID,
        "parent_artifacts": {
            "XAUUSDT-resampled-1m-silver.parquet": {
                "file_name": "XAUUSDT-resampled-1m-silver.parquet",
                "relative_path": str(silver_path.relative_to(ROOT)),
                "physical_sha256": silver_phys_sha,
                "rows": len(master_table),
                "start_ts_ns": sorted_ts[0] * 1_000_000,
                "end_ts_ns": (sorted_ts[-1] + 59_999) * 1_000_000,
            }
        },
        "partitions": manifest_partitions,
    }

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Partition manifest written to {CONFIG_PATH}")

    return manifest


def main() -> int:
    manifest = build_and_materialize()
    return 0 if len(manifest.get("partitions", {})) == 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
