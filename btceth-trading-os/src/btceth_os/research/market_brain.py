from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .unit_rates import bps_to_fraction, fraction_to_bps


class TrendDimension(str, Enum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    RANGE = "RANGE"


class VolatilityDimension(str, Enum):
    LOW_VOL = "LOW_VOL"
    NORMAL_VOL = "NORMAL_VOL"
    HIGH_VOL = "HIGH_VOL"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"


class FundingDimension(str, Enum):
    NEUTRAL = "NEUTRAL"
    EXTREME_POSITIVE = "EXTREME_POSITIVE"
    EXTREME_NEGATIVE = "EXTREME_NEGATIVE"
    DISLOCATED = "DISLOCATED"


class StressDimension(str, Enum):
    NORMAL = "NORMAL"
    MARKET_STRESS = "MARKET_STRESS"


class LiquidityDimension(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    NORMAL = "NORMAL"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"


class OpenInterestDimension(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    OI_EXPANSION = "OI_EXPANSION"
    OI_UNWIND = "OI_UNWIND"
    OI_STABLE = "OI_STABLE"


class CompositeRegime(str, Enum):
    TREND_UP_LOW_VOL = "TREND_UP_LOW_VOL"
    TREND_UP_HIGH_VOL = "TREND_UP_HIGH_VOL"
    TREND_DOWN_LOW_VOL = "TREND_DOWN_LOW_VOL"
    TREND_DOWN_HIGH_VOL = "TREND_DOWN_HIGH_VOL"
    RANGE_LOW_VOL = "RANGE_LOW_VOL"
    RANGE_HIGH_VOL = "RANGE_HIGH_VOL"
    MARKET_STRESS = "MARKET_STRESS"
    FUNDING_EXTREME = "FUNDING_EXTREME"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    RANGE_COMPRESSION = "RANGE_COMPRESSION"
    OI_EXPANSION = "OI_EXPANSION"
    OI_UNWIND = "OI_UNWIND"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"


# Backwards compatibility alias
MarketRegime = CompositeRegime


@dataclass(frozen=True)
class MarketState:
    """Multi-dimensional compositional market state representation."""

    timestamp_ns: int
    symbol: str
    price: float
    
    # Explicit independent dimensions
    trend_state: TrendDimension
    volatility_state: VolatilityDimension
    funding_state: FundingDimension
    stress_state: StressDimension
    liquidity_state: LiquidityDimension
    oi_state: OpenInterestDimension
    session_state: str
    
    # Composite headline regime
    regime: CompositeRegime

    # Underlying quantitative features
    trend_slope_30m: float
    volatility_realized_60m: float
    funding_rate: float
    funding_zscore: float
    compression_ratio: float
    rolling_drawdown_2h: float
    rationale: str


class MarketBrain:
    """Deterministic, compositional Market Brain evaluating independent dimensions and composite state."""

    # Explicit unit-safe numerical thresholds
    TREND_THRESHOLD: float = 0.003                  # 0.30% slope over 30 bars
    VOLATILITY_LOW_THRESHOLD: float = 0.35          # 35% annualized volatility
    VOLATILITY_HIGH_THRESHOLD: float = 0.55         # 55% annualized volatility
    
    MARKET_STRESS_VOL: float = 0.85                 # 85% annualized volatility
    MARKET_STRESS_DD: float = 0.035                 # 3.5% drawdown in 2 hours
    
    # Empirical funding extremes: standard rate is 1 bp (0.0001); extreme threshold is 30 bps (0.0030) per 8h
    FUNDING_EXTREME_ABS_BPS: float = 30.0
    FUNDING_EXTREME_ABS: float = float(bps_to_fraction(FUNDING_EXTREME_ABS_BPS))  # 0.0030
    FUNDING_EXTREME_Z: float = 2.5                  # 2.5 standard deviations
    
    COMPRESSION_SQUEEZE: float = 0.65               # 15m/60m ATR compression ratio
    EXPANSION_RATIO: float = 1.35                   # 15m/60m ATR expansion ratio

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
        # Optional verified microstructure / derivatives inputs
        open_interest_delta_pct: Optional[float] = None,
        spread_bps: Optional[float] = None,
        depth_collapse_ratio: Optional[float] = None,
    ) -> MarketState:
        """Evaluate compositional market state across independent dimensions."""

        # 1. Trend Dimension
        if trend_slope_30m >= cls.TREND_THRESHOLD:
            trend_dim = TrendDimension.UPTREND
        elif trend_slope_30m <= -cls.TREND_THRESHOLD:
            trend_dim = TrendDimension.DOWNTREND
        else:
            trend_dim = TrendDimension.RANGE

        # 2. Volatility Dimension
        if compression_ratio >= cls.EXPANSION_RATIO:
            vol_dim = VolatilityDimension.VOLATILITY_EXPANSION
        elif compression_ratio <= cls.COMPRESSION_SQUEEZE:
            vol_dim = VolatilityDimension.VOLATILITY_COMPRESSION
        elif volatility_realized_60m >= cls.VOLATILITY_HIGH_THRESHOLD:
            vol_dim = VolatilityDimension.HIGH_VOL
        elif volatility_realized_60m <= cls.VOLATILITY_LOW_THRESHOLD:
            vol_dim = VolatilityDimension.LOW_VOL
        else:
            vol_dim = VolatilityDimension.NORMAL_VOL

        # 3. Stress Dimension (volatility / drawdown stress)
        if volatility_realized_60m >= cls.MARKET_STRESS_VOL or rolling_drawdown_2h >= cls.MARKET_STRESS_DD:
            stress_dim = StressDimension.MARKET_STRESS
        else:
            stress_dim = StressDimension.NORMAL

        # 4. Funding Dimension
        if funding_rate >= cls.FUNDING_EXTREME_ABS or funding_zscore >= cls.FUNDING_EXTREME_Z:
            funding_dim = FundingDimension.EXTREME_POSITIVE
        elif funding_rate <= -cls.FUNDING_EXTREME_ABS or funding_zscore <= -cls.FUNDING_EXTREME_Z:
            funding_dim = FundingDimension.EXTREME_NEGATIVE
        elif abs(funding_zscore) >= 2.0:
            funding_dim = FundingDimension.DISLOCATED
        else:
            funding_dim = FundingDimension.NEUTRAL

        # 5. Open Interest Dimension: Only report if genuine OI data is provided!
        if open_interest_delta_pct is None:
            oi_dim = OpenInterestDimension.UNAVAILABLE
        elif open_interest_delta_pct >= 0.05:
            oi_dim = OpenInterestDimension.OI_EXPANSION
        elif open_interest_delta_pct <= -0.05:
            oi_dim = OpenInterestDimension.OI_UNWIND
        else:
            oi_dim = OpenInterestDimension.OI_STABLE

        # 6. Liquidity Dimension: Only report if genuine spread/depth data is provided!
        if spread_bps is None and depth_collapse_ratio is None:
            liq_dim = LiquidityDimension.UNAVAILABLE
        elif (spread_bps is not None and spread_bps >= 10.0) or (depth_collapse_ratio is not None and depth_collapse_ratio <= 0.30):
            liq_dim = LiquidityDimension.LIQUIDITY_STRESS
        else:
            liq_dim = LiquidityDimension.NORMAL

        # 7. Derive Composite Headline Regime
        if stress_dim == StressDimension.MARKET_STRESS:
            composite = CompositeRegime.MARKET_STRESS
            rationale = f"Market stress: vol={volatility_realized_60m:.2f} >= {cls.MARKET_STRESS_VOL} or dd={rolling_drawdown_2h:.3f} >= {cls.MARKET_STRESS_DD}"
        elif liq_dim == LiquidityDimension.LIQUIDITY_STRESS:
            composite = CompositeRegime.LIQUIDITY_STRESS
            rationale = "Liquidity stress: order book depth collapse / spread widening verified"
        elif funding_dim in (FundingDimension.EXTREME_POSITIVE, FundingDimension.EXTREME_NEGATIVE):
            composite = CompositeRegime.FUNDING_EXTREME
            rationale = f"Funding extreme: zscore={funding_zscore:.2f}, rate={funding_rate:.6f} ({fraction_to_bps(funding_rate):.1f} bps)"
        elif oi_dim == OpenInterestDimension.OI_EXPANSION:
            composite = CompositeRegime.OI_EXPANSION
            rationale = f"Open interest expansion: delta={open_interest_delta_pct:+.1%}"
        elif oi_dim == OpenInterestDimension.OI_UNWIND:
            composite = CompositeRegime.OI_UNWIND
            rationale = f"Open interest unwind: delta={open_interest_delta_pct:+.1%}"
        elif vol_dim == VolatilityDimension.VOLATILITY_EXPANSION:
            composite = CompositeRegime.VOLATILITY_EXPANSION
            rationale = f"Volatility expansion: ATR compression_ratio={compression_ratio:.2f} >= {cls.EXPANSION_RATIO}"
        elif vol_dim == VolatilityDimension.VOLATILITY_COMPRESSION and trend_dim == TrendDimension.RANGE:
            composite = CompositeRegime.RANGE_COMPRESSION
            rationale = f"Range compression coil: compression_ratio={compression_ratio:.2f} <= {cls.COMPRESSION_SQUEEZE}"
        elif trend_dim == TrendDimension.UPTREND:
            if vol_dim in (VolatilityDimension.HIGH_VOL, VolatilityDimension.VOLATILITY_EXPANSION):
                composite = CompositeRegime.TREND_UP_HIGH_VOL
                rationale = f"Up-trend high vol: slope={trend_slope_30m:.4f} >= {cls.TREND_THRESHOLD}"
            else:
                composite = CompositeRegime.TREND_UP_LOW_VOL
                rationale = f"Up-trend low vol: slope={trend_slope_30m:.4f} >= {cls.TREND_THRESHOLD}"
        elif trend_dim == TrendDimension.DOWNTREND:
            if vol_dim in (VolatilityDimension.HIGH_VOL, VolatilityDimension.VOLATILITY_EXPANSION):
                composite = CompositeRegime.TREND_DOWN_HIGH_VOL
                rationale = f"Down-trend high vol: slope={trend_slope_30m:.4f} <= -{cls.TREND_THRESHOLD}"
            else:
                composite = CompositeRegime.TREND_DOWN_LOW_VOL
                rationale = f"Down-trend low vol: slope={trend_slope_30m:.4f} <= -{cls.TREND_THRESHOLD}"
        else:
            if vol_dim in (VolatilityDimension.HIGH_VOL, VolatilityDimension.VOLATILITY_EXPANSION):
                composite = CompositeRegime.RANGE_HIGH_VOL
                rationale = f"Range high vol: |slope|={abs(trend_slope_30m):.4f} < {cls.TREND_THRESHOLD}"
            else:
                composite = CompositeRegime.RANGE_LOW_VOL
                rationale = f"Range low vol: |slope|={abs(trend_slope_30m):.4f} < {cls.TREND_THRESHOLD}"

        return MarketState(
            timestamp_ns=timestamp_ns,
            symbol=symbol,
            price=price,
            trend_state=trend_dim,
            volatility_state=vol_dim,
            funding_state=funding_dim,
            stress_state=stress_dim,
            liquidity_state=liq_dim,
            oi_state=oi_dim,
            session_state=session,
            regime=composite,
            trend_slope_30m=trend_slope_30m,
            volatility_realized_60m=volatility_realized_60m,
            funding_rate=funding_rate,
            funding_zscore=funding_zscore,
            compression_ratio=compression_ratio,
            rolling_drawdown_2h=rolling_drawdown_2h,
            rationale=rationale,
        )
