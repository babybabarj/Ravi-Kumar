"""
NEWS/MACRO-1A: MacroIntelligenceSnapshot.

A frozen, point-in-time container for all macro context available at
snapshot_time_utc.

TRADING_CAPABILITY = ZERO — this snapshot contains observational context
only.  It must NOT contain trading signals, entry/exit directives, position
sizes, stop-loss levels, or leverage recommendations.  The __post_init__
firewall enforces this.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from btceth_os.macro.types import (
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroEvent,
    MacroNewsItem,
    MacroSeriesObservation,
    MacroSurprise,
)
from btceth_os.macro.data_quality import aggregate_quality


# ---------------------------------------------------------------------------
# Execution field firewall
# ---------------------------------------------------------------------------

_FORBIDDEN_FIELD_PATTERNS: list[re.Pattern] = [
    re.compile(r"\blong\b", re.IGNORECASE),
    re.compile(r"\bshort\b", re.IGNORECASE),
    re.compile(r"\bbuy\b", re.IGNORECASE),
    re.compile(r"\bsell\b", re.IGNORECASE),
    re.compile(r"\bentry\b", re.IGNORECASE),
    re.compile(r"\bstop.?loss\b", re.IGNORECASE),
    re.compile(r"\btake.?profit\b", re.IGNORECASE),
    re.compile(r"\bposition.?size\b", re.IGNORECASE),
    re.compile(r"\bleverage\b", re.IGNORECASE),
    re.compile(r"\btrade.?signal\b", re.IGNORECASE),
    re.compile(r"\bexecution\b", re.IGNORECASE),
    re.compile(r"\border\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class MacroIntelligenceSnapshot:
    """
    Frozen point-in-time macro intelligence snapshot.

    Parameters
    ----------
    snapshot_time_utc:
        The exact UTC time at which this snapshot was constructed.
    snapshot_id:
        Unique identifier for this snapshot.
    trading_capability:
        MUST be 0. Firewall raises ValueError if any other value is supplied.
    macro_events:
        Tuple of MacroEvent instances visible at snapshot_time_utc.
        Can include upcoming scheduled events (with actual_value=None)
        and causally released events.
    series_observations:
        Tuple of MacroSeriesObservation instances, each with vintage history.
    news_items:
        Tuple of MacroNewsItem instances that are causally available.
    surprises:
        Tuple of MacroSurprise instances (only populated when both actual
        and consensus are legitimately available from authorised providers).
    overall_data_quality:
        Aggregate quality across all observations (fail-closed).
    dxy_status:
        Explicit status for DXY availability.
    breaking_news_status:
        Explicit status for breaking news availability.
    alfred_runtime_status:
        ALFRED runtime status.
    limitations:
        List of capability limitations active for this snapshot.
    """

    snapshot_time_utc: datetime
    snapshot_id: str
    trading_capability: int

    macro_events: tuple[MacroEvent, ...] = field(default_factory=tuple)
    series_observations: tuple[MacroSeriesObservation, ...] = field(default_factory=tuple)
    news_items: tuple[MacroNewsItem, ...] = field(default_factory=tuple)
    surprises: tuple[MacroSurprise, ...] = field(default_factory=tuple)

    overall_data_quality: MacroDataQuality = MacroDataQuality.MISSING
    dxy_status: str = "NOT_IMPLEMENTED_PROVIDER_REQUIRED"
    breaking_news_status: str = "NOT_IMPLEMENTED_PROVIDER_REQUIRED"
    alfred_runtime_status: str = "NOT_CONFIGURED"

    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # --- Execution firewall ---
        if self.trading_capability != 0:
            raise ValueError(
                "MacroIntelligenceSnapshot: trading_capability MUST be 0. "
                f"Got {self.trading_capability!r}. "
                "This snapshot is a context-only object. "
                "Trading decisions are not authorized at this phase."
            )

        # --- Snapshot ID must not be empty ---
        if not self.snapshot_id:
            raise ValueError("MacroIntelligenceSnapshot.snapshot_id must not be empty.")

        # --- Causal contract enforcement ---
        from btceth_os.macro.availability import _ensure_utc

        snap_t = _ensure_utc(self.snapshot_time_utc)

        for event in self.macro_events:
            # 1. Schedule knowledge causality
            if event.schedule_known_at_utc is not None:
                sched_known = _ensure_utc(event.schedule_known_at_utc)
                if sched_known > snap_t:
                    raise ValueError(
                        f"Causal violation: MacroEvent {event.event_id!r} schedule was not known "
                        f"until {event.schedule_known_at_utc.isoformat()} which is after "
                        f"snapshot_time_utc={self.snapshot_time_utc.isoformat()}."
                    )

            # 2. Actual value release causality
            if event.actual_value is not None:
                avail_t = event.available_at_utc or event.official_published_at_utc or event.actual_release_utc
                if avail_t is None:
                    raise ValueError(
                        f"Causal violation: MacroEvent {event.event_id!r} has actual_value={event.actual_value} "
                        f"without an availability timestamp."
                    )
                avail_t = _ensure_utc(avail_t)
                if avail_t > snap_t:
                    raise ValueError(
                        f"Causal violation: MacroEvent {event.event_id!r} has actual_value={event.actual_value} "
                        f"with release time={avail_t.isoformat()} which is after "
                        f"snapshot_time_utc={self.snapshot_time_utc.isoformat()}."
                    )

        for item in self.news_items:
            pub_t = item.available_at_utc or item.official_published_at_utc or item.published_at_utc
            if pub_t is not None:
                pub_t = _ensure_utc(pub_t)
                if pub_t > snap_t:
                    raise ValueError(
                        f"Causal violation: MacroNewsItem {item.item_id!r} has "
                        f"published_at_utc={pub_t.isoformat()} "
                        f"which is after snapshot_time_utc={self.snapshot_time_utc.isoformat()}."
                    )

    def compute_overall_quality(self) -> MacroDataQuality:
        """
        Recompute aggregate quality from all contained observations.
        Returns MISSING if no observations are present.
        """
        qualities = [obs.quality for obs in self.series_observations]
        qualities += [
            MacroDataQuality.GOOD if event.actual_value is not None or event.scheduled_at_utc is not None
            else MacroDataQuality.MISSING
            for event in self.macro_events
        ]
        return aggregate_quality([q for q in qualities if isinstance(q, MacroDataQuality)])

    @property
    def has_good_series(self) -> bool:
        """Return True if at least one series observation has GOOD quality."""
        return any(
            obs.quality == MacroDataQuality.GOOD
            for obs in self.series_observations
        )

    @property
    def causal_violation_count(self) -> int:
        """Return the number of observations with CAUSAL_VIOLATION quality."""
        return sum(
            1 for obs in self.series_observations
            if obs.quality == MacroDataQuality.CAUSAL_VIOLATION
        )

    @property
    def upcoming_events(self) -> list[MacroEvent]:
        """Return scheduled events occurring after snapshot_time_utc."""
        from btceth_os.macro.availability import upcoming_events_as_of
        return upcoming_events_as_of(self.macro_events, self.snapshot_time_utc)
