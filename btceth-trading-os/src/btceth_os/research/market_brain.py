from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class MarketRegime(str, Enum):
    TREND_UP_LOW_VOL = "TREND_UP_LOW_VOL"
    TREND_UP_HIGH_VOL = "TREND_UP_HIGH_VOL"
    TREND_DOWN_LOW_VOL = "TREND_DOWN_LOW_VOL"
    TREND_DOWN_HIGH_VOL = "TREND_DOWN_HIGH_VOL"
    RANGE_LOW_VOL = "RANGE_LOW_VOL"
    RANGE_HIGH_VOL = "RANGE_HIGH_VOL"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
    FUNDING_EXTREME = "FUNDING_EXTREME"
    OI_EXPANSION = "OI_EXPANSION"
    OI_UNWIND = "OI_UNWIND"


@dataclass(frozen=True)
class MarketState:
    timestamp_ns: int
    symbol: str
    price: float
    regime: MarketRegime
    trend_slope_30m: float
    volatility_realized_60m: float
    funding_rate: float
    funding_zscore: float
    compression_ratio: float
    rolling_drawdown_2h: float
    session: str
    rationale: str


class MarketBrain:
    """Deterministic, rule-based Market Brain evaluating market state into 10 mutually exclusive regimes."""

    # Numerical regime thresholds
    TREND_THRESHOLD: float = 0.003          # 0.30% slope over 30 bars
    VOLATILITY_THRESHOLD: float = 0.45     # 45% annualized volatility
    LIQUIDITY_STRESS_VOL: float = 0.85     # 85% annualized volatility
    LIQUIDITY_STRESS_DD: float = 0.035     # 3.5% drawdown in 2 hours
    FUNDING_EXTREME_Z: float = 2.5         # 2.5 standard deviations
    FUNDING_EXTREME_ABS: float = 0.0004    # 40 bps / 8h
    COMPRESSION_SQUEEZE: float = 0.65      # 15m/60m ATR compression ratio
    EXPANSION_RATIO: float = 1.35          # 15m/60m ATR expansion ratio

    @classmethod
    def classify_bar(
        cls,
        timestamp_ns: int,
        symbol: str,
        price: float,
        trend_slope_30m: float,
        volatility_realized_60m: float,
        funding_rate: float,
        funding_zscore: float,
        compression_ratio: float,
        rolling_drawdown_2h: float,
        session: str = "US",
    ) -> MarketState:
        """Evaluate exact deterministic regime priority."""
        # 1. Stress conditions take highest precedence
        if volatility_realized_60m >= cls.LIQUIDITY_STRESS_VOL or rolling_drawdown_2h >= cls.LIQUIDITY_STRESS_DD:
            regime = MarketRegime.LIQUIDITY_STRESS
            rationale = f"Stress: vol={volatility_realized_60m:.2f} >= {cls.LIQUIDITY_STRESS_VOL} or dd={rolling_drawdown_2h:.3f} >= {cls.LIQUIDITY_STRESS_DD}"

        # 2. Extreme funding dislocation
        elif abs(funding_zscore) >= cls.FUNDING_EXTREME_Z or abs(funding_rate) >= cls.FUNDING_EXTREME_ABS:
            regime = MarketRegime.FUNDING_EXTREME
            rationale = f"Funding extreme: zscore={funding_zscore:.2f}, rate={funding_rate:.6f}"

        # 3. Structural expansion / breakout transition
        elif compression_ratio >= cls.EXPANSION_RATIO:
            regime = MarketRegime.OI_EXPANSION
            rationale = f"Volatility expansion: compression_ratio={compression_ratio:.2f} >= {cls.EXPANSION_RATIO}"

        # 4. Range compression / pre-breakout quiet coil
        elif compression_ratio <= cls.COMPRESSION_SQUEEZE and abs(trend_slope_30m) < cls.TREND_THRESHOLD:
            regime = MarketRegime.OI_UNWIND
            rationale = f"Range compression coil: compression_ratio={compression_ratio:.2f} <= {cls.COMPRESSION_SQUEEZE}"

        # 5. Up-trend regimes
        elif trend_slope_30m >= cls.TREND_THRESHOLD:
            if volatility_realized_60m >= cls.VOLATILITY_THRESHOLD:
                regime = MarketRegime.TREND_UP_HIGH_VOL
                rationale = f"Up-trend high vol: slope={trend_slope_30m:.4f} >= {cls.TREND_THRESHOLD}, vol={volatility_realized_60m:.2f}"
            else:
                regime = MarketRegime.TREND_UP_LOW_VOL
                rationale = f"Up-trend low vol: slope={trend_slope_30m:.4f} >= {cls.TREND_THRESHOLD}, vol={volatility_realized_60m:.2f}"

        # 6. Down-trend regimes
        elif trend_slope_30m <= -cls.TREND_THRESHOLD:
            if volatility_realized_60m >= cls.VOLATILITY_THRESHOLD:
                regime = MarketRegime.TREND_DOWN_HIGH_VOL
                rationale = f"Down-trend high vol: slope={trend_slope_30m:.4f} <= -{cls.TREND_THRESHOLD}, vol={volatility_realized_60m:.2f}"
            else:
                regime = MarketRegime.TREND_DOWN_LOW_VOL
                rationale = f"Down-trend low vol: slope={trend_slope_30m:.4f} <= -{cls.TREND_THRESHOLD}, vol={volatility_realized_60m:.2f}"

        # 7. Range regimes
        else:
            if volatility_realized_60m >= cls.VOLATILITY_THRESHOLD:
                regime = MarketRegime.RANGE_HIGH_VOL
                rationale = f"Range high vol: |slope|={abs(trend_slope_30m):.4f} < {cls.TREND_THRESHOLD}, vol={volatility_realized_60m:.2f}"
            else:
                regime = MarketRegime.RANGE_LOW_VOL
                rationale = f"Range low vol: |slope|={abs(trend_slope_30m):.4f} < {cls.TREND_THRESHOLD}, vol={volatility_realized_60m:.2f}"

        return MarketState(
            timestamp_ns=timestamp_ns,
            symbol=symbol,
            price=price,
            regime=regime,
            trend_slope_30m=trend_slope_30m,
            volatility_realized_60m=volatility_realized_60m,
            funding_rate=funding_rate,
            funding_zscore=funding_zscore,
            compression_ratio=compression_ratio,
            rolling_drawdown_2h=rolling_drawdown_2h,
            session=session,
            rationale=rationale,
        )
