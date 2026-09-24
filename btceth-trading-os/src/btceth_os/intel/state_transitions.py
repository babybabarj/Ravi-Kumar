"""Layer F: State Transition Engine for INTEL-1B.

Tracks and analyzes temporal state dynamics across intelligence dimensions:
- Formal transition records capturing (asset, dimension, from_state, to_state, duration, quality)
- Duration distributions (mean, median, p10, p90)
- Rapid reversals / flip rate (e.g. flipping back to previous state within <= 3 bars)
- Persistence and stability statistics
- Unknown and degraded quality frequency

Strict non-profitability invariant:
Contains zero expected return, trade direction, entries, or strategy heuristics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, List, Optional, Sequence

from .market_state import MarketStateSnapshot


@dataclass(frozen=True)
class StateTransitionRecord:
    """Formal audit record of an observed state change."""

    asset: str
    dimension: str
    from_state: str
    to_state: str
    transition_timestamp_ns: int
    previous_state_duration_bars: int
    data_quality: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DimensionTransitionMetrics:
    """Descriptive stability and transition metrics for a single regime dimension."""

    asset: str
    dimension: str
    total_bars: int
    state_counts: Dict[str, int]
    transition_count: int
    transitions: List[StateTransitionRecord]
    durations_by_state: Dict[str, List[int]]
    mean_duration_by_state: Dict[str, float]
    median_duration_by_state: Dict[str, float]
    p10_duration_by_state: Dict[str, float]
    p90_duration_by_state: Dict[str, float]
    reversal_count: int
    rapid_flip_rate: float
    unknown_fraction: float
    degraded_fraction: float
    persistence_probability: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["transitions"] = [t.to_dict() for t in self.transitions]
        return d


class StateTransitionEngine:
    """Calculates temporal transition and stability properties for market regime sequences."""

    @staticmethod
    def _percentile(values: List[int], p: float) -> float:
        if not values:
            return 0.0
        sorted_v = sorted(values)
        idx = (len(sorted_v) - 1) * p
        lower = int(math.floor(idx))
        upper = int(math.ceil(idx))
        if lower == upper:
            return float(sorted_v[lower])
        weight = idx - lower
        return float(sorted_v[lower] * (1.0 - weight) + sorted_v[upper] * weight)

    @classmethod
    def track_dimension(
        cls,
        asset: str,
        dimension: str,
        states: Sequence[str],
        timestamps_ns: Sequence[int],
        data_qualities: Optional[Sequence[str]] = None,
        flip_window: int = 3,
    ) -> DimensionTransitionMetrics:
        """Analyze a sequence of states for duration, stability, and rapid reversals."""
        n = len(states)
        if n == 0:
            return DimensionTransitionMetrics(
                asset=asset,
                dimension=dimension,
                total_bars=0,
                state_counts={},
                transition_count=0,
                transitions=[],
                durations_by_state={},
                mean_duration_by_state={},
                median_duration_by_state={},
                p10_duration_by_state={},
                p90_duration_by_state={},
                reversal_count=0,
                rapid_flip_rate=0.0,
                unknown_fraction=0.0,
                degraded_fraction=0.0,
                persistence_probability=0.0,
            )

        qualities = data_qualities if data_qualities is not None else ["GOOD"] * n
        state_counts: Dict[str, int] = {}
        durations_by_state: Dict[str, List[int]] = {}
        transitions: List[StateTransitionRecord] = []

        current_state = states[0]
        current_duration = 1
        state_counts[current_state] = 1

        reversal_count = 0
        state_history: List[tuple[str, int]] = []  # (state, duration)

        same_state_transitions = 0

        for i in range(1, n):
            s = states[i]
            ts = timestamps_ns[i]
            q = qualities[i]
            state_counts[s] = state_counts.get(s, 0) + 1

            if s == current_state:
                current_duration += 1
                same_state_transitions += 1
            else:
                # Transition observed
                durations_by_state.setdefault(current_state, []).append(current_duration)
                transitions.append(
                    StateTransitionRecord(
                        asset=asset,
                        dimension=dimension,
                        from_state=current_state,
                        to_state=s,
                        transition_timestamp_ns=ts,
                        previous_state_duration_bars=current_duration,
                        data_quality=q,
                    )
                )
                state_history.append((current_state, current_duration))

                # Rapid reversal check: if s equals state from 2 changes ago and intermediate duration <= flip_window
                if len(state_history) >= 2:
                    prev_state, prev_duration = state_history[-2]
                    if s == prev_state and current_duration <= flip_window:
                        reversal_count += 1

                current_state = s
                current_duration = 1

        # Append final running duration
        durations_by_state.setdefault(current_state, []).append(current_duration)

        # Descriptive duration distributions
        mean_dur: Dict[str, float] = {}
        median_dur: Dict[str, float] = {}
        p10_dur: Dict[str, float] = {}
        p90_dur: Dict[str, float] = {}

        for st, durs in durations_by_state.items():
            mean_dur[st] = float(sum(durs) / len(durs)) if durs else 0.0
            median_dur[st] = cls._percentile(durs, 0.5)
            p10_dur[st] = cls._percentile(durs, 0.1)
            p90_dur[st] = cls._percentile(durs, 0.9)

        total_transitions = len(transitions)
        rapid_flip_rate = float(reversal_count / total_transitions) if total_transitions > 0 else 0.0
        persistence_prob = float(same_state_transitions / (n - 1)) if n > 1 else 1.0

        # Unknown and degraded fraction
        unknown_states = {"UNKNOWN", "UNCERTAIN"}
        unknown_count = sum(cnt for st, cnt in state_counts.items() if st in unknown_states)
        unknown_fraction = float(unknown_count / n)

        degraded_count = sum(1 for q in qualities if q in ("DEGRADED", "UNRELIABLE"))
        degraded_fraction = float(degraded_count / n)

        return DimensionTransitionMetrics(
            asset=asset,
            dimension=dimension,
            total_bars=n,
            state_counts=state_counts,
            transition_count=total_transitions,
            transitions=transitions,
            durations_by_state=durations_by_state,
            mean_duration_by_state=mean_dur,
            median_duration_by_state=median_dur,
            p10_duration_by_state=p10_dur,
            p90_duration_by_state=p90_dur,
            reversal_count=reversal_count,
            rapid_flip_rate=rapid_flip_rate,
            unknown_fraction=unknown_fraction,
            degraded_fraction=degraded_fraction,
            persistence_probability=persistence_prob,
        )

    @classmethod
    def track_snapshots(
        cls,
        asset: str,
        snapshots: Sequence[MarketStateSnapshot],
        timestamps_ns: Sequence[int],
        data_qualities: Optional[Sequence[str]] = None,
        flip_window: int = 3,
    ) -> Dict[str, DimensionTransitionMetrics]:
        """Track transitions across all 5 standard dimensions of MarketStateSnapshot."""
        trends = [s.trend_state for s in snapshots]
        vols = [s.volatility_state for s in snapshots]
        acts = [s.activity_state for s in snapshots]
        funds = [s.funding_state for s in snapshots]
        mqs = [s.market_quality_state for s in snapshots]

        return {
            "TREND": cls.track_dimension(asset, "TREND", trends, timestamps_ns, data_qualities, flip_window),
            "VOLATILITY": cls.track_dimension(asset, "VOLATILITY", vols, timestamps_ns, data_qualities, flip_window),
            "LIQUIDITY_ACTIVITY": cls.track_dimension(asset, "LIQUIDITY_ACTIVITY", acts, timestamps_ns, data_qualities, flip_window),
            "FUNDING": cls.track_dimension(asset, "FUNDING", funds, timestamps_ns, data_qualities, flip_window),
            "MARKET_QUALITY": cls.track_dimension(asset, "MARKET_QUALITY", mqs, timestamps_ns, data_qualities, flip_window),
        }
