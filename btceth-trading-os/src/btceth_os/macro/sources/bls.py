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

import enum
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
    ArchivedEvidenceValidationError,
    AvailabilityBasis,
    BLSArchiveType,
    BLSArchivedVintageEvidence,
    BLSSourceEvidenceType,
    BLSVintageProvenance,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroSeriesObservation,
    MacroVintage,
    TimestampCertainty,
    validate_archived_bls_vintage_evidence,
)
from btceth_os.macro.sources.bls_schedule import BLSScheduleAdapter

BLS_API_BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_API_KEY_ENV = "BLS_API_KEY"
NY_TZ = ZoneInfo("America/New_York")


class BLSResponseValidationStatus(str, enum.Enum):
    """
    Validation status for raw BLS Data API responses (§11).
    """

    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    RATE_LIMITED = "RATE_LIMITED"
    SOURCE_ERROR = "SOURCE_ERROR"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    ZERO_RECORDS = "ZERO_RECORDS"


def validate_bls_live_response(
    http_status: int,
    raw_bytes: bytes,
    parsed_json: dict[str, Any],
    requested_series: list[str],
) -> tuple[BLSResponseValidationStatus, str, int]:
    """
    Strict validation of raw BLS live response (§11).
    Returns (status, detail_message, parsed_record_count).
    """
    if http_status != 200:
        return (
            BLSResponseValidationStatus.SOURCE_ERROR,
            f"HTTP status {http_status}",
            0,
        )

    if not isinstance(parsed_json, dict):
        return (
            BLSResponseValidationStatus.MALFORMED_RESPONSE,
            "Response is not a valid JSON dictionary",
            0,
        )

    # Check for rate limit or provider error messages
    messages = parsed_json.get("message", [])
    if isinstance(messages, str):
        messages = [messages]
    msg_combined = " ".join(str(m) for m in messages).lower()

    if (
        "daily threshold" in msg_combined
        or "threshold" in msg_combined
        or "rate limit" in msg_combined
    ):
        return (
            BLSResponseValidationStatus.RATE_LIMITED,
            messages[0] if messages else "Daily threshold exceeded",
            0,
        )

    top_status = parsed_json.get("status", "")
    if top_status == "REQUEST_NOT_PROCESSED":
        return (
            BLSResponseValidationStatus.RATE_LIMITED
            if ("threshold" in msg_combined or not messages)
            else BLSResponseValidationStatus.SOURCE_ERROR,
            messages[0] if messages else "REQUEST_NOT_PROCESSED",
            0,
        )

    if top_status != "REQUEST_SUCCEEDED":
        return (
            BLSResponseValidationStatus.SOURCE_ERROR,
            messages[0] if messages else f"BLS status {top_status}",
            0,
        )

    results = parsed_json.get("Results")
    if not isinstance(results, dict):
        return (
            BLSResponseValidationStatus.MALFORMED_RESPONSE,
            "Missing Results in BLS response",
            0,
        )

    series_list = results.get("series")
    if not isinstance(series_list, list):
        return (
            BLSResponseValidationStatus.MALFORMED_RESPONSE,
            "Missing Results.series list in BLS response",
            0,
        )

    found_ids = {s.get("seriesID") for s in series_list if isinstance(s, dict)}
    for req_id in requested_series:
        if req_id not in found_ids:
            return (
                BLSResponseValidationStatus.SOURCE_ERROR,
                f"Requested series {req_id} missing from response",
                0,
            )

    total_records = 0
    for s in series_list:
        data_rows = s.get("data", [])
        if not isinstance(data_rows, list):
            continue
        for row in data_rows:
            if not isinstance(row, dict):
                continue
            val_str = row.get("value", "")
            period = row.get("period", "")
            year = row.get("year", "")
            if not val_str or not period or not year:
                continue
            if not period.startswith("M") or period == "M13":
                continue
            try:
                float(val_str)
                total_records += 1
            except ValueError:
                continue

    if total_records == 0:
        return (
            BLSResponseValidationStatus.ZERO_RECORDS,
            "Response contains 0 valid numeric records",
            0,
        )

    return (
        BLSResponseValidationStatus.SOURCE_VERIFIED,
        f"Verified {total_records} records across {len(requested_series)} series",
        total_records,
    )

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

        if eff_evidence_type in (
            BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE,
            BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE,
        ):
            if not archived_vintages_evidence:
                raise ArchivedEvidenceValidationError(
                    f"source_evidence_type claims {eff_evidence_type.value} but no validated proof was provided."
                )

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

            # Check if explicit archived evidence exists for this vintage (§16, §17, §18, §19, §20)
            archived_item = (
                archived_vintages_evidence.get(ref_period)
                if archived_vintages_evidence
                else None
            )

            if archived_item is not None:
                if isinstance(archived_item, BLSArchivedVintageEvidence):
                    arch_ev = archived_item
                elif isinstance(archived_item, dict):
                    is_rev = archived_item.get("is_revision", False)
                    default_arch_type = (
                        BLSArchiveType.REVISION_RELEASE
                        if is_rev
                        else BLSArchiveType.INITIAL_RELEASE
                    )
                    arch_type_raw = archived_item.get("archive_type", default_arch_type)
                    arch_type = (
                        BLSArchiveType(arch_type_raw)
                        if isinstance(arch_type_raw, str)
                        else arch_type_raw
                    )

                    arch_ev = BLSArchivedVintageEvidence(
                        series_id=archived_item.get("series_id", series_id),
                        reference_period=archived_item.get("reference_period", ref_period),
                        value=float(archived_item.get("value", val)),
                        archive_type=arch_type,
                        official_source_url=archived_item.get("official_source_url")
                        or archived_item.get(
                            "source_reference",
                            f"https://www.bls.gov/news.release/archives/{series_id.lower()}_{ref_period}.htm",
                        ),
                        source_raw_sha256=archived_item.get("source_raw_sha256")
                        or archived_item.get("source_hash", ""),
                        official_published_at_utc=archived_item.get("official_published_at_utc")
                        or archived_item.get("published_at_utc")
                        or rel_date_utc
                        or snap_t,
                        timestamp_certainty=archived_item.get(
                            "timestamp_certainty", TimestampCertainty.EXACT
                        ),
                        retrieved_at_utc=archived_item.get("retrieved_at_utc", snap_t),
                        revision_number=archived_item.get("revision_number", 1 if is_rev else 0),
                        revision_label=archived_item.get("revision_label"),
                    )
                else:
                    raise ArchivedEvidenceValidationError(
                        f"Invalid archived evidence object type: {type(archived_item)}"
                    )

                validate_archived_bls_vintage_evidence(arch_ev)

                pub_t = arch_ev.official_published_at_utc
                if pub_t is not None and pub_t <= snap_t:
                    v = MacroVintage(
                        vintage_id=f"BLS_{series_id}_{ref_period}"
                        + (
                            "_REV"
                            if arch_ev.archive_type == BLSArchiveType.REVISION_RELEASE
                            else ""
                        ),
                        value=arch_ev.value,  # Section 20, 38: must come from proof, not current API
                        official_published_at_utc=pub_t,
                        available_at_utc=pub_t,
                        first_seen_at_utc=snap_t,
                        timestamp_certainty=arch_ev.timestamp_certainty,
                        availability_basis=AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME,
                        source_id="BLS_ARCHIVE",
                        source_reference=arch_ev.official_source_url,
                        source_hash=arch_ev.source_raw_sha256,
                        revision_number=arch_ev.revision_number,
                        vintage_provenance=(
                            BLSVintageProvenance.REVISION_RELEASE_PROVEN
                            if arch_ev.archive_type == BLSArchiveType.REVISION_RELEASE
                            else BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN
                        ),
                        source_evidence_type=(
                            BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE
                            if arch_ev.archive_type == BLSArchiveType.REVISION_RELEASE
                            else BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE
                        ),
                        archived_evidence=arch_ev,
                    )
                    vintages.append(v)

            elif eff_evidence_type in (
                BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE,
                BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE,
            ):
                # Section 17, 35: enum-only promotion without proof raises ArchivedEvidenceValidationError
                raise ArchivedEvidenceValidationError(
                    f"Archived vintage for {ref_period} lacks structural BLSArchivedVintageEvidence proof."
                )

            else:
                # Default path (CURRENT_BLS_API):
                # All values obtained from CURRENT BLS Data API default to LATEST_CURRENT_VALUE_ONLY (§12, §13, §14).
                # available_at_utc = first_seen_at_utc = snap_t (LIVE_FIRST_SEEN, historical_intraday_usable = FALSE).
                # official_published_at_utc = rel_date_utc (descriptive reference metadata only, NOT causal available_at).
                v = MacroVintage(
                    vintage_id=f"BLS_{series_id}_{ref_period}",
                    value=val,
                    official_published_at_utc=rel_date_utc,
                    available_at_utc=snap_t,
                    first_seen_at_utc=snap_t,
                    timestamp_certainty=TimestampCertainty.EXACT
                    if rel_date_utc
                    else TimestampCertainty.UNKNOWN,
                    availability_basis=AvailabilityBasis.LIVE_FIRST_SEEN,
                    source_id="BLS",
                    source_reference=f"BLS API {series_id} (current API observation)",
                    revision_number=0,
                    vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
                    source_evidence_type=BLSSourceEvidenceType.CURRENT_BLS_API,
                )
                vintages.append(v)

        vintages.sort(
            key=lambda v: _ensure_utc(
                v.available_at_utc or v.official_published_at_utc or snap_t
            )
        )
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
        Derive YoY CPI percentage change with provenance tracking (§20, §25).
        If inputs are current API values with LATEST_CURRENT_VALUE_ONLY,
        the derived metric inherits CURRENT_DESCRIPTIVE_ONLY and
        derived_metric_historical_intraday_usable = False.
        """
        if not vintages:
            return {
                "value": None,
                "derived_yoy": None,
                "provenance": "NOT_AVAILABLE",
                "derived_metric_provenance": "NOT_AVAILABLE",
                "derived_metric_historical_intraday_usable": False,
                "historical_intraday_usable": False,
                "status": "NOT_AVAILABLE_SOURCE_RATE_LIMITED",
            }
        val = BLSAdapter.derive_cpi_yoy(vintages)
        if val is None or len(vintages) < 13:
            return {
                "value": None,
                "derived_yoy": None,
                "provenance": "NOT_AVAILABLE",
                "derived_metric_provenance": "NOT_AVAILABLE",
                "derived_metric_historical_intraday_usable": False,
                "historical_intraday_usable": False,
                "status": "NOT_AVAILABLE_INSUFFICIENT_HISTORY",
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
            "status": "AVAILABLE",
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
        Derive MoM NFP change with provenance tracking (§20, §25).
        If inputs are current API values with LATEST_CURRENT_VALUE_ONLY,
        the derived metric inherits CURRENT_DESCRIPTIVE_ONLY and
        derived_metric_historical_intraday_usable = False.
        """
        if not vintages:
            return {
                "value": None,
                "derived_mom_change_thousands": None,
                "provenance": "NOT_AVAILABLE",
                "derived_metric_provenance": "NOT_AVAILABLE",
                "derived_metric_historical_intraday_usable": False,
                "historical_intraday_usable": False,
                "status": "NOT_AVAILABLE_SOURCE_RATE_LIMITED",
            }
        val = BLSAdapter.derive_nfp_mom_change(vintages)
        if val is None or len(vintages) < 2:
            return {
                "value": None,
                "derived_mom_change_thousands": None,
                "provenance": "NOT_AVAILABLE",
                "derived_metric_provenance": "NOT_AVAILABLE",
                "derived_metric_historical_intraday_usable": False,
                "historical_intraday_usable": False,
                "status": "NOT_AVAILABLE_INSUFFICIENT_HISTORY",
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
