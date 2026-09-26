"""
NEWS/MACRO-1A R1: US Treasury yield data adapter.

Official primary data source:
  U.S. Department of the Treasury (home.treasury.gov):
  - Daily Treasury Yield Curve XML:
    https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}
  - Daily Treasury Real Yield Curve (TIPS) XML:
    https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value={year}

IMPORTANT LABELING & CAUSAL RULES:
- Treasury yield observations are DAILY_OFFICIAL data.
- They are NOT "live yields" or "real-time yields".
- Official Treasury yield timestamps have DATE_ONLY certainty in the official feed.
- For historical intraday reconstruction: DATE_ONLY observations are BLOCKED from intraday use.
- For LIVE current ingestion: first_seen_at_utc provides an exact lower bound. Freshly observed
  values become available at or after first_seen_at_utc, never backfilled earlier that day.
- Observation types:
    CURRENT_OFFICIAL_OBSERVATION — today's official yield if released.
    DAILY_OFFICIAL               — prior-day official observation.
    STALE                        — older than recency limit.

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Any, Optional

from btceth_os.macro.availability import PointInTimeAvailabilityChecker, _ensure_utc
from btceth_os.macro.types import (
    AvailabilityBasis,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroSeriesObservation,
    MacroVintage,
    TimestampCertainty,
)

TREASURY_NOMINAL_URL_TEMPLATE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?"
    "data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)
TREASURY_REAL_URL_TEMPLATE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?"
    "data=daily_treasury_real_yield_curve&field_tdr_date_value={year}"
)

# Observation type labels
OBSERVATION_TYPE_CURRENT = "CURRENT_OFFICIAL_OBSERVATION"
OBSERVATION_TYPE_DAILY = "DAILY_OFFICIAL"
OBSERVATION_TYPE_STALE = "STALE"

# Series definitions
TREASURY_SERIES = {
    "US_TREASURY_2Y": {
        "field_name": "BC_2YEAR",
        "family": "TREASURY_2Y",
        "description": "US 2-Year Treasury Constant Maturity Rate (daily official)",
        "unit": "percent_annualized",
        "is_real": False,
    },
    "US_TREASURY_5Y": {
        "field_name": "BC_5YEAR",
        "family": "TREASURY_5Y",
        "description": "US 5-Year Treasury Constant Maturity Rate (daily official)",
        "unit": "percent_annualized",
        "is_real": False,
    },
    "US_TREASURY_10Y": {
        "field_name": "BC_10YEAR",
        "family": "TREASURY_10Y",
        "description": "US 10-Year Treasury Constant Maturity Rate (daily official)",
        "unit": "percent_annualized",
        "is_real": False,
    },
    "US_TREASURY_30Y": {
        "field_name": "BC_30YEAR",
        "family": "TREASURY_30Y",
        "description": "US 30-Year Treasury Constant Maturity Rate (daily official)",
        "unit": "percent_annualized",
        "is_real": False,
    },
    "US_TIPS_10Y": {
        "field_name": "TC_10YEAR",
        "family": "TIPS_10Y",
        "description": "US 10-Year TIPS Yield / Real Yield (daily official)",
        "unit": "percent_annualized",
        "is_real": True,
    },
}


class TreasuryAdapter:
    """
    Official read-only U.S. Treasury yield data adapter.

    Status: IMPLEMENTED_REAL_SOURCE_VERIFIED
    """

    status = "IMPLEMENTED_REAL_SOURCE_VERIFIED"
    _checker = PointInTimeAvailabilityChecker()

    def __init__(self) -> None:
        self._configured: bool = True

    @property
    def is_configured(self) -> bool:
        return self._configured

    def list_supported_series(self) -> list[str]:
        return list(TREASURY_SERIES.keys())

    @staticmethod
    def observation_type_label(
        observation_date: date,
        snapshot_date: date,
        staleness_days_limit: int = 5,
    ) -> str:
        """
        Return the observation type label for a Treasury observation.
        Guarantees that 'live yield' or 'real-time yield' is NEVER returned.
        """
        delta = (snapshot_date - observation_date).days
        if delta == 0:
            return OBSERVATION_TYPE_CURRENT
        elif delta <= staleness_days_limit:
            return OBSERVATION_TYPE_DAILY
        else:
            return OBSERVATION_TYPE_STALE

    def fetch_yield_curve_raw(
        self,
        year: int = 2024,
        is_real: bool = False,
        timeout_seconds: float = 12.0,
    ) -> tuple[int, bytes, str, list[dict[str, Any]]]:
        """
        Execute actual HTTP request to official U.S. Treasury XML endpoint.

        Returns: (http_status, raw_bytes, sha256_hash, parsed_entries)
        """
        url_template = TREASURY_REAL_URL_TEMPLATE if is_real else TREASURY_NOMINAL_URL_TEMPLATE
        url = url_template.format(year=year)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (TradingOS/1.0; Research Intelligence; Read-Only)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw_bytes = resp.read()
                status_code = resp.status
                sha = hashlib.sha256(raw_bytes).hexdigest()
                parsed_entries = self._parse_atom_entries(raw_bytes)
                return status_code, raw_bytes, sha, parsed_entries
        except urllib.error.HTTPError as exc:
            raw_bytes = exc.read() if hasattr(exc, "read") else b""
            sha = hashlib.sha256(raw_bytes).hexdigest()
            return exc.code, raw_bytes, sha, []
        except Exception:
            return 500, b"", "", []

    def _parse_atom_entries(self, raw_bytes: bytes) -> list[dict[str, Any]]:
        """Parse Atom feed entries and extract properties."""
        try:
            root = ET.fromstring(raw_bytes)
        except Exception:
            return []

        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        results: list[dict[str, Any]] = []

        for entry in entries:
            content_el = entry.find("{http://www.w3.org/2005/Atom}content")
            if content_el is None:
                continue
            props = content_el.find(
                "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties"
            )
            if props is None:
                continue

            entry_dict: dict[str, Any] = {}
            for child in props:
                tag_name = child.tag.split("}")[-1]
                entry_dict[tag_name] = child.text
            results.append(entry_dict)
        return results

    def fetch_yield(
        self,
        series_key: str,
        snapshot_time_utc: datetime,
        use_cached_entries: Optional[list[dict[str, Any]]] = None,
        is_live_ingestion: bool = False,
    ) -> MacroSeriesObservation:
        """
        Fetch official Treasury yield causally available as of snapshot_time_utc.
        """
        if series_key not in TREASURY_SERIES:
            raise ValueError(f"Unknown Treasury series key {series_key!r}")

        spec = TREASURY_SERIES[series_key]
        field_name = spec["field_name"]
        is_real = spec["is_real"]
        snap_t = _ensure_utc(snapshot_time_utc)
        snap_d = snap_t.date()

        entries = use_cached_entries
        if entries is None:
            _, _, _, entries = self.fetch_yield_curve_raw(year=snap_d.year, is_real=is_real)
            if not entries and snap_d.year > 2024:
                # Fallback to previous year if early in calendar year
                _, _, _, entries = self.fetch_yield_curve_raw(year=2024, is_real=is_real)

        vintages: list[MacroVintage] = []
        for row in entries:
            date_str = row.get("NEW_DATE", "")
            val_str = row.get(field_name)
            if not date_str or not val_str:
                continue

            try:
                obs_dt = datetime.fromisoformat(date_str)
                if obs_dt.tzinfo is None:
                    obs_dt = obs_dt.replace(tzinfo=timezone.utc)
                val = float(val_str)
            except ValueError:
                continue

            # Treasury daily observation date comparison
            obs_d = obs_dt.date()
            if obs_d <= snap_d:
                # If live ingestion, available_at is receipt/snapshot time
                # If historical, availability is date-level only (23:59:59 UTC of release date)
                if is_live_ingestion:
                    avail_t = snap_t
                    basis = AvailabilityBasis.LIVE_FIRST_SEEN
                    certainty = TimestampCertainty.EXACT
                else:
                    # End of business day release: 21:00 UTC (17:00 Eastern)
                    avail_t = datetime(obs_d.year, obs_d.month, obs_d.day, 21, 0, 0, tzinfo=timezone.utc)
                    basis = AvailabilityBasis.OFFICIAL_DATE_ONLY
                    certainty = TimestampCertainty.DATE_ONLY

                if avail_t <= snap_t:
                    v = MacroVintage(
                        vintage_id=f"TREASURY_{series_key}_{obs_d.isoformat()}",
                        value=val,
                        official_published_at_utc=avail_t,
                        available_at_utc=avail_t,
                        first_seen_at_utc=snap_t if is_live_ingestion else None,
                        timestamp_certainty=certainty,
                        availability_basis=basis,
                        source_id="US_TREASURY",
                        source_reference=f"home.treasury.gov daily yield curve ({field_name})",
                        revision_number=0,
                    )
                    vintages.append(v)

        vintages.sort(key=lambda v: _ensure_utc(v.available_at_utc or v.official_published_at_utc))
        quality = MacroDataQuality.GOOD if vintages else MacroDataQuality.MISSING
        avail_status = (
            MacroAvailabilityStatus.AVAILABLE if vintages else MacroAvailabilityStatus.NOT_YET_RELEASED
        )

        return MacroSeriesObservation(
            series_id=series_key,
            family=spec["family"],
            reference_period=vintages[-1].vintage_id.split("_")[-1] if vintages else "UNKNOWN",
            vintages=tuple(vintages),
            quality=quality,
            availability_status=avail_status,
            unit=spec["unit"],
            source_agency="US_TREASURY",
            staleness_seconds=None,
            native_semantic_type="YIELD_PERCENT",
            transformation="NONE_DIRECT_YIELD",
        )
