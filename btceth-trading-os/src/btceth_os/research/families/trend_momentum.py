from __future__ import annotations

from typing import Any, Sequence

from ..backtest import Candle
from .base import BaseStrategyFamily


class TrendMomentumFamily(BaseStrategyFamily):
    """Family A: Moving average trend-following with momentum filters."""

    def __init__(self) -> None:
        super().__init__(
            family_id="FAMILY_A_TREND_MOMENTUM",
            hypothesis="Directional momentum persists over multi-hour horizons following moving average crossovers in trending regimes.",
        )

    def generate_positions(self, candles: Sequence[Candle], parameters: dict[str, Any]) -> list[int]:
        self.increment_variant_counter()
        fast_win = int(parameters.get("fast_window", 30))
        slow_win = int(parameters.get("slow_window", 120))
        threshold_bps = float(parameters.get("threshold_bps", 0.0)) / 10000.0

        n = len(candles)
        positions = [0] * n
        if n < slow_win:
            return positions

        closes = [float(c.close) for c in candles]

        # Rolling simple moving averages
        fast_sum = sum(closes[:fast_win])
        slow_sum = sum(closes[:slow_win])

        fast_mas = [0.0] * n
        slow_mas = [0.0] * n
        fast_mas[fast_win - 1] = fast_sum / fast_win
        slow_mas[slow_win - 1] = slow_sum / slow_win

        for i in range(fast_win, n):
            fast_sum += closes[i] - closes[i - fast_win]
            fast_mas[i] = fast_sum / fast_win

        for i in range(slow_win, n):
            slow_sum += closes[i] - closes[i - slow_win]
            slow_mas[i] = slow_sum / slow_win

        for i in range(slow_win, n):
            f_ma = fast_mas[i]
            s_ma = slow_mas[i]
            diff_ratio = (f_ma - s_ma) / s_ma if s_ma > 0 else 0.0
            if diff_ratio > threshold_bps:
                positions[i] = 1
            elif diff_ratio < -threshold_bps:
                positions[i] = -1
            else:
                positions[i] = 0

        return positions
