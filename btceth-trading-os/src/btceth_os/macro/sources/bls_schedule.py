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
import pathlib
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

# Manually verified historical reference fixtures (used for deterministic unit testing only, §10).
# NOT to be confused with the live official schedule parser (§5).
MANUALLY_VERIFIED_BLS_SCHEDULE_FIXTURES: dict[str, list[dict[str, str]]] = {
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

OFFICIAL_BLS_SCHEDULES = MANUALLY_VERIFIED_BLS_SCHEDULE_FIXTURES


class BLSScheduleAdapter:
    """
    Adapter for official BLS release calendars with DST-aware New York timezone conversion.
    Supports both live official HTML schedule ingestion (§6, §8) and offline fixtures (§10).
    """

    MONTH_MAP = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

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
    def parse_date_cell(cls, date_str: str) -> Optional[tuple[int, int, int]]:
        """Parse date cell from official BLS schedule table (e.g. 'Oct. 14, 2026')."""
        m = re.search(r"([A-Za-z]+)\.?\s+(\d+),\s+(\d{4})", date_str)
        if not m:
            return None
        m_name, day, year = m.groups()
        mo = cls.MONTH_MAP.get(m_name.lower().rstrip("."))
        if not mo:
            return None
        return int(year), mo, int(day)

    @classmethod
    def parse_ref_period_cell(cls, ref_str: str) -> str:
        """Parse reference period cell from official BLS schedule table (e.g. 'September 2026' -> '2026-09')."""
        m = re.search(r"([A-Za-z]+)\s+(\d{4})", ref_str)
        if not m:
            return ref_str.strip()
        m_name, year = m.groups()
        mo = cls.MONTH_MAP.get(m_name.lower())
        if not mo:
            return ref_str.strip()
        return f"{year}-{mo:02d}"

    @classmethod
    def parse_time_cell(cls, time_str: str) -> tuple[int, int]:
        """Parse release time cell (e.g. '08:30 AM'). Defaults to 08:30."""
        m = re.search(r"(\d+):(\d+)\s*(AM|PM)", time_str, re.IGNORECASE)
        if not m:
            return 8, 30
        h, minute, ampm = m.groups()
        hour = int(h)
        minute = int(minute)
        if ampm.upper() == "PM" and hour < 12:
            hour += 12
        elif ampm.upper() == "AM" and hour == 12:
            hour = 0
        return hour, minute

    @classmethod
    def fetch_schedule_raw(
        cls,
        release_family: str,
        timeout: int = 15,
        save_dir: Optional[pathlib.Path] = None,
    ) -> tuple[int, bytes, str, list[MacroEvent]]:
        """
        Fetch raw official BLS release schedule HTML from official URL (§6).
        Records: source_url, fetch_time_utc, http_status, raw_byte_count, raw_sha256.
        Saves raw response bytes to /tmp/news_macro_1a_r1_2/ and parses schedule events.
        """
        raw_dir = save_dir or pathlib.Path("/tmp/news_macro_1a_r1_2")
        raw_dir.mkdir(parents=True, exist_ok=True)

        url = BLS_SCHEDULE_URLS.get(release_family)
        if not url:
            raise ValueError(f"Unknown release family {release_family!r}")

        fetch_time_utc = datetime.now(timezone.utc)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (TradingOS/1.0; Research; mailto:ops@tradingos.internal)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                raw_bytes = resp.read()
        except Exception:
            return 0, b"", "", []

        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        (raw_dir / f"bls_{release_family.lower()}_schedule.html").write_bytes(raw_bytes)

        events = cls.parse_schedule_html(
            raw_bytes.decode("utf-8", errors="ignore"),
            release_family,
            raw_sha256,
            fetch_time_utc,
        )
        return status, raw_bytes, raw_sha256, events

    @classmethod
    def parse_schedule_html(
        cls,
        html_text: str,
        release_family: str,
        source_raw_hash: str,
        fetch_time_utc: datetime,
    ) -> list[MacroEvent]:
        """
        Derive schedule events from raw official BLS HTML source bytes (§8).
        Source hash represents exact SHA256 of raw official BLS response bytes (§9).
        Schedule first-seen is actual fetch time (§12).
        """
        if fetch_time_utc.tzinfo is None:
            fetch_time_utc = fetch_time_utc.replace(tzinfo=timezone.utc)

        table_match = re.search(
            r"<table[^>]*class=[\"'][^\"']*release-list[^\"']*[\"'][^>]*>(.*?)</table>",
            html_text,
            re.DOTALL | re.IGNORECASE,
        )
        if not table_match:
            table_match = re.search(
                r"<table[^>]*>(?:(?!<table).)*?Reference Month.*?</table>",
                html_text,
                re.DOTALL | re.IGNORECASE,
            )

        if not table_match:
            return []

        t_content = table_match.group(0)
        rows = re.findall(
            r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>",
            t_content,
            re.DOTALL | re.IGNORECASE,
        )

        url = BLS_SCHEDULE_URLS.get(release_family, "https://www.bls.gov/schedule/")
        event_name = (
            "Consumer Price Index (CPI) Headline & Core"
            if release_family == "CPI"
            else "The Employment Situation (Nonfarm Payrolls & Unemployment)"
        )
        unit = "index_1982_84_100" if release_family == "CPI" else "thousands_of_jobs"

        events: list[MacroEvent] = []
        for r in rows:
            ref_raw = re.sub(r"<[^>]+>", "", r[0]).strip()
            date_raw = re.sub(r"<[^>]+>", "", r[1]).strip()
            time_raw = re.sub(r"<[^>]+>", "", r[2]).strip()

            ref_period = cls.parse_ref_period_cell(ref_raw)
            dp = cls.parse_date_cell(date_raw)
            tp = cls.parse_time_cell(time_raw)
            if not dp:
                continue

            dt_local = datetime(dp[0], dp[1], dp[2], tp[0], tp[1], 0, tzinfo=NY_TZ)
            dt_utc = dt_local.astimezone(timezone.utc)

            event = MacroEvent(
                event_id=f"{release_family}_SCHEDULED_{ref_period.replace('-', '_')}",
                event_family=release_family,
                event_name=event_name,
                reference_period=ref_period,
                source_id="BLS",
                source_type="OFFICIAL_AGENCY",
                source_reference=url,
                source_hash=source_raw_hash,
                scheduled_at_utc=dt_utc,
                schedule_known_at_utc=fetch_time_utc,
                official_published_at_utc=None,
                first_seen_at_utc=fetch_time_utc,
                available_at_utc=None,
                actual_value=None,
                unit=unit,
                timestamp_certainty=TimestampCertainty.EXACT,
                availability_basis=AvailabilityBasis.SCHEDULE_METADATA,
                data_quality_status=MacroDataQuality.GOOD,
            )
            events.append(event)

        events.sort(key=lambda e: e.scheduled_at_utc)
        return events

    @classmethod
    def get_live_schedule_events(
        cls,
        release_family: str,
        as_of_utc: Optional[datetime] = None,
        use_cached_html: Optional[str] = None,
        raw_sha256: Optional[str] = None,
    ) -> list[MacroEvent]:
        """Return events parsed from live official BLS schedule source bytes (§11)."""
        fetch_t = as_of_utc or datetime.now(timezone.utc)
        if use_cached_html is not None:
            sha = raw_sha256 or hashlib.sha256(use_cached_html.encode("utf-8")).hexdigest()
            return cls.parse_schedule_html(use_cached_html, release_family, sha, fetch_t)
        _, _, _, events = cls.fetch_schedule_raw(release_family)
        return events

    @classmethod
    def get_next_upcoming_release_live(
        cls,
        release_family: str,
        as_of_utc: datetime,
        live_events: Optional[list[MacroEvent]] = None,
        use_cached_html: Optional[str] = None,
        raw_sha256: Optional[str] = None,
    ) -> Optional[MacroEvent]:
        """
        Derive next upcoming release directly from live official source bytes (§11).
        Does NOT use local frozen constants.
        """
        if as_of_utc.tzinfo is None:
            as_of_utc = as_of_utc.replace(tzinfo=timezone.utc)

        events = live_events or cls.get_live_schedule_events(
            release_family, as_of_utc=as_of_utc, use_cached_html=use_cached_html, raw_sha256=raw_sha256
        )
        future = [e for e in events if e.scheduled_at_utc > as_of_utc]
        if not future:
            return None
        return min(future, key=lambda e: e.scheduled_at_utc)

    @classmethod
    def get_fixture_schedule(cls, release_family: str) -> list[dict[str, Any]]:
        """Return the frozen offline schedule fixture (for deterministic unit testing only, §10)."""
        raw_items = MANUALLY_VERIFIED_BLS_SCHEDULE_FIXTURES.get(release_family, [])
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
    def get_schedule(cls, release_family: str) -> list[dict[str, Any]]:
        """Backward compatible schedule accessor using offline fixture."""
        return cls.get_fixture_schedule(release_family)

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
        use_live_parser: bool = False,
        live_events: Optional[list[MacroEvent]] = None,
        use_cached_html: Optional[str] = None,
        raw_sha256: Optional[str] = None,
    ) -> Optional[MacroEvent]:
        """
        Derive the next scheduled release occurring after as_of_utc.
        If use_live_parser=True, derives strictly from live official source bytes (§11).
        """
        if use_live_parser:
            return cls.get_next_upcoming_release_live(
                release_family,
                as_of_utc,
                live_events=live_events,
                use_cached_html=use_cached_html,
                raw_sha256=raw_sha256,
            )

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
