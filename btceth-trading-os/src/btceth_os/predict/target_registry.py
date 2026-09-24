"""Target Registry and Formal Target Contracts for PRED-1A.

Every predictive target must have a formal contract:
  - target_id
  - asset
  - definition
  - horizon
  - horizon_bars
  - label_available_at
  - minimum_history
  - future_window
  - overlap_policy
  - purge_requirement
  - embargo_requirement
  - units
  - missingness_rule
  - target_type
  - research_only

No target may exist as an undocumented inline calculation.
Targets represent future descriptive market behavior, NOT trade signals (no BUY, SELL, LONG, SHORT, ENTRY, EXIT, STOP, TARGET).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence


FORBIDDEN_EXECUTION_KEYWORDS = {
    "BUY", "SELL", "LONG", "SHORT", "ENTRY", "EXIT", "STOP",
    "TAKE_PROFIT", "POSITION_SIZE", "LEVERAGE", "ORDER", "TRADE",
    "SL", "TP", "R:R", "POSITION",
}


class InvalidTargetContractError(ValueError):
    """Raised when a target definition violates the formal research contract."""
    pass


@dataclass(frozen=True)
class TargetDefinition:
    target_id: str
    asset: str
    definition: str
    horizon: str
    horizon_bars: int
    label_available_at: str
    minimum_history: int
    future_window: int
    overlap_policy: str
    purge_requirement: int
    embargo_requirement: int
    units: str
    missingness_rule: str
    target_type: str = "continuous"  # "continuous" or "classification"
    research_only: bool = True

    def __post_init__(self) -> None:
        # Verify no execution semantics in target metadata
        for kw in FORBIDDEN_EXECUTION_KEYWORDS:
            if kw in self.target_id.upper() or kw in self.units.upper():
                raise InvalidTargetContractError(
                    f"Target metadata cannot contain execution keyword '{kw}': {self.target_id}"
                )
        if self.future_window <= 0:
            raise InvalidTargetContractError(f"future_window must be > 0: {self.future_window}")
        if self.purge_requirement < self.future_window:
            raise InvalidTargetContractError(
                f"purge_requirement ({self.purge_requirement}) cannot be less than future_window ({self.future_window})"
            )
        if not self.research_only:
            raise InvalidTargetContractError("research_only must be True in PRED-1A")


def create_standard_target_catalog(asset: str = "XAUUSDT") -> List[TargetDefinition]:
    """Instantiates the formal 12-target research catalog for PRED-1A."""
    targets = [
        # Continuous Log Returns
        TargetDefinition(
            target_id="future_log_return_5m",
            asset=asset,
            definition="Log return over forward 5-minute window: ln(close_{t+5} / close_t)",
            horizon="5m",
            horizon_bars=5,
            label_available_at="t + 5m",
            minimum_history=1,
            future_window=5,
            overlap_policy="PURGE",
            purge_requirement=5,
            embargo_requirement=5,
            units="log_return",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        TargetDefinition(
            target_id="future_log_return_15m",
            asset=asset,
            definition="Log return over forward 15-minute window: ln(close_{t+15} / close_t)",
            horizon="15m",
            horizon_bars=15,
            label_available_at="t + 15m",
            minimum_history=1,
            future_window=15,
            overlap_policy="PURGE",
            purge_requirement=15,
            embargo_requirement=15,
            units="log_return",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        TargetDefinition(
            target_id="future_log_return_1h",
            asset=asset,
            definition="Log return over forward 60-minute window: ln(close_{t+60} / close_t)",
            horizon="1h",
            horizon_bars=60,
            label_available_at="t + 1h",
            minimum_history=1,
            future_window=60,
            overlap_policy="PURGE",
            purge_requirement=60,
            embargo_requirement=60,
            units="log_return",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        TargetDefinition(
            target_id="future_log_return_4h",
            asset=asset,
            definition="Log return over forward 240-minute window: ln(close_{t+240} / close_t)",
            horizon="4h",
            horizon_bars=240,
            label_available_at="t + 4h",
            minimum_history=1,
            future_window=240,
            overlap_policy="PURGE",
            purge_requirement=240,
            embargo_requirement=60,
            units="log_return",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        # Realized Volatility
        TargetDefinition(
            target_id="future_realized_volatility_15m",
            asset=asset,
            definition="Sample standard deviation of 1-minute log returns over forward 15-minute window",
            horizon="15m",
            horizon_bars=15,
            label_available_at="t + 15m",
            minimum_history=1,
            future_window=15,
            overlap_policy="PURGE",
            purge_requirement=15,
            embargo_requirement=15,
            units="volatility",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        TargetDefinition(
            target_id="future_realized_volatility_1h",
            asset=asset,
            definition="Sample standard deviation of 1-minute log returns over forward 60-minute window",
            horizon="1h",
            horizon_bars=60,
            label_available_at="t + 1h",
            minimum_history=1,
            future_window=60,
            overlap_policy="PURGE",
            purge_requirement=60,
            embargo_requirement=60,
            units="volatility",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        TargetDefinition(
            target_id="future_realized_volatility_4h",
            asset=asset,
            definition="Sample standard deviation of 1-minute log returns over forward 240-minute window",
            horizon="4h",
            horizon_bars=240,
            label_available_at="t + 4h",
            minimum_history=1,
            future_window=240,
            overlap_policy="PURGE",
            purge_requirement=240,
            embargo_requirement=60,
            units="volatility",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        # Extremal Excursions
        TargetDefinition(
            target_id="future_max_up_move_1h",
            asset=asset,
            definition="Maximum upward price excursion over forward 60m: (max(high_{t+1..t+60}) - close_t) / close_t",
            horizon="1h",
            horizon_bars=60,
            label_available_at="t + 1h",
            minimum_history=1,
            future_window=60,
            overlap_policy="PURGE",
            purge_requirement=60,
            embargo_requirement=60,
            units="percentage_move",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        TargetDefinition(
            target_id="future_max_down_move_1h",
            asset=asset,
            definition="Maximum downward price excursion over forward 60m: (close_t - min(low_{t+1..t+60})) / close_t",
            horizon="1h",
            horizon_bars=60,
            label_available_at="t + 1h",
            minimum_history=1,
            future_window=60,
            overlap_policy="PURGE",
            purge_requirement=60,
            embargo_requirement=60,
            units="percentage_move",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="continuous",
        ),
        # State Transitions (Classification)
        TargetDefinition(
            target_id="future_trend_state_15m",
            asset=asset,
            definition="Directional classification of 15m return (1 if future_log_return_15m > 0 else 0)",
            horizon="15m",
            horizon_bars=15,
            label_available_at="t + 15m",
            minimum_history=1,
            future_window=15,
            overlap_policy="PURGE",
            purge_requirement=15,
            embargo_requirement=15,
            units="binary_state",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="classification",
        ),
        TargetDefinition(
            target_id="future_volatility_state_1h",
            asset=asset,
            definition="Binary indicator: 1 if future_realized_volatility_1h > trailing 60m median realized vol, else 0",
            horizon="1h",
            horizon_bars=60,
            label_available_at="t + 1h",
            minimum_history=60,
            future_window=60,
            overlap_policy="PURGE",
            purge_requirement=60,
            embargo_requirement=60,
            units="binary_state",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="classification",
        ),
        TargetDefinition(
            target_id="future_liquidity_state_15m",
            asset=asset,
            definition="Binary indicator: 1 if future 15m average volume > trailing 60m median volume, else 0",
            horizon="15m",
            horizon_bars=15,
            label_available_at="t + 15m",
            minimum_history=60,
            future_window=15,
            overlap_policy="PURGE",
            purge_requirement=15,
            embargo_requirement=15,
            units="binary_state",
            missingness_rule="NAN_IF_INSUFFICIENT_FORWARD_WINDOW",
            target_type="classification",
        ),
    ]
    return targets


class TargetRegistry:
    """Registry managing approved predictive target definitions."""

    def __init__(self, targets: Optional[List[TargetDefinition]] = None):
        self._targets: Dict[str, TargetDefinition] = {}
        target_list = targets if targets is not None else create_standard_target_catalog()
        for t in target_list:
            self.register_target(t)

    def register_target(self, target: TargetDefinition) -> None:
        if target.target_id in self._targets:
            raise ValueError(f"Target '{target.target_id}' is already registered.")
        self._targets[target.target_id] = target

    def get_target(self, target_id: str) -> TargetDefinition:
        if target_id not in self._targets:
            raise KeyError(f"Target '{target_id}' is not in TargetRegistry.")
        return self._targets[target_id]

    def list_target_ids(self) -> List[str]:
        return list(self._targets.keys())

    def list_targets(self) -> List[TargetDefinition]:
        return list(self._targets.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "registry_version": "1.0.0",
            "targets_count": len(self._targets),
            "targets": [asdict(t) for t in self._targets.values()],
        }


class TargetCalculationEngine:
    """Computes target labels from raw price and bar arrays."""

    @staticmethod
    def compute_target(
        target_def: TargetDefinition,
        closes: Sequence[float],
        highs: Sequence[float],
        lows: Sequence[float],
        volumes: Sequence[float],
    ) -> List[Optional[float]]:
        """Computes target vector for each index t.
        
        Returns None for indices where future window exceeds array length.
        """
        n = len(closes)
        k = target_def.future_window
        result: List[Optional[float]] = [None] * n

        if target_def.target_id == "future_log_return_5m":
            for i in range(n - 5):
                c0 = closes[i]
                c1 = closes[i + 5]
                if c0 > 0 and c1 > 0:
                    result[i] = math.log(c1 / c0)

        elif target_def.target_id == "future_log_return_15m":
            for i in range(n - 15):
                c0 = closes[i]
                c1 = closes[i + 15]
                if c0 > 0 and c1 > 0:
                    result[i] = math.log(c1 / c0)

        elif target_def.target_id == "future_log_return_1h":
            for i in range(n - 60):
                c0 = closes[i]
                c1 = closes[i + 60]
                if c0 > 0 and c1 > 0:
                    result[i] = math.log(c1 / c0)

        elif target_def.target_id == "future_log_return_4h":
            for i in range(n - 240):
                c0 = closes[i]
                c1 = closes[i + 240]
                if c0 > 0 and c1 > 0:
                    result[i] = math.log(c1 / c0)

        elif target_def.target_id == "future_realized_volatility_15m":
            for i in range(n - 15):
                rets = []
                for j in range(i + 1, i + 16):
                    if closes[j - 1] > 0 and closes[j] > 0:
                        rets.append(math.log(closes[j] / closes[j - 1]))
                if len(rets) == 15:
                    mean_r = sum(rets) / 15.0
                    var = sum((r - mean_r) ** 2 for r in rets) / 14.0
                    result[i] = math.sqrt(var)

        elif target_def.target_id == "future_realized_volatility_1h":
            for i in range(n - 60):
                rets = []
                for j in range(i + 1, i + 61):
                    if closes[j - 1] > 0 and closes[j] > 0:
                        rets.append(math.log(closes[j] / closes[j - 1]))
                if len(rets) == 60:
                    mean_r = sum(rets) / 60.0
                    var = sum((r - mean_r) ** 2 for r in rets) / 59.0
                    result[i] = math.sqrt(var)

        elif target_def.target_id == "future_realized_volatility_4h":
            for i in range(n - 240):
                rets = []
                for j in range(i + 1, i + 241):
                    if closes[j - 1] > 0 and closes[j] > 0:
                        rets.append(math.log(closes[j] / closes[j - 1]))
                if len(rets) == 240:
                    mean_r = sum(rets) / 240.0
                    var = sum((r - mean_r) ** 2 for r in rets) / 239.0
                    result[i] = math.sqrt(var)

        elif target_def.target_id == "future_max_up_move_1h":
            for i in range(n - 60):
                c0 = closes[i]
                if c0 > 0:
                    max_h = max(highs[i + 1 : i + 61])
                    result[i] = (max_h - c0) / c0

        elif target_def.target_id == "future_max_down_move_1h":
            for i in range(n - 60):
                c0 = closes[i]
                if c0 > 0:
                    min_l = min(lows[i + 1 : i + 61])
                    result[i] = (c0 - min_l) / c0

        elif target_def.target_id == "future_trend_state_15m":
            for i in range(n - 15):
                c0 = closes[i]
                c1 = closes[i + 15]
                if c0 > 0 and c1 > 0:
                    result[i] = 1.0 if c1 > c0 else 0.0

        elif target_def.target_id == "future_volatility_state_1h":
            # Realized vol 1h compared to trailing 60m realized vol
            for i in range(60, n - 60):
                trail_rets = [math.log(closes[j] / closes[j - 1]) for j in range(i - 59, i + 1)]
                fwd_rets = [math.log(closes[j] / closes[j - 1]) for j in range(i + 1, i + 61)]
                trail_vol = math.sqrt(sum((r - sum(trail_rets) / 60) ** 2 for r in trail_rets) / 59)
                fwd_vol = math.sqrt(sum((r - sum(fwd_rets) / 60) ** 2 for r in fwd_rets) / 59)
                result[i] = 1.0 if fwd_vol > trail_vol else 0.0

        elif target_def.target_id == "future_liquidity_state_15m":
            for i in range(60, n - 15):
                trail_vols = volumes[i - 59 : i + 1]
                median_trail = sorted(trail_vols)[len(trail_vols) // 2]
                fwd_avg_vol = sum(volumes[i + 1 : i + 16]) / 15.0
                result[i] = 1.0 if fwd_avg_vol > median_trail else 0.0

        return result
