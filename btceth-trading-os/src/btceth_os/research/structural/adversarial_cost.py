from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence
import yaml

from ..cost_model import DetailedCostPolicy
from .multi_leg_accounting import MultiLegTradeEpisode, RelativePerpPairEpisode
from .portfolio_equity import PortfolioEquityEngine
from .capital_governor import CapitalPolicy

CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "research_execution_cost_policy_v1.yaml"


@dataclass(frozen=True)
class ExecutionCostProfile:
    tier_name: str
    description: str
    spot_taker_bps: Decimal
    spot_maker_bps: Decimal
    spot_spread_bps: Decimal
    spot_base_slippage_bps: Decimal
    perp_taker_bps: Decimal
    perp_maker_bps: Decimal
    perp_spread_bps: Decimal
    perp_base_slippage_bps: Decimal
    default_legging_bps: Decimal

    def get_spot_policy(self, hourly_vol_pct: Decimal = Decimal("0.0"), maker: bool = False) -> DetailedCostPolicy:
        fee = self.spot_maker_bps if maker else self.spot_taker_bps
        slip = compute_volatility_scaled_slippage(self.spot_base_slippage_bps, hourly_vol_pct)
        return DetailedCostPolicy(
            instrument_type="SPOT",
            exchange_fee_bps=fee,
            spread_bps=self.spot_spread_bps,
            slippage_bps=slip,
            include_funding=False,
        )

    def get_perp_policy(self, hourly_vol_pct: Decimal = Decimal("0.0"), maker: bool = False) -> DetailedCostPolicy:
        fee = self.perp_maker_bps if maker else self.perp_taker_bps
        slip = compute_volatility_scaled_slippage(self.perp_base_slippage_bps, hourly_vol_pct)
        return DetailedCostPolicy(
            instrument_type="PERP",
            exchange_fee_bps=fee,
            spread_bps=self.perp_spread_bps,
            slippage_bps=slip,
            include_funding=True,
        )


def compute_volatility_scaled_slippage(
    base_slippage_bps: Decimal,
    hourly_vol_pct: Decimal,
    vol_threshold_pct: Decimal = Decimal("0.01"),
    vol_multiplier: Decimal = Decimal("1.0"),
) -> Decimal:
    """Calculate volatility-scaled slippage under SCENARIO_SLIPPAGE_MODEL.

    Formula: slippage = base_slippage * (1.0 + (hourly_vol / vol_threshold) * vol_multiplier)
    """
    if hourly_vol_pct <= Decimal("0.0"):
        return base_slippage_bps
    scale = Decimal("1.0") + (hourly_vol_pct / vol_threshold_pct) * vol_multiplier
    return base_slippage_bps * scale


def load_cost_profiles(config_path: Path | str = CONFIG_PATH) -> dict[str, ExecutionCostProfile]:
    """Load execution cost assumption tiers from versioned YAML configuration."""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    profiles: dict[str, ExecutionCostProfile] = {}
    for tier_key in ["BASE_RESEARCH_ASSUMPTION", "STRESSED_RESEARCH_ASSUMPTION", "ADVERSARIAL_RESEARCH_ASSUMPTION"]:
        if tier_key in raw:
            d = raw[tier_key]
            profiles[tier_key] = ExecutionCostProfile(
                tier_name=d["label"],
                description=d["description"],
                spot_taker_bps=Decimal(str(d["spot_taker_fee_bps"])),
                spot_maker_bps=Decimal(str(d["spot_maker_fee_bps"])),
                spot_spread_bps=Decimal(str(d["spot_spread_bps"])),
                spot_base_slippage_bps=Decimal(str(d["spot_base_slippage_bps"])),
                perp_taker_bps=Decimal(str(d["perp_taker_fee_bps"])),
                perp_maker_bps=Decimal(str(d["perp_maker_fee_bps"])),
                perp_spread_bps=Decimal(str(d["perp_spread_bps"])),
                perp_base_slippage_bps=Decimal(str(d["perp_base_slippage_bps"])),
                default_legging_bps=Decimal(str(d.get("default_legging_bps", 0.0))),
            )
    return profiles


# Pre-loaded canonical profiles
COST_PROFILES = load_cost_profiles()
BASE_TIER = COST_PROFILES["BASE_RESEARCH_ASSUMPTION"]
STRESSED_TIER = COST_PROFILES["STRESSED_RESEARCH_ASSUMPTION"]
ADVERSARIAL_TIER = COST_PROFILES["ADVERSARIAL_RESEARCH_ASSUMPTION"]


def apply_cost_profile_to_spot_perp_episode(
    ep: MultiLegTradeEpisode,
    profile: ExecutionCostProfile,
    maker_perp: bool = False,
    hourly_vol_pct: Decimal = Decimal("0.0"),
) -> MultiLegTradeEpisode:
    """Reconstruct an episode with the specified execution cost profile."""
    spot_pol = profile.get_spot_policy(hourly_vol_pct=hourly_vol_pct)
    perp_pol = profile.get_perp_policy(hourly_vol_pct=hourly_vol_pct, maker=maker_perp)
    return replace(ep, spot_cost_policy=spot_pol, perp_cost_policy=perp_pol)


def apply_cost_profile_to_relative_pair_episode(
    ep: RelativePerpPairEpisode,
    profile: ExecutionCostProfile,
    maker: bool = False,
    hourly_vol_pct: Decimal = Decimal("0.0"),
) -> RelativePerpPairEpisode:
    """Reconstruct a 2-perp relative pair episode with the specified execution cost profile."""
    p1 = profile.get_perp_policy(hourly_vol_pct=hourly_vol_pct, maker=maker)
    p2 = profile.get_perp_policy(hourly_vol_pct=hourly_vol_pct, maker=maker)
    return replace(ep, asset1_cost_policy=p1, asset2_cost_policy=p2)


def evaluate_episodes_under_tier(
    episodes: Sequence[Any],
    profile: ExecutionCostProfile,
    capital_policy: Optional[CapitalPolicy] = None,
    maker_perp: bool = False,
) -> dict[str, Any]:
    """Replay episodes through PortfolioEquityEngine using explicit CapitalPolicy."""
    c_pol = capital_policy or CapitalPolicy()
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
        starting_equity=c_pol.starting_equity,
        max_concurrency=c_pol.max_concurrent_episodes,
    )
    first_ts = episodes[0].entry_ts_ns
    engine.record_initial_state(first_ts)

    recomputed_episodes = []
    for ep in episodes:
        if isinstance(ep, MultiLegTradeEpisode):
            recomputed_ep = apply_cost_profile_to_spot_perp_episode(ep, profile, maker_perp=maker_perp)
            committed = c_pol.compute_spot_perp_commitment(recomputed_ep.spot_notional_entry, recomputed_ep.perp_notional_entry)
        elif isinstance(ep, RelativePerpPairEpisode):
            recomputed_ep = apply_cost_profile_to_relative_pair_episode(ep, profile, maker=maker_perp)
            committed = c_pol.compute_relative_pair_commitment(recomputed_ep.gross_notional_entry / Decimal("2.0"), recomputed_ep.gross_notional_entry / Decimal("2.0"))
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
