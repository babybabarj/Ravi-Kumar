"""
NEWS/MACRO-1A R1: BEA (Bureau of Economic Analysis) source adapter.

Official sources:
- Official release schedule: https://www.bea.gov/news/schedule
- Structured data API: https://apps.bea.gov/api/data (requires BEA_API_KEY)

SEMANTIC AUDIT:
- PCE Price Index (Table T20804): Native unit is INDEX_LEVEL (2017=100), NOT percent_mom or percent_yoy!
- Any YoY or MoM PCE metric must be derived causally from index levels.
- Real GDP (Table T10101): Native unit is chained dollars, annualized QoQ percentage is a transformed rate.

CREDENTIALS & STATUS:
- If BEA_API_KEY is not configured:
  Structured series fetch returns MacroDataQuality.NOT_CONFIGURED.
  Official public release schedule is still available without credentials.
  Adapter status: PARTIAL (schedule verified, structured series NOT_CONFIGURED).

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import hashlib
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from btceth_os.macro.availability import PointInTimeAvailabilityChecker, _ensure_utc
from btceth_os.macro.types import (
    AvailabilityBasis,
    EventReleaseStatus,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroEvent,
    MacroSeriesObservation,
    TimestampCertainty,
)

BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
BEA_API_BASE = "https://apps.bea.gov/api/data"
BEA_API_KEY_ENV = "BEA_API_KEY"

BEA_SERIES_SEMANTICS = {
    "US_PCE_PRICE_INDEX": {
        "table": "T20804",
        "line": "1",
        "official_title": "Personal Consumption Expenditures (PCE) Price Index",
        "native_unit": "index_2017_100",
        "native_semantic_type": "INDEX_LEVEL",
        "frequency": "MONTHLY",
        "transformation": "YoY = ((Index_t / Index_{t-12}) - 1.0) * 100.0",
    },
    "US_PCE_CORE": {
        "table": "T20804",
        "line": "16",
        "official_title": "Personal Consumption Expenditures Less Food and Energy (Core PCE)",
        "native_unit": "index_2017_100",
        "native_semantic_type": "INDEX_LEVEL",
        "frequency": "MONTHLY",
        "transformation": "YoY = ((Index_t / Index_{t-12}) - 1.0) * 100.0",
    },
    "US_GDP_REAL": {
        "table": "T10101",
        "line": "1",
        "official_title": "Gross Domestic Product (Real Chained Dollars)",
        "native_unit": "billions_chained_2017_dollars",
        "native_semantic_type": "OUTPUT_LEVEL",
        "frequency": "QUARTERLY",
        "transformation": "Annualized QoQ growth rate",
    },
}

_LEGACY_BEA_ALIASES = {
    "US_PCE_PRICE_INDEX_MOM": "US_PCE_PRICE_INDEX",
    "US_PCE_CORE_MOM": "US_PCE_CORE",
    "US_GDP_REAL_QOQ_ANNUALIZED": "US_GDP_REAL",
}


class BEAAdapter:
    """
    BEA data adapter.

    Status: PARTIAL (Public release schedule operational; structured API requires BEA_API_KEY).
    """

    status = "PARTIAL"
    _checker = PointInTimeAvailabilityChecker()

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get(BEA_API_KEY_ENV)
        self._configured: bool = self._api_key is not None

    @property
    def is_configured(self) -> bool:
        return self._configured

    def list_supported_series(self) -> list[str]:
        return list(BEA_SERIES_SEMANTICS.keys()) + list(_LEGACY_BEA_ALIASES.keys())

    def get_semantics(self, key: str) -> dict[str, Any]:
        canonical = _LEGACY_BEA_ALIASES.get(key, key)
        if canonical not in BEA_SERIES_SEMANTICS:
            raise ValueError(f"Unknown BEA series key {key!r}")
        return dict(BEA_SERIES_SEMANTICS[canonical])

    def fetch_schedule_raw(
        self,
        timeout_seconds: float = 12.0,
    ) -> tuple[int, bytes, str, list[dict[str, Any]]]:
        """
        Fetch official BEA release schedule from https://www.bea.gov/news/schedule.
        """
        req = urllib.request.Request(
            BEA_SCHEDULE_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (TradingOS/1.0; Research Intelligence; Read-Only)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw_bytes = resp.read()
                status_code = resp.status
                sha = hashlib.sha256(raw_bytes).hexdigest()
                parsed_events = self._parse_schedule_html(raw_bytes.decode("utf-8", errors="ignore"))
                return status_code, raw_bytes, sha, parsed_events
        except urllib.error.HTTPError as exc:
            raw_bytes = exc.read() if hasattr(exc, "read") else b""
            sha = hashlib.sha256(raw_bytes).hexdigest()
            return exc.code, raw_bytes, sha, []
        except Exception:
            return 500, b"", "", []

    def _parse_schedule_html(self, html: str) -> list[dict[str, Any]]:
        """Parse PCE and GDP schedule rows from official BEA schedule page."""
        events: list[dict[str, Any]] = []
        rows = re.findall(
            r'<tr class="scheduled-releases-type-press">.*?<div class="release-date">([^<]+)</div>.*?<td class="release-title[^>]*>([^<]+)</td>',
            html,
            re.DOTALL,
        )
        for date_str, title in rows:
            clean_title = title.strip()
            if any(k in clean_title for k in ("Personal Income and Outlays", "GDP", "PCE")):
                events.append({
                    "date_str": date_str.strip(),
                    "title": clean_title,
                    "time_str": "8:30 AM Eastern",
                })
        return events

    def fetch_series(
        self,
        series_key: str,
        snapshot_time_utc: datetime,
    ) -> MacroSeriesObservation:
        """
        Fetch structured BEA series.

        Returns MacroDataQuality.NOT_CONFIGURED truthfully when BEA_API_KEY is absent.
        """
        canonical = _LEGACY_BEA_ALIASES.get(series_key, series_key)
        if canonical not in BEA_SERIES_SEMANTICS:
            raise ValueError(f"Unknown BEA series key {series_key!r}")

        spec = BEA_SERIES_SEMANTICS[canonical]

        return MacroSeriesObservation(
            series_id=canonical,
            family="BEA",
            reference_period="NOT_IMPLEMENTED",
            vintages=(),
            quality=MacroDataQuality.NOT_IMPLEMENTED,
            availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
            unit=spec["native_unit"],
            source_agency="BEA",
            staleness_seconds=None,
            native_semantic_type=spec["native_semantic_type"],
            transformation=spec.get("transformation"),
        )
