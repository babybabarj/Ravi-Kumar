"""
NEWS/MACRO-1A: Federal Reserve source adapter.

Covers:
  - FOMC rate decisions and statements (federalreserve.gov)
  - Federal Reserve speeches (federalreserve.gov/newsevents/speech)
  - FOMC meeting minutes

IMPORTANT: NEWS/MACRO-1A does NOT include hawkish/dovish NLP scoring,
sentiment scoring, or LLM interpretation of Fed communications.
This adapter is a stub for data availability tracking only.

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from btceth_os.macro.types import (
    MacroDataQuality,
    MacroAvailabilityStatus,
    MacroNewsItem,
)


FED_API_BASE = "https://www.federalreserve.gov"

# Known FOMC meeting schedule endpoints (official)
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_SPEECH_URL = "https://www.federalreserve.gov/newsevents/speech.htm"


class FedAdapter:
    """
    Federal Reserve data adapter (stub in NEWS/MACRO-1A).

    Tracks FOMC decisions, speeches, and minutes.
    No NLP, no sentiment scoring, no hawkish/dovish classification.

    All methods return MacroDataQuality.NOT_IMPLEMENTED in this phase.
    No API key required (public website data), but a future structured
    data feed would require configuration.
    """

    def __init__(self) -> None:
        # No API key required for Fed public data in the stub phase.
        # A structured provider integration would use environment config.
        self._configured: bool = False  # stub: NOT_IMPLEMENTED

    @property
    def is_configured(self) -> bool:
        return self._configured

    def fetch_latest_fomc_statement(
        self,
        snapshot_time_utc: datetime,
    ) -> MacroNewsItem:
        """
        Return the most recently available FOMC statement at snapshot_time_utc.

        Returns NOT_IMPLEMENTED stub in this phase.
        """
        return MacroNewsItem(
            item_id="FOMC_STATEMENT_NOT_IMPLEMENTED",
            source="FEDERAL_RESERVE",
            item_type="FOMC_STATEMENT",
            published_at_utc=snapshot_time_utc,  # placeholder for stub
            headline="NOT_IMPLEMENTED: FOMC statement provider not configured.",
            quality=MacroDataQuality.NOT_IMPLEMENTED,
            availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
            url=None,
        )

    def fetch_latest_fomc_minutes(
        self,
        snapshot_time_utc: datetime,
    ) -> MacroNewsItem:
        """Return NOT_IMPLEMENTED stub for FOMC minutes."""
        return MacroNewsItem(
            item_id="FOMC_MINUTES_NOT_IMPLEMENTED",
            source="FEDERAL_RESERVE",
            item_type="FOMC_MINUTES",
            published_at_utc=snapshot_time_utc,
            headline="NOT_IMPLEMENTED: FOMC minutes provider not configured.",
            quality=MacroDataQuality.NOT_IMPLEMENTED,
            availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
            url=None,
        )

    def fetch_recent_speeches(
        self,
        snapshot_time_utc: datetime,
        max_items: int = 5,
    ) -> list[MacroNewsItem]:
        """Return NOT_IMPLEMENTED stub for Fed speeches."""
        return [
            MacroNewsItem(
                item_id="FED_SPEECH_NOT_IMPLEMENTED",
                source="FEDERAL_RESERVE",
                item_type="FED_SPEECH",
                published_at_utc=snapshot_time_utc,
                headline="NOT_IMPLEMENTED: Fed speech provider not configured.",
                quality=MacroDataQuality.NOT_IMPLEMENTED,
                availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
                url=None,
            )
        ]
