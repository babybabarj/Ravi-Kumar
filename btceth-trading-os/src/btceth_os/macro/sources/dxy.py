"""
NEWS/MACRO-1A: DXY (ICE U.S. Dollar Index) source adapter.

DXY DEFINITION:
  DXY = the ICE U.S. Dollar Index, published by Intercontinental Exchange (ICE).
  It measures the US Dollar against a basket of 6 major currencies weighted as:
    EUR 57.6%, JPY 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF 3.6%.

DXY IS NOT:
  - FRED DXY (broad trade-weighted dollar index)
  - Federal Reserve broad dollar index
  - A synthetic FX basket
  - A homemade EUR/JPY/GBP basket
  - Any other dollar index

If no authorised ICE DXY provider is configured:
  DXY_STATUS = NOT_IMPLEMENTED_PROVIDER_REQUIRED

This adapter MUST NOT:
  - Substitute any other index for DXY
  - Compute a synthetic basket and label it DXY
  - Use FRED DTWEXBGS or similar broad dollar indices as DXY

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


# Official ICE DXY ticker and description
DXY_TICKER = "DX-Y.NYB"
DXY_DESCRIPTION = "ICE U.S. Dollar Index (DXY) — 6-currency basket weighted by trade"
DXY_COMPONENT_CURRENCIES = {
    "EUR": 0.576,
    "JPY": 0.136,
    "GBP": 0.119,
    "CAD": 0.091,
    "SEK": 0.042,
    "CHF": 0.036,
}

# Explicit status constant
DXY_STATUS_NOT_IMPLEMENTED = "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


class DXYAdapter:
    """
    ICE U.S. Dollar Index (DXY) adapter.

    STATUS: NOT_IMPLEMENTED_PROVIDER_REQUIRED.

    No free public API currently provides authorised intraday DXY data.
    This adapter explicitly refuses to substitute any other index.

    All methods return MacroDataQuality.PROVIDER_REQUIRED.
    """

    # Explicit refusal list — these must NOT be used as DXY substitutes
    REFUSED_SUBSTITUTES: list[str] = [
        "FRED_DTWEXBGS",        # FRED broad trade-weighted dollar index
        "FRED_DTWEXAFEGS",      # FRED advanced foreign economies dollar index
        "FRED_BROAD_DOLLAR",    # Federal Reserve broad dollar index
        "SYNTHETIC_FX_BASKET",  # Any homemade basket
        "EUR_JPY_GBP_BASKET",   # Homemade EUR/JPY/GBP blend
    ]

    def __init__(self) -> None:
        # No authorised provider currently configured
        self._configured: bool = False

    @property
    def status(self) -> str:
        """Return the DXY adapter status string."""
        return DXY_STATUS_NOT_IMPLEMENTED

    @property
    def is_configured(self) -> bool:
        return self._configured

    def fetch_dxy(
        self,
        snapshot_time_utc: datetime,
    ) -> MacroSeriesObservation:
        """
        Return the ICE DXY observation available at snapshot_time_utc.

        Returns PROVIDER_REQUIRED status — no authorised provider configured.
        Does NOT substitute any other index.
        """
        return MacroSeriesObservation(
            series_id="DXY_ICE",
            family="DXY",
            reference_period="NOT_IMPLEMENTED",
            vintages=(),
            quality=MacroDataQuality.PROVIDER_REQUIRED,
            availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
            unit="index_points",
            source_agency="ICE",
            staleness_seconds=None,
        )

    @staticmethod
    def validate_not_substitute(label: str) -> None:
        """
        Raise ValueError if the provided label refers to a refused DXY substitute.

        This is a defence-in-depth check.
        """
        upper = label.upper()
        refused = [s.upper() for s in DXYAdapter.REFUSED_SUBSTITUTES]
        for r in refused:
            if r in upper:
                raise ValueError(
                    f"DXY substitute refused: {label!r}. "
                    "DXY must be the ICE U.S. Dollar Index only. "
                    "Do not substitute FRED broad dollar, synthetic baskets, "
                    "or any other index."
                )
