"""Capital allocation, return on capital (RoC), and breakeven modeling for structural strategies."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .multi_leg_accounting import MultiLegTradeEpisode


@dataclass(frozen=True)
class CapitalRequirementPolicy:
    """Capital allocation rules for two-leg cash-and-carry positions."""
    spot_capital_fraction: Decimal = Decimal("1.00")      # 100% cash funded for spot purchases
    perp_margin_fraction: Decimal = Decimal("0.50")       # 50% margin (2x leverage limit on perp leg)
    safety_buffer_fraction: Decimal = Decimal("0.25")     # 25% cash buffer to absorb adverse basis spikes


def calculate_total_committed_capital(
    spot_notional: Decimal,
    perp_notional: Decimal,
    policy: CapitalRequirementPolicy | None = None,
) -> Decimal:
    """Calculate realistic total committed capital across spot, perp margin, and safety buffer."""
    p = policy or CapitalRequirementPolicy()
    spot_committed = spot_notional * p.spot_capital_fraction
    perp_committed = perp_notional * (p.perp_margin_fraction + p.safety_buffer_fraction)
    return spot_committed + perp_committed


def compute_capital_normalized_metrics(
    episode: MultiLegTradeEpisode,
    policy: CapitalRequirementPolicy | None = None,
) -> dict[str, float]:
    """Compute capital-normalized returns, preventing artificial return inflation."""
    p = policy or CapitalRequirementPolicy()
    spot_notional = episode.spot_notional_entry
    perp_notional = episode.perp_notional_entry
    gross_exposure = spot_notional + perp_notional
    total_committed = calculate_total_committed_capital(spot_notional, perp_notional, p)
    
    net_pnl = episode.net_pnl
    
    return_on_capital = float(net_pnl / total_committed) if total_committed > 0 else 0.0
    return_on_gross_exposure = float(net_pnl / gross_exposure) if gross_exposure > 0 else 0.0
    
    holding_hours = float(episode.holding_hours)
    if holding_hours > 0 and total_committed > 0:
        annualized_carry = return_on_capital * (8760.0 / holding_hours)
    else:
        annualized_carry = 0.0

    return {
        "spot_notional": float(spot_notional),
        "perp_notional": float(perp_notional),
        "gross_exposure": float(gross_exposure),
        "total_committed_capital": float(total_committed),
        "return_on_capital": return_on_capital,
        "return_on_capital_bps": return_on_capital * 10000.0,
        "return_on_gross_exposure": return_on_gross_exposure,
        "annualized_carry_yield": annualized_carry,
    }


def compute_round_trip_breakeven_bps(
    spot_fee_bps: Decimal,
    spot_slip_bps: Decimal,
    perp_fee_bps: Decimal,
    perp_slip_bps: Decimal,
) -> Decimal:
    """Calculate minimum funding or basis yield (in bps) required to cover round-trip transaction costs."""
    # Round-trip = entry + exit for both legs
    spot_round_trip = (spot_fee_bps + spot_slip_bps) * Decimal("2.0")
    perp_round_trip = (perp_fee_bps + perp_slip_bps) * Decimal("2.0")
    return spot_round_trip + perp_round_trip
