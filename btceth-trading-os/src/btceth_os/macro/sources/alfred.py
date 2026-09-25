"""
NEWS/MACRO-1A: FRED/ALFRED (Archival FRED) vintage adapter.

ALFRED (Archival Federal Reserve Economic Data) provides vintage history —
the exact values that were available at any given point in time before
subsequent revisions.

This is critical for the append-only vintage model: ALFRED enables
constructing truly point-in-time observations where the value at
time t reflects what was actually known at time t, not the final revised value.

ALFRED API endpoint: https://alfred.stlouisfed.org/
API key env var: ALFRED_API_KEY

RUNTIME BEHAVIOUR:
  If ALFRED_API_KEY is not set in the environment:
    ALFRED_RUNTIME_STATUS = NOT_CONFIGURED
    The adapter does NOT fail or raise.
    All methods return MacroDataQuality.NOT_CONFIGURED.
    The MacroIntelligenceSnapshot.alfred_runtime_status = "NOT_CONFIGURED".

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


ALFRED_API_BASE = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
ALFRED_API_KEY_ENV = "ALFRED_API_KEY"


class ALFREDAdapter:
    """
    ALFRED (Archival FRED) vintage adapter.

    Provides point-in-time vintage values for FRED series.

    If ALFRED_API_KEY is not configured:
      - ALFRED_RUNTIME_STATUS = NOT_CONFIGURED
      - All fetch methods return MacroDataQuality.NOT_CONFIGURED
      - Does NOT raise an exception

    In NEWS/MACRO-1A, even if the key is configured, the full integration
    is NOT_IMPLEMENTED (the adapter is a stub with the contract defined).
    """

    _checker = PointInTimeAvailabilityChecker()

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get(ALFRED_API_KEY_ENV)
        self._key_configured: bool = self._api_key is not None

    @property
    def runtime_status(self) -> str:
        """
        Return ALFRED runtime status string.

        "CONFIGURED"     — API key is present in environment.
        "NOT_CONFIGURED" — API key absent; adapter returns NOT_CONFIGURED quality.
        """
        return "CONFIGURED" if self._key_configured else "NOT_CONFIGURED"

    @property
    def is_configured(self) -> bool:
        """True if ALFRED_API_KEY is set."""
        return self._key_configured

    def fetch_vintage(
        self,
        series_id: str,
        snapshot_time_utc: datetime,
    ) -> MacroSeriesObservation:
        """
        Fetch the vintage value for series_id as it was known at snapshot_time_utc.

        If not configured → returns NOT_CONFIGURED quality.
        If configured but integration not yet built → returns NOT_IMPLEMENTED.

        Parameters
        ----------
        series_id:
            A valid FRED series ID (e.g. "CPIAUCSL", "PAYEMS", "DGS10").
        snapshot_time_utc:
            The point in time at which we want the vintage value.

        Returns
        -------
        MacroSeriesObservation with appropriate quality state.
        """
        if not self._key_configured:
            return MacroSeriesObservation(
                series_id=f"ALFRED_{series_id}",
                family="ALFRED",
                reference_period="NOT_CONFIGURED",
                vintages=(),
                quality=MacroDataQuality.NOT_CONFIGURED,
                availability_status=MacroAvailabilityStatus.PROVIDER_NOT_CONFIGURED,
                unit="unknown",
                source_agency="FRED_ALFRED",
                staleness_seconds=None,
            )

        # Key is configured but integration is NOT_IMPLEMENTED in this phase
        return MacroSeriesObservation(
            series_id=f"ALFRED_{series_id}",
            family="ALFRED",
            reference_period="NOT_IMPLEMENTED",
            vintages=(),
            quality=MacroDataQuality.NOT_IMPLEMENTED,
            availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
            unit="unknown",
            source_agency="FRED_ALFRED",
            staleness_seconds=None,
        )

    def build_vintage_list(
        self,
        raw_alfred_response: list[dict],
        snapshot_time_utc: datetime,
    ) -> tuple[MacroVintage, ...]:
        """
        Build an append-only vintage list from a raw ALFRED API response.

        The vintage list is chronological.  Only vintages published at or before
        snapshot_time_utc are included (causal guarantee).

        Parameters
        ----------
        raw_alfred_response:
            List of dicts with keys "realtime_start", "value".
        snapshot_time_utc:
            The snapshot reference time.

        Returns
        -------
        Tuple of MacroVintage instances in chronological order.
        """
        snap_t = _ensure_utc(snapshot_time_utc)
        vintages = []
        for entry in raw_alfred_response:
            published_str = entry.get("realtime_start")
            value = entry.get("value")
            if published_str is None or value is None:
                continue
            try:
                published_at = datetime.fromisoformat(published_str)
                published_at = _ensure_utc(published_at)
            except ValueError:
                continue
            # Causal filter: only include vintages available at snapshot_time
            if published_at <= snap_t:
                try:
                    vintages.append(
                        MacroVintage(
                            published_at_utc=published_at,
                            value=float(value),
                        )
                    )
                except (ValueError, TypeError):
                    continue
        vintages.sort(key=lambda v: _ensure_utc(v.published_at_utc))
        return tuple(vintages)
