"""
NEWS/MACRO-1A R1: Causal Point-in-Time Macro & Official-News Intelligence Layer.

This package provides the macro intelligence foundation for Trading OS.
It does NOT provide trading signals, entries, stops, targets, position
sizing, leverage, or profitability optimization.

TRADING_CAPABILITY = ZERO
"""
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
    MacroSourceConflict,
    MacroSurprise,
    MacroVintage,
    TimestampCertainty,
)
from btceth_os.macro.snapshot import MacroIntelligenceSnapshot
from btceth_os.macro.availability import (
    PointInTimeAvailabilityChecker,
    event_view_as_of,
    news_view_as_of,
    series_value_as_of,
    upcoming_events_as_of,
)
from btceth_os.macro.event_registry import MACRO_EVENT_REGISTRY, MacroEventFamily

from btceth_os.macro.status import aggregate_macro_status

__all__ = [
    "MacroEvent",
    "MacroSeriesObservation",
    "MacroNewsItem",
    "MacroDataQuality",
    "MacroAvailabilityStatus",
    "MacroIntelligenceSnapshot",
    "PointInTimeAvailabilityChecker",
    "MACRO_EVENT_REGISTRY",
    "MacroEventFamily",
    "TimestampCertainty",
    "AvailabilityBasis",
    "EventReleaseStatus",
    "MacroSourceConflict",
    "MacroVintage",
    "MacroSurprise",
    "MacroEventView",
    "MacroNewsView",
    "event_view_as_of",
    "news_view_as_of",
    "series_value_as_of",
    "upcoming_events_as_of",
    "aggregate_macro_status",
]
