from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import time
from typing import Any


class QualityState(StrEnum):
    VALID = "VALID"
    SOURCE_ANOMALY = "SOURCE_ANOMALY"
    REPAIRED = "REPAIRED"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"
    QUARANTINED = "QUARANTINED"


class SourceConflict(RuntimeError):
    pass


def now_ns() -> int:
    return time.time_ns()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class RawEnvelope:
    source: str
    market: str
    dataset: str
    instrument_id: str
    payload: dict[str, Any]
    source_ts_raw: int | None = None
    source_ts_unit: str | None = None
    source_precision: str | None = None
    ts_event_ns: int | None = None
    ts_recv_ns: int = 0
    ts_ingest_ns: int = 0
    connection_id: str | None = None
    subscription_id: str | None = None
    collector_version: str = "0.1.0"
    schema_hint: str | None = None

    @property
    def payload_hash(self) -> str:
        return sha256(canonical_json(self.payload).encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        out = self.__dict__.copy()
        out["payload_hash"] = self.payload_hash
        return out


class DedupIndex:
    """Deterministic in-process duplicate/conflict detector for source identifiers."""

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def observe(self, key: str, payload_hash: str) -> str:
        existing = self._seen.get(key)
        if existing is None:
            self._seen[key] = payload_hash
            return "NEW"
        if existing == payload_hash:
            return "DUPLICATE"
        raise SourceConflict(f"SOURCE_CONFLICT key={key}")


def ns_from_source_timestamp(value: int | None, unit: str | None) -> int | None:
    if value is None:
        return None
    factors = {"s": 1_000_000_000, "ms": 1_000_000, "us": 1_000, "ns": 1}
    if unit not in factors:
        raise ValueError(f"unsupported source timestamp unit: {unit}")
    return int(value) * factors[unit]
