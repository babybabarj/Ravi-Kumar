"""
NEWS/MACRO-1A: Point-in-time availability contract and query API.

The fundamental causal rules:
1. Released data is available at snapshot_time_utc if and only if
   available_at_utc <= snapshot_time_utc.
2. Scheduled event metadata is visible if and only if
   schedule_known_at_utc <= snapshot_time_utc, even if scheduled_at_utc > snapshot_time_utc.
3. Actual values for upcoming events are strictly hidden (actual_value = None)
   until available_at_utc <= snapshot_time_utc.
4. Date-only observations are blocked from intraday historical feature extraction.
5. In live ingestion, available_at_utc cannot precede first_seen_at_utc unless
   an exact official publication timestamp is supported by verified provenance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from btceth_os.macro.types import (
    AvailabilityBasis,
    EventReleaseStatus,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroEvent,
    MacroEventView,
    MacroNewsItem,
    MacroNewsView,
    MacroSeriesObservation,
    MacroVintage,
    TimestampCertainty,
)


class PointInTimeAvailabilityChecker:
    """
    Enforces the point-in-time causal availability contract.

    All methods are stateless and purely functional.
    No side effects; no data mutation.
    """

    # Default maximum staleness for series considered "current" (seconds).
    DEFAULT_STALENESS_LIMIT_SECONDS: float = 60 * 60 * 24 * 7  # 7 days

    def check_vintage_availability(
        self,
        vintages: tuple[MacroVintage, ...],
        snapshot_time_utc: datetime,
        staleness_limit_seconds: Optional[float] = None,
        resolution: str = "INTRADAY",
    ) -> tuple[MacroAvailabilityStatus, Optional[float]]:
        """
        Given a series' vintage list, return (availability_status, staleness_seconds).
        """
        if staleness_limit_seconds is None:
            staleness_limit_seconds = self.DEFAULT_STALENESS_LIMIT_SECONDS

        snapshot_time_utc = _ensure_utc(snapshot_time_utc)

        eligible = []
        for v in vintages:
            t = v.available_at_utc or v.official_published_at_utc or v.published_at_utc
            if t is None:
                continue
            t = _ensure_utc(t)
            if t <= snapshot_time_utc:
                if resolution == "INTRADAY" and v.timestamp_certainty in (
                    TimestampCertainty.DATE_ONLY,
                    TimestampCertainty.TIME_UNCERTAIN,
                    TimestampCertainty.UNKNOWN,
                ):
                    continue
                eligible.append((t, v))

        if not eligible:
            return MacroAvailabilityStatus.NOT_YET_RELEASED, None

        latest_time, latest_vintage = max(eligible, key=lambda pair: pair[0])
        staleness = (snapshot_time_utc - latest_time).total_seconds()

        if staleness > staleness_limit_seconds:
            return MacroAvailabilityStatus.STALE, staleness

        return MacroAvailabilityStatus.AVAILABLE, staleness

    def check_event_availability(
        self,
        actual_release_utc: Optional[datetime],
        snapshot_time_utc: datetime,
    ) -> MacroAvailabilityStatus:
        """
        Check whether a macro event release is causally available at snapshot_time_utc.
        """
        if actual_release_utc is None:
            return MacroAvailabilityStatus.NOT_YET_RELEASED

        snapshot_time_utc = _ensure_utc(snapshot_time_utc)
        actual_release_utc = _ensure_utc(actual_release_utc)

        if actual_release_utc <= snapshot_time_utc:
            return MacroAvailabilityStatus.AVAILABLE
        return MacroAvailabilityStatus.NOT_YET_RELEASED

    def is_causal_violation(
        self,
        published_at_utc: Optional[datetime],
        snapshot_time_utc: datetime,
    ) -> bool:
        """
        Return True if using this observation at snapshot_time would constitute
        a causal (look-ahead) violation.
        """
        if published_at_utc is None:
            return False
        return _ensure_utc(published_at_utc) > _ensure_utc(snapshot_time_utc)

    def validate_live_availability(
        self,
        available_at_utc: datetime,
        first_seen_at_utc: Optional[datetime],
        basis: AvailabilityBasis,
        certainty: TimestampCertainty,
        has_verified_provenance: bool = False,
    ) -> bool:
        """
        In live ingestion, available_at_utc must not precede first_seen_at_utc
        unless exact official publication timestamp is supported by verified provenance.
        """
        available_at_utc = _ensure_utc(available_at_utc)
        if first_seen_at_utc is None:
            return True
        first_seen_at_utc = _ensure_utc(first_seen_at_utc)

        if available_at_utc < first_seen_at_utc:
            if basis == AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME and certainty == TimestampCertainty.EXACT and has_verified_provenance:
                return True
            return False
        return True

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
    """Return a timezone-aware UTC datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Point-in-time Query API (§13)
# ---------------------------------------------------------------------------


def event_view_as_of(event: MacroEvent, snapshot_time: datetime) -> MacroEventView:
    """
    Return point-in-time view of an event as of snapshot_time.

    Distinguishes:
    - NOT_YET_KNOWN: schedule itself was unknown at snapshot_time.
    - RELEASED: release has occurred and actual value is available.
    - SCHEDULED_NOT_RELEASED: schedule known, release has not occurred.
    - TIMESTAMP_UNCERTAIN: release timing certainty is ambiguous.
    """
    snap_t = _ensure_utc(snapshot_time)

    # Check if schedule was known
    if event.schedule_known_at_utc is not None:
        if _ensure_utc(event.schedule_known_at_utc) > snap_t:
            return MacroEventView(
                event_id=event.event_id,
                event_family=event.event_family,
                event_name=event.event_name,
                reference_period=event.reference_period,
                status=EventReleaseStatus.NOT_YET_KNOWN,
                scheduled_at_utc=None,
                available_at_utc=None,
                actual_value=None,
                consensus_value=None,
                unit=event.unit,
                timestamp_certainty=TimestampCertainty.UNKNOWN,
                availability_basis=AvailabilityBasis.UNKNOWN,
                data_quality=MacroDataQuality.MISSING,
            )

    avail_t = event.available_at_utc or event.official_published_at_utc or event.actual_release_utc
    if avail_t is not None and _ensure_utc(avail_t) <= snap_t and event.actual_value is not None:
        return MacroEventView(
            event_id=event.event_id,
            event_family=event.event_family,
            event_name=event.event_name,
            reference_period=event.reference_period,
            status=EventReleaseStatus.RELEASED,
            scheduled_at_utc=event.scheduled_at_utc,
            available_at_utc=avail_t,
            actual_value=event.actual_value,
            consensus_value=event.consensus_value,
            unit=event.unit,
            timestamp_certainty=event.timestamp_certainty,
            availability_basis=event.availability_basis,
            data_quality=event.data_quality_status,
        )

    # If scheduled in future or unreleased:
    sched_t = event.scheduled_at_utc or event.scheduled_release_utc
    return MacroEventView(
        event_id=event.event_id,
        event_family=event.event_family,
        event_name=event.event_name,
        reference_period=event.reference_period,
        status=EventReleaseStatus.SCHEDULED_NOT_RELEASED,
        scheduled_at_utc=sched_t,
        available_at_utc=None,
        actual_value=None,
        consensus_value=event.consensus_value,
        unit=event.unit,
        timestamp_certainty=event.timestamp_certainty,
        availability_basis=event.availability_basis,
        data_quality=MacroDataQuality.GOOD,
    )


def series_value_as_of(
    series: MacroSeriesObservation,
    snapshot_time: datetime,
    resolution: str = "INTRADAY",
) -> Optional[float]:
    """
    Return point-in-time value of a series as of snapshot_time.

    If resolution == "INTRADAY":
        DATE_ONLY, TIME_UNCERTAIN, and UNKNOWN observations are BLOCKED.
        Returns None.
    If resolution == "DAILY":
        DATE_ONLY observations are permitted.
    """
    snap_t = _ensure_utc(snapshot_time)
    eligible = []
    for v in series.vintages:
        t = v.available_at_utc or v.official_published_at_utc or v.published_at_utc
        if t is None:
            continue
        t = _ensure_utc(t)
        if t <= snap_t:
            if resolution == "INTRADAY" and v.timestamp_certainty in (
                TimestampCertainty.DATE_ONLY,
                TimestampCertainty.TIME_UNCERTAIN,
                TimestampCertainty.UNKNOWN,
            ):
                continue
            eligible.append((t, v))

    if not eligible:
        return None
    return max(eligible, key=lambda pair: pair[0])[1].value


def news_view_as_of(item: MacroNewsItem, snapshot_time: datetime) -> MacroNewsView:
    """
    Return point-in-time view of a news item as of snapshot_time.
    """
    snap_t = _ensure_utc(snapshot_time)
    avail_t = item.available_at_utc or item.official_published_at_utc or item.published_at_utc
    if avail_t is not None and _ensure_utc(avail_t) <= snap_t:
        return MacroNewsView(
            item_id=item.item_id,
            source=item.source,
            item_type=item.item_type,
            headline=item.headline,
            status=EventReleaseStatus.RELEASED,
            available_at_utc=avail_t,
            url=item.url,
            data_quality=item.quality,
        )
    return MacroNewsView(
        item_id=item.item_id,
        source=item.source,
        item_type=item.item_type,
        headline=item.headline,
        status=EventReleaseStatus.NOT_AVAILABLE,
        available_at_utc=None,
        url=item.url,
        data_quality=MacroDataQuality.MISSING,
    )


def upcoming_events_as_of(
    events: Sequence[MacroEvent],
    snapshot_time: datetime,
) -> list[MacroEvent]:
    """
    Return causal upcoming scheduled events as of snapshot_time.

    Rules:
    1. Schedule must be known at or before snapshot_time.
    2. Scheduled time must be after snapshot_time.
    3. Actual value must be None (not yet released).
    """
    snap_t = _ensure_utc(snapshot_time)
    upcoming = []
    for event in events:
        if event.schedule_known_at_utc is not None:
            if _ensure_utc(event.schedule_known_at_utc) > snap_t:
                continue

        sched_t = event.scheduled_at_utc or event.scheduled_release_utc
        if sched_t is None:
            continue
        if _ensure_utc(sched_t) <= snap_t:
            continue

        # Must not have actual value released prior to snapshot
        avail_t = event.available_at_utc or event.official_published_at_utc or event.actual_release_utc
        if avail_t is not None and _ensure_utc(avail_t) <= snap_t and event.actual_value is not None:
            continue

        # Build clean upcoming event representation with actual_value=None
        if event.actual_value is not None:
            # Mask actual value
            event_cleaned = MacroEvent(
                event_id=event.event_id,
                event_family=event.event_family,
                event_name=event.event_name,
                reference_period=event.reference_period,
                source_id=event.source_id,
                source_type=event.source_type,
                source_reference=event.source_reference,
                source_hash=event.source_hash,
                scheduled_at_utc=sched_t,
                schedule_known_at_utc=event.schedule_known_at_utc,
                official_published_at_utc=None,
                first_seen_at_utc=None,
                available_at_utc=None,
                actual_value=None,
                previous_value=event.previous_value,
                revised_previous_value=event.revised_previous_value,
                consensus_value=event.consensus_value,
                consensus_status=event.consensus_status,
                unit=event.unit,
                timestamp_certainty=event.timestamp_certainty,
                availability_basis=event.availability_basis,
                data_quality_status=event.data_quality_status,
            )
            upcoming.append(event_cleaned)
        else:
            upcoming.append(event)

    return sorted(
        upcoming,
        key=lambda e: _ensure_utc(e.scheduled_at_utc or e.scheduled_release_utc),
    )
