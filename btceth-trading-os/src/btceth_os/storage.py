from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import gzip
import json
from pathlib import Path
from typing import Iterable, Mapping, Any

import pyarrow as pa
import pyarrow.parquet as pq

from .core import RawEnvelope, canonical_json


class RawStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def append(self, env: RawEnvelope) -> Path:
        dt = datetime.fromtimestamp((env.ts_recv_ns or 0) / 1_000_000_000, tz=timezone.utc)
        path = self.root / env.source / env.market / env.dataset / env.instrument_id.replace(":", "_") / f"{dt:%Y/%m/%d/%H}.jsonl.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = canonical_json(env.as_dict()).encode() + b"\n"
        with gzip.open(path, "ab") as fh:
            fh.write(line)
        return path

    @staticmethod
    def read(path: str | Path) -> list[dict[str, Any]]:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


SILVER_SCHEMA = pa.schema([
    pa.field("source", pa.string(), nullable=False),
    pa.field("market", pa.string(), nullable=False),
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("instrument_id", pa.string(), nullable=False),
    pa.field("ts_event_ns", pa.int64()),
    pa.field("ts_recv_ns", pa.int64(), nullable=False),
    pa.field("ts_ingest_ns", pa.int64(), nullable=False),
    pa.field("source_ts_raw", pa.int64()),
    pa.field("source_ts_unit", pa.string()),
    pa.field("source_precision", pa.string()),
    pa.field("record_key", pa.string(), nullable=False),
    pa.field("payload_hash", pa.string(), nullable=False),
    pa.field("values_json", pa.string(), nullable=False),
])


def _exactify(value: Any) -> Any:
    if isinstance(value, float):
        return format(Decimal(str(value)), "f")
    if isinstance(value, dict):
        return {k: _exactify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_exactify(v) for v in value]
    return value


class SilverStore:
    """Generic Phase-1A normalized event store. Numeric source values remain exact strings."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def write(self, records: Iterable[Mapping[str, Any]], filename: str) -> Path:
        rows = []
        for rec in records:
            values = _exactify(dict(rec["values"]))
            values_json = canonical_json(values)
            rows.append({
                "source": str(rec["source"]),
                "market": str(rec["market"]),
                "dataset": str(rec["dataset"]),
                "instrument_id": str(rec["instrument_id"]),
                "ts_event_ns": rec.get("ts_event_ns"),
                "ts_recv_ns": int(rec["ts_recv_ns"]),
                "ts_ingest_ns": int(rec["ts_ingest_ns"]),
                "source_ts_raw": rec.get("source_ts_raw"),
                "source_ts_unit": rec.get("source_ts_unit"),
                "source_precision": rec.get("source_precision"),
                "record_key": str(rec["record_key"]),
                "payload_hash": str(rec["payload_hash"]),
                "values_json": values_json,
            })
        table = pa.Table.from_pylist(rows, schema=SILVER_SCHEMA)
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, path, compression="zstd")
        return path

    @staticmethod
    def read(path: str | Path) -> pa.Table:
        return pq.read_table(path)


def file_sha256(path: str | Path) -> str:
    h = sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
