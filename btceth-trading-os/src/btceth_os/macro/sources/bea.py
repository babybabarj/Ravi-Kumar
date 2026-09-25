"""
NEWS/MACRO-1A: BEA (Bureau of Economic Analysis) source adapter.

Official data source: BEA API (apps.bea.gov/api).
API key env var: BEA_API_KEY.

Supported series:
  PCE  — Table T20804 (Personal Consumption Expenditures price index)
  GDP  — Table T10101 (Real Gross Domestic Product)

CAUSAL GUARANTEE: observations are only returned if their published_at_utc
<= snapshot_time_utc.

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
)


BEA_SERIES: dict[str, dict] = {
    "US_PCE_PRICE_INDEX_MOM": {
        "table": "T20804",
        "line": "1",
        "unit": "percent_mom",
        "description": "PCE Price Index (headline, month-over-month)",
    },
    "US_PCE_CORE_MOM": {
        "table": "T20804",
        "line": "16",
        "unit": "percent_mom",
        "description": "PCE Core Price Index (ex. food and energy, mom)",
    },
    "US_GDP_REAL_QOQ_ANNUALIZED": {
        "table": "T10101",
        "line": "1",
        "unit": "percent_annualized_qoq",
        "description": "Real GDP (chained 2017 dollars, annualized QoQ)",
    },
}

BEA_API_BASE = "https://apps.bea.gov/api/data"


class BEAAdapter:
    """
    BEA API adapter (stub in NEWS/MACRO-1A).

    All fetch methods return MacroDataQuality.NOT_IMPLEMENTED.
    Credentials: BEA_API_KEY environment variable.
    """

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get("BEA_API_KEY")
        self._configured: bool = self._api_key is not None

    @property
    def is_configured(self) -> bool:
        return self._configured

    def fetch_series(
        self,
        series_key: str,
        snapshot_time_utc: datetime,
    ) -> MacroSeriesObservation:
        """Return NOT_IMPLEMENTED stub for BEA series."""
        if series_key not in BEA_SERIES:
            raise ValueError(
                f"Unknown BEA series key {series_key!r}. "
                f"Valid keys: {sorted(BEA_SERIES.keys())}."
            )
        spec = BEA_SERIES[series_key]
        return MacroSeriesObservation(
            series_id=series_key,
            family="BEA",
            reference_period="NOT_IMPLEMENTED",
            vintages=(),
            quality=MacroDataQuality.NOT_IMPLEMENTED,
            availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
            unit=spec["unit"],
            source_agency="BEA",
            staleness_seconds=None,
        )

    def list_supported_series(self) -> list[str]:
        return list(BEA_SERIES.keys())
