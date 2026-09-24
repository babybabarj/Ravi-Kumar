"""Causal Timeframe Resampling Policy for INTEL-1A.

Aggregates 1-minute bars into higher timeframes (5m, 15m, 1h, 4h, 1d) with strict causality:
an aggregated period becomes visible ONLY after its final constituent bar has completed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class AggregatedBar:
    period_start_ns: int
    period_end_ns: int  # Timestamp when the bar becomes available
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    constituent_bars_count: int


TIMEFRAME_STEP_NS: Dict[str, int] = {
    "1m": 60_000_000_000,
    "5m": 300_000_000_000,
    "15m": 900_000_000_000,
    "1h": 3600_000_000_000,
    "4h": 14400_000_000_000,
    "1d": 86400_000_000_000,
}


class CausalResampler:
    """Aggregates 1m bars into higher timeframe intervals while guaranteeing strict availability timestamps."""

    @staticmethod
    def resample(
        timeframe: str,
        ts_ns_list: Sequence[int],
        open_list: Sequence[float],
        high_list: Sequence[float],
        low_list: Sequence[float],
        close_list: Sequence[float],
        volume_list: Sequence[float],
        trade_count_list: Optional[Sequence[int]] = None,
    ) -> List[AggregatedBar]:
        if timeframe not in TIMEFRAME_STEP_NS:
            raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {list(TIMEFRAME_STEP_NS.keys())}")

        step_ns = TIMEFRAME_STEP_NS[timeframe]
        n = len(ts_ns_list)
        if n == 0:
            return []

        tc_list = trade_count_list or [0] * n
        aggregated: List[AggregatedBar] = []

        current_bucket_start: Optional[int] = None
        bucket_opens: List[float] = []
        bucket_highs: List[float] = []
        bucket_lows: List[float] = []
        bucket_closes: List[float] = []
        bucket_vols: List[float] = []
        bucket_tcs: List[int] = []

        for i in range(n):
            ts = ts_ns_list[i]
            bucket_start = (ts // step_ns) * step_ns

            if current_bucket_start is not None and bucket_start != current_bucket_start:
                # Flush previous completed bucket
                bar = AggregatedBar(
                    period_start_ns=current_bucket_start,
                    period_end_ns=current_bucket_start + step_ns,  # Available only after period closes
                    timeframe=timeframe,
                    open=bucket_opens[0],
                    high=max(bucket_highs),
                    low=min(bucket_lows),
                    close=bucket_closes[-1],
                    volume=sum(bucket_vols),
                    trade_count=sum(bucket_tcs),
                    constituent_bars_count=len(bucket_opens),
                )
                aggregated.append(bar)
                bucket_opens = []
                bucket_highs = []
                bucket_lows = []
                bucket_closes = []
                bucket_vols = []
                bucket_tcs = []

            current_bucket_start = bucket_start
            bucket_opens.append(open_list[i])
            bucket_highs.append(high_list[i])
            bucket_lows.append(low_list[i])
            bucket_closes.append(close_list[i])
            bucket_vols.append(volume_list[i])
            bucket_tcs.append(tc_list[i])

        # Note: In-progress incomplete final bucket is intentionally NOT emitted to guarantee causality
        return aggregated
