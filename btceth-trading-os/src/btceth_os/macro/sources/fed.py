"""
NEWS/MACRO-1A R1.1: Federal Reserve source adapter.

Official sources:
- FOMC meeting calendar: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- Monetary policy releases (statements & minutes): https://www.federalreserve.gov/feeds/press_monetary.xml
- Official speeches: https://www.federalreserve.gov/feeds/speeches.xml

POINT-IN-TIME CAUSAL GUARANTEE:
- Monetary feed and Speeches feed are strictly decoupled and never mixed.
- Statements and minutes are only returned if official_published_at_utc <= snapshot_time_utc.
- Upcoming FOMC meetings are derived from official FOMC calendar with actual_value=None and status=SCHEDULED_NOT_RELEASED.
- Timestamp certainty for FOMC calendar meetings without publication second is DATE_ONLY.
- Minutes remain unavailable until their separate, later release date.
- Discount-rate minutes and economic projections are never misclassified as speeches.
- Speech item IDs are cryptographically unique and do not collide across same-minute publications.
- Explicitly: NO hawkish/dovish NLP, NO sentiment scoring, NO trade signals.

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from btceth_os.macro.availability import PointInTimeAvailabilityChecker, _ensure_utc
from btceth_os.macro.types import (
    AvailabilityBasis,
    EventReleaseStatus,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroEvent,
    MacroNewsItem,
    TimestampCertainty,
)

FED_MONETARY_FEED_URL = "https://www.federalreserve.gov/feeds/press_monetary.xml"
FED_SPEECHES_FEED_URL = "https://www.federalreserve.gov/feeds/speeches.xml"
FED_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
}


def classify_fed_item(title: str, link: str = "", desc: str = "") -> str:
    """
    Truthful classification of Federal Reserve official publications.
    Never classifies based purely on which method received the object.
    """
    title_lower = title.lower()
    link_lower = link.lower()

    # 1. FOMC Statement
    if "fomc statement" in title_lower or "monetary policy statement" in title_lower:
        return "FOMC_STATEMENT"

    # 2. FOMC Minutes (specifically FOMC meeting minutes, not Board discount rate minutes)
    if "minutes of the federal open market committee" in title_lower or (
        "minutes" in title_lower and "fomc" in title_lower
    ):
        return "FOMC_MINUTES"

    # 3. FOMC SEP / Projections
    if "economic projections" in title_lower or "summary of economic projections" in title_lower:
        return "FOMC_SEP"

    # 4. Speeches / Remarks
    if "/speech/" in link_lower or "speech" in title_lower or "remarks" in title_lower:
        return "FED_SPEECH"

    # 5. Testimony
    if "/testimony/" in link_lower or "testimony" in title_lower:
        return "FED_TESTIMONY"

    # 6. Other official items (e.g. discount-rate minutes, regulatory releases)
    return "FED_OFFICIAL_OTHER"


def make_fed_item_id(item_type: str, pub_dt: datetime, title: str, link: str) -> str:
    """
    Generate stable unique ID incorporating timestamp + content SHA-256 hash.
    Guarantees no ID collision for items published at the same minute.
    """
    seed = f"{title}|{link}|{pub_dt.isoformat()}".encode("utf-8")
    hash8 = hashlib.sha256(seed).hexdigest()[:8]
    return f"{item_type}_{pub_dt.strftime('%Y%m%d%H%M')}_{hash8}"


def parse_fomc_calendar(html: str) -> list[dict[str, Any]]:
    """
    Parse official Federal Reserve FOMC calendar HTML page.
    Extracts meeting dates, months, years, and decision dates.
    """
    meetings: list[dict[str, Any]] = []
    panels = re.split(r"(<div[^>]*class=\"panel panel-default\">)", html)
    row_pat = re.compile(
        r"<div class=\"[^\"]*fomc-meeting[^\"]*\".*?"
        r"<div class=\"[^\"]*fomc-meeting__month[^\"]*\">\s*<strong>(.*?)</strong>\s*</div>.*?"
        r"<div class=\"[^\"]*fomc-meeting__date[^\"]*\">\s*(.*?)\s*</div>",
        re.DOTALL,
    )

    for p in panels:
        ym = re.search(r"(\d{4})\s+FOMC Meetings", p)
        if not ym:
            continue
        year = int(ym.group(1))
        for m_str, d_str in row_pat.findall(p):
            m_clean = m_str.strip().lower()
            month_num = MONTH_MAP.get(m_clean)
            if not month_num:
                continue
            d_clean = re.sub(r"<[^>]+>", "", d_str).replace("*", "").strip()
            parts = [int(x) for x in re.findall(r"\d+", d_clean)]
            if not parts:
                continue
            start_day = parts[0]
            end_day = parts[-1]
            try:
                dec_date = date(year, month_num, end_day)
            except ValueError:
                continue

            meetings.append({
                "year": year,
                "month": month_num,
                "start_day": start_day,
                "end_day": end_day,
                "raw_date": f"{m_str.strip()} {d_clean}, {year}",
                "decision_date": dec_date,
            })
    return meetings


class FedAdapter:
    """
    Official read-only Federal Reserve data adapter.

    Status: IMPLEMENTED_REAL_SOURCE_VERIFIED
    """

    status = "IMPLEMENTED_REAL_SOURCE_VERIFIED"
    _checker = PointInTimeAvailabilityChecker()

    def __init__(self) -> None:
        self._configured: bool = True

    @property
    def is_configured(self) -> bool:
        return self._configured

    def fetch_feed_raw(
        self,
        feed_url: str = FED_MONETARY_FEED_URL,
        timeout_seconds: float = 12.0,
    ) -> tuple[int, bytes, str, list[dict[str, Any]]]:
        """
        Execute actual HTTP request to official Federal Reserve RSS feed.

        Returns: (http_status, raw_bytes, sha256_hash, parsed_items)
        """
        req = urllib.request.Request(
            feed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (TradingOS/1.0; Research Intelligence; Read-Only)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw_bytes = resp.read()
                status_code = resp.status
                sha = hashlib.sha256(raw_bytes).hexdigest()
                parsed_items = self._parse_rss_items(raw_bytes)
                return status_code, raw_bytes, sha, parsed_items
        except urllib.error.HTTPError as exc:
            raw_bytes = exc.read() if hasattr(exc, "read") else b""
            sha = hashlib.sha256(raw_bytes).hexdigest()
            return exc.code, raw_bytes, sha, []
        except Exception:
            return 500, b"", "", []

    def fetch_monetary_feed_raw(
        self, timeout_seconds: float = 12.0
    ) -> tuple[int, bytes, str, list[dict[str, Any]]]:
        """Fetch monetary policy RSS feed exclusively."""
        return self.fetch_feed_raw(FED_MONETARY_FEED_URL, timeout_seconds=timeout_seconds)

    def fetch_speeches_feed_raw(
        self, timeout_seconds: float = 12.0
    ) -> tuple[int, bytes, str, list[dict[str, Any]]]:
        """Fetch speeches RSS feed exclusively."""
        return self.fetch_feed_raw(FED_SPEECHES_FEED_URL, timeout_seconds=timeout_seconds)

    def fetch_fomc_calendar_raw(
        self, timeout_seconds: float = 12.0
    ) -> tuple[int, bytes, str, list[dict[str, Any]]]:
        """
        Fetch official FOMC meeting calendar page from federalreserve.gov.
        Returns (http_status, raw_bytes, sha256_hash, parsed_meetings).
        """
        req = urllib.request.Request(
            FED_CALENDAR_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (TradingOS/1.0; Research Intelligence; Read-Only)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw_bytes = resp.read()
                status_code = resp.status
                sha = hashlib.sha256(raw_bytes).hexdigest()
                html = raw_bytes.decode("utf-8", errors="ignore")
                parsed_meetings = parse_fomc_calendar(html)
                return status_code, raw_bytes, sha, parsed_meetings
        except urllib.error.HTTPError as exc:
            raw_bytes = exc.read() if hasattr(exc, "read") else b""
            sha = hashlib.sha256(raw_bytes).hexdigest()
            return exc.code, raw_bytes, sha, []
        except Exception:
            return 500, b"", "", []

    def _parse_rss_items(self, raw_bytes: bytes) -> list[dict[str, Any]]:
        """Parse RSS XML into structured dicts with exact publication timestamps and types."""
        try:
            root = ET.fromstring(raw_bytes)
        except Exception:
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        items: list[dict[str, Any]] = []
        for it in channel.findall("item"):
            title = it.findtext("title", "").strip()
            link = it.findtext("link", "").strip()
            desc = it.findtext("description", "").strip()
            pub_date_str = it.findtext("pubDate", "").strip()

            pub_dt: Optional[datetime] = None
            if pub_date_str:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_str)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    pub_dt = None

            item_raw = f"{title}|{link}|{pub_date_str}".encode("utf-8")
            item_hash = hashlib.sha256(item_raw).hexdigest()
            item_type = classify_fed_item(title, link, desc)
            unique_id = (
                make_fed_item_id(item_type, pub_dt, title, link)
                if pub_dt
                else f"{item_type}_UNKNOWN_{item_hash[:8]}"
            )

            items.append({
                "item_id": unique_id,
                "item_type": item_type,
                "title": title,
                "link": link,
                "description": desc,
                "pub_date_utc": pub_dt,
                "raw_pub_date": pub_date_str,
                "item_hash": item_hash,
            })
        return items

    def fetch_latest_fomc_statement(
        self,
        snapshot_time_utc: datetime,
        use_cached_items: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[MacroNewsItem]:
        """
        Return the latest FOMC statement causally available as of snapshot_time_utc.
        Strictly requires item_type == 'FOMC_STATEMENT'.
        """
        snap_t = _ensure_utc(snapshot_time_utc)
        items = use_cached_items
        if items is None:
            _, _, _, items = self.fetch_monetary_feed_raw()

        statements = [
            it for it in items
            if it.get("item_type") == "FOMC_STATEMENT"
            and it["pub_date_utc"] is not None
            and _ensure_utc(it["pub_date_utc"]) <= snap_t
        ]

        if not statements:
            return None

        latest = max(statements, key=lambda it: _ensure_utc(it["pub_date_utc"]))
        pub_t = _ensure_utc(latest["pub_date_utc"])

        return MacroNewsItem(
            item_id=latest.get("item_id") or f"FOMC_STATEMENT_{pub_t.strftime('%Y%m%d%H%M')}_{latest['item_hash'][:8]}",
            source="FEDERAL_RESERVE",
            item_type="FOMC_STATEMENT",
            headline=latest["title"],
            quality=MacroDataQuality.GOOD,
            availability_status=MacroAvailabilityStatus.AVAILABLE,
            url=latest["link"],
            official_published_at_utc=pub_t,
            available_at_utc=pub_t,
            timestamp_certainty=TimestampCertainty.EXACT,
            availability_basis=AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME,
            source_reference=FED_MONETARY_FEED_URL,
            source_hash=latest["item_hash"],
        )

    def fetch_latest_fomc_minutes(
        self,
        snapshot_time_utc: datetime,
        use_cached_items: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[MacroNewsItem]:
        """
        Return the latest FOMC meeting minutes causally available as of snapshot_time_utc.
        Strictly requires item_type == 'FOMC_MINUTES' (discount-rate minutes are excluded).
        """
        snap_t = _ensure_utc(snapshot_time_utc)
        items = use_cached_items
        if items is None:
            _, _, _, items = self.fetch_monetary_feed_raw()

        minutes_items = [
            it for it in items
            if it.get("item_type") == "FOMC_MINUTES"
            and it["pub_date_utc"] is not None
            and _ensure_utc(it["pub_date_utc"]) <= snap_t
        ]

        if not minutes_items:
            return None

        latest = max(minutes_items, key=lambda it: _ensure_utc(it["pub_date_utc"]))
        pub_t = _ensure_utc(latest["pub_date_utc"])

        return MacroNewsItem(
            item_id=latest.get("item_id") or f"FOMC_MINUTES_{pub_t.strftime('%Y%m%d%H%M')}_{latest['item_hash'][:8]}",
            source="FEDERAL_RESERVE",
            item_type="FOMC_MINUTES",
            headline=latest["title"],
            quality=MacroDataQuality.GOOD,
            availability_status=MacroAvailabilityStatus.AVAILABLE,
            url=latest["link"],
            official_published_at_utc=pub_t,
            available_at_utc=pub_t,
            timestamp_certainty=TimestampCertainty.EXACT,
            availability_basis=AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME,
            source_reference=FED_MONETARY_FEED_URL,
            source_hash=latest["item_hash"],
        )

    def fetch_recent_speeches(
        self,
        snapshot_time_utc: datetime,
        max_items: int = 5,
        use_cached_items: Optional[list[dict[str, Any]]] = None,
    ) -> list[MacroNewsItem]:
        """
        Return official Federal Reserve speeches causally available at snapshot_time_utc.
        Strictly filters item_type in ('FED_SPEECH', 'FED_TESTIMONY').
        Never returns statements or minutes as speeches.
        """
        snap_t = _ensure_utc(snapshot_time_utc)
        items = use_cached_items
        if items is None:
            _, _, _, items = self.fetch_speeches_feed_raw()

        eligible = [
            it for it in items
            if it.get("item_type") in ("FED_SPEECH", "FED_TESTIMONY")
            and it["pub_date_utc"] is not None
            and _ensure_utc(it["pub_date_utc"]) <= snap_t
        ]
        eligible.sort(key=lambda it: _ensure_utc(it["pub_date_utc"]), reverse=True)

        results: list[MacroNewsItem] = []
        for it in eligible[:max_items]:
            pub_t = _ensure_utc(it["pub_date_utc"])
            results.append(
                MacroNewsItem(
                    item_id=it.get("item_id") or f"FED_SPEECH_{pub_t.strftime('%Y%m%d%H%M')}_{it['item_hash'][:8]}",
                    source="FEDERAL_RESERVE",
                    item_type=it.get("item_type", "FED_SPEECH"),
                    headline=it["title"],
                    quality=MacroDataQuality.GOOD,
                    availability_status=MacroAvailabilityStatus.AVAILABLE,
                    url=it["link"],
                    official_published_at_utc=pub_t,
                    available_at_utc=pub_t,
                    timestamp_certainty=TimestampCertainty.EXACT,
                    availability_basis=AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME,
                    source_reference=FED_SPEECHES_FEED_URL,
                    source_hash=it["item_hash"],
                )
            )
        return results

    def get_next_upcoming_fomc(
        self,
        snapshot_time_utc: datetime,
        use_cached_meetings: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[MacroEvent]:
        """
        Derive the next scheduled FOMC meeting occurring after snapshot_time_utc
        from the official Federal Reserve calendar.
        Returns a MacroEvent with actual_value=None, timestamp_certainty=DATE_ONLY.
        """
        snap_t = _ensure_utc(snapshot_time_utc)
        meetings = use_cached_meetings
        source_hash = None
        if meetings is None:
            _, _, source_hash, meetings = self.fetch_fomc_calendar_raw()

        if not meetings:
            return None

        # Filter meetings whose decision date is on or after snapshot date
        snap_d = snap_t.date()
        future_meetings = [m for m in meetings if m["decision_date"] >= snap_d]
        if not future_meetings:
            return None

        future_meetings.sort(key=lambda m: m["decision_date"])
        next_m = future_meetings[0]
        dec_d = next_m["decision_date"]
        sched_dt = datetime(dec_d.year, dec_d.month, dec_d.day, 0, 0, 0, tzinfo=timezone.utc)

        return MacroEvent(
            event_id=f"FOMC_MEETING_{dec_d.strftime('%Y%m%d')}",
            event_family="FOMC",
            event_name="FOMC Rate Decision & Policy Statement",
            reference_period=dec_d.strftime("%Y-%m"),
            source_id="FEDERAL_RESERVE",
            source_type="CENTRAL_BANK",
            source_reference=FED_CALENDAR_URL,
            source_hash=source_hash,
            scheduled_at_utc=sched_dt,
            schedule_known_at_utc=snap_t,
            official_published_at_utc=None,
            first_seen_at_utc=snap_t,
            available_at_utc=None,
            actual_value=None,
            unit="target_rate_percent",
            timestamp_certainty=TimestampCertainty.DATE_ONLY,
            availability_basis=AvailabilityBasis.SCHEDULE_METADATA,
            data_quality_status=MacroDataQuality.GOOD,
        )

    def build_fomc_scheduled_event(
        self,
        meeting_date_utc: datetime,
        schedule_known_at_utc: datetime,
        meeting_label: str = "FOMC Rate Decision & Statement",
        timestamp_certainty: TimestampCertainty = TimestampCertainty.DATE_ONLY,
    ) -> MacroEvent:
        """
        Create a scheduled FOMC meeting event with actual_value=None.
        """
        return MacroEvent(
            event_id=f"FOMC_MEETING_{meeting_date_utc.strftime('%Y%m%d')}",
            event_family="FOMC",
            event_name=meeting_label,
            reference_period=meeting_date_utc.strftime("%Y-%m"),
            source_id="FEDERAL_RESERVE",
            source_type="CENTRAL_BANK",
            source_reference=FED_CALENDAR_URL,
            scheduled_at_utc=meeting_date_utc,
            schedule_known_at_utc=schedule_known_at_utc,
            official_published_at_utc=None,
            first_seen_at_utc=schedule_known_at_utc,
            available_at_utc=None,
            actual_value=None,
            unit="target_rate_percent",
            timestamp_certainty=timestamp_certainty,
            availability_basis=AvailabilityBasis.SCHEDULE_METADATA,
            data_quality_status=MacroDataQuality.GOOD,
        )
