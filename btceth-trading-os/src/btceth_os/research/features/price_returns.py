from __future__ import annotations

import math
from typing import Sequence

from .registry import GLOBAL_FEATURE_REGISTRY, FeatureMetadata


def compute_log_returns(closes: Sequence[float], lookback: int = 1) -> list[float]:
    """Point-in-time log return over `lookback` bars: ln(close[t] / close[t-lookback])."""
    if lookback < 1:
        raise ValueError("lookback must be at least 1")
    n = len(closes)
    out = [0.0] * n
    for i in range(lookback, n):
        c_curr = closes[i]
        c_prev = closes[i - lookback]
        if c_curr > 0.0 and c_prev > 0.0:
            out[i] = math.log(c_curr / c_prev)
        else:
            out[i] = 0.0
    return out


def compute_trend_slope(closes: Sequence[float], lookback: int = 30) -> list[float]:
    """Point-in-time linear regression slope over the past `lookback` bars, normalized by current close."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    n = len(closes)
    out = [0.0] * n
    x_mean = (lookback - 1) / 2.0
    var_x = sum((x - x_mean) ** 2 for x in range(lookback))

    for i in range(lookback - 1, n):
        c_curr = closes[i]
        if c_curr <= 0.0:
            continue
        window = closes[i - lookback + 1 : i + 1]
        y_mean = sum(window) / lookback
        cov_xy = sum((x - x_mean) * (y - y_mean) for x, y in enumerate(window))
        slope = cov_xy / var_x if var_x > 0 else 0.0
        # Percentage slope over the whole window
        out[i] = (slope * lookback) / c_curr
    return out


def compute_breakout_distance(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 60,
) -> list[float]:
    """Distance from prior N-period high/low channel. Positive if above prior high, negative if below prior low."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    n = len(closes)
    out = [0.0] * n
    for i in range(lookback, n):
        prior_high = max(highs[i - lookback : i])
        prior_low = min(lows[i - lookback : i])
        c = closes[i]
        if c > prior_high and prior_high > 0:
            out[i] = (c - prior_high) / prior_high
        elif c < prior_low and prior_low > 0:
            out[i] = (c - prior_low) / prior_low
        else:
            channel_range = prior_high - prior_low
            if channel_range > 0:
                mid = (prior_high + prior_low) / 2.0
                out[i] = (c - mid) / channel_range
            else:
                out[i] = 0.0
    return out


def compute_normalized_range_position(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 30,
) -> list[float]:
    """Stochastic %K style normalized range position in [0.0, 1.0]."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    n = len(closes)
    out = [0.5] * n
    for i in range(lookback - 1, n):
        window_high = max(highs[i - lookback + 1 : i + 1])
        window_low = min(lows[i - lookback + 1 : i + 1])
        rng = window_high - window_low
        if rng > 1e-12:
            val = (closes[i] - window_low) / rng
            out[i] = max(0.0, min(1.0, val))
        else:
            out[i] = 0.5
    return out


def compute_rolling_drawdown(closes: Sequence[float], lookback: int = 120) -> list[float]:
    """Rolling peak-to-trough drawdown over past `lookback` bars, in [0.0, 1.0]."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    n = len(closes)
    out = [0.0] * n
    for i in range(lookback - 1, n):
        window = closes[i - lookback + 1 : i + 1]
        peak = window[0]
        max_dd = 0.0
        for price in window:
            if price > peak:
                peak = price
            elif peak > 0:
                dd = (peak - price) / peak
                if dd > max_dd:
                    max_dd = dd
        out[i] = max_dd
    return out


# Register standard price & return features
for h, name in [(1, "1m"), (5, "5m"), (15, "15m"), (60, "1h"), (240, "4h")]:
    GLOBAL_FEATURE_REGISTRY.register(
        FeatureMetadata(
            feature_id=f"log_return_{name}",
            name=f"Log Return {name}",
            category="price_returns",
            lookback_bars=h,
            source_fields=("close",),
            description=f"Natural log price return over {name} ({h} 1m bars)",
        ),
        lambda closes, _h=h: compute_log_returns(closes, lookback=_h),
    )

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="trend_slope_30m",
        name="Normalized Trend Slope 30m",
        category="price_returns",
        lookback_bars=30,
        source_fields=("close",),
        description="OLS linear regression slope over past 30 bars, normalized by close",
    ),
    compute_trend_slope,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="breakout_dist_60m",
        name="Channel Breakout Distance 60m",
        category="price_returns",
        lookback_bars=60,
        source_fields=("close", "high", "low"),
        description="Normalized distance from prior 60-bar high/low channel",
    ),
    compute_breakout_distance,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="norm_range_pos_30m",
        name="Normalized Range Position 30m",
        category="price_returns",
        lookback_bars=30,
        source_fields=("close", "high", "low"),
        description="Stochastic %K normalized price position in 30m high-low window",
    ),
    compute_normalized_range_position,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="rolling_drawdown_2h",
        name="Rolling Peak Drawdown 2h",
        category="price_returns",
        lookback_bars=120,
        source_fields=("close",),
        description="Peak-to-trough drawdown over rolling 120-minute window",
    ),
    compute_rolling_drawdown,
)
