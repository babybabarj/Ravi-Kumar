from __future__ import annotations

from typing import Any, Sequence

from ..backtest import Candle
from .base import BaseStrategyFamily


class BreakoutExpansionFamily(BaseStrategyFamily):
    """Family B: Donchian Channel Breakout with Volatility Expansion."""

    def __init__(self) -> None:
        super().__init__(
            family_id="FAMILY_B_BREAKOUT_EXPANSION",
            hypothesis="Price breaking out of multi-hour Donchian channels leads to continuation before mean-reverting.",
        )

    def generate_positions(self, candles: Sequence[Candle], parameters: dict[str, Any]) -> list[int]:
        self.increment_variant_counter()
        entry_window = int(parameters.get("entry_window", 120))
        exit_window = int(parameters.get("exit_window", 60))

        n = len(candles)
        positions = [0] * n
        if n < max(entry_window, exit_window) + 1:
            return positions

        closes = [float(c.close) for c in candles]
        current_pos = 0

        for i in range(entry_window, n):
            prior_entry_window = closes[i - entry_window : i]
            upper_band = max(prior_entry_window)
            lower_band = min(prior_entry_window)

            c = closes[i]
            if c > upper_band:
                current_pos = 1
            elif c < lower_band:
                current_pos = -1
            elif current_pos != 0:
                # Check exit window
                prior_exit_window = closes[i - exit_window : i]
                exit_mid = (max(prior_exit_window) + min(prior_exit_window)) / 2.0
                if (current_pos == 1 and c < exit_mid) or (current_pos == -1 and c > exit_mid):
                    current_pos = 0

            positions[i] = current_pos

        return positions
