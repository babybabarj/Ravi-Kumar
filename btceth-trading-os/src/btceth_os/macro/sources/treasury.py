"""
NEWS/MACRO-1A: US Treasury yield data adapter.

Official data source: US Treasury Fiscal Data API (fiscaldata.treasury.gov)
or FRED series (DGS2, DGS5, DGS10, DGS30, DFII10).

IMPORTANT LABELING RULES:
- Treasury yield observations are DAILY_OFFICIAL data released by the
  US Treasury after market close.
- Do NOT call these "live yields".
- Do NOT call these "real-time yields".
- Observation types:
    CURRENT_OFFICIAL_OBSERVATION — today's official yield if already published.
    DAILY_OFFICIAL               — a prior-day official observation.
    STALE                        — observation is available but older than the
                                   recency window.

CAUSAL GUARANTEE: yields are only surfaced if their published date
(the official release date) <= snapshot_date.

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import os
from datetime import datetime, date
from typing import Optional

from btceth_os.macro.types import (
    MacroDataQuality,
    MacroAvailabilityStatus,
    MacroSeriesObservation,
    MacroVintage,
)


# FRED/Treasury series mapping
TREASURY_SERIES: dict[str, dict] = {
    "US_TREASURY_2Y": {
        "fred_series": "DGS2",
        "unit": "percent_annualized",
        "description": "US 2-Year Treasury Constant Maturity Rate (daily official)",
        "family": "TREASURY_2Y",
    },
    "US_TREASURY_5Y": {
        "fred_series": "DGS5",
        "unit": "percent_annualized",
        "description": "US 5-Year Treasury Constant Maturity Rate (daily official)",
        "family": "TREASURY_5Y",
    },
    "US_TREASURY_10Y": {
        "fred_series": "DGS10",
        "unit": "percent_annualized",
        "description": "US 10-Year Treasury Constant Maturity Rate (daily official)",
        "family": "TREASURY_10Y",
    },
    "US_TREASURY_30Y": {
        "fred_series": "DGS30",
        "unit": "percent_annualized",
        "description": "US 30-Year Treasury Constant Maturity Rate (daily official)",
        "family": "TREASURY_30Y",
    },
    "US_TIPS_10Y": {
        "fred_series": "DFII10",
        "unit": "percent_annualized",
        "description": "US 10-Year TIPS Yield / Real Yield (daily official)",
        "family": "TIPS_10Y",
    },
}

# Labels for daily Treasury observations (must not be called "live yields")
OBSERVATION_TYPE_CURRENT = "CURRENT_OFFICIAL_OBSERVATION"
OBSERVATION_TYPE_DAILY = "DAILY_OFFICIAL"
OBSERVATION_TYPE_STALE = "STALE"

FRED_API_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TREASURY_FISCAL_API_BASE = "https://api.fiscaldata.treasury.gov/services/api/v1"


class TreasuryAdapter:
    """
    US Treasury yield adapter (stub in NEWS/MACRO-1A).

    Covers 2Y, 5Y, 10Y, 30Y nominal Treasury yields and 10Y TIPS real yield.

    Labeling contract:
    - These are DAILY_OFFICIAL observations, not "live yields".
    - Observation type is CURRENT_OFFICIAL_OBSERVATION if today's official
      yield is available; DAILY_OFFICIAL for prior-day; STALE if older than
      recency window.

    All fetch methods return MacroDataQuality.NOT_IMPLEMENTED in this phase.
    Credentials: FRED_API_KEY environment variable (optional for public series).
    """

    def __init__(self) -> None:
        self._fred_api_key: Optional[str] = os.environ.get("FRED_API_KEY")
        self._configured: bool = False  # stub: NOT_IMPLEMENTED

    @property
    def is_configured(self) -> bool:
        return self._configured

    def fetch_yield(
        self,
        series_key: str,
        snapshot_time_utc: datetime,
    ) -> MacroSeriesObservation:
        """
        Fetch the latest official Treasury yield causally available at snapshot_time_utc.

        Returns NOT_IMPLEMENTED stub in this phase.
        """
        if series_key not in TREASURY_SERIES:
            raise ValueError(
                f"Unknown Treasury series key {series_key!r}. "
                f"Valid keys: {sorted(TREASURY_SERIES.keys())}."
            )
        spec = TREASURY_SERIES[series_key]
        return MacroSeriesObservation(
            series_id=series_key,
            family=spec["family"],
            reference_period="NOT_IMPLEMENTED",
            vintages=(),
            quality=MacroDataQuality.NOT_IMPLEMENTED,
            availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
            unit=spec["unit"],
            source_agency="US_TREASURY",
            staleness_seconds=None,
        )

    def list_supported_series(self) -> list[str]:
        return list(TREASURY_SERIES.keys())

    @staticmethod
    def observation_type_label(
        observation_date: date,
        snapshot_date: date,
        staleness_days_limit: int = 5,
    ) -> str:
        """
        Return the correct observation type label for a Treasury yield observation.

        Parameters
        ----------
        observation_date:
            The date the yield was officially published.
        snapshot_date:
            The date of the snapshot.
        staleness_days_limit:
            If the yield is older than this many business days, label as STALE.

        Returns
        -------
        One of: CURRENT_OFFICIAL_OBSERVATION, DAILY_OFFICIAL, STALE.
        Never returns "live yield" or similar.
        """
        delta = (snapshot_date - observation_date).days
        if delta == 0:
            return OBSERVATION_TYPE_CURRENT
        elif delta <= staleness_days_limit:
            return OBSERVATION_TYPE_DAILY
        else:
            return OBSERVATION_TYPE_STALE
