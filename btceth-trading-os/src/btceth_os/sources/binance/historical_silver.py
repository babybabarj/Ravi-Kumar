from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import re
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from ...quality.canonical import QualityFinding, detect_missing_kline_minutes, validate_bronze_records
from .archive_parser import BronzeRecord


DECIMAL = pa.decimal128(38, 18)
PROVENANCE_FIELDS = [
    pa.field("instrument_id", pa.string(), nullable=False),
    pa.field("source_dataset", pa.string(), nullable=False),
    pa.field("source_object_sha256", pa.string(), nullable=False),
    pa.field("source_member", pa.string(), nullable=False),
    pa.field("source_row_number", pa.int64(), nullable=False),
    pa.field("ts_event_ns", pa.int64(), nullable=False),
    pa.field("source_ts_raw", pa.int64(), nullable=False),
    pa.field("source_ts_unit", pa.string(), nullable=False),
]
KLINE_SCHEMA = pa.schema([
    *PROVENANCE_FIELDS,
    pa.field("open", DECIMAL, nullable=False), pa.field("high", DECIMAL, nullable=False),
    pa.field("low", DECIMAL, nullable=False), pa.field("close", DECIMAL, nullable=False),
    pa.field("volume", DECIMAL, nullable=False), pa.field("quote_volume", DECIMAL, nullable=False),
    pa.field("trade_count", pa.int64(), nullable=False),
])
FUNDING_SCHEMA = pa.schema([
    *PROVENANCE_FIELDS,
    pa.field("funding_interval_hours", pa.int64(), nullable=False),
    pa.field("funding_rate", DECIMAL, nullable=False),
])
TRADE_SCHEMA = pa.schema([
    *PROVENANCE_FIELDS,
    pa.field("trade_id", pa.int64(), nullable=False),
    pa.field("price", DECIMAL, nullable=False), pa.field("quantity", DECIMAL, nullable=False),
    pa.field("quote_quantity", DECIMAL, nullable=False), pa.field("is_buyer_maker", pa.bool_(), nullable=False),
    pa.field("is_best_match", pa.bool_()),
])
AGG_TRADE_SCHEMA = pa.schema([
    *PROVENANCE_FIELDS,
    pa.field("agg_trade_id", pa.int64(), nullable=False), pa.field("first_trade_id", pa.int64(), nullable=False),
    pa.field("last_trade_id", pa.int64(), nullable=False),
    pa.field("price", DECIMAL, nullable=False), pa.field("quantity", DECIMAL, nullable=False), pa.field("is_buyer_maker", pa.bool_(), nullable=False),
])


class SilverBuildError(ValueError):
    pass


def write_historical_silver(
    records: Iterable[BronzeRecord],
    destination: Path | str,
    source_object_sha256: str,
) -> tuple[Path, list[QualityFinding]]:
    """Build one exact, source-specific Silver Parquet object from homogeneous Bronze records."""
    if not re.fullmatch(r"[0-9a-f]{64}", source_object_sha256):
        raise SilverBuildError("source_object_sha256 must be a lowercase SHA-256 hex digest")
    rows = list(records)
    if not rows:
        raise SilverBuildError("cannot build Silver from zero Bronze records")
    dataset = rows[0].source_dataset_name
    if any(row.source_dataset_name != dataset for row in rows):
        raise SilverBuildError("Silver input must contain exactly one source dataset")
    findings = validate_bronze_records(rows)
    blocking = [finding for finding in findings if finding.code != "MISSING_INTERVAL"]
    if blocking:
        raise SilverBuildError(f"blocking Bronze quality findings: {[finding.code for finding in blocking]}")
    if dataset in {"klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"}:
        schema, output_rows = KLINE_SCHEMA, [_kline_row(row, source_object_sha256) for row in rows]
        findings.extend(detect_missing_kline_minutes(rows))
    elif dataset == "fundingRate":
        schema, output_rows = FUNDING_SCHEMA, [_funding_row(row, source_object_sha256) for row in rows]
    elif dataset == "trades":
        schema, output_rows = TRADE_SCHEMA, [_trade_row(row, source_object_sha256) for row in rows]
    elif dataset == "aggTrades":
        schema, output_rows = AGG_TRADE_SCHEMA, [_agg_trade_row(row, source_object_sha256) for row in rows]
    else:
        raise SilverBuildError(f"Silver schema not implemented for {dataset!r}")
    path = Path(destination)
    if path.exists():
        raise SilverBuildError(f"refusing to overwrite existing Silver object: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(output_rows, schema=schema), path, compression="zstd")
    return path, findings


def _kline_row(record: BronzeRecord, physical_hash: str) -> dict[str, object]:
    values = record.values
    return _provenance(record, physical_hash) | {
        "open": Decimal(str(values["open"])), "high": Decimal(str(values["high"])),
        "low": Decimal(str(values["low"])), "close": Decimal(str(values["close"])),
        "volume": Decimal(str(values["volume"])), "quote_volume": Decimal(str(values["quote_volume"])),
        "trade_count": int(values["count"]),
    }


def _funding_row(record: BronzeRecord, physical_hash: str) -> dict[str, object]:
    values = record.values
    return _provenance(record, physical_hash) | {
        "funding_interval_hours": int(values["funding_interval_hours"]),
        "funding_rate": Decimal(str(values["last_funding_rate"])),
    }


def _trade_row(record: BronzeRecord, physical_hash: str) -> dict[str, object]:
    values = record.values
    return _provenance(record, physical_hash) | {
        "trade_id": int(values["id"]),
        "price": Decimal(str(values["price"])), "quantity": Decimal(str(values["qty"])),
        "quote_quantity": Decimal(str(values["quote_qty"])), "is_buyer_maker": bool(values["is_buyer_maker"]),
        "is_best_match": bool(values["is_best_match"]),
    }


def _agg_trade_row(record: BronzeRecord, physical_hash: str) -> dict[str, object]:
    values = record.values
    return _provenance(record, physical_hash) | {
        "agg_trade_id": int(values["agg_trade_id"]),
        "first_trade_id": int(values["first_trade_id"]), "last_trade_id": int(values["last_trade_id"]),
        "price": Decimal(str(values["price"])), "quantity": Decimal(str(values["quantity"])),
        "is_buyer_maker": bool(values["is_buyer_maker"]),
    }


def _provenance(record: BronzeRecord, physical_hash: str) -> dict[str, object]:
    return {
        "instrument_id": record.instrument_id, "source_dataset": record.source_dataset_name,
        "source_object_sha256": physical_hash, "source_member": record.source_member,
        "source_row_number": record.row_number, "ts_event_ns": record.ts_event_ns,
        "source_ts_raw": record.source_ts_raw, "source_ts_unit": record.source_ts_unit,
    }
