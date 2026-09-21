from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional, Sequence


class TemporalIntegrityViolationError(RuntimeError):
    """Raised when temporal causality or clock hierarchy is violated."""
    pass


class SettlementBoundaryStatus(str, Enum):
    HELD_THROUGH = "HELD_THROUGH"
    NOT_HELD = "NOT_HELD"
    AMBIGUOUS_SETTLEMENT_BOUNDARY = "AMBIGUOUS_SETTLEMENT_BOUNDARY"


@dataclass(frozen=True)
class TemporalEventContract:
    source_ts_ns: int
    available_ts_ns: int
    decision_ts_ns: int
    execution_ts_ns: int
    fill_ts_ns: int

    def validate(self) -> None:
        """Enforce the strict temporal invariant:

        source_ts <= available_ts <= decision_ts <= execution_ts <= fill_ts
        """
        if not (self.source_ts_ns <= self.available_ts_ns):
            raise TemporalIntegrityViolationError(
                f"Clock hierarchy violated: source_ts ({self.source_ts_ns}) > available_ts ({self.available_ts_ns})"
            )
        if not (self.available_ts_ns <= self.decision_ts_ns):
            raise TemporalIntegrityViolationError(
                f"TEMPORAL_LEAKAGE_DETECTED: available_ts ({self.available_ts_ns}) > decision_ts ({self.decision_ts_ns})"
            )
        if not (self.decision_ts_ns <= self.execution_ts_ns):
            raise TemporalIntegrityViolationError(
                f"Causality violated: decision_ts ({self.decision_ts_ns}) > execution_ts ({self.execution_ts_ns})"
            )
        if not (self.execution_ts_ns <= self.fill_ts_ns):
            raise TemporalIntegrityViolationError(
                f"Execution causality violated: execution_ts ({self.execution_ts_ns}) > fill_ts ({self.fill_ts_ns})"
            )


def classify_funding_settlement_boundary(
    entry_fill_ts_ns: int,
    exit_fill_ts_ns: int,
    settlement_ts_ns: int,
) -> SettlementBoundaryStatus:
    """Conservative unambiguous funding settlement boundary rule.

    Conservative rule:
    - Held through settlement: entry_fill_ts < settlement_ts < exit_fill_ts
    - Not held: exit_fill_ts < settlement_ts OR entry_fill_ts > settlement_ts
    - Ambiguous: entry_fill_ts == settlement_ts OR exit_fill_ts == settlement_ts
    """
    if entry_fill_ts_ns == settlement_ts_ns or exit_fill_ts_ns == settlement_ts_ns:
        return SettlementBoundaryStatus.AMBIGUOUS_SETTLEMENT_BOUNDARY

    if entry_fill_ts_ns < settlement_ts_ns < exit_fill_ts_ns:
        return SettlementBoundaryStatus.HELD_THROUGH

    return SettlementBoundaryStatus.NOT_HELD


def compute_causal_rolling_mean(series: Sequence[float], window: int) -> list[Optional[float]]:
    """Compute strictly causal rolling mean up to index i (uses only [i-window+1 : i+1])."""
    res: list[Optional[float]] = []
    for i in range(len(series)):
        if i + 1 < window:
            res.append(None)
        else:
            w_vals = series[i - window + 1 : i + 1]
            res.append(sum(w_vals) / float(window))
    return res


def compute_causal_rolling_basis_bps(
    spot_series: Sequence[float],
    perp_series: Sequence[float],
) -> list[float]:
    """Compute strictly point-in-time basis in bps = ((perp - spot) / spot) * 10000."""
    assert len(spot_series) == len(perp_series)
    return [
        ((p - s) / s) * 10000.0
        for s, p in zip(spot_series, perp_series)
    ]
