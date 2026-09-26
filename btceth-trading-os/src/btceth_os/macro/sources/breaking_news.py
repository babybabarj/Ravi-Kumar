"""
NEWS/MACRO-1A R1: Breaking news source adapter.

IMPORTANT RULE:
  If no authorised point-in-time news provider is configured:
    STATUS = NOT_IMPLEMENTED_PROVIDER_REQUIRED

  Do NOT:
  - Scrape arbitrary websites to reconstruct breaking news retrospectively.
  - Infer past news from current article timestamps.
  - Use RSS feeds of unknown provenance as authorised real-time news.
  - Claim any scraped content is point-in-time verified.
  - Fabricate publication timestamps for status placeholders.

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from btceth_os.macro.types import (
    AvailabilityBasis,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroNewsItem,
    TimestampCertainty,
)

BREAKING_NEWS_STATUS_NOT_IMPLEMENTED = "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


class BreakingNewsAdapter:
    """
    Breaking news adapter.

    STATUS: NOT_IMPLEMENTED_PROVIDER_REQUIRED.

    No authorised point-in-time news provider is configured.
    All methods return MacroDataQuality.PROVIDER_REQUIRED.
    Does NOT fabricate publication timestamps.
    """

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.environ.get("NEWS_API_KEY")
        self._configured: bool = False

    @property
    def status(self) -> str:
        """Return the breaking news adapter status string."""
        return BREAKING_NEWS_STATUS_NOT_IMPLEMENTED

    @property
    def is_configured(self) -> bool:
        return self._configured

    def fetch_breaking_news(
        self,
        snapshot_time_utc: datetime,
        max_items: int = 10,
    ) -> list[MacroNewsItem]:
        """
        Return breaking news items available at snapshot_time_utc.

        Returns a single NOT_IMPLEMENTED_PROVIDER_REQUIRED status item
        without any fabricated publication timestamp.
        """
        return [
            MacroNewsItem(
                item_id="BREAKING_NEWS_NOT_IMPLEMENTED",
                source="NOT_CONFIGURED",
                item_type="BREAKING_NEWS",
                headline=(
                    "NOT_IMPLEMENTED_PROVIDER_REQUIRED: "
                    "No authorised point-in-time news provider configured. "
                    "Do not scrape or retrospectively reconstruct breaking news."
                ),
                quality=MacroDataQuality.PROVIDER_REQUIRED,
                availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
                url=None,
                official_published_at_utc=None,
                first_seen_at_utc=None,
                available_at_utc=None,
                timestamp_certainty=TimestampCertainty.UNKNOWN,
                availability_basis=AvailabilityBasis.UNKNOWN,
                published_at_utc=None,
            )
        ]
