"""
NEWS/MACRO-1A: Causal Point-in-Time Macro & Official-News Intelligence Layer.

This package provides the macro intelligence foundation for Trading OS.
It does NOT provide trading signals, entries, stops, targets, position
sizing, leverage, or profitability optimization.

TRADING_CAPABILITY = ZERO
"""
from btceth_os.macro.types import (
    MacroEvent,
    MacroSeriesObservation,
    MacroNewsItem,
    MacroDataQuality,
    MacroAvailabilityStatus,
)
from btceth_os.macro.snapshot import MacroIntelligenceSnapshot
from btceth_os.macro.availability import PointInTimeAvailabilityChecker
from btceth_os.macro.event_registry import MACRO_EVENT_REGISTRY, MacroEventFamily

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
]
