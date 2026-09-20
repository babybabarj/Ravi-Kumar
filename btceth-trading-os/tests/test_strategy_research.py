from __future__ import annotations

from decimal import Decimal
import math
from pathlib import Path
import tempfile
import pytest

from btceth_os.research.backtest import Candle, CostModel, run_backtest
from btceth_os.research.experiment_registry import ExperimentRecord, ExperimentRegistry, compute_experiment_id
from btceth_os.research.families import (
    BreakoutExpansionFamily,
    FundingBasisFamily,
    MeanReversionFamily,
    TrendMomentumFamily,
)
from btceth_os.research.features import (
    compute_breakout_distance,
    compute_log_returns,
    compute_normalized_range_position,
    compute_realized_volatility,
    compute_rolling_drawdown,
    compute_trend_slope,
    timestamp_to_session_info,
)
from btceth_os.research.manifest import ResearchDatasetManifest, compute_logical_sha256
from btceth_os.research.market_brain import MarketBrain, MarketRegime
from btceth_os.research.validation import (
    BASE_COSTS,
    STRESSED_COSTS,
    StrategyValidationPolicy,
    compute_deflated_sharpe_ratio,
    compute_pbo_cscv,
    compute_sharpe_ratio,
    compute_skewness_and_kurtosis,
    compute_sortino_ratio,
    compute_trade_concentration,
    evaluate_cost_stress,
    evaluate_parameter_neighborhood,
    run_block_bootstrap,
    verify_future_leakage_perturbation,
    verify_truncated_history_equivalence,
)


def test_research_dataset_logical_sha256_determinism():
    records_a = [
        ("100", "50000.0"),
        ("200", "50100.0"),
    ]
    records_b = [
        ("100", "50000.0"),
        ("200", "50100.0"),
    ]
    records_c = [
        ("100", "50000.1"),
        ("200", "50100.0"),
    ]
    sha_a = compute_logical_sha256(records_a)
    sha_b = compute_logical_sha256(records_b)
    sha_c = compute_logical_sha256(records_c)

    assert sha_a == sha_b
    assert sha_a != sha_c
    assert len(sha_a) == 64


def test_future_leakage_perturbation():
    # 500 bars of synthetic prices
    series = [100.0 + 10.0 * math.sin(i / 20.0) + (i * 0.05) for i in range(500)]
    cutoff = 250

    # Test log return
    assert verify_future_leakage_perturbation(
        lambda s: compute_log_returns(s, lookback=5),
        series,
        test_index=cutoff,
    )

    # Test trend slope
    assert verify_future_leakage_perturbation(
        lambda s: compute_trend_slope(s, lookback=30),
        series,
        test_index=cutoff,
    )

    # Test realized volatility
    assert verify_future_leakage_perturbation(
        lambda s: compute_realized_volatility(s, lookback=60),
        series,
        test_index=cutoff,
    )

    # Test rolling drawdown
    assert verify_future_leakage_perturbation(
        lambda s: compute_rolling_drawdown(s, lookback=60),
        series,
        test_index=cutoff,
    )


def test_truncated_history_equivalence():
    series = [100.0 + 5.0 * math.cos(i / 15.0) for i in range(300)]
    cutoff = 180

    assert verify_truncated_history_equivalence(
        lambda s: compute_log_returns(s, lookback=15),
        series,
        cutoff_index=cutoff,
    )
    assert verify_truncated_history_equivalence(
        lambda s: compute_trend_slope(s, lookback=45),
        series,
        cutoff_index=cutoff,
    )


def test_market_brain_regime_classification():
    # 1. Liquidity stress
    st1 = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.90,  # >= 0.85
        funding_rate=0.0001,
        funding_zscore=0.2,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
    )
    assert st1.regime == MarketRegime.LIQUIDITY_STRESS

    # 2. Extreme funding dislocation
    st2 = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.30,
        funding_rate=0.0006,  # >= 0.0004
        funding_zscore=2.8,   # >= 2.5
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
    )
    assert st2.regime == MarketRegime.FUNDING_EXTREME

    # 3. Volatility expansion
    st3 = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.35,
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.45,  # >= 1.35
        rolling_drawdown_2h=0.01,
    )
    assert st3.regime == MarketRegime.OI_EXPANSION

    # 4. Range compression coil
    st4 = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.25,
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=0.55,  # <= 0.65
        rolling_drawdown_2h=0.01,
    )
    assert st4.regime == MarketRegime.OI_UNWIND

    # 5. Trend up low vol
    st5 = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.005,  # >= 0.003
        volatility_realized_60m=0.30,  # < 0.45
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
    )
    assert st5.regime == MarketRegime.TREND_UP_LOW_VOL

    # 6. Trend up high vol
    st6 = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.005,  # >= 0.003
        volatility_realized_60m=0.55,  # >= 0.45
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
    )
    assert st6.regime == MarketRegime.TREND_UP_HIGH_VOL

    # 7. Trend down low vol
    st7 = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=-0.005,  # <= -0.003
        volatility_realized_60m=0.30,
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
    )
    assert st7.regime == MarketRegime.TREND_DOWN_LOW_VOL

    # 8. Range low vol
    st8 = MarketBrain.classify_bar(
        timestamp_ns=1000,
        symbol="BTCUSDT",
        price=70000.0,
        trend_slope_30m=0.001,
        volatility_realized_60m=0.25,
        funding_rate=0.0001,
        funding_zscore=0.1,
        compression_ratio=1.0,
        rolling_drawdown_2h=0.01,
    )
    assert st8.regime == MarketRegime.RANGE_LOW_VOL


def test_experiment_registry_sqlite_wal():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_exp.sqlite"
        registry = ExperimentRegistry(db_file)

        exp_id = compute_experiment_id("FAM_A", "STRAT_1", "Test hypothesis", "deadbeef", {"fast": 10})
        rec = ExperimentRecord(
            experiment_id=exp_id,
            family="FAM_A",
            strategy_id="STRAT_1",
            variant_index=1,
            hypothesis="Test hypothesis",
            parameters={"fast": 10},
            dataset_logical_sha256="deadbeef",
            code_commit="commit123",
            train_start_ts=100,
            train_end_ts=200,
            test_start_ts=201,
            test_end_ts=300,
            in_sample_net_return=0.05,
            in_sample_sharpe=1.2,
            out_of_sample_net_return=-0.02,
            out_of_sample_stressed_return=-0.05,
            out_of_sample_trades=35,
            out_of_sample_sharpe=-0.4,
            max_drawdown=0.08,
            deflated_sharpe_ratio=0.12,
            pbo=0.45,
            status="REJECTED",
            rejection_reasons=["Negative net return"],
        )
        registry.record_experiment(rec)

        assert registry.get_total_experiments_count() == 1
        assert registry.get_variants_tested_count("FAM_A") == 1
        assert registry.get_variants_tested_count("FAM_B") == 0

        # Export test
        json_export = registry.export_to_json(Path(tmp_dir) / "registry.json")
        assert json_export.exists()
        import json

        data = json.loads(json_export.read_text())
        assert data["total_experiments"] == 1
        assert data["experiments"][0]["experiment_id"] == exp_id


def test_deflated_sharpe_ratio_multiple_testing_penalty():
    # Observed Period Sharpe = 0.08, length = 500, var_sr = 0.01
    # As number of variants tested (N) increases, DSR MUST decrease!
    dsr_n1 = compute_deflated_sharpe_ratio(
        observed_sr=0.08,
        num_variants=1,
        var_sr=0.01,
        skewness=0.0,
        kurtosis=3.0,
        sample_length=500,
    )
    dsr_n10 = compute_deflated_sharpe_ratio(
        observed_sr=0.08,
        num_variants=10,
        var_sr=0.01,
        skewness=0.0,
        kurtosis=3.0,
        sample_length=500,
    )
    dsr_n100 = compute_deflated_sharpe_ratio(
        observed_sr=0.08,
        num_variants=100,
        var_sr=0.01,
        skewness=0.0,
        kurtosis=3.0,
        sample_length=500,
    )

    assert dsr_n1 > dsr_n10 > dsr_n100
    assert 0.0 <= dsr_n100 <= 1.0


def test_cost_stress_evaluation():
    candles = [
        Candle(ts_event_ns=1000 + i * 60_000_000_000, close=Decimal(str(100 + (i % 5))))
        for i in range(100)
    ]
    # Alternating position generates heavy turnover
    positions = [1 if i % 2 == 0 else -1 for i in range(100)]

    comp = evaluate_cost_stress(candles, positions, BASE_COSTS, STRESSED_COSTS)
    assert comp.base_result.trades > 50
    # Stressed net return must be strictly worse than base net return
    assert comp.stressed_result.net_return < comp.base_result.net_return
    assert comp.performance_degradation_pct > 0.0


def test_promotion_policy_rejects_brittle_strategy():
    policy = StrategyValidationPolicy()
    # Strategy fails cost stress
    res = policy.evaluate(
        out_of_sample_trades=50,
        net_return_base=0.02,
        net_return_stressed=-0.01,  # Fails
        annualized_sharpe=1.2,
        max_drawdown=0.05,
        deflated_sharpe_ratio=0.96,
        pbo=0.20,
        parameter_stability_ratio=0.80,
        trade_concentration_top1=0.20,
    )
    assert not res.is_promoted
    assert res.status == "REJECTED"
    assert any("stressed" in r.lower() for r in res.rejection_reasons)


def test_time_session_classification():
    # 2024-11-01 02:00:00 UTC (Asia session, Friday)
    ts_asia = 1730426400 * 1_000_000_000
    hour, dow, a, e, u = timestamp_to_session_info(ts_asia)
    assert hour == 2
    assert a == 1
    assert e == 0
    assert u == 0
    assert dow == 4  # Friday
