"""
NEWS/MACRO-1A: Point-in-time availability contract.

The fundamental causal rule:
    An observation is available at snapshot_time_utc if and only if
    observation.published_at_utc <= snapshot_time_utc.

No futures information is ever injected into the snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from btceth_os.macro.types import MacroAvailabilityStatus, MacroDataQuality, MacroVintage


class PointInTimeAvailabilityChecker:
    """
    Enforces the point-in-time causal availability contract.

    All methods are stateless and purely functional.
    No side effects; no data mutation.
    """

    # Default maximum staleness for series considered "current" (seconds).
    # Observations older than this are rated STALE rather than GOOD.
    DEFAULT_STALENESS_LIMIT_SECONDS: float = 60 * 60 * 24 * 7  # 7 days

    def check_vintage_availability(
        self,
        vintages: tuple[MacroVintage, ...],
        snapshot_time_utc: datetime,
        staleness_limit_seconds: Optional[float] = None,
    ) -> tuple[MacroAvailabilityStatus, Optional[float]]:
        """
        Given a series' vintage list, return (availability_status, staleness_seconds).

        Parameters
        ----------
        vintages:
            Chronological list of published vintages.
        snapshot_time_utc:
            The point in time at which we are constructing the snapshot.
        staleness_limit_seconds:
            If None, uses DEFAULT_STALENESS_LIMIT_SECONDS.

        Returns
        -------
        (MacroAvailabilityStatus, staleness_seconds | None)
        """
        if staleness_limit_seconds is None:
            staleness_limit_seconds = self.DEFAULT_STALENESS_LIMIT_SECONDS

        # Ensure snapshot_time_utc is timezone-aware
        snapshot_time_utc = _ensure_utc(snapshot_time_utc)

        eligible = [
            v for v in vintages
            if _ensure_utc(v.published_at_utc) <= snapshot_time_utc
        ]

        if not eligible:
            return MacroAvailabilityStatus.NOT_YET_RELEASED, None

        latest = max(eligible, key=lambda v: _ensure_utc(v.published_at_utc))
        staleness = (
            snapshot_time_utc - _ensure_utc(latest.published_at_utc)
        ).total_seconds()

        if staleness > staleness_limit_seconds:
            return MacroAvailabilityStatus.STALE, staleness

        return MacroAvailabilityStatus.AVAILABLE, staleness

    def check_event_availability(
        self,
        actual_release_utc: datetime,
        snapshot_time_utc: datetime,
    ) -> MacroAvailabilityStatus:
        """
        Check whether a macro event release is causally available at snapshot_time_utc.

        Parameters
        ----------
        actual_release_utc:
            When the event was publicly released.
        snapshot_time_utc:
            The snapshot reference time.

        Returns
        -------
        MacroAvailabilityStatus.AVAILABLE or NOT_YET_RELEASED
        """
        snapshot_time_utc = _ensure_utc(snapshot_time_utc)
        actual_release_utc = _ensure_utc(actual_release_utc)

        if actual_release_utc <= snapshot_time_utc:
            return MacroAvailabilityStatus.AVAILABLE
        return MacroAvailabilityStatus.NOT_YET_RELEASED

    def is_causal_violation(
        self,
        published_at_utc: datetime,
        snapshot_time_utc: datetime,
    ) -> bool:
        """
        Return True if using this observation at snapshot_time would constitute
        a causal (look-ahead) violation.

        published_at_utc > snapshot_time_utc → True (violation, must block).
        """
        return _ensure_utc(published_at_utc) > _ensure_utc(snapshot_time_utc)

    def quality_from_availability(
        self,
        status: MacroAvailabilityStatus,
    ) -> MacroDataQuality:
        """
        Map availability status to a MacroDataQuality state (fail-closed).
        """
        mapping = {
            MacroAvailabilityStatus.AVAILABLE: MacroDataQuality.GOOD,
            MacroAvailabilityStatus.NOT_YET_RELEASED: MacroDataQuality.CAUSAL_VIOLATION,
            MacroAvailabilityStatus.STALE: MacroDataQuality.STALE,
            MacroAvailabilityStatus.PROVIDER_NOT_CONFIGURED: MacroDataQuality.NOT_CONFIGURED,
            MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED: MacroDataQuality.NOT_IMPLEMENTED,
        }
        return mapping.get(status, MacroDataQuality.MISSING)


def _ensure_utc(dt: datetime) -> datetime:
    """
    Return a timezone-aware UTC datetime.

    If dt is naive, it is assumed to be UTC (and marked as such).
    If dt is already tz-aware, it is returned as-is.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
