"""Data Quality Assessment Gate for INTEL-1A.

Evaluates raw and pre-feature market data for causal integrity, completeness,
plausibility, and session sanity before computing intelligence states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

import pyarrow as pa


class DataQualityStatus(str, Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    UNRELIABLE = "UNRELIABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BarDataQualityAssessment:
    status: str
    reasons: List[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        return self.status in (DataQualityStatus.GOOD.value, DataQualityStatus.DEGRADED.value)


class DataQualityGate:
    """Evaluates market data stream rows or bar tables for physical and logical data quality."""

    @staticmethod
    def assess_bar(
        ts_ns: int,
        prev_ts_ns: Optional[int],
        open_p: Optional[float],
        high_p: Optional[float],
        low_p: Optional[float],
        close_p: Optional[float],
        volume: Optional[float],
        trade_count: Optional[int] = None,
        holiday_status: Optional[str] = None,
        price_index_mode_certainty: Optional[str] = None,
        expected_step_ns: int = 60_000_000_000,
    ) -> BarDataQualityAssessment:
        reasons: List[str] = []
        is_unreliable = False
        is_degraded = False

        # 1. Timestamp checks
        if prev_ts_ns is not None:
            if ts_ns < prev_ts_ns:
                reasons.append("NON_MONOTONIC_TIMESTAMP")
                is_unreliable = True
            elif ts_ns == prev_ts_ns:
                reasons.append("DUPLICATE_TIMESTAMP")
                is_unreliable = True
            elif ts_ns - prev_ts_ns > expected_step_ns:
                reasons.append(f"MISSING_BAR_GAP_{((ts_ns - prev_ts_ns) // 1_000_000_000)}S")
                is_degraded = True

        # 2. Impossible OHLC checks
        if any(p is None for p in (open_p, high_p, low_p, close_p)):
            reasons.append("NULL_OHLC_VALUE")
            is_unreliable = True
        else:
            if high_p < low_p:
                reasons.append("IMPOSSIBLE_OHLC_HIGH_LESS_THAN_LOW")
                is_unreliable = True
            if open_p < low_p or open_p > high_p:
                reasons.append("IMPOSSIBLE_OHLC_OPEN_OUTSIDE_HIGH_LOW")
                is_unreliable = True
            if close_p < low_p or close_p > high_p:
                reasons.append("IMPOSSIBLE_OHLC_CLOSE_OUTSIDE_HIGH_LOW")
                is_unreliable = True
            if open_p <= 0 or close_p <= 0:
                reasons.append("NON_POSITIVE_PRICE")
                is_unreliable = True

        # 3. Volume and count checks
        if volume is None or volume < 0:
            reasons.append("NEGATIVE_OR_NULL_VOLUME")
            is_unreliable = True
        elif volume == 0.0 and trade_count is not None and trade_count > 0:
            reasons.append("ZERO_VOLUME_WITH_POSITIVE_TRADE_COUNT")
            is_degraded = True

        if trade_count is not None and trade_count < 0:
            reasons.append("NEGATIVE_TRADE_COUNT")
            is_unreliable = True

        # 4. Session uncertainty
        if holiday_status == "NOT_IMPLEMENTED" and price_index_mode_certainty == "HOLIDAY_UNKNOWN":
            reasons.append("HOLIDAY_STATE_UNPROVEN")
            is_degraded = True

        if is_unreliable:
            return BarDataQualityAssessment(status=DataQualityStatus.UNRELIABLE.value, reasons=reasons)
        if is_degraded:
            return BarDataQualityAssessment(status=DataQualityStatus.DEGRADED.value, reasons=reasons)
        return BarDataQualityAssessment(status=DataQualityStatus.GOOD.value, reasons=[])

    @classmethod
    def assess_table(cls, table: pa.Table) -> List[BarDataQualityAssessment]:
        """Assesses an entire PyArrow table causally bar-by-bar."""
        num_rows = table.num_rows
        if num_rows == 0:
            return []

        col_names = table.column_names

        def get_col(name: str) -> List[Any]:
            if name in col_names:
                return [x.as_py() for x in table[name]]
            return [None] * num_rows

        ts_list = get_col("ts_event_ns")
        open_list = get_col("open")
        high_list = get_col("high")
        low_list = get_col("low")
        close_list = get_col("close")
        vol_list = get_col("volume")
        tc_list = get_col("trade_count")
        hol_list = get_col("holiday_status")
        pim_list = get_col("price_index_mode_certainty")

        assessments: List[BarDataQualityAssessment] = []
        for i in range(num_rows):
            prev_ts = ts_list[i - 1] if i > 0 else None
            ass = cls.assess_bar(
                ts_ns=ts_list[i],
                prev_ts_ns=prev_ts,
                open_p=float(open_list[i]) if open_list[i] is not None else None,
                high_p=float(high_list[i]) if high_list[i] is not None else None,
                low_p=float(low_list[i]) if low_list[i] is not None else None,
                close_p=float(close_list[i]) if close_list[i] is not None else None,
                volume=float(vol_list[i]) if vol_list[i] is not None else None,
                trade_count=int(tc_list[i]) if tc_list[i] is not None else None,
                holiday_status=hol_list[i],
                price_index_mode_certainty=pim_list[i],
            )
            assessments.append(ass)
        return assessments
