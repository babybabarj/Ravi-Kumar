"""
NEWS/MACRO-1A: Breaking news source adapter.

IMPORTANT RULE:
  If no authorised point-in-time news provider is configured:
    STATUS = NOT_IMPLEMENTED_PROVIDER_REQUIRED

  Do NOT:
  - Scrape arbitrary websites to reconstruct breaking news retrospectively.
  - Infer past news from current article timestamps.
  - Use RSS feeds of unknown provenance as authorised real-time news.
  - Claim any scraped content is point-in-time verified.

An authorised point-in-time news provider must:
  1. Provide a machine-readable API with exact publication timestamps.
  2. Guarantee that historical queries return only the information that
     was available at the queried timestamp (no future-leaking content).
  3. Have an explicit data license permitting commercial use.

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


# Status constant
BREAKING_NEWS_STATUS_NOT_IMPLEMENTED = "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


class BreakingNewsAdapter:
    """
    Breaking news adapter.

    STATUS: NOT_IMPLEMENTED_PROVIDER_REQUIRED.

    No authorised point-in-time news provider is configured.
    All methods return MacroDataQuality.PROVIDER_REQUIRED.

    This adapter explicitly refuses to scrape or reconstruct news
    retrospectively.
    """

    def __init__(self) -> None:
        # Env var for a future authorised provider API key
        self._api_key: Optional[str] = os.environ.get("NEWS_API_KEY")
        self._configured: bool = False  # stub: NOT_IMPLEMENTED_PROVIDER_REQUIRED

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

        Returns a single NOT_IMPLEMENTED_PROVIDER_REQUIRED item.
        Does NOT scrape, reconstruct, or infer news from any source.
        """
        return [
            MacroNewsItem(
                item_id="BREAKING_NEWS_NOT_IMPLEMENTED",
                source="NOT_CONFIGURED",
                item_type="BREAKING_NEWS",
                published_at_utc=snapshot_time_utc,
                headline=(
                    "NOT_IMPLEMENTED_PROVIDER_REQUIRED: "
                    "No authorised point-in-time news provider configured. "
                    "Do not scrape or retrospectively reconstruct breaking news."
                ),
                quality=MacroDataQuality.PROVIDER_REQUIRED,
                availability_status=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED,
                url=None,
            )
        ]
