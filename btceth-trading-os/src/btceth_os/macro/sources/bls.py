"""
NEWS/MACRO-1A: BLS (Bureau of Labor Statistics) source adapter.

Official data source: BLS Data API (api.bls.gov).
API key: optional for public series; required for higher rate limits.

Supported series:
  CPI  — CUSR0000SA0 (headline), CUSR0000SA0L1E (core)
  PPI  — WPSFD4
  NFP  — CES0000000001
  Unemployment — LNS14000000
  JOLTS — JTS000000000000000JOL

CAUSAL GUARANTEE: observations are only returned if their published_at_utc
(the BLS release date/time) <= snapshot_time_utc.

API key env var: BLS_API_KEY (optional; if absent, uses unauthenticated access).

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from btceth_os.macro.types import (
    MacroDataQuality,
    MacroAvailabilityStatus,
    MacroSeriesObservation,
    MacroVintage,
)
from btceth_os.macro.availability import PointInTimeAvailabilityChecker, _ensure_utc


# BLS series IDs for supported families
BLS_SERIES: dict[str, dict] = {
    "US_CPI_HEADLINE_YOY": {
        "series_id": "CUSR0000SA0",
        "unit": "percent_yoy",
        "description": "US CPI All Urban Consumers (Headline)",
    },
    "US_CPI_CORE_YOY": {
        "series_id": "CUSR0000SA0L1E",
        "unit": "percent_yoy",
        "description": "US CPI All Urban Consumers Less Food and Energy (Core)",
    },
    "US_PPI_FINAL_DEMAND_MOM": {
        "series_id": "WPSFD4",
        "unit": "percent_mom",
        "description": "US PPI Final Demand",
    },
    "US_NFP_MOM": {
        "series_id": "CES0000000001",
        "unit": "thousands_jobs",
        "description": "US Total Nonfarm Payroll Employment",
    },
    "US_UNEMPLOYMENT_RATE": {
        "series_id": "LNS14000000",
        "unit": "percent",
        "description": "US Unemployment Rate (U-3)",
    },
    "US_JOLTS_OPENINGS": {
        "series_id": "JTS000000000000000JOL",
        "unit": "thousands_openings",
        "description": "US JOLTS Total Nonfarm Job Openings",
    },
}

BLS_API_BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


class BLSAdapter:
    """
    BLS Data API adapter.

    In NEWS/MACRO-1A this adapter is a STUB.  All fetch methods return
    MacroDataQuality.NOT_IMPLEMENTED.  This is intentional — the data types
    and contracts are defined; provider integration will be built in a later
    phase when authorised API access is established.

    No API key is committed to git.  Credentials must be provided via the
    BLS_API_KEY environment variable.
    """

    _checker = PointInTimeAvailabilityChecker()

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get("BLS_API_KEY")
        self._configured: bool = self._api_key is not None

    @property
    def is_configured(self) -> bool:
        """True if a BLS API key is available in the environment."""
        return self._configured

    def fetch_series(
        self,
        series_key: str,
        snapshot_time_utc: datetime,
    ) -> MacroSeriesObservation:
        """
        Fetch a BLS series observation causal at snapshot_time_utc.

        Parameters
        ----------
        series_key:
            One of the keys in BLS_SERIES.
        snapshot_time_utc:
            Snapshot reference time.

        Returns
        -------
        MacroSeriesObservation with quality NOT_IMPLEMENTED (stub phase).
        """
        if series_key not in BLS_SERIES:
            raise ValueError(
                f"Unknown BLS series key {series_key!r}. "
                f"Valid keys: {sorted(BLS_SERIES.keys())}."
            )

        spec = BLS_SERIES[series_key]
        return MacroSeriesObservation(
            series_id=series_key,
            family="BLS",
            reference_period="NOT_IMPLEMENTED",
            vintages=(),
            quality=MacroDataQuality.NOT_IMPLEMENTED,
            availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
            unit=spec["unit"],
            source_agency="BLS",
            staleness_seconds=None,
        )

    def list_supported_series(self) -> list[str]:
        """Return the list of supported BLS series keys."""
        return list(BLS_SERIES.keys())
