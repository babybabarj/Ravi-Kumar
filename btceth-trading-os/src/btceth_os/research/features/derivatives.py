from __future__ import annotations

import bisect
import math
from typing import Sequence

from .registry import GLOBAL_FEATURE_REGISTRY, FeatureMetadata


EIGHT_HOURS_NS = 8 * 3600 * 1_000_000_000


def align_funding_rates_to_klines(
    kline_ts_ns: Sequence[int],
    funding_ts_ns: Sequence[int],
    funding_rates: Sequence[float],
) -> list[float]:
    """Point-in-time alignment: each kline timestamp receives the most recent known funding rate prior to or at its timestamp."""
    if len(funding_ts_ns) != len(funding_rates):
        raise ValueError("funding_ts_ns and funding_rates must have equal length")
    if not funding_ts_ns:
        return [0.0] * len(kline_ts_ns)

    # Validate that funding_ts_ns is sorted
    for i in range(1, len(funding_ts_ns)):
        if funding_ts_ns[i] < funding_ts_ns[i - 1]:
            raise ValueError("funding_ts_ns must be sorted")

    aligned = [0.0] * len(kline_ts_ns)
    for i, ts in enumerate(kline_ts_ns):
        idx = bisect.bisect_right(funding_ts_ns, ts) - 1
        if idx >= 0:
            aligned[i] = funding_rates[idx]
        else:
            aligned[i] = funding_rates[0]
    return aligned


def compute_funding_zscore(
    aligned_funding_rates: Sequence[float],
    lookback_bars: int = 1440,
) -> list[float]:
    """Point-in-time rolling z-score of funding rate over rolling window (e.g. 1440 1m bars = 24h)."""
    if lookback_bars < 2:
        raise ValueError("lookback_bars must be at least 2")
    n = len(aligned_funding_rates)
    out = [0.0] * n

    for i in range(lookback_bars - 1, n):
        window = aligned_funding_rates[i - lookback_bars + 1 : i + 1]
        mean_val = sum(window) / lookback_bars
        var = sum((x - mean_val) ** 2 for x in window) / (lookback_bars - 1)
        std_val = math.sqrt(var)
        if std_val > 1e-10:
            out[i] = (aligned_funding_rates[i] - mean_val) / std_val
        else:
            out[i] = 0.0
    return out


def compute_funding_percentile(
    aligned_funding_rates: Sequence[float],
    lookback_bars: int = 1440,
) -> list[float]:
    """Point-in-time rolling percentile [0.0, 1.0] of funding rate over lookback window."""
    if lookback_bars < 1:
        raise ValueError("lookback_bars must be at least 1")
    n = len(aligned_funding_rates)
    out = [0.5] * n

    for i in range(lookback_bars - 1, n):
        curr = aligned_funding_rates[i]
        window = aligned_funding_rates[i - lookback_bars + 1 : i + 1]
        less_count = sum(1 for x in window if x < curr)
        equal_count = sum(1 for x in window if x == curr)
        out[i] = (less_count + 0.5 * equal_count) / lookback_bars
    return out


def compute_minutes_to_funding(kline_ts_ns: Sequence[int]) -> list[float]:
    """Deterministic minutes remaining until the next 8-hour funding settlement (00:00, 08:00, 16:00 UTC)."""
    out = [0.0] * len(kline_ts_ns)
    for i, ts in enumerate(kline_ts_ns):
        cycle_pos_ns = ts % EIGHT_HOURS_NS
        rem_ns = (EIGHT_HOURS_NS - cycle_pos_ns) % EIGHT_HOURS_NS
        out[i] = rem_ns / (60.0 * 1_000_000_000.0)
    return out


# Register standard derivatives features
GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="funding_rate_current",
        name="Current Funding Rate",
        category="derivatives",
        lookback_bars=1,
        source_fields=("funding_rate",),
        description="Point-in-time effective 8h funding rate for the current bar",
    ),
    align_funding_rates_to_klines,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="funding_zscore_24h",
        name="Funding Rate Z-Score 24h",
        category="derivatives",
        lookback_bars=1440,
        source_fields=("funding_rate",),
        description="24-hour rolling z-score of the effective funding rate",
    ),
    compute_funding_zscore,
)

GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="minutes_to_funding",
        name="Minutes to Next Funding",
        category="derivatives",
        lookback_bars=1,
        source_fields=("ts_event_ns",),
        description="Minutes remaining until the next scheduled 8h funding event",
    ),
    compute_minutes_to_funding,
)
