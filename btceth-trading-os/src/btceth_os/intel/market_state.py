"""Layer C: Market State Engine for INTEL-1A.

Produces descriptive, non-executable market state classifications across five key dimensions:
1. TREND (UP, DOWN, RANGE, UNCERTAIN)
2. VOLATILITY (LOW, NORMAL, HIGH, EXTREME, UNKNOWN)
3. LIQUIDITY_ACTIVITY (THIN, NORMAL, ELEVATED, UNKNOWN)
4. FUNDING (NEGATIVE_EXTREME, NEGATIVE, NEUTRAL, POSITIVE, POSITIVE_EXTREME, UNKNOWN)
5. MARKET_QUALITY (HEALTHY, DEGRADED, UNRELIABLE, UNKNOWN)

Uncertainty is treated as a first-class result, never hidden or forced.
All outputs are strictly descriptive and contain zero buy/sell signals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class TrendRegime(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    RANGE = "RANGE"
    UNCERTAIN = "UNCERTAIN"


class VolatilityRegime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class LiquidityActivityRegime(str, Enum):
    THIN = "THIN"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    UNKNOWN = "UNKNOWN"


class FundingRegime(str, Enum):
    NEGATIVE_EXTREME = "NEGATIVE_EXTREME"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    POSITIVE = "POSITIVE"
    POSITIVE_EXTREME = "POSITIVE_EXTREME"
    UNKNOWN = "UNKNOWN"


class MarketQualityRegime(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNRELIABLE = "UNRELIABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MarketStateSnapshot:
    trend_state: str
    volatility_state: str
    activity_state: str
    funding_state: str
    market_quality_state: str
    uncertainties: List[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MarketStateEngine:
    """Classifies descriptive market regimes from causal feature inputs."""

    @staticmethod
    def classify_trend(
        efficiency_ratio: Optional[float],
        directional_persistence: Optional[float],
        slope: Optional[float],
    ) -> tuple[str, Optional[str]]:
        if efficiency_ratio is None or directional_persistence is None or slope is None:
            return TrendRegime.UNCERTAIN.value, "INSUFFICIENT_TREND_HISTORY"

        if efficiency_ratio > 0.4:
            if directional_persistence >= 0.65 and slope > 0.0001:
                return TrendRegime.UP.value, None
            if directional_persistence <= 0.35 and slope < -0.0001:
                return TrendRegime.DOWN.value, None
            return TrendRegime.UNCERTAIN.value, "DISCORDANT_DIRECTIONAL_SIGNALS"

        if efficiency_ratio < 0.25:
            return TrendRegime.RANGE.value, None

        return TrendRegime.UNCERTAIN.value, "INTERMEDIATE_EFFICIENCY_UNCERTAINTY"

    @staticmethod
    def classify_volatility(
        vol_percentile: Optional[float],
        short_vol: Optional[float],
    ) -> tuple[str, Optional[str]]:
        if vol_percentile is None:
            if short_vol is None:
                return VolatilityRegime.UNKNOWN.value, "INSUFFICIENT_VOLATILITY_HISTORY"
            return VolatilityRegime.UNKNOWN.value, "WARMUP_PERIOD_PERCENTILE_UNAVAILABLE"

        if vol_percentile < 0.20:
            return VolatilityRegime.LOW.value, None
        if vol_percentile <= 0.75:
            return VolatilityRegime.NORMAL.value, None
        if vol_percentile <= 0.95:
            return VolatilityRegime.HIGH.value, None
        return VolatilityRegime.EXTREME.value, None

    @staticmethod
    def classify_activity(
        vol_percentile: Optional[float],
        activity_score: Optional[float],
    ) -> tuple[str, Optional[str]]:
        if vol_percentile is None and activity_score is None:
            return LiquidityActivityRegime.UNKNOWN.value, "INSUFFICIENT_ACTIVITY_HISTORY"

        if vol_percentile is not None:
            if vol_percentile < 0.20:
                return LiquidityActivityRegime.THIN.value, None
            if vol_percentile > 0.80:
                return LiquidityActivityRegime.ELEVATED.value, None
            return LiquidityActivityRegime.NORMAL.value, None

        if activity_score is not None:
            if activity_score < -1.0:
                return LiquidityActivityRegime.THIN.value, None
            if activity_score > 1.5:
                return LiquidityActivityRegime.ELEVATED.value, None
            return LiquidityActivityRegime.NORMAL.value, None

        return LiquidityActivityRegime.UNKNOWN.value, "ACTIVITY_METRICS_UNAVAILABLE"

    @staticmethod
    def classify_funding(
        latest_funding_rate: Optional[Any],
    ) -> tuple[str, Optional[str]]:
        if latest_funding_rate is None:
            return FundingRegime.UNKNOWN.value, "FUNDING_RATE_UNOBSERVED"

        try:
            r = float(latest_funding_rate)
        except (ValueError, TypeError):
            return FundingRegime.UNKNOWN.value, "INVALID_FUNDING_RATE_FORMAT"

        # Binance benchmark thresholds (e.g. 0.01% is standard 8h interest)
        if r > 0.0010:  # > 0.10% per interval is elevated/extreme
            return FundingRegime.POSITIVE_EXTREME.value, None
        if r > 0.0001:
            return FundingRegime.POSITIVE.value, None
        if r < -0.0010:
            return FundingRegime.NEGATIVE_EXTREME.value, None
        if r < -0.0001:
            return FundingRegime.NEGATIVE.value, None
        return FundingRegime.NEUTRAL.value, None

    @classmethod
    def evaluate_state(
        cls,
        features: Dict[str, Any],
        data_quality_status: str,
        data_quality_reasons: Optional[List[str]] = None,
    ) -> MarketStateSnapshot:
        uncertainties: List[str] = []

        # Market quality classification
        if data_quality_status == "UNRELIABLE":
            mq = MarketQualityRegime.UNRELIABLE.value
            uncertainties.append("DATA_QUALITY_UNRELIABLE")
        elif data_quality_status == "DEGRADED":
            mq = MarketQualityRegime.DEGRADED.value
            uncertainties.extend(data_quality_reasons or ["DATA_QUALITY_DEGRADED"])
        elif data_quality_status == "GOOD":
            mq = MarketQualityRegime.HEALTHY.value
        else:
            mq = MarketQualityRegime.UNKNOWN.value
            uncertainties.append("DATA_QUALITY_UNKNOWN")

        # Trend
        trend, u_trend = cls.classify_trend(
            features.get("efficiency_ratio_20m"),
            features.get("directional_persistence_20m"),
            features.get("rolling_slope_20m"),
        )
        if u_trend:
            uncertainties.append(u_trend)

        # Volatility
        vol, u_vol = cls.classify_volatility(
            features.get("volatility_percentile_trailing_1440m"),
            features.get("short_horizon_vol_10m"),
        )
        if u_vol:
            uncertainties.append(u_vol)

        # Activity
        act, u_act = cls.classify_activity(
            features.get("volume_percentile_trailing_1440m"),
            features.get("abnormal_activity_score_60m"),
        )
        if u_act:
            uncertainties.append(u_act)

        # Funding
        fund, u_fund = cls.classify_funding(
            features.get("latest_realized_funding_rate")
        )
        if u_fund:
            uncertainties.append(u_fund)

        # Session uncertainties
        if features.get("holiday_status") == "NOT_IMPLEMENTED":
            if features.get("price_index_mode_certainty") == "HOLIDAY_UNKNOWN":
                uncertainties.append("SESSION_HOLIDAY_STATUS_UNPROVEN")

        return MarketStateSnapshot(
            trend_state=trend,
            volatility_state=vol,
            activity_state=act,
            funding_state=fund,
            market_quality_state=mq,
            uncertainties=sorted(set(uncertainties)),
        )
