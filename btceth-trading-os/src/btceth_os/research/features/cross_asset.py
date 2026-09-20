from __future__ import annotations

import math
from typing import Sequence

from .registry import GLOBAL_FEATURE_REGISTRY, FeatureMetadata


def compute_eth_btc_ratio(btc_closes: Sequence[float], eth_closes: Sequence[float]) -> list[float]:
    """ETH / BTC price ratio at each synchronized point-in-time timestamp."""
    n = min(len(btc_closes), len(eth_closes))
    out = [0.0] * n
    for i in range(n):
        if btc_closes[i] > 0:
            out[i] = eth_closes[i] / btc_closes[i]
    return out


def compute_relative_return_diff(
    btc_returns: Sequence[float],
    eth_returns: Sequence[float],
) -> list[float]:
    """Relative return spread: ETH return minus BTC return."""
    n = min(len(btc_returns), len(eth_returns))
    out = [0.0] * n
    for i in range(n):
        out[i] = eth_returns[i] - btc_returns[i]
    return out


def compute_rolling_correlation(
    btc_returns: Sequence[float],
    eth_returns: Sequence[float],
    lookback: int = 60,
) -> list[float]:
    """Rolling Pearson correlation between BTC and ETH returns over `lookback` bars."""
    if lookback < 3:
        raise ValueError("lookback must be at least 3")
    n = min(len(btc_returns), len(eth_returns))
    out = [0.0] * n

    for i in range(lookback - 1, n):
        win_x = btc_returns[i - lookback + 1 : i + 1]
        win_y = eth_returns[i - lookback + 1 : i + 1]
        mean_x = sum(win_x) / lookback
        mean_y = sum(win_y) / lookback

        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(win_x, win_y))
        var_x = sum((x - mean_x) ** 2 for x in win_x)
        var_y = sum((y - mean_y) ** 2 for y in win_y)

        denom = math.sqrt(var_x * var_y)
        if denom > 1e-12:
            corr = cov / denom
            out[i] = max(-1.0, min(1.0, corr))
        else:
            out[i] = 0.0
    return out


def compute_ratio_zscore(ratio: Sequence[float], lookback: int = 1440) -> list[float]:
    """Point-in-time rolling z-score of the ETH/BTC price ratio."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    n = len(ratio)
    out = [0.0] * n

    for i in range(lookback - 1, n):
        window = ratio[i - lookback + 1 : i + 1]
        mean_val = sum(window) / lookback
        var = sum((x - mean_val) ** 2 for x in window) / (lookback - 1)
        std_val = math.sqrt(var)
        if std_val > 1e-12:
            out[i] = (ratio[i] - mean_val) / std_val
        else:
            out[i] = 0.0
    return out


# Register standard cross-asset features
GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="eth_btc_ratio",
        name="ETH / BTC Ratio",
        category="cross_asset",
        lookback_bars=1,
        source_fields=("close_btc", "close_eth"),
        description="ETH/BTC price ratio at each synchronized minute bar",
    ),
    compute_eth_btc_ratio,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="eth_btc_rel_return",
        name="ETH vs BTC Relative Return",
        category="cross_asset",
        lookback_bars=1,
        source_fields=("ret_btc", "ret_eth"),
        description="Difference between ETH return and BTC return",
    ),
    compute_relative_return_diff,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="btc_eth_corr_60m",
        name="BTC-ETH Rolling Correlation 60m",
        category="cross_asset",
        lookback_bars=60,
        source_fields=("ret_btc", "ret_eth"),
        description="60-minute rolling Pearson correlation between BTC and ETH returns",
    ),
    compute_rolling_correlation,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="eth_btc_ratio_zscore_24h",
        name="ETH/BTC Ratio Z-Score 24h",
        category="cross_asset",
        lookback_bars=1440,
        source_fields=("eth_btc_ratio",),
        description="24-hour rolling z-score of the ETH/BTC price ratio",
    ),
    compute_ratio_zscore,
)
