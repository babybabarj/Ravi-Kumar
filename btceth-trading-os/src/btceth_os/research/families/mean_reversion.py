from __future__ import annotations

import math
from typing import Any, Sequence

from ..backtest import Candle
from .base import BaseStrategyFamily


class MeanReversionFamily(BaseStrategyFamily):
    """Family C: Short-horizon Bollinger / Z-score mean reversion."""

    def __init__(self) -> None:
        super().__init__(
            family_id="FAMILY_C_MEAN_REVERSION",
            hypothesis="Extreme short-term deviations from the rolling moving average mean-revert toward the equilibrium center.",
        )

    def generate_positions(self, candles: Sequence[Candle], parameters: dict[str, Any]) -> list[int]:
        self.increment_variant_counter()
        window = int(parameters.get("window", 60))
        entry_z = float(parameters.get("entry_z", 2.0))
        exit_z = float(parameters.get("exit_z", 0.5))

        n = len(candles)
        positions = [0] * n
        if n < window:
            return positions

        closes = [float(c.close) for c in candles]
        current_pos = 0

        for i in range(window - 1, n):
            sub = closes[i - window + 1 : i + 1]
            mean_val = sum(sub) / window
            var = sum((x - mean_val) ** 2 for x in sub) / (window - 1)
            std_val = math.sqrt(var)

            if std_val > 1e-10:
                z = (closes[i] - mean_val) / std_val
            else:
                z = 0.0

            if z < -entry_z:
                current_pos = 1
            elif z > entry_z:
                current_pos = -1
            elif abs(z) <= exit_z:
                current_pos = 0

            positions[i] = current_pos

        return positions
