from __future__ import annotations

import pytest

from btceth_os.research.validation.statistical import (
    compute_pbo_cscv,
    estimate_trial_sharpe_variance,
    run_monte_carlo_drawdown_simulation,
    run_moving_block_bootstrap,
)


def test_pbo_insufficient_data_returns_not_computable():
    # Only 1 variant provided -> MUST NOT return 0.0! Must return PBO_NOT_COMPUTABLE
    single_variant = [[0.01, -0.005, 0.02, -0.01] * 10]
    res1 = compute_pbo_cscv(single_variant, num_blocks=16)
    assert res1.status == "PBO_NOT_COMPUTABLE"
    assert res1.pbo is None
    assert "INSUFFICIENT_VARIANTS" in str(res1.reason)

    # Empty matrix
    res_empty = compute_pbo_cscv([], num_blocks=16)
    assert res_empty.status == "PBO_NOT_COMPUTABLE"
    assert res_empty.pbo is None

    # Series too short for number of blocks
    short_variants = [[0.01, -0.01] * 5, [0.02, -0.02] * 5]  # len = 10, blocks = 16
    res_short = compute_pbo_cscv(short_variants, num_blocks=16)
    assert res_short.status == "PBO_NOT_COMPUTABLE"
    assert res_short.pbo is None
    assert "INSUFFICIENT_OBSERVATIONS" in str(res_short.reason)


def test_pbo_computed_on_variant_matrix():
    # 5 variants across 320 periods (20 periods per block for 16 blocks)
    import random
    rng = random.Random(42)
    variants = []
    for _ in range(5):
        rets = [rng.gauss(0.0001, 0.01) for _ in range(320)]
        variants.append(rets)

    res = compute_pbo_cscv(variants, num_blocks=16)
    assert res.status == "COMPUTED"
    assert res.pbo is not None
    assert 0.0 <= res.pbo <= 1.0
    assert res.num_variants == 5


def test_estimate_trial_sharpe_variance():
    # 4 trial Sharpes: [0.5, 1.0, 1.5, 2.0]
    # Mean = 1.25, Variance = ((0.5-1.25)^2 + (1.0-1.25)^2 + (1.5-1.25)^2 + (2.0-1.25)^2) / 3
    # = (0.5625 + 0.0625 + 0.0625 + 0.5625) / 3 = 1.25 / 3 = 0.416667
    sharpes = [0.5, 1.0, 1.5, 2.0]
    var_est = estimate_trial_sharpe_variance(sharpes)
    assert abs(var_est - 0.416667) < 1e-4


def test_monte_carlo_drawdown_simulation():
    # 50 simulated trades with positive drift and occasional losses
    trades = [0.02, -0.015, 0.01, 0.03, -0.02, 0.015, -0.01] * 8
    mc_res = run_monte_carlo_drawdown_simulation(trades, num_simulations=500, seed=42)

    assert mc_res.max_drawdown_p95 >= 0.0
    assert mc_res.max_drawdown_p99 >= mc_res.max_drawdown_p95
    assert 0 <= mc_res.prob_drawdown_exceeds_15pct <= 1.0
    assert mc_res.longest_losing_streak_p95 >= 1
