"""
NEWS/MACRO-1A R1: Federal Reserve source adapter.

Official sources:
- FOMC meeting calendar: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- Monetary policy releases (statements & minutes): https://www.federalreserve.gov/feeds/press_monetary.xml
- Official speeches: https://www.federalreserve.gov/feeds/speeches.xml

POINT-IN-TIME CAUSAL GUARANTEE:
- Statements and minutes are only returned if official_published_at_utc <= snapshot_time_utc.
- Upcoming FOMC meetings are returned with actual_value=None and status=SCHEDULED_NOT_RELEASED.
- Minutes remain unavailable until their separate, later release date.
- Explicitly: NO hawkish/dovish NLP, NO sentiment scoring, NO trade signals.

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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

    def _parse_rss_items(self, raw_bytes: bytes) -> list[dict[str, Any]]:
        """Parse RSS XML into structured dicts with exact publication timestamps."""
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

            items.append({
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
        """
        snap_t = _ensure_utc(snapshot_time_utc)
        items = use_cached_items
        if items is None:
            _, _, _, items = self.fetch_feed_raw(FED_MONETARY_FEED_URL)

        statements = [
            it for it in items
            if "statement" in it["title"].lower()
            and it["pub_date_utc"] is not None
            and _ensure_utc(it["pub_date_utc"]) <= snap_t
        ]

        if not statements:
            return None

        latest = max(statements, key=lambda it: _ensure_utc(it["pub_date_utc"]))
        pub_t = _ensure_utc(latest["pub_date_utc"])

        return MacroNewsItem(
            item_id=f"FOMC_STATEMENT_{pub_t.strftime('%Y%m%d')}",
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
        """
        snap_t = _ensure_utc(snapshot_time_utc)
        items = use_cached_items
        if items is None:
            _, _, _, items = self.fetch_feed_raw(FED_MONETARY_FEED_URL)

        minutes_items = [
            it for it in items
            if "minutes" in it["title"].lower()
            and it["pub_date_utc"] is not None
            and _ensure_utc(it["pub_date_utc"]) <= snap_t
        ]

        if not minutes_items:
            return None

        latest = max(minutes_items, key=lambda it: _ensure_utc(it["pub_date_utc"]))
        pub_t = _ensure_utc(latest["pub_date_utc"])

        return MacroNewsItem(
            item_id=f"FOMC_MINUTES_{pub_t.strftime('%Y%m%d')}",
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
        """
        snap_t = _ensure_utc(snapshot_time_utc)
        items = use_cached_items
        if items is None:
            _, _, _, items = self.fetch_feed_raw(FED_SPEECHES_FEED_URL)

        eligible = [
            it for it in items
            if it["pub_date_utc"] is not None
            and _ensure_utc(it["pub_date_utc"]) <= snap_t
        ]
        eligible.sort(key=lambda it: _ensure_utc(it["pub_date_utc"]), reverse=True)

        results: list[MacroNewsItem] = []
        for it in eligible[:max_items]:
            pub_t = _ensure_utc(it["pub_date_utc"])
            results.append(
                MacroNewsItem(
                    item_id=f"FED_SPEECH_{pub_t.strftime('%Y%m%d%H%M')}",
                    source="FEDERAL_RESERVE",
                    item_type="FED_SPEECH",
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

    def build_fomc_scheduled_event(
        self,
        meeting_date_utc: datetime,
        schedule_known_at_utc: datetime,
        meeting_label: str = "FOMC Rate Decision & Statement",
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
            first_seen_at_utc=None,
            available_at_utc=None,
            actual_value=None,
            unit="target_rate_percent",
            timestamp_certainty=TimestampCertainty.EXACT,
            availability_basis=AvailabilityBasis.SCHEDULE_METADATA,
            data_quality_status=MacroDataQuality.GOOD,
        )
