from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
import random
from typing import Optional, Sequence

EULER_MASCHERONI = 0.57721566490153286060651209


def normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_ppf(p: float) -> float:
    """Inverse normal CDF (quantile function) using rational approximation and Newton-Raphson refinement."""
    if p <= 0.0:
        return -10.0
    if p >= 1.0:
        return 10.0
    if p == 0.5:
        return 0.0

    # Initial rational approximation
    t = math.sqrt(-2.0 * math.log(min(p, 1.0 - p)))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    x0 = t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t)
    x = -x0 if p < 0.5 else x0

    # Newton-Raphson refinement
    inv_sqrt_2pi = 1.0 / math.sqrt(2.0 * math.pi)
    for _ in range(5):
        diff = normal_cdf(x) - p
        pdf = inv_sqrt_2pi * math.exp(-0.5 * x * x)
        if pdf < 1e-15:
            break
        x = x - diff / pdf
    return x


def compute_sharpe_ratio(returns: Sequence[float], periods_per_year: float = 252.0) -> float:
    """Annualized Sharpe ratio assuming 0 risk-free rate."""
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(var)
    if std_r < 1e-12:
        return 0.0
    return (mean_r / std_r) * math.sqrt(periods_per_year)


def compute_sortino_ratio(returns: Sequence[float], periods_per_year: float = 252.0) -> float:
    """Annualized Sortino ratio based on downside standard deviation."""
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    downside_sq = [r * r for r in returns if r < 0.0]
    if not downside_sq:
        return 5.0 if mean_r > 0 else 0.0
    downside_dev = math.sqrt(sum(downside_sq) / len(returns))
    if downside_dev < 1e-12:
        return 0.0
    return (mean_r / downside_dev) * math.sqrt(periods_per_year)


def compute_skewness_and_kurtosis(returns: Sequence[float]) -> tuple[float, float]:
    """Sample skewness and excess kurtosis."""
    n = len(returns)
    if n < 4:
        return 0.0, 3.0
    mean_r = sum(returns) / n
    var = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
    std_r = math.sqrt(var)
    if std_r < 1e-12:
        return 0.0, 3.0
    m3 = sum((r - mean_r) ** 3 for r in returns) / n
    m4 = sum((r - mean_r) ** 4 for r in returns) / n
    skew = m3 / (std_r**3)
    kurt = m4 / (std_r**4)
    return skew, kurt


def estimate_trial_sharpe_variance(variant_sharpes: Sequence[float]) -> float:
    """Calculate empirical cross-sectional variance of Sharpe ratios across explored variants."""
    n = len(variant_sharpes)
    if n < 2:
        return 0.01  # Safe minimum fallback when only 1 variant exists
    mean_sr = sum(variant_sharpes) / n
    var_sr = sum((s - mean_sr) ** 2 for s in variant_sharpes) / (n - 1)
    return max(1e-6, var_sr)


def compute_deflated_sharpe_ratio(
    observed_sr: float,
    num_variants: int,
    var_sr: float,
    skewness: float,
    kurtosis: float,
    sample_length: int,
) -> float:
    """Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio with multiple-testing adjustment."""
    if sample_length < 5 or observed_sr <= 0.0:
        return 0.0
    num_variants = max(1, num_variants)
    var_sr = max(1e-6, var_sr)

    # Expected max Sharpe under null of zero skill
    if num_variants == 1:
        e_max_sr = 0.0
    else:
        p1 = 1.0 - 1.0 / num_variants
        p2 = 1.0 - 1.0 / (num_variants * math.e)
        z1 = normal_ppf(min(0.99999, max(0.00001, p1)))
        z2 = normal_ppf(min(0.99999, max(0.00001, p2)))
        e_max_sr = math.sqrt(var_sr) * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)

    # Standard deviation of estimated Sharpe
    denom = sample_length - 1
    term = 1.0 - 0.5 * skewness * observed_sr + ((kurtosis - 1.0) / 4.0) * (observed_sr**2)
    std_est = math.sqrt(max(1e-12, term / denom))

    z_score = (observed_sr - e_max_sr) / std_est
    return float(normal_cdf(z_score))


def run_moving_block_bootstrap(
    trade_pnls: Sequence[float],
    num_samples: int = 1000,
    block_size: int = 5,
    seed: int = 42,
) -> dict[str, float]:
    """Moving block bootstrap to estimate empirical distribution and 95% lower CI of trade expectancy."""
    if len(trade_pnls) < 2:
        return {
            "mean_expectancy": 0.0,
            "lower_ci_95": 0.0,
            "upper_ci_95": 0.0,
            "pct_positive_equity": 0.0,
        }

    rng = random.Random(seed)
    n = len(trade_pnls)
    k = max(1, min(block_size, n // 2))
    means: list[float] = []
    positive_equity_count = 0

    for _ in range(num_samples):
        sample: list[float] = []
        while len(sample) < n:
            start_idx = rng.randint(0, n - k)
            sample.extend(trade_pnls[start_idx : start_idx + k])
        sample = sample[:n]
        mean_s = sum(sample) / n
        means.append(mean_s)
        if sum(sample) > 0:
            positive_equity_count += 1

    means.sort()
    idx_lower = int(num_samples * 0.05)
    idx_upper = int(num_samples * 0.95)

    return {
        "mean_expectancy": float(sum(means) / num_samples),
        "lower_ci_95": float(means[idx_lower]),
        "upper_ci_95": float(means[idx_upper]),
        "pct_positive_equity": float(positive_equity_count / num_samples),
    }


# Backwards compatibility alias
run_block_bootstrap = run_moving_block_bootstrap


def compute_trade_concentration(trade_pnls: Sequence[float]) -> dict[str, float]:
    """Calculate the share of net profits generated by the top 1%, 5%, and 10% best trades."""
    winning_trades = sorted([p for p in trade_pnls if p > 0.0], reverse=True)
    total_gross_profit = sum(winning_trades)
    if total_gross_profit <= 0.0 or not winning_trades:
        return {"top1_share": 1.0, "top5_share": 1.0, "top10_share": 1.0}

    n = len(winning_trades)
    top1_k = max(1, math.ceil(n * 0.01))
    top5_k = max(1, math.ceil(n * 0.05))
    top10_k = max(1, math.ceil(n * 0.10))

    return {
        "top1_share": float(sum(winning_trades[:top1_k]) / total_gross_profit),
        "top5_share": float(sum(winning_trades[:top5_k]) / total_gross_profit),
        "top10_share": float(sum(winning_trades[:top10_k]) / total_gross_profit),
    }


@dataclass(frozen=True)
class CSCVResult:
    pbo: Optional[float]
    status: str  # "COMPUTED" or "PBO_NOT_COMPUTABLE"
    reason: Optional[str]
    num_variants: int
    num_partitions: int
    num_combinations: int


def compute_pbo_cscv(
    variants_returns_matrix: Sequence[Sequence[float]],
    num_blocks: int = 16,
) -> CSCVResult:
    """Combinatorially Symmetric Cross-Validation (CSCV) Probability of Backtest Overfitting.
    
    Evaluates parameter variants across combinatorial IS/OOS splits.
    Returns CSCVResult with status = 'PBO_NOT_COMPUTABLE' if inputs are insufficient.
    """
    if not variants_returns_matrix or len(variants_returns_matrix) < 2:
        return CSCVResult(
            pbo=None,
            status="PBO_NOT_COMPUTABLE",
            reason="INSUFFICIENT_VARIANTS: at least 2 variants are required to compute PBO",
            num_variants=len(variants_returns_matrix) if variants_returns_matrix else 0,
            num_partitions=num_blocks,
            num_combinations=0,
        )

    num_variants = len(variants_returns_matrix)
    series_len = len(variants_returns_matrix[0])
    if series_len < num_blocks * 2:
        return CSCVResult(
            pbo=None,
            status="PBO_NOT_COMPUTABLE",
            reason=f"INSUFFICIENT_OBSERVATIONS: series length ({series_len}) is too short for {num_blocks} blocks",
            num_variants=num_variants,
            num_partitions=num_blocks,
            num_combinations=0,
        )

    block_size = series_len // num_blocks
    chunked_variants = []
    for var_rets in variants_returns_matrix:
        chunks = []
        for b in range(num_blocks):
            start = b * block_size
            end = (b + 1) * block_size if b < num_blocks - 1 else series_len
            chunks.append(var_rets[start:end])
        chunked_variants.append(chunks)

    half = num_blocks // 2
    all_combos = list(itertools.combinations(range(num_blocks), half))
    sample_combos = all_combos[:500] if len(all_combos) > 500 else all_combos

    overfit_count = 0
    total_trials = len(sample_combos)

    for is_indices in sample_combos:
        is_set = set(is_indices)
        oos_set = [b for b in range(num_blocks) if b not in is_set]

        is_scores = []
        oos_scores = []
        for v in range(num_variants):
            is_rets = [r for b in is_indices for r in chunked_variants[v][b]]
            oos_rets = [r for b in oos_set for r in chunked_variants[v][b]]
            is_scores.append((sum(is_rets), v))
            oos_scores.append(sum(oos_rets))

        is_scores.sort(reverse=True)
        best_v = is_scores[0][1]

        best_oos_score = oos_scores[best_v]
        oos_rank = sum(1 for s in oos_scores if s > best_oos_score)
        if oos_rank >= num_variants / 2.0:
            overfit_count += 1

    pbo_value = float(overfit_count / total_trials) if total_trials > 0 else 0.0
    return CSCVResult(
        pbo=pbo_value,
        status="COMPUTED",
        reason=None,
        num_variants=num_variants,
        num_partitions=num_blocks,
        num_combinations=total_trials,
    )


@dataclass(frozen=True)
class MonteCarloSimulationResult:
    max_drawdown_p95: float
    max_drawdown_p99: float
    prob_drawdown_exceeds_15pct: float
    longest_losing_streak_p95: int
    median_recovery_trades: int


def run_monte_carlo_drawdown_simulation(
    trade_returns: Sequence[float],
    num_simulations: int = 1000,
    seed: int = 42,
) -> MonteCarloSimulationResult:
    """Simulate order permutations of trades to construct robust empirical risk distributions."""
    if len(trade_returns) < 5:
        return MonteCarloSimulationResult(0.0, 0.0, 0.0, 0, 0)

    rng = random.Random(seed)
    n = len(trade_returns)
    max_drawdowns: list[float] = []
    losing_streaks: list[int] = []

    for _ in range(num_simulations):
        perm = list(trade_returns)
        rng.shuffle(perm)

        # Track equity curve, drawdown, losing streak
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        current_losing_streak = 0
        max_streak = 0

        for r in perm:
            equity *= 1.0 + r
            if equity > peak:
                peak = equity
            else:
                dd = (peak - equity) / peak if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd

            if r < 0:
                current_losing_streak += 1
                if current_losing_streak > max_streak:
                    max_streak = current_losing_streak
            else:
                current_losing_streak = 0

        max_drawdowns.append(max_dd)
        losing_streaks.append(max_streak)

    max_drawdowns.sort()
    losing_streaks.sort()

    idx_p95 = int(num_simulations * 0.95)
    idx_p99 = int(num_simulations * 0.99)

    p_exceed_15 = sum(1 for dd in max_drawdowns if dd >= 0.15) / num_simulations

    return MonteCarloSimulationResult(
        max_drawdown_p95=float(max_drawdowns[idx_p95]),
        max_drawdown_p99=float(max_drawdowns[idx_p99]),
        prob_drawdown_exceeds_15pct=float(p_exceed_15),
        longest_losing_streak_p95=int(losing_streaks[idx_p95]),
        median_recovery_trades=int(n // 4),
    )
