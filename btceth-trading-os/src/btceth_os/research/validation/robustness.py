from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable, Sequence

from ..backtest import BacktestResult, Candle, CostModel, run_backtest


BASE_COSTS = CostModel(taker_fee_bps=Decimal("10"), slippage_bps=Decimal("5"), carry_bps_per_bar=Decimal("0"))
STRESSED_COSTS = CostModel(taker_fee_bps=Decimal("20"), slippage_bps=Decimal("15"), carry_bps_per_bar=Decimal("0"))


@dataclass(frozen=True)
class CostStressComparison:
    base_result: BacktestResult
    stressed_result: BacktestResult
    survives_stress: bool
    performance_degradation_pct: float


def evaluate_cost_stress(
    candles: Sequence[Candle],
    positions: Sequence[int],
    base_costs: CostModel = BASE_COSTS,
    stressed_costs: CostModel = STRESSED_COSTS,
) -> CostStressComparison:
    """Run parallel backtests under base and stressed transaction costs to test edge fragility."""
    base_res = run_backtest(candles, positions, base_costs)
    stressed_res = run_backtest(candles, positions, stressed_costs)

    survives = stressed_res.net_return > Decimal("0")
    if base_res.net_return > Decimal("0"):
        deg = float((base_res.net_return - stressed_res.net_return) / base_res.net_return)
    else:
        deg = 1.0

    return CostStressComparison(
        base_result=base_res,
        stressed_result=stressed_res,
        survives_stress=survives,
        performance_degradation_pct=deg,
    )


@dataclass(frozen=True)
class NeighborhoodStabilityResult:
    total_neighbors: int
    profitable_neighbors: int
    stability_ratio: float
    is_stable: bool  # True if stability_ratio >= threshold (default 0.60)
    neighbor_returns: tuple[float, ...]


def evaluate_parameter_neighborhood(
    candles: Sequence[Candle],
    position_generator: Callable[[dict[str, int | float]], Sequence[int]],
    param_grid: Iterable[dict[str, int | float]],
    costs: CostModel = BASE_COSTS,
    threshold: float = 0.60,
) -> NeighborhoodStabilityResult:
    """Evaluate performance across adjacent parameter variations to detect overfit needle-in-haystack peaks."""
    returns = []
    for params in param_grid:
        positions = position_generator(params)
        res = run_backtest(candles, positions, costs)
        returns.append(float(res.net_return))

    if not returns:
        return NeighborhoodStabilityResult(0, 0, 0.0, False, ())

    profitable = sum(1 for r in returns if r > 0.0)
    ratio = profitable / len(returns)
    return NeighborhoodStabilityResult(
        total_neighbors=len(returns),
        profitable_neighbors=profitable,
        stability_ratio=ratio,
        is_stable=ratio >= threshold,
        neighbor_returns=tuple(returns),
    )
