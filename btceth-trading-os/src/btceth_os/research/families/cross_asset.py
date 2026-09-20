from __future__ import annotations

from typing import Any, Sequence

from ..backtest import Candle
from .base import BaseStrategyFamily


class CrossAssetDivergenceFamily(BaseStrategyFamily):
    """Family G: Cross-asset ETH/BTC relative strength divergence."""

    def __init__(self) -> None:
        super().__init__(
            family_id="FAMILY_G_CROSS_ASSET_DIVERGENCE",
            hypothesis="Extreme divergence between ETH and BTC relative performance mean-reverts toward historical equilibrium.",
        )

    def generate_positions(self, candles: Sequence[Candle], parameters: dict[str, Any]) -> list[int]:
        self.increment_variant_counter()
        ratio_zscores: Sequence[float] = parameters.get("ratio_zscores", [])
        threshold = float(parameters.get("threshold", 1.8))

        n = len(candles)
        positions = [0] * n
        if not ratio_zscores or len(ratio_zscores) != n:
            return positions

        current_pos = 0
        for i in range(n):
            z = ratio_zscores[i]
            if z > threshold:
                # ETH excessively strong relative to BTC -> short ETH
                current_pos = -1
            elif z < -threshold:
                # ETH excessively weak relative to BTC -> long ETH
                current_pos = 1
            elif abs(z) < 0.3:
                current_pos = 0

            positions[i] = current_pos

        return positions
