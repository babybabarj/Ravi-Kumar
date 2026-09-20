from __future__ import annotations

import pytest

from btceth_os.research.market_brain import (
    CompositeRegime,
    FundingDimension,
    LiquidityDimension,
    MarketBrain,
    OpenInterestDimension,
    StressDimension,
    TrendDimension,
    VolatilityDimension,
)


def test_volatility_expansion_not_labeled_oi():
    # High compression ratio (1.45 >= 1.35) without OI data
    st = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.35,
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.45,
        rolling_drawdown_2h=0.01,
        open_interest_delta_pct=None,
    )
    # Must be VOLATILITY_EXPANSION, NEVER fake OI_EXPANSION!
    assert st.regime == CompositeRegime.VOLATILITY_EXPANSION
    assert st.regime != CompositeRegime.OI_EXPANSION
    assert st.volatility_state == VolatilityDimension.VOLATILITY_EXPANSION
    assert st.oi_state == OpenInterestDimension.UNAVAILABLE


def test_range_compression_not_labeled_oi_unwind():
    # Low compression ratio (0.55 <= 0.65) and flat slope without OI data
    st = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.25,
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=0.55,
        rolling_drawdown_2h=0.01,
        open_interest_delta_pct=None,
    )
    # Must be RANGE_COMPRESSION, NEVER fake OI_UNWIND!
    assert st.regime == CompositeRegime.RANGE_COMPRESSION
    assert st.regime != CompositeRegime.OI_UNWIND
    assert st.volatility_state == VolatilityDimension.VOLATILITY_COMPRESSION
    assert st.oi_state == OpenInterestDimension.UNAVAILABLE


def test_true_open_interest_requires_verified_oi():
    # With verified positive OI growth (+8%)
    st_exp = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.35,
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
        open_interest_delta_pct=0.08,
    )
    assert st_exp.oi_state == OpenInterestDimension.OI_EXPANSION
    assert st_exp.regime == CompositeRegime.OI_EXPANSION

    # With verified negative OI decline (-8%)
    st_unw = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.35,
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
        open_interest_delta_pct=-0.08,
    )
    assert st_unw.oi_state == OpenInterestDimension.OI_UNWIND
    assert st_unw.regime == CompositeRegime.OI_UNWIND


def test_market_stress_semantics():
    # Realized vol = 0.90 without order book data
    st = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.005,  # Upward trending
        volatility_realized_60m=0.90,  # Extreme vol
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
    )
    # Volatility spike is MARKET_STRESS, not LIQUIDITY_STRESS
    assert st.regime == CompositeRegime.MARKET_STRESS
    assert st.stress_state == StressDimension.MARKET_STRESS
    assert st.liquidity_state == LiquidityDimension.UNAVAILABLE
    # Compositional state preserves trend: market was simultaneously an uptrend!
    assert st.trend_state == TrendDimension.UPTREND


def test_funding_threshold_units():
    # Standard funding rate is ~1 bp (0.0001)
    # Threshold is 30 bps (0.0030)
    assert MarketBrain.FUNDING_EXTREME_ABS_BPS == 30.0
    assert MarketBrain.FUNDING_EXTREME_ABS == 0.0030

    # Test 35 bps (0.0035 > 0.0030)
    st = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.30,
        funding_rate=0.0035,  # 35 bps
        funding_zscore=1.5,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
    )
    assert st.funding_state == FundingDimension.EXTREME_POSITIVE
    assert st.regime == CompositeRegime.FUNDING_EXTREME
