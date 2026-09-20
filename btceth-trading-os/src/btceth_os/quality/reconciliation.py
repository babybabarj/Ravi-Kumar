from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from ..sources.binance.archive_parser import BronzeRecord


@dataclass(frozen=True)
class ReconciliationFinding:
    code: str
    ts_event_ns: int
    detail: str


def reconcile_kline_records(
    primary: Iterable[BronzeRecord],
    comparison: Iterable[BronzeRecord],
) -> list[ReconciliationFinding]:
    """Compare two kline sources by event time without merging or correcting either source."""
    left, right = _kline_map(primary), _kline_map(comparison)
    findings: list[ReconciliationFinding] = []
    for timestamp in sorted(set(left) | set(right)):
        if timestamp not in left:
            findings.append(ReconciliationFinding("MISSING_FROM_PRIMARY", timestamp, "present only in comparison source"))
        elif timestamp not in right:
            findings.append(ReconciliationFinding("MISSING_FROM_COMPARISON", timestamp, "present only in primary source"))
        elif _signature(left[timestamp]) != _signature(right[timestamp]):
            findings.append(ReconciliationFinding("KLINE_VALUE_MISMATCH", timestamp, "OHLCV or trade-count differs"))
    return findings


def _kline_map(records: Iterable[BronzeRecord]) -> dict[int, BronzeRecord]:
    rows = list(records)
    if any(row.source_dataset_name not in {"klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"} for row in rows):
        raise ValueError("reconciliation accepts only kline Bronze records")
    if len({row.instrument_id for row in rows}) > 1:
        raise ValueError("reconciliation requires one instrument per source")
    result: dict[int, BronzeRecord] = {}
    for row in rows:
        if row.ts_event_ns in result:
            raise ValueError(f"duplicate kline timestamp at {row.ts_event_ns}")
        result[row.ts_event_ns] = row
    return result


def _signature(record: BronzeRecord) -> tuple[object, ...]:
    values = record.values
    return tuple(values[key] for key in ("open", "high", "low", "close", "volume", "quote_volume", "count"))
