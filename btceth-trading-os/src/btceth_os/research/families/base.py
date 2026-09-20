from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
import math
from typing import Any, Dict, List, Sequence

from ..backtest import Candle, CostModel, BacktestResult, run_backtest
from ..validation.statistical import run_block_bootstrap


@dataclass(frozen=True)
class ForwardReturnStats:
    horizon_bars: int
    count_signals: int
    mean_return_bps: float
    median_return_bps: float
    pct_positive: float
    t_statistic: float
    bootstrap_lower_ci_bps: float


class BaseStrategyFamily(ABC):
    """Abstract base class for quantitative research strategy families."""

    def __init__(self, family_id: str, hypothesis: str) -> None:
        self.family_id = family_id
        self.hypothesis = hypothesis
        self._variants_tested = 0

    @property
    def variants_tested_count(self) -> int:
        return self._variants_tested

    def increment_variant_counter(self) -> int:
        self._variants_tested += 1
        return self._variants_tested

    @abstractmethod
    def generate_positions(self, candles: Sequence[Candle], parameters: dict[str, Any]) -> list[int]:
        """Generate position series (-1, 0, 1) using strictly closed bars up to current index."""
        raise NotImplementedError

    def evaluate_forward_returns(
        self,
        candles: Sequence[Candle],
        positions: Sequence[int],
        horizons: tuple[int, ...] = (5, 15, 30, 60, 240),
    ) -> dict[int, ForwardReturnStats]:
        """Measure forward returns from entry signals to assess raw predictive validity before costs."""
        n = len(candles)
        stats: dict[int, ForwardReturnStats] = {}

        for h in horizons:
            signal_returns: list[float] = []
            for i in range(1, n - h):
                # Check for position entry / transition
                prev_pos = positions[i - 1]
                curr_pos = positions[i]
                if curr_pos != 0 and curr_pos != prev_pos:
                    # Entry took place at bar i close (or candle[i])
                    # Forward return over horizon h: (close[i+h] / close[i] - 1) * direction
                    c_entry = float(candles[i].close)
                    c_exit = float(candles[i + h].close)
                    if c_entry > 0:
                        ret = curr_pos * (c_exit / c_entry - 1.0)
                        signal_returns.append(ret)

            count = len(signal_returns)
            if count < 2:
                stats[h] = ForwardReturnStats(h, count, 0.0, 0.0, 0.0, 0.0, 0.0)
                continue

            mean_r = sum(signal_returns) / count
            var_r = sum((r - mean_r) ** 2 for r in signal_returns) / (count - 1)
            std_r = math.sqrt(var_r)
            t_stat = (mean_r / (std_r / math.sqrt(count))) if std_r > 1e-12 else 0.0

            sorted_rets = sorted(signal_returns)
            median_r = sorted_rets[count // 2]
            pct_pos = sum(1 for r in signal_returns if r > 0) / count

            boot = run_block_bootstrap(signal_returns, num_samples=500, block_size=1)
            lower_ci = boot["lower_ci_95"]

            stats[h] = ForwardReturnStats(
                horizon_bars=h,
                count_signals=count,
                mean_return_bps=mean_r * 10000.0,
                median_return_bps=median_r * 10000.0,
                pct_positive=pct_pos,
                t_statistic=t_stat,
                bootstrap_lower_ci_bps=lower_ci * 10000.0,
            )

        return stats
