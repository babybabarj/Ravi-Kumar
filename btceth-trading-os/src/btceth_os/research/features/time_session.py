from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from .registry import GLOBAL_FEATURE_REGISTRY, FeatureMetadata


def timestamp_to_session_info(ts_ns: int) -> tuple[int, int, int, int, int]:
    """Return (hour, day_of_week, is_asia, is_europe, is_us)."""
    dt = datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=timezone.utc)
    hour = dt.hour
    dow = dt.weekday()  # 0=Monday, 6=Sunday

    is_asia = 1 if 0 <= hour < 8 else 0
    is_europe = 1 if 7 <= hour < 16 else 0
    is_us = 1 if 13 <= hour < 21 else 0

    return hour, dow, is_asia, is_europe, is_us


def compute_session_flags(timestamps_ns: Sequence[int]) -> tuple[list[int], list[int], list[int], list[int]]:
    """Return lists for (is_asia, is_europe, is_us, is_weekend)."""
    n = len(timestamps_ns)
    asia = [0] * n
    europe = [0] * n
    us = [0] * n
    weekend = [0] * n

    for i, ts in enumerate(timestamps_ns):
        hour, dow, a, e, u = timestamp_to_session_info(ts)
        asia[i] = a
        europe[i] = e
        us[i] = u
        weekend[i] = 1 if dow in (5, 6) else 0

    return asia, europe, us, weekend


# Register time session features
GLOBAL_FEATURE_REGISTRY.register(
    FeatureMetadata(
        feature_id="session_flags",
        name="Trading Session Indicators",
        category="time_session",
        lookback_bars=1,
        source_fields=("ts_event_ns",),
        description="Point-in-time binary session membership (Asia 00-08 UTC, Europe 07-16 UTC, US 13-21 UTC, Weekend)",
    ),
    lambda ts: compute_session_flags(ts)[0],  # Returns asia by default
)
