from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from ..sources.binance.archive_parser import BronzeRecord


@dataclass(frozen=True)
class QualityFinding:
    code: str
    row_number: int
    detail: str


def validate_bronze_records(records: Iterable[BronzeRecord]) -> list[QualityFinding]:
    """Check ordering, duplicate event time, and source-specific financial invariants."""
    findings: list[QualityFinding] = []
    previous_ts: int | None = None
    seen: set[tuple[int, str]] = set()
    for record in records:
        key = (record.ts_event_ns, str(record.values))
        if key in seen:
            findings.append(QualityFinding("DUPLICATE_IDENTICAL", record.row_number, "same timestamp and values"))
        seen.add(key)
        if previous_ts is not None and record.ts_event_ns < previous_ts:
            findings.append(QualityFinding("TIMESTAMP_OUT_OF_ORDER", record.row_number, "event timestamp decreased"))
        previous_ts = record.ts_event_ns
        values = record.values
        if record.source_dataset_name in {"klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"}:
            open_, high, low, close = (Decimal(str(values[name])) for name in ("open", "high", "low", "close"))
            if high < max(open_, close) or low > min(open_, close) or high < low:
                findings.append(QualityFinding("INVALID_OHLC", record.row_number, "OHLC bounds violated"))
            if Decimal(str(values["volume"])) < 0:
                findings.append(QualityFinding("NEGATIVE_VOLUME", record.row_number, "volume is negative"))
    return findings


def detect_missing_kline_minutes(records: Iterable[BronzeRecord]) -> list[QualityFinding]:
    """Report missing 1-minute intervals; it never manufactures replacement bars."""
    rows = list(records)
    findings: list[QualityFinding] = []
    for previous, current in zip(rows, rows[1:]):
        gap = current.ts_event_ns - previous.ts_event_ns
        if gap > 60_000_000_000:
            missing = gap // 60_000_000_000 - 1
            findings.append(QualityFinding("MISSING_INTERVAL", current.row_number, f"{missing} missing 1m intervals"))
    return findings
