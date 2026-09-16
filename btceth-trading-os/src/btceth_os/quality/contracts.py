from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Sequence
from ..core import ns_from_source_timestamp, QualityState


@dataclass(frozen=True)
class TimestampRecord:
    """Canonical timestamp record preserving source precision and int64 nanosecond normalization."""

    ts_event_ns: int | None
    ts_ingest_ns: int
    source_ts_raw: int | str | None
    source_ts_unit: str | None  # "ms", "us", "s", "ns"
    source_precision: str | None

    @classmethod
    def from_source(
        cls,
        source_ts: int | None,
        unit: str = "ms",
        ingest_ns: int = 0,
    ) -> TimestampRecord:
        """Construct canonical timestamp record from source values without manufacturing false precision."""
        if source_ts is None:
            return cls(
                ts_event_ns=None,
                ts_ingest_ns=ingest_ns,
                source_ts_raw=None,
                source_ts_unit=None,
                source_precision=None,
            )
        event_ns = ns_from_source_timestamp(source_ts, unit)
        return cls(
            ts_event_ns=event_ns,
            ts_ingest_ns=ingest_ns,
            source_ts_raw=source_ts,
            source_ts_unit=unit,
            source_precision=unit,
        )

    @classmethod
    def from_spot_source(
        cls,
        source_ts: int | None,
        ingest_ns: int = 0,
    ) -> TimestampRecord:
        """Construct canonical timestamp record for Binance Spot, resolving ms vs us based on 2025 boundary."""
        if source_ts is None:
            return cls(
                ts_event_ns=None,
                ts_ingest_ns=ingest_ns,
                source_ts_raw=None,
                source_ts_unit=None,
                source_precision=None,
            )
        event_ns, unit = resolve_spot_timestamp(source_ts)
        return cls(
            ts_event_ns=event_ns,
            ts_ingest_ns=ingest_ns,
            source_ts_raw=source_ts,
            source_ts_unit=unit,
            source_precision=unit,
        )


def resolve_spot_timestamp(raw_ts: int) -> tuple[int, str]:
    """Resolve Spot raw timestamp to (ts_event_ns, source_unit).

    Binance Spot switched to microsecond timestamps on 2025-01-01 (1735689600000000 us).
    Values >= 1_000_000_000_000_000 (16 digits) are microseconds ('us').
    Values < 1_000_000_000_000_000 (13 digits) are milliseconds ('ms').
    """
    if raw_ts >= 1_000_000_000_000_000:
        unit = "us"
        event_ns = raw_ts * 1_000
    else:
        unit = "ms"
        event_ns = raw_ts * 1_000_000
    return event_ns, unit


def validate_timestamp_monotonicity(timestamps: Sequence[int | None]) -> bool:
    """Validate that non-null event timestamps are non-decreasing."""
    last = -1
    for ts in timestamps:
        if ts is not None:
            if ts < last:
                return False
            last = ts
    return True


class FinancialDecimal:
    """Financial precision enforcement utility preventing floating-point contamination."""

    @staticmethod
    def parse(value: str | int | Decimal) -> Decimal:
        """Strictly parse price or quantity without floating-point intermediary."""
        if isinstance(value, float):
            raise TypeError(
                f"Binary float {value!r} is forbidden as canonical financial truth. Pass str, int, or Decimal."
            )
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid financial decimal value: {value!r}") from exc

    @staticmethod
    def format_exact(value: Decimal) -> str:
        """Format Decimal to string preserving exact fixed notation without scientific notation."""
        return format(value, "f")
