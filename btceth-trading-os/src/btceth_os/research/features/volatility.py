from __future__ import annotations

import math
from typing import Sequence

from .registry import GLOBAL_FEATURE_REGISTRY, FeatureMetadata


ANNUALIZED_FACTOR_1M = math.sqrt(525600.0)  # minutes per year


def compute_realized_volatility(closes: Sequence[float], lookback: int = 60) -> list[float]:
    """Annualized close-to-close realized volatility over rolling `lookback` 1m bars."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    n = len(closes)
    out = [0.0] * n
    # Precompute 1-period log returns
    log_rets = [0.0] * n
    for i in range(1, n):
        if closes[i] > 0 and closes[i - 1] > 0:
            log_rets[i] = math.log(closes[i] / closes[i - 1])

    for i in range(lookback, n):
        window = log_rets[i - lookback + 1 : i + 1]
        mean_r = sum(window) / lookback
        var = sum((r - mean_r) ** 2 for r in window) / (lookback - 1)
        out[i] = math.sqrt(max(0.0, var)) * ANNUALIZED_FACTOR_1M
    return out


def compute_parkinson_volatility(
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 60,
) -> list[float]:
    """Annualized Parkinson high-low range volatility over rolling `lookback` 1m bars."""
    if lookback < 1:
        raise ValueError("lookback must be at least 1")
    n = len(highs)
    out = [0.0] * n
    factor = 1.0 / (4.0 * math.log(2.0))

    sq_log_hl = [0.0] * n
    for i in range(n):
        if highs[i] > 0 and lows[i] > 0 and highs[i] >= lows[i]:
            sq_log_hl[i] = math.log(highs[i] / lows[i]) ** 2

    for i in range(lookback - 1, n):
        window_sum = sum(sq_log_hl[i - lookback + 1 : i + 1])
        variance = (factor * window_sum) / lookback
        out[i] = math.sqrt(max(0.0, variance)) * ANNUALIZED_FACTOR_1M
    return out


def compute_garman_klass_volatility(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    lookback: int = 60,
) -> list[float]:
    """Annualized Garman-Klass volatility accounting for open, high, low, and close."""
    if lookback < 1:
        raise ValueError("lookback must be at least 1")
    n = len(closes)
    out = [0.0] * n
    c2 = 2.0 * math.log(2.0) - 1.0

    gk_term = [0.0] * n
    for i in range(n):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        if o > 0 and h > 0 and l > 0 and c > 0 and h >= l:
            log_hl = math.log(h / l)
            log_co = math.log(c / o)
            gk_term[i] = 0.5 * (log_hl**2) - c2 * (log_co**2)

    for i in range(lookback - 1, n):
        window_sum = sum(gk_term[i - lookback + 1 : i + 1])
        variance = max(0.0, window_sum / lookback)
        out[i] = math.sqrt(variance) * ANNUALIZED_FACTOR_1M
    return out


def compute_average_true_range(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    lookback: int = 14,
) -> list[float]:
    """Average True Range normalized by current close price: ATR / Close."""
    if lookback < 1:
        raise ValueError("lookback must be at least 1")
    n = len(closes)
    out = [0.0] * n
    tr = [0.0] * n
    for i in range(n):
        h, l = highs[i], lows[i]
        if i == 0:
            tr[i] = h - l
        else:
            prev_c = closes[i - 1]
            tr[i] = max(h - l, abs(h - prev_c), abs(l - prev_c))

    for i in range(lookback - 1, n):
        c = closes[i]
        if c > 0:
            atr_val = sum(tr[i - lookback + 1 : i + 1]) / lookback
            out[i] = atr_val / c
    return out


def compute_range_compression_ratio(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    short_window: int = 15,
    long_window: int = 60,
) -> list[float]:
    """Ratio of short-term ATR to long-term ATR: < 0.70 signifies compression/squeeze."""
    atr_short = compute_average_true_range(highs, lows, closes, lookback=short_window)
    atr_long = compute_average_true_range(highs, lows, closes, lookback=long_window)
    n = len(closes)
    out = [1.0] * n
    for i in range(long_window - 1, n):
        if atr_long[i] > 1e-12:
            out[i] = atr_short[i] / atr_long[i]
        else:
            out[i] = 1.0
    return out


# Register standard volatility features
GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="realized_vol_60m",
        name="Realized Volatility 60m",
        category="volatility",
        lookback_bars=60,
        source_fields=("close",),
        description="Annualized close-to-close realized volatility over rolling 60-bar window",
    ),
    compute_realized_volatility,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="parkinson_vol_60m",
        name="Parkinson Volatility 60m",
        category="volatility",
        lookback_bars=60,
        source_fields=("high", "low"),
        description="Annualized Parkinson high-low range volatility over rolling 60-bar window",
    ),
    compute_parkinson_volatility,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="garman_klass_vol_60m",
        name="Garman-Klass Volatility 60m",
        category="volatility",
        lookback_bars=60,
        source_fields=("open", "high", "low", "close"),
        description="Annualized Garman-Klass OHLC volatility over rolling 60-bar window",
    ),
    compute_garman_klass_volatility,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="atr_pct_14",
        name="ATR Percentage 14",
        category="volatility",
        lookback_bars=14,
        source_fields=("high", "low", "close"),
        description="14-bar Average True Range expressed as percentage of close",
    ),
    compute_average_true_range,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="range_compression_15_60",
        name="Range Compression Ratio 15/60",
        category="volatility",
        lookback_bars=60,
        source_fields=("high", "low", "close"),
        description="Ratio of 15m ATR to 60m ATR (< 0.70 = compression squeeze)",
    ),
    compute_range_compression_ratio,
)
