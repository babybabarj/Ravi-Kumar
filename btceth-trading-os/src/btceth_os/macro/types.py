"""
NEWS/MACRO-1A: Core dataclass types.

All data classes are immutable (frozen=True).

TRADING_CAPABILITY = ZERO — these types describe macro observations only.
They must NOT contain entry/exit signals, position sizes, or trade instructions.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class MacroDataQuality(str, enum.Enum):
    """
    Fail-closed quality states for macro data.

    GOOD              — observation is causal and complete.
    STALE             — observation is available but outside recency window.
    MISSING           — no observation available for this period.
    VINTAGE_AMBIGUOUS — multiple revisions exist; exact revision unknown for t.
    NOT_CONFIGURED    — provider credentials or configuration are absent.
    NOT_IMPLEMENTED   — provider integration not yet built.
    PROVIDER_REQUIRED — data type exists but no authorised provider is configured.
    CAUSAL_VIOLATION  — observation published_at_utc > snapshot_time_utc (blocked).
    """

    GOOD = "GOOD"
    STALE = "STALE"
    MISSING = "MISSING"
    VINTAGE_AMBIGUOUS = "VINTAGE_AMBIGUOUS"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    PROVIDER_REQUIRED = "PROVIDER_REQUIRED"
    CAUSAL_VIOLATION = "CAUSAL_VIOLATION"


class MacroAvailabilityStatus(str, enum.Enum):
    """
    Point-in-time availability verdict for a macro observation.

    AVAILABLE              — the observation is causally available at snapshot_time.
    NOT_YET_RELEASED       — the observation's published_at_utc is after snapshot_time.
    PROVIDER_NOT_CONFIGURED — no provider credentials; data could not be fetched.
    PROVIDER_NOT_IMPLEMENTED — integration not yet built for this data family.
    STALE                  — the observation is available but older than the recency limit.
    """

    AVAILABLE = "AVAILABLE"
    NOT_YET_RELEASED = "NOT_YET_RELEASED"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_NOT_IMPLEMENTED = "PROVIDER_NOT_IMPLEMENTED"
    STALE = "STALE"


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MacroEvent:
    """
    A single official macro data release or scheduled event.

    Parameters
    ----------
    event_id:
        Unique identifier, e.g. "CPI_US_MONTHLY_2026_09".
    family:
        Logical grouping, e.g. "CPI", "NFP", "FOMC".
    description:
        Human-readable label.
    reference_period:
        The period the data describes (ISO 8601 date string, e.g. "2026-09").
    scheduled_release_utc:
        The time the release was scheduled in advance (if known).
    actual_release_utc:
        The time the release actually became public.
    actual_value:
        The headline value as officially reported.
    prior_value:
        The previously reported value for the preceding period.
    consensus_value:
        Analyst consensus estimate.  MUST be None if no authorised provider
        supplies it — do not scrape, infer, or backfill.
    consensus_status:
        Describes the consensus availability. "NOT_AVAILABLE" if no authorised
        provider is configured.
    unit:
        Unit string, e.g. "percent_yoy", "thousands_jobs", "index_points".
    source_agency:
        Official releasing agency, e.g. "BLS", "BEA", "FOMC".
    """

    event_id: str
    family: str
    description: str
    reference_period: str
    actual_release_utc: datetime
    actual_value: Optional[float]
    prior_value: Optional[float]
    unit: str
    source_agency: str
    scheduled_release_utc: Optional[datetime] = None
    consensus_value: Optional[float] = None
    consensus_status: str = "NOT_AVAILABLE"

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("MacroEvent.event_id must not be empty.")
        if not self.family:
            raise ValueError("MacroEvent.family must not be empty.")
        if not self.source_agency:
            raise ValueError("MacroEvent.source_agency must not be empty.")


@dataclass(frozen=True)
class MacroVintage:
    """
    A single revision of a macro series value.

    Parameters
    ----------
    published_at_utc:
        The UTC datetime at which this vintage became publicly available.
    value:
        The numeric value as published in this vintage.
    vintage_label:
        Optional human-readable label, e.g. "initial", "first_revision".
    """

    published_at_utc: datetime
    value: float
    vintage_label: Optional[str] = None


@dataclass(frozen=True)
class MacroSeriesObservation:
    """
    A point-in-time observation of a macro data series with vintage history.

    Vintage model: append-only list of (published_at_utc, value) pairs.
    Query: max(v for v in vintages if v.published_at_utc <= snapshot_time_utc).
    Never overwrite vintages; always append new revisions.

    Parameters
    ----------
    series_id:
        Unique series identifier, e.g. "US_CPI_YOY", "US_10Y_TREASURY_YIELD".
    family:
        Logical family grouping, e.g. "CPI", "TREASURY".
    reference_period:
        The period the data covers (ISO 8601 date string).
    vintages:
        Chronological list of published vintages.  Must be non-empty if quality
        is GOOD.  Must be append-only; never mutate existing entries.
    quality:
        Data quality state at the time of snapshot construction.
    availability_status:
        Point-in-time availability verdict.
    unit:
        Unit of the value, e.g. "percent_yoy", "percent_annualized".
    source_agency:
        Official releasing agency.
    staleness_seconds:
        Age of the most recently available vintage at snapshot_time, in seconds.
        None if no vintage is available.
    """

    series_id: str
    family: str
    reference_period: str
    vintages: tuple[MacroVintage, ...]
    quality: MacroDataQuality
    availability_status: MacroAvailabilityStatus
    unit: str
    source_agency: str
    staleness_seconds: Optional[float] = None

    def latest_value_at(self, snapshot_time_utc: datetime) -> Optional[float]:
        """
        Return the latest value causally available at snapshot_time_utc.

        Returns None if no vintage is available at or before snapshot_time_utc.
        """
        eligible = [v for v in self.vintages if v.published_at_utc <= snapshot_time_utc]
        if not eligible:
            return None
        return max(eligible, key=lambda v: v.published_at_utc).value

    def __post_init__(self) -> None:
        if not self.series_id:
            raise ValueError("MacroSeriesObservation.series_id must not be empty.")


@dataclass(frozen=True)
class MacroNewsItem:
    """
    A single official news item or policy communication.

    IMPORTANT: This type does NOT carry hawkish/dovish NLP scores, sentiment
    ratings, or LLM-generated interpretations.  NEWS/MACRO-1A is strictly
    a data foundation phase.

    Parameters
    ----------
    item_id:
        Unique item identifier.
    source:
        Originating body, e.g. "FEDERAL_RESERVE", "US_TREASURY".
    item_type:
        Classification, e.g. "FOMC_STATEMENT", "FED_SPEECH", "PRESS_RELEASE".
    published_at_utc:
        UTC datetime when the item was publicly released.
    headline:
        Official headline or short title.
    url:
        Canonical source URL if known; None otherwise.
    quality:
        Data quality state.
    availability_status:
        Point-in-time availability verdict.
    """

    item_id: str
    source: str
    item_type: str
    published_at_utc: datetime
    headline: str
    quality: MacroDataQuality
    availability_status: MacroAvailabilityStatus
    url: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("MacroNewsItem.item_id must not be empty.")
        if not self.headline:
            raise ValueError("MacroNewsItem.headline must not be empty.")


@dataclass(frozen=True)
class MacroSurprise:
    """
    Computed surprise for a macro release.

    MUST only be created when BOTH actual and consensus values are legitimately
    available from authorised providers.  Do NOT infer consensus from prior
    values or economic calendars of unknown provenance.

    Parameters
    ----------
    event_id:
        References MacroEvent.event_id.
    actual_value:
        The officially released value.
    consensus_value:
        The authorised consensus estimate.
    surprise_magnitude:
        actual_value - consensus_value (in the unit of the series).
    surprise_direction:
        "BEAT", "MISS", or "IN_LINE" (within tolerance).
    in_line_tolerance:
        The absolute tolerance used for IN_LINE classification.
    """

    event_id: str
    actual_value: float
    consensus_value: float
    surprise_magnitude: float
    surprise_direction: str
    in_line_tolerance: float

    def __post_init__(self) -> None:
        allowed = {"BEAT", "MISS", "IN_LINE"}
        if self.surprise_direction not in allowed:
            raise ValueError(
                f"surprise_direction must be one of {allowed}; "
                f"got {self.surprise_direction!r}."
            )
        expected = round(self.actual_value - self.consensus_value, 10)
        if abs(expected - self.surprise_magnitude) > 1e-8:
            raise ValueError(
                "surprise_magnitude must equal actual_value - consensus_value."
            )
