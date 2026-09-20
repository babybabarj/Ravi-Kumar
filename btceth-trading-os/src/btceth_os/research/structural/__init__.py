"""Structural and market-neutral research modules (Research Round 3)."""
from .basis_metrics import (
    compute_basis_velocity,
    compute_mark_spot_basis,
    compute_mark_spot_basis_ratio,
    compute_perp_index_basis,
    compute_rolling_zscores,
    compute_trade_basis,
    compute_trade_basis_ratio,
)
from .capital_model import (
    CapitalRequirementPolicy,
    calculate_total_committed_capital,
    compute_capital_normalized_metrics,
    compute_round_trip_breakeven_bps,
)
from .intent import LegIntent, MultiLegStrategyIntent
from .multi_leg_accounting import FundingCashFlowEvent, MultiLegTradeEpisode
from .risk_models import (
    MarginStressResult,
    evaluate_margin_and_basis_stress,
    simulate_legging_friction,
)

__all__ = [
    "compute_trade_basis",
    "compute_trade_basis_ratio",
    "compute_mark_spot_basis",
    "compute_mark_spot_basis_ratio",
    "compute_perp_index_basis",
    "compute_rolling_zscores",
    "compute_basis_velocity",
    "CapitalRequirementPolicy",
    "calculate_total_committed_capital",
    "compute_capital_normalized_metrics",
    "compute_round_trip_breakeven_bps",
    "LegIntent",
    "MultiLegStrategyIntent",
    "FundingCashFlowEvent",
    "MultiLegTradeEpisode",
    "MarginStressResult",
    "evaluate_margin_and_basis_stress",
    "simulate_legging_friction",
]
