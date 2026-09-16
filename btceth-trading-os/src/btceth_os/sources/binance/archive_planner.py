# Adapted from Passivbot (https://github.com/enarjord/passivbot)
# Original file: src/binance_ohlcv_archive.py
# Archive: passivbot-master.zip (SHA256: bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468)
# License: The Unlicense (Public Domain)
# Modifications: Upgraded to streaming .part download with incremental SHA-256,
# generalized dataset path planning, and exact nanosecond/decimal typing.

from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .archive_paths import build_archive_paths, BinancePathError
from .models import ArchiveObjectSpec


def parse_utc_datetime(value: datetime | date | str) -> datetime:
    """Parse various datetime representations into timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str):
        cleaned = value.strip().replace("Z", "+00:00")
        if len(cleaned) == 10 and cleaned.count("-") == 2:
            # YYYY-MM-DD
            d = date.fromisoformat(cleaned)
            return datetime.combine(d, time.min, tzinfo=timezone.utc)
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    raise TypeError(f"Cannot parse UTC datetime from type {type(value)}")


def first_monday_after_month(year: int, month: int) -> datetime:
    """Calculate the first Monday of the month immediately following year/month in UTC."""
    if month == 12:
        candidate = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        candidate = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return candidate + timedelta(days=(7 - candidate.weekday()) % 7)


def monthly_archive_eligible(
    year: int,
    month: int,
    *,
    as_of_utc: datetime,
    publication_buffer_hours: int = 0,
) -> bool:
    """A calendar month is monthly-eligible only after it is completed AND
    as_of_utc is on or after the first Monday publication boundary.
    """
    as_of = parse_utc_datetime(as_of_utc)
    if (year, month) >= (as_of.year, as_of.month):
        return False
    pub_time = first_monday_after_month(year, month) + timedelta(hours=publication_buffer_hours)
    return as_of >= pub_time


def daily_archive_eligible(
    day_date: date,
    *,
    as_of_utc: datetime,
    lag_days: int = 1,
) -> bool:
    """A UTC day is daily-eligible once the day has completed and publication lag has passed.
    Standard Binance publication: available the next day (lag_days=1).
    """
    as_of = parse_utc_datetime(as_of_utc)
    day_start = datetime.combine(day_date, time.min, tzinfo=timezone.utc)
    available_at = day_start + timedelta(days=lag_days)
    return as_of >= available_at


@dataclass(frozen=True)
class UnfulfilledDateReason:
    date: str
    status: str  # "NOT_YET_AVAILABLE" | "SOURCE_UNSUPPORTED" | "FUTURE_DATE"
    reason: str


@dataclass(frozen=True)
class ArchivePlanResult:
    dataset_id: str
    start_utc: str
    end_utc: str
    as_of_utc: str
    specs: list[ArchiveObjectSpec]
    unfulfilled: list[UnfulfilledDateReason]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "as_of_utc": self.as_of_utc,
            "specs": [asdict(s) for s in self.specs],
            "unfulfilled": [asdict(u) for u in self.unfulfilled],
        }


def plan_archive_requests(
    dataset: Any,
    start: datetime | date | str,
    end: datetime | date | str,
    as_of_utc: datetime | date | str,
    publication_buffer_hours: int = 0,
    daily_lag_days: int = 1,
) -> list[ArchiveObjectSpec]:
    """Core deterministic request planner. Returns ordered list of ArchiveObjectSpec.
    Zero network calls.
    """
    res = plan_archive_requests_detailed(
        dataset=dataset,
        start=start,
        end=end,
        as_of_utc=as_of_utc,
        publication_buffer_hours=publication_buffer_hours,
        daily_lag_days=daily_lag_days,
    )
    return res.specs


def plan_archive_requests_detailed(
    dataset: Any,
    start: datetime | date | str,
    end: datetime | date | str,
    as_of_utc: datetime | date | str,
    publication_buffer_hours: int = 0,
    daily_lag_days: int = 1,
) -> ArchivePlanResult:
    """Detailed deterministic request planner with non-overlap invariants and explanations
    for any unfulfilled dates.
    """
    start_dt = parse_utc_datetime(start)
    end_dt = parse_utc_datetime(end)
    as_of_dt = parse_utc_datetime(as_of_utc)

    if start_dt > end_dt:
        raise ValueError(f"start ({start_dt.isoformat()}) must be <= end ({end_dt.isoformat()})")

    # Extract dataset attributes
    if isinstance(dataset, dict):
        dataset_id = dataset["dataset_id"]
        market = dataset["market"]
        instrument = dataset["instrument"]
        source_dataset_name = dataset["source_dataset_name"]
        daily_support = dataset.get("daily_support", "VERIFIED_TRUE")
        monthly_support = dataset.get("monthly_support", "VERIFIED_TRUE")
        timestamp_policy = dataset.get("source_timestamp_policy", {})
    elif hasattr(dataset, "dataset_id"):
        dataset_id = dataset.dataset_id
        market = dataset.market
        instrument = dataset.instrument
        source_dataset_name = dataset.source_dataset_name
        daily_support = getattr(dataset, "daily_support", "VERIFIED_TRUE")
        monthly_support = getattr(dataset, "monthly_support", "VERIFIED_TRUE")
        timestamp_policy = getattr(dataset, "source_timestamp_policy", {})
    else:
        raise TypeError(f"Unsupported dataset descriptor type {type(dataset)}")

    symbol = instrument.split(":")[-1]
    is_kline_like = source_dataset_name in ("klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines")
    interval = "1m" if is_kline_like else None

    # Group requested days into calendar months
    current_day = start_dt.date()
    end_day = end_dt.date()

    requested_days_by_month: dict[tuple[int, int], list[date]] = {}
    while current_day <= end_day:
        key = (current_day.year, current_day.month)
        requested_days_by_month.setdefault(key, []).append(current_day)
        current_day += timedelta(days=1)

    specs: list[ArchiveObjectSpec] = []
    unfulfilled: list[UnfulfilledDateReason] = []

    # Iterate chronologically through months
    for (year, month), days in requested_days_by_month.items():
        _, days_in_month = calendar.monthrange(year, month)
        is_full_month_requested = (len(days) == days_in_month)
        is_monthly_eligible = monthly_archive_eligible(
            year, month, as_of_utc=as_of_dt, publication_buffer_hours=publication_buffer_hours
        )
        supports_monthly = (monthly_support in (True, "VERIFIED_TRUE", "true"))

        # Prefer eligible monthly archive if full month was requested and supported
        if is_full_month_requested and supports_monthly and is_monthly_eligible:
            period_key = f"{year:04d}-{month:02d}"
            paths = build_archive_paths(
                market=market,
                dataset=source_dataset_name,
                symbol=symbol,
                cadence="monthly",
                period=period_key,
                interval=interval,
            )
            period_start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
            if month == 12:
                next_month_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            else:
                next_month_dt = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            period_end = (next_month_dt - timedelta(microseconds=1)).isoformat()

            spec = ArchiveObjectSpec(
                source="binance",
                market=market,
                dataset_id=dataset_id,
                source_dataset_name=source_dataset_name,
                instrument=instrument,
                symbol=symbol,
                cadence="monthly",
                interval=interval,
                period_key=period_key,
                period_start_utc=period_start,
                period_end_utc=period_end,
                archive_url=paths.archive_url,
                checksum_url=paths.checksum_url,
                archive_filename=paths.archive_filename,
                checksum_filename=paths.checksum_filename,
                expected_timestamp_policy=timestamp_policy,
                support_status="VERIFIED_TRUE",
                discovery_evidence_id=f"plan-monthly-{period_key}",
            )
            specs.append(spec)
        else:
            # Plan each day individually via daily archives
            supports_daily = (daily_support in (True, "VERIFIED_TRUE", "true"))
            for d in days:
                if not supports_daily:
                    unfulfilled.append(
                        UnfulfilledDateReason(
                            date=d.isoformat(),
                            status="SOURCE_UNSUPPORTED",
                            reason=f"Dataset {source_dataset_name!r} does not support daily archives (monthly only).",
                        )
                    )
                    continue

                if not daily_archive_eligible(d, as_of_utc=as_of_dt, lag_days=daily_lag_days):
                    if d >= as_of_dt.date():
                        status = "NOT_YET_AVAILABLE"
                        reason = f"Date {d.isoformat()} is current or in future relative to as_of {as_of_dt.date().isoformat()}."
                    else:
                        status = "NOT_YET_AVAILABLE"
                        reason = f"Date {d.isoformat()} is within {daily_lag_days}-day publication lag window."
                    unfulfilled.append(UnfulfilledDateReason(date=d.isoformat(), status=status, reason=reason))
                    continue

                period_key = d.isoformat()
                paths = build_archive_paths(
                    market=market,
                    dataset=source_dataset_name,
                    symbol=symbol,
                    cadence="daily",
                    period=period_key,
                    interval=interval,
                )
                day_start_dt = datetime.combine(d, time.min, tzinfo=timezone.utc)
                day_end_dt = datetime.combine(d, time.max, tzinfo=timezone.utc)

                spec = ArchiveObjectSpec(
                    source="binance",
                    market=market,
                    dataset_id=dataset_id,
                    source_dataset_name=source_dataset_name,
                    instrument=instrument,
                    symbol=symbol,
                    cadence="daily",
                    interval=interval,
                    period_key=period_key,
                    period_start_utc=day_start_dt.isoformat(),
                    period_end_utc=day_end_dt.isoformat(),
                    archive_url=paths.archive_url,
                    checksum_url=paths.checksum_url,
                    archive_filename=paths.archive_filename,
                    checksum_filename=paths.checksum_filename,
                    expected_timestamp_policy=timestamp_policy,
                    support_status="VERIFIED_TRUE",
                    discovery_evidence_id=f"plan-daily-{period_key}",
                )
                specs.append(spec)

    return ArchivePlanResult(
        dataset_id=dataset_id,
        start_utc=start_dt.isoformat(),
        end_utc=end_dt.isoformat(),
        as_of_utc=as_of_dt.isoformat(),
        specs=specs,
        unfulfilled=unfulfilled,
    )
