from __future__ import annotations

from typing import Any, Sequence

from ..backtest import Candle
from .base import BaseStrategyFamily


class FundingBasisFamily(BaseStrategyFamily):
    """Family D: Funding rate dislocation contrarian positioning."""

    def __init__(self) -> None:
        super().__init__(
            family_id="FAMILY_D_FUNDING_DISLOCATION",
            hypothesis="Extreme crowded perpetual funding rates precede directional unwind as over-leveraged positioning liquidates.",
        )

    def generate_positions(self, candles: Sequence[Candle], parameters: dict[str, Any]) -> list[int]:
        self.increment_variant_counter()
        aligned_funding_zscores: Sequence[float] = parameters.get("aligned_funding_zscores", [])
        z_threshold = float(parameters.get("z_threshold", 2.0))

        n = len(candles)
        positions = [0] * n
        if not aligned_funding_zscores or len(aligned_funding_zscores) != n:
            return positions

        current_pos = 0
        for i in range(n):
            z = aligned_funding_zscores[i]
            if z >= z_threshold:
                # Funding excessively high -> overcrowded longs -> short position
                current_pos = -1
            elif z <= -z_threshold:
                # Funding deeply negative -> overcrowded shorts -> long position
                current_pos = 1
            elif abs(z) < 0.5:
                # Returned to neutral
                current_pos = 0

            positions[i] = current_pos

        return positions
