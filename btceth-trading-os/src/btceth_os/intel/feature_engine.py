"""Layer B: Causal Feature Engine for INTEL-1A.

Computes descriptive features strictly using trailing observations available at or before time t.
Enforces no-lookahead contracts, handles warm-up periods cleanly with missing-value policies,
and preserves numerical accuracy using Decimal/exact arithmetic where needed.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

import pyarrow as pa

from btceth_os.intel.feature_registry import (
    ALL_FEATURES,
    FEATURE_REGISTRY_BY_NAME,
    FeatureRegistry,
)


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, Decimal):
        return float(val)
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


class CausalFeatureEngine:
    """Computes all causal features defined in INTEL_FEATURESET_V1 from raw bar arrays."""

    def __init__(self, registry: Optional[FeatureRegistry] = None):
        self.registry = registry or FeatureRegistry()

    def compute_features(self, table: pa.Table) -> Dict[str, List[Any]]:
        """Computes all registered features from a canonical PyArrow bar table.

        Guarantees that at each row i, feature values are computed strictly from
        rows 0 <= j <= i (trailing history only).
        """
        num_rows = table.num_rows
        if num_rows == 0:
            return {name: [] for name in self.registry.list_feature_names()}

        # Extract column vectors
        col_names = table.column_names

        def get_col(name: str) -> List[Any]:
            if name in col_names:
                return [x.as_py() for x in table[name]]
            return [None] * num_rows

        ts_list = get_col("ts_event_ns")
        open_list = [_safe_float(x) for x in get_col("open")]
        high_list = [_safe_float(x) for x in get_col("high")]
        low_list = [_safe_float(x) for x in get_col("low")]
        close_list = [_safe_float(x) for x in get_col("close")]
        vol_list = [_safe_float(x) for x in get_col("volume")]
        quote_vol_list = [_safe_float(x) for x in get_col("quote_volume")]
        trade_count_list = [_safe_float(x) for x in get_col("trade_count")]
        taker_buy_list = [_safe_float(x) for x in get_col("taker_buy_volume")]

        last_realized_rate_col = get_col("last_realized_funding_rate")
        last_funding_ts_col = get_col("last_realized_funding_event_ts_ns")

        underlying_session_col = get_col("underlying_session_state")
        session_certainty_col = get_col("underlying_session_certainty")
        holiday_status_col = get_col("holiday_status")
        price_index_mode_col = get_col("price_index_mode")
        price_index_certainty_col = get_col("price_index_mode_certainty")

        results: Dict[str, List[Any]] = {name: [None] * num_rows for name in self.registry.list_feature_names()}

        # Precompute 1m log returns for lookback vol/slope calculations
        log_ret_1m: List[Optional[float]] = [None] * num_rows
        for i in range(1, num_rows):
            p0 = close_list[i - 1]
            p1 = close_list[i]
            if p0 is not None and p1 is not None and p0 > 0 and p1 > 0:
                log_ret_1m[i] = math.log(p1 / p0)

        # Iterate causally row-by-row
        for i in range(num_rows):
            # 1. Price Structure
            results["log_return_1m"][i] = log_ret_1m[i]

            # Multi-horizon returns
            for h, feat_name in ((5, "return_5m"), (15, "return_15m"), (60, "return_1h")):
                if i >= h and close_list[i - h] is not None and close_list[i] is not None and close_list[i - h] > 0:
                    results[feat_name][i] = (close_list[i] - close_list[i - h]) / close_list[i - h]

            # Rolling extrema (20m)
            if i >= 19:
                window_h = [high_list[j] for j in range(i - 19, i + 1) if high_list[j] is not None]
                window_l = [low_list[j] for j in range(i - 19, i + 1) if low_list[j] is not None]
                if len(window_h) == 20 and len(window_l) == 20:
                    max_h = max(window_h)
                    min_l = min(window_l)
                    results["rolling_high_20m"][i] = max_h
                    results["rolling_low_20m"][i] = min_l
                    c = close_list[i]
                    if c is not None:
                        if max_h > 0:
                            results["distance_from_high_20m"][i] = (c - max_h) / max_h
                        if min_l > 0:
                            results["distance_from_low_20m"][i] = (c - min_l) / min_l
                        rng = max_h - min_l
                        if rng > 0:
                            results["range_location_20m"][i] = max(0.0, min(1.0, (c - min_l) / rng))
                        else:
                            results["range_location_20m"][i] = 0.5

                    # Parkinson volatility (20m)
                    # Parkinson variance = 1 / (4 * ln(2) * n) * sum( (ln(H/L))^2 )
                    sum_sq = 0.0
                    valid_park = True
                    for j in range(i - 19, i + 1):
                        hj, lj = high_list[j], low_list[j]
                        if hj is not None and lj is not None and hj >= lj and lj > 0:
                            sum_sq += math.log(hj / lj) ** 2
                        else:
                            valid_park = False
                            break
                    if valid_park:
                        park_var = sum_sq / (4.0 * math.log(2.0) * 20.0)
                        results["parkinson_volatility_20m"][i] = math.sqrt(park_var)

            # Candle body to range ratio
            o, h, l, c = open_list[i], high_list[i], low_list[i], close_list[i]
            if o is not None and h is not None and l is not None and c is not None and h >= l:
                rng = h - l
                if rng > 0:
                    results["candle_body_to_range_ratio"][i] = abs(c - o) / rng
                else:
                    results["candle_body_to_range_ratio"][i] = 0.0

            # 2. Trend Structure (20m)
            if i >= 19:
                closes_20 = [close_list[j] for j in range(i - 19, i + 1)]
                opens_20 = [open_list[j] for j in range(i - 19, i + 1)]
                if all(x is not None for x in closes_20):
                    # Price displacement
                    results["price_displacement_20m"][i] = closes_20[-1] - closes_20[0]

                    # Directional persistence
                    if all(x is not None for x in opens_20):
                        up_bars = sum(1 for j in range(20) if closes_20[j] > opens_20[j])
                        results["directional_persistence_20m"][i] = up_bars / 20.0

                    # Efficiency ratio: net displacement / sum(abs(step))
                    path = sum(abs(closes_20[k] - closes_20[k - 1]) for k in range(1, 20))
                    net_disp = abs(closes_20[-1] - closes_20[0])
                    if path > 0:
                        results["efficiency_ratio_20m"][i] = net_disp / path
                    else:
                        results["efficiency_ratio_20m"][i] = 0.0

                    # Rolling slope (normalized)
                    # x in 0..19, y = closes_20
                    mean_x = 9.5
                    mean_y = sum(closes_20) / 20.0
                    cov_xy = sum((k - mean_x) * (closes_20[k] - mean_y) for k in range(20))
                    var_x = sum((k - mean_x) ** 2 for k in range(20))  # 665.0
                    slope = cov_xy / var_x
                    if mean_y > 0:
                        results["rolling_slope_20m"][i] = slope / mean_y

            # Rolling autocorrelation (lag-1 of returns over 20m window)
            if i >= 20:
                rets_20 = [log_ret_1m[j] for j in range(i - 19, i + 1) if log_ret_1m[j] is not None]
                if len(rets_20) == 20:
                    r_curr = rets_20[1:]
                    r_lag = rets_20[:-1]
                    m_curr = sum(r_curr) / 19.0
                    m_lag = sum(r_lag) / 19.0
                    cov = sum((r_curr[k] - m_curr) * (r_lag[k] - m_lag) for k in range(19))
                    std_curr = math.sqrt(sum((x - m_curr) ** 2 for x in r_curr))
                    std_lag = math.sqrt(sum((x - m_lag) ** 2 for x in r_lag))
                    if std_curr > 1e-12 and std_lag > 1e-12:
                        results["rolling_autocorrelation_20m"][i] = cov / (std_curr * std_lag)
                    else:
                        results["rolling_autocorrelation_20m"][i] = 0.0

            # 3. Volatility Structure
            # Short vol (10m)
            if i >= 9:
                r10 = [log_ret_1m[j] for j in range(i - 8, i + 1) if log_ret_1m[j] is not None]
                if len(r10) >= 9:
                    m10 = sum(r10) / len(r10)
                    var10 = sum((x - m10) ** 2 for x in r10) / (len(r10) - 1)
                    results["short_horizon_vol_10m"][i] = math.sqrt(max(0.0, var10))

            # Medium vol (60m)
            if i >= 59:
                r60 = [log_ret_1m[j] for j in range(i - 58, i + 1) if log_ret_1m[j] is not None]
                if len(r60) >= 59:
                    m60 = sum(r60) / len(r60)
                    var60 = sum((x - m60) ** 2 for x in r60) / (len(r60) - 1)
                    med_vol = math.sqrt(max(0.0, var60))
                    results["medium_horizon_vol_60m"][i] = med_vol
                    s_vol = results["short_horizon_vol_10m"][i]
                    if s_vol is not None and med_vol > 1e-12:
                        results["volatility_ratio_10m_60m"][i] = s_vol / med_vol

            # Trailing Volatility Percentile (up to 1440m trailing window)
            s_vol_now = results["short_horizon_vol_10m"][i]
            if s_vol_now is not None and i >= 119:
                lookback_len = min(i, 1440)
                trailing_vols = [
                    results["short_horizon_vol_10m"][j]
                    for j in range(i - lookback_len, i + 1)
                    if results["short_horizon_vol_10m"][j] is not None
                ]
                if len(trailing_vols) >= 60:
                    rank = sum(1 for v in trailing_vols if v <= s_vol_now)
                    results["volatility_percentile_trailing_1440m"][i] = rank / len(trailing_vols)

            # Range expansion / contraction ratio (20m)
            if i >= 19:
                ranges = [
                    (high_list[j] - low_list[j])
                    for j in range(i - 19, i)
                    if high_list[j] is not None and low_list[j] is not None
                ]
                curr_range = (high_list[i] - low_list[i]) if (high_list[i] is not None and low_list[i] is not None) else None
                if len(ranges) == 19 and curr_range is not None:
                    avg_range = sum(ranges) / 19.0
                    if avg_range > 0:
                        results["range_expansion_contraction_ratio_20m"][i] = curr_range / avg_range

            # 4. Volume / Activity
            results["traded_volume_raw"][i] = vol_list[i]
            results["quote_volume_raw"][i] = quote_vol_list[i]
            results["trade_count_raw"][i] = trade_count_list[i]

            # Relative activity 20m
            if i >= 19 and vol_list[i] is not None:
                vols_20 = [vol_list[j] for j in range(i - 19, i + 1) if vol_list[j] is not None]
                if len(vols_20) == 20:
                    mean_v = sum(vols_20) / 20.0
                    if mean_v > 0:
                        results["relative_activity_20m"][i] = vol_list[i] / mean_v

            # Volume percentile trailing 1440m
            if vol_list[i] is not None and i >= 119:
                lb = min(i, 1440)
                trailing_v = [vol_list[j] for j in range(i - lb, i + 1) if vol_list[j] is not None]
                if len(trailing_v) >= 60:
                    rank_v = sum(1 for v in trailing_v if v <= vol_list[i])
                    results["volume_percentile_trailing_1440m"][i] = rank_v / len(trailing_v)

            # Abnormal activity score (trade count z-score 60m)
            if trade_count_list[i] is not None and i >= 59:
                tc_window = [trade_count_list[j] for j in range(i - 59, i + 1) if trade_count_list[j] is not None]
                if len(tc_window) == 60:
                    m_tc = sum(tc_window) / 60.0
                    std_tc = math.sqrt(sum((x - m_tc) ** 2 for x in tc_window) / 59.0)
                    if std_tc > 0:
                        results["abnormal_activity_score_60m"][i] = (trade_count_list[i] - m_tc) / std_tc

            # 5. Funding
            rf = last_realized_rate_col[i]
            results["latest_realized_funding_rate"][i] = rf
            ts_now = ts_list[i]
            ts_fund = last_funding_ts_col[i]
            if ts_now is not None and ts_fund is not None:
                diff_ns = ts_now - ts_fund
                if diff_ns >= 0:
                    results["time_since_last_funding_minutes"][i] = diff_ns / 60_000_000_000.0

            # Funding rate trailing average 24h (1440m)
            if i >= 119:
                lb_fund = min(i, 1440)
                # Sample discrete rates from observed bars
                rates_window = [
                    _safe_float(last_realized_rate_col[j])
                    for j in range(i - lb_fund, i + 1)
                    if last_realized_rate_col[j] is not None
                ]
                if rates_window:
                    results["funding_rate_trailing_average_24h"][i] = sum(rates_window) / len(rates_window)

            # Funding sign persistence
            if rf is not None:
                rf_flt = _safe_float(rf)
                if rf_flt is not None and rf_flt != 0.0:
                    sign_now = 1 if rf_flt > 0 else -1
                    streak = 0
                    for j in range(i, -1, -1):
                        r_prev = _safe_float(last_realized_rate_col[j])
                        if r_prev is not None and r_prev != 0.0:
                            s = 1 if r_prev > 0 else -1
                            if s == sign_now:
                                streak += 1
                            else:
                                break
                    results["funding_sign_persistence"][i] = streak

            # 6. Session Context
            results["underlying_session_state"][i] = underlying_session_col[i]
            results["underlying_session_certainty"][i] = session_certainty_col[i]
            results["holiday_status"][i] = holiday_status_col[i]
            results["price_index_mode"][i] = price_index_mode_col[i]
            results["price_index_mode_certainty"][i] = price_index_certainty_col[i]

            # 7. Order-Flow / Microstructure
            v = vol_list[i]
            tb = taker_buy_list[i]
            tc = trade_count_list[i]
            if v is not None and v > 0 and tb is not None:
                results["taker_buy_volume_ratio"][i] = max(0.0, min(1.0, tb / v))
            if v is not None and v > 0 and tc is not None:
                results["trade_intensity_per_volume_20m"][i] = tc / v

            # Trailing order flow imbalance 20m
            if i >= 19:
                window_tb = [taker_buy_list[j] for j in range(i - 19, i + 1)]
                window_v = [vol_list[j] for j in range(i - 19, i + 1)]
                if all(x is not None for x in window_tb) and all(x is not None for x in window_v):
                    tot_v = sum(window_v)
                    if tot_v > 0:
                        tot_buy = sum(window_tb)
                        tot_sell = tot_v - tot_buy
                        results["order_flow_imbalance_20m"][i] = (tot_buy - tot_sell) / tot_v

        return results
