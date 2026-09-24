import json
import pytest
from pathlib import Path

from btceth_os.trade_board import (
    TradeDecision,
    evaluate_asset_trade_board,
    evaluate_all_assets_trade_board,
    read_shadow_bot_telemetry,
)
from btceth_os.intel.market_state import (
    MarketStateSnapshot,
    MarketQualityRegime,
    TrendRegime,
    VolatilityRegime,
    FundingRegime,
    LiquidityActivityRegime,
)


def test_volatility_compression_breakout_long():
    """VP-007: Volatility compression coiling with neutral/negative funding triggers LONG."""
    features = {
        "short_horizon_vol_10m": 0.010,
        "volatility_percentile_trailing_1440m": 0.14,
        "efficiency_ratio_20m": 0.45,
        "directional_persistence_20m": 0.70,
        "rolling_slope_20m": 0.0004,
        "volume_percentile_trailing_1440m": 0.50,
        "abnormal_activity_score_60m": 0.2,
        "latest_realized_funding_rate": -0.00002,
        "data_quality_status": "GOOD",
    }
    decision = evaluate_asset_trade_board(
        asset="BTCUSDT",
        current_price=64000.0,
        features=features,
    )
    assert decision.action == "TAKE_LONG"
    assert decision.display_action == "TAKE TRADE: LONG"
    assert decision.primary_rule_id == "VP-007"
    assert decision.setup_name == "VOLATILITY_COMPRESSION_BREAKOUT"
    assert decision.confidence >= 70.0
    assert decision.stop_loss < 64000.0
    assert decision.take_profit_1 > 64000.0
    assert decision.take_profit_2 > decision.take_profit_1
    assert decision.risk_reward_ratio >= 1.8


def test_negative_funding_short_squeeze_long():
    """VP-011: Negative funding with stabilizing price triggers short squeeze LONG."""
    features = {
        "short_horizon_vol_10m": 0.015,
        "volatility_percentile_trailing_1440m": 0.45,
        "efficiency_ratio_20m": 0.35,
        "directional_persistence_20m": 0.55,
        "rolling_slope_20m": 0.0001,
        "volume_percentile_trailing_1440m": 0.75,
        "abnormal_activity_score_60m": 1.2,
        "latest_realized_funding_rate": -0.00035,
        "data_quality_status": "GOOD",
    }
    decision = evaluate_asset_trade_board(
        asset="BTCUSDT",
        current_price=63000.0,
        features=features,
    )
    assert decision.action == "TAKE_LONG"
    assert decision.display_action == "TAKE TRADE: LONG"
    assert decision.primary_rule_id == "VP-011"
    assert decision.setup_name == "NEGATIVE_FUNDING_SHORT_SQUEEZE"
    assert decision.confidence >= 80.0
    assert any("VP-011" in r for r in decision.supporting_reasons)


def test_trend_continuation_short():
    """VP-004 / VP-009: Downward trend structure triggers SHORT."""
    features = {
        "short_horizon_vol_10m": 0.020,
        "volatility_percentile_trailing_1440m": 0.65,
        "efficiency_ratio_20m": 0.48,
        "directional_persistence_20m": 0.25,
        "rolling_slope_20m": -0.0008,
        "volume_percentile_trailing_1440m": 0.60,
        "abnormal_activity_score_60m": 0.5,
        "latest_realized_funding_rate": 0.00005,
        "data_quality_status": "GOOD",
    }
    decision = evaluate_asset_trade_board(
        asset="ETHUSDT",
        current_price=2600.0,
        features=features,
    )
    assert decision.action == "TAKE_SHORT"
    assert decision.display_action == "TAKE TRADE: SHORT"
    assert decision.primary_rule_id == "VP-004"
    assert decision.setup_name == "TREND_BREAKDOWN_CONTINUATION"
    assert decision.confidence >= 70.0
    assert decision.stop_loss > 2600.0
    assert decision.take_profit_1 < 2600.0
    assert decision.take_profit_2 < decision.take_profit_1


def test_degraded_market_quality_fails_closed():
    """VP-008: Degraded data quality forces immediate NO TRADE."""
    features = {
        "short_horizon_vol_10m": 0.010,
        "volatility_percentile_trailing_1440m": 0.15,
        "efficiency_ratio_20m": 0.50,
        "directional_persistence_20m": 0.75,
        "rolling_slope_20m": 0.0005,
        "latest_realized_funding_rate": 0.00001,
        "data_quality_status": "DEGRADED",
        "data_quality_reasons": ["FEED_STALE_180S"],
    }
    decision = evaluate_asset_trade_board(
        asset="BTCUSDT",
        current_price=64000.0,
        features=features,
    )
    assert decision.action == "NO_TRADE"
    assert decision.display_action == "NO TRADE (WAIT)"
    assert decision.confidence == 0.0
    assert decision.setup_name == "DATA_QUALITY_PRESERVATION"
    assert any("VP-008" in w for w in decision.trap_warnings)


def test_range_chop_no_edge():
    """VP-008: Mid-range noise with no edge results in NO TRADE."""
    features = {
        "short_horizon_vol_10m": 0.012,
        "volatility_percentile_trailing_1440m": 0.45,
        "efficiency_ratio_20m": 0.18,  # low efficiency ratio -> RANGE
        "directional_persistence_20m": 0.50,
        "rolling_slope_20m": -0.00005,
        "volume_percentile_trailing_1440m": 0.35,
        "abnormal_activity_score_60m": -0.2,
        "latest_realized_funding_rate": 0.00003,
        "data_quality_status": "GOOD",
    }
    decision = evaluate_asset_trade_board(
        asset="BTCUSDT",
        current_price=63500.0,
        features=features,
    )
    assert decision.action == "NO_TRADE"
    assert decision.display_action == "NO TRADE (WAIT)"
    assert decision.setup_name == "RANGE_NO_EDGE_WAIT"
    assert any("VP-008" in w for w in decision.trap_warnings)


def test_shadow_bot_telemetry_reader(tmp_path):
    """Verifies reading shadow bot telemetry safely."""
    # Missing file
    res_missing = read_shadow_bot_telemetry(tmp_path / "absent_heartbeat.json")
    assert res_missing["connected"] is False

    # Present file
    hb_file = tmp_path / "heartbeat.json"
    hb_file.write_text(json.dumps({
        "state": "IDLE_WAIT",
        "pid": 9999,
        "git_commit": "f358dd4",
        "cycle_count": 42,
        "last_decision": "NO TRADE (NO TRADE)",
    }), encoding="utf-8")

    res_present = read_shadow_bot_telemetry(hb_file)
    assert res_present["connected"] is True
    assert res_present["pid"] == 9999
    assert res_present["cycle_count"] == 42
    assert res_present["last_decision"] == "NO TRADE (NO TRADE)"


def test_evaluate_all_assets_trade_board():
    """Verifies multi-asset evaluation across BTC, ETH, and XAU."""
    result = evaluate_all_assets_trade_board()
    assert "BTCUSDT" in result["decisions"]
    assert "ETHUSDT" in result["decisions"]
    assert "XAUUSDT" in result["decisions"]
    assert "cross_asset_matrix" in result
    assert "timestamp_utc" in result

    btc = result["decisions"]["BTCUSDT"]
    assert btc["display_action"] in ("TAKE TRADE: LONG", "TAKE TRADE: SHORT", "NO TRADE (WAIT)")
    assert "risk_reward_ratio" in btc
    assert "stop_loss" in btc
    assert "take_profit_1" in btc
