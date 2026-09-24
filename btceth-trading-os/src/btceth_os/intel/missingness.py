"""Layer D: Missingness Semantics for INTEL-1B.

Explicitly preserves why a feature, state, or metric cannot be evaluated,
preventing silent collapsing into None, NaN, or 0.

Supported deterministic missingness reasons:
- NOT_ENOUGH_HISTORY: Lookback window extends before available observation start.
- SOURCE_UNAVAILABLE: Upstream source stream (e.g. index price or funding) not published.
- DATA_GAP: Discontinuity or missing bar interval detected.
- HOLIDAY_UNKNOWN: TradFi holiday / session calendar uncertainty.
- SESSION_UNKNOWN: Contract session state unproven or unclassified.
- NOT_APPLICABLE: Feature does not apply to this instrument class.
- CALCULATION_UNDEFINED: Mathematical singularity (e.g. zero variance in denominator).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class MissingReason(str, Enum):
    NOT_ENOUGH_HISTORY = "NOT_ENOUGH_HISTORY"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    DATA_GAP = "DATA_GAP"
    HOLIDAY_UNKNOWN = "HOLIDAY_UNKNOWN"
    SESSION_UNKNOWN = "SESSION_UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CALCULATION_UNDEFINED = "CALCULATION_UNDEFINED"


@dataclass(frozen=True)
class MissingValue:
    """Explicitly wraps a missing value with its deterministic causal rationale."""

    reason: MissingReason
    details: Optional[str] = None

    @property
    def is_missing(self) -> bool:
        return True

    @property
    def is_valid(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"is_missing": True, "reason": self.reason.value}
        if self.details:
            d["details"] = self.details
        return d

    def __repr__(self) -> str:
        if self.details:
            return f"MissingValue({self.reason.value}: {self.details})"
        return f"MissingValue({self.reason.value})"


def is_missing_value(val: Any) -> bool:
    """Check if a value is an explicit MissingValue instance."""
    return isinstance(val, MissingValue)
