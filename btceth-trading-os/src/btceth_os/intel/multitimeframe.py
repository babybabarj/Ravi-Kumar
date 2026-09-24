"""Layer K: Multi-Timeframe Consistency Auditor for INTEL-1B.

Validates multi-timeframe aggregation and resampling consistency across:
- 1m, 5m, 15m, 1h, 4h, 1d
Enforcing:
1. Strict Bar Close Rule: Higher timeframe observations become available ONLY after bucket completion.
2. Incomplete Final Bucket: Never published prior to full duration expiry.
3. Source Completeness: Tracks constituent bar counts per aggregate interval.
4. Zero Future Leakage: Asserting all availability timestamps obey causality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

from .resampler import CausalResampler, TIMEFRAME_STEP_NS, AggregatedBar


@dataclass(frozen=True)
class MultiTimeframeAuditResult:
    timeframe: str
    step_ns: int
    total_source_bars: int
    aggregated_bars_count: int
    first_available_ts_ns: Optional[int]
    last_available_ts_ns: Optional[int]
    incomplete_final_bucket_suppressed: bool
    mean_constituent_bars: float
    expected_constituent_bars: int
    completeness_ratio: float
    zero_future_leakage: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MultiTimeframeAuditor:
    """Audits multi-timeframe resampling consistency and causal availability guarantees."""

    EXPECTED_CONSTITUENTS_1M: Dict[str, int] = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }

    @classmethod
    def audit_timeframe(
        cls,
        timeframe: str,
        ts_ns_list: Sequence[int],
        open_list: Sequence[float],
        high_list: Sequence[float],
        low_list: Sequence[float],
        close_list: Sequence[float],
        volume_list: Sequence[float],
        trade_count_list: Optional[Sequence[int]] = None,
    ) -> MultiTimeframeAuditResult:
        if timeframe not in TIMEFRAME_STEP_NS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        step_ns = TIMEFRAME_STEP_NS[timeframe]
        n_src = len(ts_ns_list)

        if n_src == 0:
            return MultiTimeframeAuditResult(
                timeframe=timeframe,
                step_ns=step_ns,
                total_source_bars=0,
                aggregated_bars_count=0,
                first_available_ts_ns=None,
                last_available_ts_ns=None,
                incomplete_final_bucket_suppressed=True,
                mean_constituent_bars=0.0,
                expected_constituent_bars=cls.EXPECTED_CONSTITUENTS_1M.get(timeframe, 1),
                completeness_ratio=1.0,
                zero_future_leakage=True,
            )

        bars = CausalResampler.resample(
            timeframe=timeframe,
            ts_ns_list=ts_ns_list,
            open_list=open_list,
            high_list=high_list,
            low_list=low_list,
            close_list=close_list,
            volume_list=volume_list,
            trade_count_list=trade_count_list,
        )

        n_agg = len(bars)
        first_avail = bars[0].period_end_ns if n_agg > 0 else None
        last_avail = bars[-1].period_end_ns if n_agg > 0 else None

        # Verify bar close rule: each bar's availability timestamp is strictly at or after period end
        zero_leakage = all(b.period_end_ns >= (b.period_start_ns + step_ns) for b in bars)

        # Check incomplete final bucket: if the last source bar has not crossed the final bucket end,
        # ensure no partial bar was published
        last_src_ts = ts_ns_list[-1]
        last_bucket_start = (last_src_ts // step_ns) * step_ns
        last_bucket_end = last_bucket_start + step_ns

        # An uncompleted bucket ends strictly after the last available source bar
        incomplete_suppressed = True
        if n_agg > 0:
            if last_avail is not None and last_avail > (last_src_ts + 60_000_000_000):
                # The published bar claims to cover past what was available
                incomplete_suppressed = False

        expected_const = cls.EXPECTED_CONSTITUENTS_1M.get(timeframe, 1)
        mean_const = sum(b.constituent_bars_count for b in bars) / n_agg if n_agg > 0 else 0.0
        comp_ratio = mean_const / expected_const if expected_const > 0 else 1.0

        return MultiTimeframeAuditResult(
            timeframe=timeframe,
            step_ns=step_ns,
            total_source_bars=n_src,
            aggregated_bars_count=n_agg,
            first_available_ts_ns=first_avail,
            last_available_ts_ns=last_avail,
            incomplete_final_bucket_suppressed=incomplete_suppressed,
            mean_constituent_bars=round(mean_const, 2),
            expected_constituent_bars=expected_const,
            completeness_ratio=round(comp_ratio, 4),
            zero_future_leakage=zero_leakage,
        )
