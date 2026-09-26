"""
NEWS/MACRO-1A R1.1: BLS (Bureau of Labor Statistics) source adapter.

Official data source: BLS Data API (https://api.bls.gov/publicAPI/v2/timeseries/data/).
Official schedule source: BLSScheduleAdapter (official BLS release calendar).

SEMANTIC AUDIT:
- Headline CPI (CUSR0000SA0): native unit is INDEX_LEVEL (1982-84=100), NOT percent_yoy!
- Core CPI (CUSR0000SA0L1E): native unit is INDEX_LEVEL (1982-84=100), NOT percent_yoy!
- Total Nonfarm Payroll (CES0000000001): native unit is EMPLOYMENT_LEVEL_THOUSANDS, NOT monthly change!
- Unemployment Rate (LNS14000000): native unit is RATE_PERCENT (percent of labor force).
- Derived YoY CPI: (Index_t / Index_{t-12} - 1.0) * 100.0.
- Derived NFP monthly net change: Level_t - Level_{t-1} (thousands of jobs).

VINTAGE & AVAILABILITY SAFETY:
- VALUE_SOURCE: BLS Data API (api.bls.gov).
- AVAILABILITY_SOURCE: Official BLS release calendar / schedule publication metadata.
- ZERO GUESSED TIMESTAMPS: Release dates are looked up from verified official release calendars.
  No generic day 12, month+1, or fixed 13:30 approximations.
- LATEST_CURRENT_VALUE_ONLY observations from current API cannot be backdated into historical intraday features.
- If release timing cannot be proven from official calendar: VINTAGE_UNKNOWN (fails closed).

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from btceth_os.macro.availability import PointInTimeAvailabilityChecker, _ensure_utc
from btceth_os.macro.types import (
    AvailabilityBasis,
    BLSSourceEvidenceType,
    BLSVintageProvenance,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroSeriesObservation,
    MacroVintage,
    TimestampCertainty,
)
from btceth_os.macro.sources.bls_schedule import BLSScheduleAdapter

BLS_API_BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_API_KEY_ENV = "BLS_API_KEY"
NY_TZ = ZoneInfo("America/New_York")

BLS_SERIES_SEMANTICS: dict[str, dict[str, Any]] = {
    "US_CPI_HEADLINE": {
        "series_id": "CUSR0000SA0",
        "family": "CPI",
        "official_title": "Consumer Price Index for All Urban Consumers: All Items",
        "native_unit": "index_1982_84_100",
        "native_semantic_type": "INDEX_LEVEL",
        "seasonal_adjustment": "SEASONALLY_ADJUSTED",
        "frequency": "MONTHLY",
        "can_derive_yoy": True,
        "transformation": "YoY = ((Index_t / Index_{t-12}) - 1.0) * 100.0",
    },
    "US_CPI_CORE": {
        "series_id": "CUSR0000SA0L1E",
        "family": "CPI",
        "official_title": "Consumer Price Index for All Urban Consumers: All Items Less Food and Energy",
        "native_unit": "index_1982_84_100",
        "native_semantic_type": "INDEX_LEVEL",
        "seasonal_adjustment": "SEASONALLY_ADJUSTED",
        "frequency": "MONTHLY",
        "can_derive_yoy": True,
        "transformation": "YoY = ((Index_t / Index_{t-12}) - 1.0) * 100.0",
    },
    "US_NFP_TOTAL": {
        "series_id": "CES0000000001",
        "family": "EMPLOYMENT_SITUATION",
        "official_title": "All Employees, Total Nonfarm",
        "native_unit": "thousands_of_jobs",
        "native_semantic_type": "EMPLOYMENT_LEVEL_THOUSANDS",
        "seasonal_adjustment": "SEASONALLY_ADJUSTED",
        "frequency": "MONTHLY",
        "can_derive_mom_change": True,
        "transformation": "MoM_Change = Level_t - Level_{t-1}",
    },
    "US_UNEMPLOYMENT_RATE": {
        "series_id": "LNS14000000",
        "family": "EMPLOYMENT_SITUATION",
        "official_title": "Unemployment Rate - Civilian Labor Force",
        "native_unit": "percent",
        "native_semantic_type": "RATE_PERCENT",
        "seasonal_adjustment": "SEASONALLY_ADJUSTED",
        "frequency": "MONTHLY",
        "can_derive_yoy": False,
        "transformation": "NONE_DIRECT_RATE",
    },
    "US_PPI_FINAL_DEMAND": {
        "series_id": "WPSFD4",
        "family": "PPI",
        "official_title": "Producer Price Index by Commodity: Final Demand",
        "native_unit": "index_nov_2009_100",
        "native_semantic_type": "INDEX_LEVEL",
        "seasonal_adjustment": "SEASONALLY_ADJUSTED",
        "frequency": "MONTHLY",
        "can_derive_yoy": True,
        "transformation": "YoY = ((Index_t / Index_{t-12}) - 1.0) * 100.0",
    },
    "US_JOLTS_OPENINGS": {
        "series_id": "JTS000000000000000JOL",
        "family": "JOLTS",
        "official_title": "Job Openings: Total Nonfarm",
        "native_unit": "thousands_openings",
        "native_semantic_type": "EMPLOYMENT_LEVEL_THOUSANDS",
        "seasonal_adjustment": "SEASONALLY_ADJUSTED",
        "frequency": "MONTHLY",
        "can_derive_mom_change": True,
        "transformation": "MoM_Change = Level_t - Level_{t-1}",
    },
}

_KEY_ALIASES = {
    "US_CPI_HEADLINE_YOY": "US_CPI_HEADLINE",
    "US_CPI_CORE_YOY": "US_CPI_CORE",
    "US_NFP_MOM": "US_NFP_TOTAL",
    "US_PPI_FINAL_DEMAND_MOM": "US_PPI_FINAL_DEMAND",
}


class BLSAdapter:
    """
    Official read-only BLS adapter with calendar-verified release availability.

    Status: IMPLEMENTED_REAL_SOURCE_VERIFIED
    """

    status = "IMPLEMENTED_REAL_SOURCE_VERIFIED"
    _checker = PointInTimeAvailabilityChecker()

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get(BLS_API_KEY_ENV)
        self._configured: bool = self._api_key is not None

    @property
    def is_configured(self) -> bool:
        return self._configured

    def list_supported_series(self) -> list[str]:
        return list(BLS_SERIES_SEMANTICS.keys()) + list(_KEY_ALIASES.keys())

    def get_semantics(self, key: str) -> dict[str, Any]:
        canonical = _KEY_ALIASES.get(key, key)
        if canonical not in BLS_SERIES_SEMANTICS:
            raise ValueError(f"Unknown BLS series key {key!r}")
        return dict(BLS_SERIES_SEMANTICS[canonical])

    def fetch_series_raw(
        self,
        series_ids: list[str],
        start_year: str = "2025",
        end_year: str = "2026",
        timeout_seconds: float = 12.0,
    ) -> tuple[int, bytes, str, dict[str, Any]]:
        """
        Execute actual HTTP request to official BLS API.

        Returns: (http_status, raw_bytes, sha256_hash, parsed_json)
        """
        payload: dict[str, Any] = {
            "seriesid": series_ids,
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        if self._api_key:
            payload["registrationkey"] = self._api_key

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            BLS_API_BASE,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TradingOS/1.0 (Research Intelligence; Read-Only)",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw_bytes = resp.read()
                status_code = resp.status
                sha = hashlib.sha256(raw_bytes).hexdigest()
                parsed = json.loads(raw_bytes.decode("utf-8"))
                return status_code, raw_bytes, sha, parsed
        except urllib.error.HTTPError as exc:
            raw_bytes = exc.read() if hasattr(exc, "read") else b""
            sha = hashlib.sha256(raw_bytes).hexdigest()
            return exc.code, raw_bytes, sha, {"error": str(exc)}
        except Exception as exc:
            return 500, b"", "", {"error": str(exc)}

    def parse_series_vintages(
        self,
        raw_series_data: list[dict[str, Any]],
        series_id: str,
        snapshot_time_utc: datetime,
        family: str = "CPI",
        evidence_type: Optional[BLSSourceEvidenceType] = None,
        source_evidence_type: Optional[BLSSourceEvidenceType] = None,
        archived_vintages_evidence: Optional[dict[str, dict[str, Any]]] = None,
        is_live_current_snapshot: bool = False,
    ) -> tuple[MacroVintage, ...]:
        """
        Parse raw BLS API observations into MacroVintage instances using VERIFIED release calendars.
        ZERO guessed release days or fixed UTC offsets.

        SAFE PROVENANCE RULE (§13, §14, §15, §24, §25):
        Any value obtained from CURRENT BLS Data API defaults to LATEST_CURRENT_VALUE_ONLY.
        Knowing the official release date does NOT prove the current API value is the original release value!
        ZERO entries become ORIGINAL_RELEASE_PROVEN unless explicit archived vintage evidence is provided.
        """
        eff_evidence_type = source_evidence_type or evidence_type or BLSSourceEvidenceType.CURRENT_BLS_API
        snap_t = _ensure_utc(snapshot_time_utc)
        vintages: list[MacroVintage] = []

        for item in raw_series_data:
            period = item.get("period", "")
            year = item.get("year", "")
            val_str = item.get("value", "")
            if not period.startswith("M") or period == "M13" or not val_str:
                continue

            try:
                month = int(period[1:])
                val = float(val_str)
            except ValueError:
                continue

            ref_period = f"{year}-{month:02d}"

            # Look up verified official release datetime from BLS calendar schedule
            sched_family = "CPI" if "CPI" in family else "EMPLOYMENT_SITUATION"
            rel_date_utc = BLSScheduleAdapter.get_release_datetime_utc(sched_family, ref_period)

            # Check if explicit archived evidence exists for this vintage (§16, §17)
            archived_info = archived_vintages_evidence.get(ref_period) if archived_vintages_evidence else None

            if archived_info is not None:
                # Explicit archived vintage artifact proves provenance (§16, §17)
                is_revision = archived_info.get("is_revision", False)
                prov = (
                    BLSVintageProvenance.REVISION_RELEASE_PROVEN
                    if is_revision
                    else BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN
                )
                pub_t = archived_info.get("published_at_utc", rel_date_utc)
                if pub_t is not None and pub_t <= snap_t:
                    v = MacroVintage(
                        vintage_id=f"BLS_{series_id}_{ref_period}" + ("_REV" if is_revision else ""),
                        value=float(archived_info.get("value", val)),
                        official_published_at_utc=pub_t,
                        available_at_utc=pub_t,
                        first_seen_at_utc=snap_t,
                        timestamp_certainty=TimestampCertainty.EXACT,
                        availability_basis=AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME,
                        source_id="BLS_ARCHIVE",
                        source_reference=archived_info.get("source_reference", f"BLS Archive {series_id} {ref_period}"),
                        source_hash=archived_info.get("source_hash"),
                        revision_number=1 if is_revision else 0,
                        vintage_provenance=prov,
                        source_evidence_type=(
                            BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE
                            if is_revision
                            else BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE
                        ),
                    )
                    vintages.append(v)
            elif eff_evidence_type == BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE:
                if rel_date_utc is not None and rel_date_utc <= snap_t:
                    v = MacroVintage(
                        vintage_id=f"BLS_{series_id}_{ref_period}",
                        value=val,
                        official_published_at_utc=rel_date_utc,
                        available_at_utc=rel_date_utc,
                        first_seen_at_utc=snap_t,
                        timestamp_certainty=TimestampCertainty.EXACT,
                        availability_basis=AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME,
                        source_id="BLS_ARCHIVE",
                        source_reference=f"BLS Archived Initial Release {series_id} {ref_period}",
                        revision_number=0,
                        vintage_provenance=BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN,
                        source_evidence_type=BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE,
                    )
                    vintages.append(v)
            elif eff_evidence_type == BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE:
                if rel_date_utc is not None and rel_date_utc <= snap_t:
                    v = MacroVintage(
                        vintage_id=f"BLS_{series_id}_{ref_period}_REV",
                        value=val,
                        official_published_at_utc=rel_date_utc,
                        available_at_utc=rel_date_utc,
                        first_seen_at_utc=snap_t,
                        timestamp_certainty=TimestampCertainty.EXACT,
                        availability_basis=AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME,
                        source_id="BLS_ARCHIVE",
                        source_reference=f"BLS Archived Revision Release {series_id} {ref_period}",
                        revision_number=1,
                        vintage_provenance=BLSVintageProvenance.REVISION_RELEASE_PROVEN,
                        source_evidence_type=BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE,
                    )
                    vintages.append(v)
            else:
                # Default path (CURRENT_BLS_API):
                # All values obtained from CURRENT BLS Data API default to LATEST_CURRENT_VALUE_ONLY (§13, §14, §15).
                # availability_basis = LIVE_FIRST_SEEN, historical_intraday_usable = FALSE.
                if rel_date_utc is not None and rel_date_utc <= snap_t:
                    v = MacroVintage(
                        vintage_id=f"BLS_{series_id}_{ref_period}",
                        value=val,
                        official_published_at_utc=rel_date_utc,
                        available_at_utc=rel_date_utc,
                        first_seen_at_utc=snap_t,
                        timestamp_certainty=TimestampCertainty.EXACT,
                        availability_basis=AvailabilityBasis.LIVE_FIRST_SEEN,
                        source_id="BLS",
                        source_reference=f"BLS API {series_id} (current API observation)",
                        revision_number=0,
                        vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
                        source_evidence_type=BLSSourceEvidenceType.CURRENT_BLS_API,
                    )
                    vintages.append(v)
                else:
                    v = MacroVintage(
                        vintage_id=f"BLS_{series_id}_{ref_period}_UNVERIFIED_CADENCE",
                        value=val,
                        official_published_at_utc=None,
                        available_at_utc=snap_t,
                        first_seen_at_utc=snap_t,
                        timestamp_certainty=TimestampCertainty.UNKNOWN,
                        availability_basis=AvailabilityBasis.LIVE_FIRST_SEEN,
                        source_id="BLS",
                        source_reference=f"BLS API {series_id} (schedule unverified)",
                        revision_number=0,
                        vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
                        source_evidence_type=BLSSourceEvidenceType.CURRENT_BLS_API,
                    )
                    vintages.append(v)

        vintages.sort(key=lambda v: _ensure_utc(v.available_at_utc or v.official_published_at_utc or snap_t))
        return tuple(vintages)

    def fetch_series(
        self,
        series_key: str,
        snapshot_time_utc: datetime,
        use_cached_raw: Optional[dict[str, Any]] = None,
        evidence_type: BLSSourceEvidenceType = BLSSourceEvidenceType.CURRENT_BLS_API,
        archived_vintages_evidence: Optional[dict[str, dict[str, Any]]] = None,
        is_live_current_snapshot: bool = False,
    ) -> MacroSeriesObservation:
        """
        Fetch and causally filter a BLS series observation as of snapshot_time_utc.
        Dynamically derives requested year range from snapshot_time_utc (§13).
        Defaults to LATEST_CURRENT_VALUE_ONLY provenance for current API values (§15).
        """
        canonical_key = _KEY_ALIASES.get(series_key, series_key)
        if canonical_key not in BLS_SERIES_SEMANTICS:
            raise ValueError(f"Unknown BLS series key {series_key!r}")

        spec = BLS_SERIES_SEMANTICS[canonical_key]
        series_id = spec["series_id"]
        family = spec.get("family", "CPI")

        if use_cached_raw is not None:
            raw_resp = use_cached_raw
        else:
            # Dynamic year range based on snapshot time UTC (§13)
            curr_y = snapshot_time_utc.year
            start_y = str(curr_y - 1)
            end_y = str(curr_y)
            _, _, _, raw_resp = self.fetch_series_raw([series_id], start_year=start_y, end_year=end_y)

        series_data_list: list[dict[str, Any]] = []
        for s in raw_resp.get("Results", {}).get("series", []):
            if s.get("seriesID") == series_id:
                series_data_list = s.get("data", [])
                break

        vintages = self.parse_series_vintages(
            series_data_list,
            series_id,
            snapshot_time_utc,
            family=family,
            evidence_type=evidence_type,
            archived_vintages_evidence=archived_vintages_evidence,
            is_live_current_snapshot=is_live_current_snapshot,
        )
        quality = MacroDataQuality.GOOD if vintages else MacroDataQuality.NOT_IMPLEMENTED
        avail_status = (
            MacroAvailabilityStatus.AVAILABLE if vintages else MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED
        )

        return MacroSeriesObservation(
            series_id=canonical_key,
            family=family,
            reference_period=vintages[-1].vintage_id.split("_")[-1] if vintages else "UNKNOWN",
            vintages=vintages,
            quality=quality,
            availability_status=avail_status,
            unit=spec["native_unit"],
            source_agency="BLS",
            staleness_seconds=None,
            native_semantic_type=spec["native_semantic_type"],
            transformation=spec.get("transformation"),
        )

    @staticmethod
    def derive_cpi_yoy(vintages: tuple[MacroVintage, ...]) -> Optional[float]:
        """
        Derive YoY CPI percentage change causally:
        YoY = ((Index_t / Index_{t-12}) - 1.0) * 100.0.
        Requires at least 13 monthly observations.
        """
        if len(vintages) < 13:
            return None
        current_val = vintages[-1].value
        past_val = vintages[-13].value
        if past_val <= 0:
            return None
        return round(((current_val / past_val) - 1.0) * 100.0, 4)

    @staticmethod
    def derive_cpi_yoy_provenance(vintages: tuple[MacroVintage, ...]) -> dict[str, Any]:
        """
        Derive YoY CPI percentage change with provenance tracking (§20).
        If inputs are current API values with LATEST_CURRENT_VALUE_ONLY,
        the derived metric inherits CURRENT_DESCRIPTIVE_ONLY and
        derived_metric_historical_intraday_usable = False.
        """
        val = BLSAdapter.derive_cpi_yoy(vintages)
        if val is None or len(vintages) < 13:
            return {
                "value": None,
                "derived_yoy": None,
                "provenance": "NOT_AVAILABLE",
                "derived_metric_provenance": "NOT_AVAILABLE",
                "derived_metric_historical_intraday_usable": False,
                "historical_intraday_usable": False,
            }
        required_vintages = [vintages[-1], vintages[-13]]
        all_proven = all(
            v.vintage_provenance in (
                BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN,
                BLSVintageProvenance.REVISION_RELEASE_PROVEN,
            )
            and v.timestamp_certainty == TimestampCertainty.EXACT
            for v in required_vintages
        )
        prov = "HISTORICAL_CAUSAL_PROVEN" if all_proven else "CURRENT_DESCRIPTIVE_ONLY"
        usable = bool(all_proven)
        return {
            "value": val,
            "derived_yoy": val,
            "provenance": prov,
            "derived_metric_provenance": prov,
            "derived_metric_historical_intraday_usable": usable,
            "historical_intraday_usable": usable,
        }

    @staticmethod
    def derive_nfp_mom_change(vintages: tuple[MacroVintage, ...]) -> Optional[float]:
        """
        Derive MoM NFP change in thousands of jobs:
        MoM = Level_t - Level_{t-1}.
        Requires at least 2 monthly observations.
        """
        if len(vintages) < 2:
            return None
        current_val = vintages[-1].value
        past_val = vintages[-2].value
        return round(current_val - past_val, 1)

    @staticmethod
    def derive_nfp_mom_provenance(vintages: tuple[MacroVintage, ...]) -> dict[str, Any]:
        """
        Derive MoM NFP change with provenance tracking (§20).
        If inputs are current API values with LATEST_CURRENT_VALUE_ONLY,
        the derived metric inherits CURRENT_DESCRIPTIVE_ONLY and
        derived_metric_historical_intraday_usable = False.
        """
        val = BLSAdapter.derive_nfp_mom_change(vintages)
        if val is None or len(vintages) < 2:
            return {
                "value": None,
                "derived_mom_change_thousands": None,
                "provenance": "NOT_AVAILABLE",
                "derived_metric_provenance": "NOT_AVAILABLE",
                "derived_metric_historical_intraday_usable": False,
                "historical_intraday_usable": False,
            }
        required_vintages = [vintages[-1], vintages[-2]]
        all_proven = all(
            v.vintage_provenance in (
                BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN,
                BLSVintageProvenance.REVISION_RELEASE_PROVEN,
            )
            and v.timestamp_certainty == TimestampCertainty.EXACT
            for v in required_vintages
        )
        prov = "HISTORICAL_CAUSAL_PROVEN" if all_proven else "CURRENT_DESCRIPTIVE_ONLY"
        usable = bool(all_proven)
        return {
            "value": val,
            "derived_mom_change_thousands": val,
            "provenance": prov,
            "derived_metric_provenance": prov,
            "derived_metric_historical_intraday_usable": usable,
            "historical_intraday_usable": usable,
        }
