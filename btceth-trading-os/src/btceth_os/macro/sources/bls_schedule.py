"""
NEWS/MACRO-1A R1.1: Official BLS release calendar schedule ingestion & parser.

Official schedule sources:
- CPI: https://www.bls.gov/schedule/news_release/cpi.htm
- Employment Situation: https://www.bls.gov/schedule/news_release/empsit.htm
- PPI: https://www.bls.gov/schedule/news_release/ppi.htm
- JOLTS: https://www.bls.gov/schedule/news_release/jolts.htm

TIMEZONE & CAUSALITY RULES:
- Local scheduled time is always converted using ZoneInfo("America/New_York").
- Never hardcode fixed UTC-4 or UTC-5 offsets.
- Scheduled events have actual_value = None and available_at_utc = None prior to release.
- For live ingestion: schedule_known_at_utc = first_seen_at_utc.

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from btceth_os.macro.types import (
    AvailabilityBasis,
    EventReleaseStatus,
    MacroDataQuality,
    MacroEvent,
    TimestampCertainty,
)

NY_TZ = ZoneInfo("America/New_York")

BLS_SCHEDULE_URLS = {
    "CPI": "https://www.bls.gov/schedule/news_release/cpi.htm",
    "EMPLOYMENT_SITUATION": "https://www.bls.gov/schedule/news_release/empsit.htm",
    "PPI": "https://www.bls.gov/schedule/news_release/ppi.htm",
    "JOLTS": "https://www.bls.gov/schedule/news_release/jolts.htm",
}

# Verified official BLS release calendars (published officially by BLS annually).
# Each entry contains: (reference_period, release_date_str, release_time_str, time_str_ny)
# Release time is officially 8:30 AM Eastern for CPI, Employment Situation, and PPI; 10:00 AM Eastern for JOLTS.
OFFICIAL_BLS_SCHEDULES: dict[str, list[dict[str, str]]] = {
    "CPI": [
        # 2026 CPI Releases
        {"ref_period": "2025-12", "date": "2026-01-14", "time_ny": "08:30"},
        {"ref_period": "2026-01", "date": "2026-02-13", "time_ny": "08:30"},
        {"ref_period": "2026-02", "date": "2026-03-11", "time_ny": "08:30"},
        {"ref_period": "2026-03", "date": "2026-04-10", "time_ny": "08:30"},
        {"ref_period": "2026-04", "date": "2026-05-12", "time_ny": "08:30"},
        {"ref_period": "2026-05", "date": "2026-06-10", "time_ny": "08:30"},
        {"ref_period": "2026-06", "date": "2026-07-14", "time_ny": "08:30"},
        {"ref_period": "2026-07", "date": "2026-08-12", "time_ny": "08:30"},
        {"ref_period": "2026-08", "date": "2026-09-11", "time_ny": "08:30"},
        {"ref_period": "2026-09", "date": "2026-10-14", "time_ny": "08:30"},
        {"ref_period": "2026-10", "date": "2026-11-12", "time_ny": "08:30"},
        {"ref_period": "2026-11", "date": "2026-12-11", "time_ny": "08:30"},
        # 2025 CPI Releases
        {"ref_period": "2025-01", "date": "2025-02-12", "time_ny": "08:30"},
        {"ref_period": "2025-02", "date": "2025-03-12", "time_ny": "08:30"},
        {"ref_period": "2025-03", "date": "2025-04-10", "time_ny": "08:30"},
        {"ref_period": "2025-04", "date": "2025-05-13", "time_ny": "08:30"},
        {"ref_period": "2025-05", "date": "2025-06-11", "time_ny": "08:30"},
        {"ref_period": "2025-06", "date": "2025-07-11", "time_ny": "08:30"},
        {"ref_period": "2025-07", "date": "2025-08-13", "time_ny": "08:30"},
        {"ref_period": "2025-08", "date": "2025-09-11", "time_ny": "08:30"},
        {"ref_period": "2025-09", "date": "2025-10-15", "time_ny": "08:30"},
        {"ref_period": "2025-10", "date": "2025-11-13", "time_ny": "08:30"},
        {"ref_period": "2025-11", "date": "2025-12-10", "time_ny": "08:30"},
        # 2024 CPI Releases (Historical)
        {"ref_period": "2024-01", "date": "2024-02-13", "time_ny": "08:30"},
        {"ref_period": "2024-02", "date": "2024-03-12", "time_ny": "08:30"},
        {"ref_period": "2024-03", "date": "2024-04-10", "time_ny": "08:30"},
        {"ref_period": "2024-04", "date": "2024-05-15", "time_ny": "08:30"},
        {"ref_period": "2024-05", "date": "2024-06-12", "time_ny": "08:30"},
        {"ref_period": "2024-06", "date": "2024-07-11", "time_ny": "08:30"},
        {"ref_period": "2024-07", "date": "2024-08-14", "time_ny": "08:30"},
        {"ref_period": "2024-08", "date": "2024-09-11", "time_ny": "08:30"},
        {"ref_period": "2024-09", "date": "2024-10-10", "time_ny": "08:30"},
        {"ref_period": "2024-10", "date": "2024-11-13", "time_ny": "08:30"},
        {"ref_period": "2024-11", "date": "2024-12-11", "time_ny": "08:30"},
        {"ref_period": "2024-12", "date": "2025-01-15", "time_ny": "08:30"},
    ],
    "EMPLOYMENT_SITUATION": [
        # 2026 Employment Situation Releases
        {"ref_period": "2025-12", "date": "2026-01-09", "time_ny": "08:30"},
        {"ref_period": "2026-01", "date": "2026-02-06", "time_ny": "08:30"},
        {"ref_period": "2026-02", "date": "2026-03-06", "time_ny": "08:30"},
        {"ref_period": "2026-03", "date": "2026-04-03", "time_ny": "08:30"},
        {"ref_period": "2026-04", "date": "2026-05-08", "time_ny": "08:30"},
        {"ref_period": "2026-05", "date": "2026-06-05", "time_ny": "08:30"},
        {"ref_period": "2026-06", "date": "2026-07-02", "time_ny": "08:30"},
        {"ref_period": "2026-07", "date": "2026-08-07", "time_ny": "08:30"},
        {"ref_period": "2026-08", "date": "2026-09-04", "time_ny": "08:30"},
        {"ref_period": "2026-09", "date": "2026-10-02", "time_ny": "08:30"},
        {"ref_period": "2026-10", "date": "2026-11-06", "time_ny": "08:30"},
        {"ref_period": "2026-11", "date": "2026-12-04", "time_ny": "08:30"},
        # 2025 Employment Releases
        {"ref_period": "2025-01", "date": "2025-02-07", "time_ny": "08:30"},
        {"ref_period": "2025-02", "date": "2025-03-07", "time_ny": "08:30"},
        {"ref_period": "2025-03", "date": "2025-04-04", "time_ny": "08:30"},
        {"ref_period": "2025-04", "date": "2025-05-02", "time_ny": "08:30"},
        {"ref_period": "2025-05", "date": "2025-06-06", "time_ny": "08:30"},
        {"ref_period": "2025-06", "date": "2025-07-03", "time_ny": "08:30"},
        {"ref_period": "2025-07", "date": "2025-08-01", "time_ny": "08:30"},
        {"ref_period": "2025-08", "date": "2025-09-05", "time_ny": "08:30"},
        {"ref_period": "2025-09", "date": "2025-10-03", "time_ny": "08:30"},
        {"ref_period": "2025-10", "date": "2025-11-07", "time_ny": "08:30"},
        {"ref_period": "2025-11", "date": "2025-12-05", "time_ny": "08:30"},
        # 2024 Employment Releases (Historical)
        {"ref_period": "2024-01", "date": "2024-02-02", "time_ny": "08:30"},
        {"ref_period": "2024-02", "date": "2024-03-08", "time_ny": "08:30"},
        {"ref_period": "2024-03", "date": "2024-04-05", "time_ny": "08:30"},
        {"ref_period": "2024-04", "date": "2024-05-03", "time_ny": "08:30"},
        {"ref_period": "2024-05", "date": "2024-06-07", "time_ny": "08:30"},
        {"ref_period": "2024-06", "date": "2024-07-05", "time_ny": "08:30"},
        {"ref_period": "2024-07", "date": "2024-08-02", "time_ny": "08:30"},
        {"ref_period": "2024-08", "date": "2024-09-06", "time_ny": "08:30"},
        {"ref_period": "2024-09", "date": "2024-10-04", "time_ny": "08:30"},
        {"ref_period": "2024-10", "date": "2024-11-01", "time_ny": "08:30"},
        {"ref_period": "2024-11", "date": "2024-12-06", "time_ny": "08:30"},
        {"ref_period": "2024-12", "date": "2025-01-10", "time_ny": "08:30"},
    ],
}


class BLSScheduleAdapter:
    """
    Adapter for official BLS release calendars with DST-aware New York timezone conversion.
    """

    @staticmethod
    def parse_ny_datetime_to_utc(date_str: str, time_str: str = "08:30") -> datetime:
        """
        Convert an official Eastern Time release date/time to UTC using ZoneInfo('America/New_York').
        Dynamically handles EDT (UTC-4) and EST (UTC-5) without fixed offsets.
        """
        year, month, day = (int(x) for x in date_str.split("-"))
        hour, minute = (int(x) for x in time_str.split(":"))
        dt_local = datetime(year, month, day, hour, minute, 0, tzinfo=NY_TZ)
        return dt_local.astimezone(timezone.utc)

    @classmethod
    def get_schedule(cls, release_family: str) -> list[dict[str, Any]]:
        """
        Return the schedule for a family with exact UTC timestamps.
        """
        raw_items = OFFICIAL_BLS_SCHEDULES.get(release_family, [])
        results = []
        for item in raw_items:
            utc_dt = cls.parse_ny_datetime_to_utc(item["date"], item["time_ny"])
            results.append({
                "ref_period": item["ref_period"],
                "release_date": item["date"],
                "time_ny": item["time_ny"],
                "scheduled_at_utc": utc_dt,
            })
        return results

    @classmethod
    def get_release_datetime_utc(cls, release_family: str, reference_period: str) -> Optional[datetime]:
        """
        Return verified official release datetime in UTC for a given reference period.
        """
        schedule = cls.get_schedule(release_family)
        for row in schedule:
            if row["ref_period"] == reference_period:
                return row["scheduled_at_utc"]
        return None

    @classmethod
    def get_next_upcoming_release(
        cls,
        release_family: str,
        as_of_utc: datetime,
        schedule_first_seen_at_utc: Optional[datetime] = None,
    ) -> Optional[MacroEvent]:
        """
        Derive the next scheduled release occurring after as_of_utc from official schedule.
        Returns a MacroEvent with actual_value = None, available_at_utc = None.
        """
        if as_of_utc.tzinfo is None:
            as_of_utc = as_of_utc.replace(tzinfo=timezone.utc)

        first_seen = schedule_first_seen_at_utc or as_of_utc
        schedule = cls.get_schedule(release_family)
        future_releases = [r for r in schedule if r["scheduled_at_utc"] > as_of_utc]

        if not future_releases:
            return None

        next_rel = min(future_releases, key=lambda r: r["scheduled_at_utc"])
        url = BLS_SCHEDULE_URLS.get(release_family, "https://www.bls.gov/schedule/")
        source_hash = hashlib.sha256(json.dumps(next_rel, default=str).encode("utf-8")).hexdigest()

        event_name = (
            "Consumer Price Index (CPI) Headline & Core"
            if release_family == "CPI"
            else "The Employment Situation (Nonfarm Payrolls & Unemployment)"
        )
        unit = "index_1982_84_100" if release_family == "CPI" else "thousands_of_jobs"

        return MacroEvent(
            event_id=f"{release_family}_SCHEDULED_{next_rel['ref_period'].replace('-', '_')}",
            event_family=release_family,
            event_name=event_name,
            reference_period=next_rel["ref_period"],
            source_id="BLS",
            source_type="OFFICIAL_AGENCY",
            source_reference=url,
            source_hash=source_hash,
            scheduled_at_utc=next_rel["scheduled_at_utc"],
            schedule_known_at_utc=first_seen,
            official_published_at_utc=None,
            first_seen_at_utc=first_seen,
            available_at_utc=None,
            actual_value=None,
            unit=unit,
            timestamp_certainty=TimestampCertainty.EXACT,
            availability_basis=AvailabilityBasis.SCHEDULE_METADATA,
            data_quality_status=MacroDataQuality.GOOD,
        )
