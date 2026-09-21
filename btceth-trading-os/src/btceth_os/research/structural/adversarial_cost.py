"""Research Round 3B: Adversarial Execution Cost Model & Sensitivity Analysis.

Defines:
1. Cost Matrix Tiers:
   - Base Tier: Spot taker 0.10% (10 bps), Perp taker 0.05% (5 bps), Perp maker 0.02% (2 bps), slippage 0.02% (2 bps) per leg.
   - Stressed Tier: Spot taker 0.15% (15 bps), Perp taker 0.075% (7.5 bps), Perp maker 0.04% (4 bps), slippage 0.05% (5 bps) per leg.
   - Adversarial Tier: Spot taker 0.20% (20 bps), Perp taker 0.10% (10 bps), Perp maker 0.05% (5 bps), slippage 0.10% (10 bps) per leg.
2. Volatility-Scaled Slippage:
   - slippage_pct = base_slippage * (1 + hourly_vol_pct / 0.01)
3. Cost Sensitivity Evaluator:
   - Evaluates structural trade episodes under Base, Stressed, and Adversarial Tiers.
   - Computes Breakeven Cost (fee + slippage level where net profit / Sharpe drops to 0).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
import math
from typing import Any, Sequence

from ..cost_model import DetailedCostPolicy
from .multi_leg_accounting import MultiLegTradeEpisode, RelativePerpPairEpisode
from .portfolio_equity import PortfolioEquityEngine


@dataclass(frozen=True)
class ExecutionCostProfile:
    tier_name: str
    spot_taker_bps: Decimal
    perp_taker_bps: Decimal
    perp_maker_bps: Decimal
    base_slippage_bps: Decimal
    spread_bps: Decimal = Decimal("1.0")

    def get_spot_policy(self, hourly_vol_pct: Decimal = Decimal("0.0")) -> DetailedCostPolicy:
        slip = compute_volatility_scaled_slippage(self.base_slippage_bps, hourly_vol_pct)
        return DetailedCostPolicy(
            instrument_type="SPOT",
            exchange_fee_bps=self.spot_taker_bps,
            spread_bps=self.spread_bps,
            slippage_bps=slip,
            include_funding=False,
        )

    def get_perp_policy(
        self,
        maker: bool = False,
        hourly_vol_pct: Decimal = Decimal("0.0"),
    ) -> DetailedCostPolicy:
        fee = self.perp_maker_bps if maker else self.perp_taker_bps
        slip = compute_volatility_scaled_slippage(self.base_slippage_bps, hourly_vol_pct)
        return DetailedCostPolicy(
            instrument_type="PERP",
            exchange_fee_bps=fee,
            spread_bps=self.spread_bps,
            slippage_bps=slip,
            include_funding=True,
        )


# Canonical Tiers defined by Section 7
BASE_TIER = ExecutionCostProfile(
    tier_name="BASE",
    spot_taker_bps=Decimal("10.0"),    # 0.10%
    perp_taker_bps=Decimal("5.0"),     # 0.05%
    perp_maker_bps=Decimal("2.0"),     # 0.02%
    base_slippage_bps=Decimal("2.0"),  # 0.02%
    spread_bps=Decimal("1.0"),
)

STRESSED_TIER = ExecutionCostProfile(
    tier_name="STRESSED",
    spot_taker_bps=Decimal("15.0"),    # 0.15%
    perp_taker_bps=Decimal("7.5"),     # 0.075%
    perp_maker_bps=Decimal("4.0"),     # 0.04%
    base_slippage_bps=Decimal("5.0"),  # 0.05%
    spread_bps=Decimal("2.0"),
)

ADVERSARIAL_TIER = ExecutionCostProfile(
    tier_name="ADVERSARIAL",
    spot_taker_bps=Decimal("20.0"),    # 0.20%
    perp_taker_bps=Decimal("10.0"),    # 0.10%
    perp_maker_bps=Decimal("5.0"),     # 0.05%
    base_slippage_bps=Decimal("10.0"), # 0.10%
    spread_bps=Decimal("3.0"),
)


def compute_volatility_scaled_slippage(
    base_slippage_bps: Decimal,
    hourly_vol_pct: Decimal,
) -> Decimal:
    """Calculate volatility-scaled slippage.

    Formula: slippage = base_slippage * (1 + hourly_vol_pct / 0.01)
    e.g. if hourly_vol_pct is 0.015 (1.5%), scale factor is 1 + 1.5 = 2.5.
    """
    if hourly_vol_pct <= Decimal("0.0"):
        return base_slippage_bps
    scale = Decimal("1.0") + (hourly_vol_pct / Decimal("0.01"))
    return base_slippage_bps * scale


def apply_cost_profile_to_spot_perp_episode(
    ep: MultiLegTradeEpisode,
    profile: ExecutionCostProfile,
    maker_perp: bool = False,
    hourly_vol_pct: Decimal = Decimal("0.0"),
) -> MultiLegTradeEpisode:
    """Reconstruct an episode with the specified execution cost profile."""
    spot_pol = profile.get_spot_policy(hourly_vol_pct=hourly_vol_pct)
    perp_pol = profile.get_perp_policy(maker=maker_perp, hourly_vol_pct=hourly_vol_pct)
    return replace(ep, spot_cost_policy=spot_pol, perp_cost_policy=perp_pol)


def apply_cost_profile_to_relative_pair_episode(
    ep: RelativePerpPairEpisode,
    profile: ExecutionCostProfile,
    maker: bool = False,
    hourly_vol_pct: Decimal = Decimal("0.0"),
) -> RelativePerpPairEpisode:
    """Reconstruct a 2-perp relative pair episode with the specified execution cost profile."""
    p1 = profile.get_perp_policy(maker=maker, hourly_vol_pct=hourly_vol_pct)
    p2 = profile.get_perp_policy(maker=maker, hourly_vol_pct=hourly_vol_pct)
    return replace(ep, asset1_cost_policy=p1, asset2_cost_policy=p2)


def evaluate_episodes_under_tier(
    episodes: Sequence[Any],
    profile: ExecutionCostProfile,
    starting_equity: Decimal = Decimal("100000.0"),
    maker_perp: bool = False,
) -> dict[str, Any]:
    """Replay episodes through PortfolioEquityEngine under a specific cost tier."""
    if not episodes:
        return {
            "tier": profile.tier_name,
            "episode_count": 0,
            "period_net_pnl": 0.0,
            "portfolio_return_pct": 0.0,
            "daily_sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "gross_pnl": 0.0,
            "total_costs": 0.0,
        }

    engine = PortfolioEquityEngine(
        starting_equity=starting_equity,
        max_concurrency=1,
    )
    first_ts = episodes[0].entry_ts_ns
    engine.record_initial_state(first_ts)

    recomputed_episodes = []
    for ep in episodes:
        if isinstance(ep, MultiLegTradeEpisode):
            recomputed_ep = apply_cost_profile_to_spot_perp_episode(ep, profile, maker_perp=maker_perp)
            committed = recomputed_ep.spot_notional_entry * Decimal("1.75")
        elif isinstance(ep, RelativePerpPairEpisode):
            recomputed_ep = apply_cost_profile_to_relative_pair_episode(ep, profile, maker=maker_perp)
            committed = recomputed_ep.gross_notional_entry * Decimal("0.75")
        else:
            raise TypeError(f"Unsupported episode type: {type(ep)}")

        engine.open_episode(recomputed_ep, committed)
        engine.close_episode(recomputed_ep, committed, recomputed_ep.exit_ts_ns)
        recomputed_episodes.append(recomputed_ep)

    total_hours = (episodes[-1].exit_ts_ns - episodes[0].entry_ts_ns) / 3_600_000_000_000
    summary = engine.compute_summary_metrics(recomputed_episodes, total_period_hours=total_hours)

    total_gross = sum(
        (
            (ep.spot_pnl + ep.perp_pnl + ep.total_funding_pnl)
            if isinstance(ep, MultiLegTradeEpisode)
            else (ep.price_pnl + ep.total_funding_pnl)
        )
        for ep in recomputed_episodes
    )
    total_costs = sum(ep.total_costs for ep in recomputed_episodes)

    return {
        "tier": profile.tier_name,
        "episode_count": len(recomputed_episodes),
        "period_net_pnl": summary["period_net_pnl"],
        "portfolio_return_pct": summary["portfolio_return_pct"],
        "daily_sharpe": summary["daily_sharpe"],
        "max_drawdown_pct": summary["max_drawdown_pct"],
        "gross_pnl": round(float(total_gross), 2),
        "total_costs": round(float(total_costs), 2),
    }


def compute_breakeven_cost_bps(episodes: Sequence[Any]) -> float:
    """Calculate the breakeven one-way cost rate (bps) where net profit drops to zero.

    Breakeven bps = (Gross PnL / Total Traded Notional Volume) * 10,000 bps
    If Gross PnL <= 0, breakeven is 0.0 (the strategy has zero or negative gross edge).
    """
    if not episodes:
        return 0.0

    total_gross = Decimal("0")
    total_volume = Decimal("0")

    for ep in episodes:
        if isinstance(ep, MultiLegTradeEpisode):
            gross = ep.spot_pnl + ep.perp_pnl + ep.total_funding_pnl - ep.temporary_delta_loss_usd
            vol = (ep.spot_entry_price * ep.spot_quantity) + (ep.spot_exit_price * ep.spot_quantity) + \
                  (ep.perp_entry_price * ep.perp_quantity) + (ep.perp_exit_price * ep.perp_quantity)
        elif isinstance(ep, RelativePerpPairEpisode):
            gross = ep.price_pnl + ep.total_funding_pnl - ep.temporary_delta_loss_usd
            vol = (ep.asset1_entry_price * ep.asset1_quantity) + (ep.asset1_exit_price * ep.asset1_quantity) + \
                  (ep.asset2_entry_price * ep.asset2_quantity) + (ep.asset2_exit_price * ep.asset2_quantity)
        else:
            continue

        total_gross += gross
        total_volume += vol

    if total_volume <= Decimal("0") or total_gross <= Decimal("0"):
        return 0.0

    be_rate = total_gross / total_volume
    return round(float(be_rate * Decimal("10000.0")), 2)
