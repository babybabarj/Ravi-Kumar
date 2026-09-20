"""Multi-leg position tracking and P&L decomposition for structural strategies."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from ..cost_model import DetailedCostPolicy, compute_funding_cash_flow
from ..unit_rates import bps_to_fraction


@dataclass(frozen=True)
class FundingCashFlowEvent:
    """Individual historical funding settlement cash flow."""
    ts_event_ns: int
    funding_rate: Decimal
    mark_price: Decimal
    position_side: int  # +1 long perp, -1 short perp, 0 flat
    notional_usd: Decimal
    cash_flow_usd: Decimal


@dataclass(frozen=True)
class MultiLegTradeEpisode:
    """Complete accounting for a two-leg structural trade episode."""
    episode_id: str
    strategy_id: str
    asset: str  # e.g. "BTC" or "ETH"
    entry_ts_ns: int
    exit_ts_ns: int
    
    # Spot Leg
    spot_side: int  # +1 for long spot, 0 for flat, -1 for short (if borrow permitted)
    spot_entry_price: Decimal
    spot_exit_price: Decimal
    spot_quantity: Decimal
    
    # Perp Leg
    perp_side: int  # -1 for short perp, +1 for long perp, 0 for flat
    perp_entry_price: Decimal
    perp_exit_price: Decimal
    perp_quantity: Decimal
    
    # Cost Policies Applied
    spot_cost_policy: DetailedCostPolicy
    perp_cost_policy: DetailedCostPolicy
    
    # Funding Events Recorded During Holding Period
    funding_events: tuple[FundingCashFlowEvent, ...] = field(default_factory=tuple)
    
    # Operational Friction / Legging
    legging_delay_ms: int = 0
    temporary_delta_loss_usd: Decimal = Decimal("0")
    rebalance_costs_usd: Decimal = Decimal("0")

    @property
    def holding_hours(self) -> Decimal:
        diff_ns = self.exit_ts_ns - self.entry_ts_ns
        return Decimal(diff_ns) / Decimal(3_600_000_000_000)

    @property
    def spot_notional_entry(self) -> Decimal:
        return self.spot_quantity * self.spot_entry_price

    @property
    def perp_notional_entry(self) -> Decimal:
        return self.perp_quantity * self.perp_entry_price

    @property
    def spot_pnl(self) -> Decimal:
        """Spot price delta P&L (NO funding on spot)."""
        return Decimal(self.spot_side) * self.spot_quantity * (self.spot_exit_price - self.spot_entry_price)

    @property
    def perp_pnl(self) -> Decimal:
        """Perp price delta P&L (excluding funding)."""
        return Decimal(self.perp_side) * self.perp_quantity * (self.perp_exit_price - self.perp_entry_price)

    @property
    def total_funding_pnl(self) -> Decimal:
        """Sum of all realized funding cash flows."""
        return sum((f.cash_flow_usd for f in self.funding_events), Decimal("0"))

    @property
    def spot_fees(self) -> Decimal:
        entry_fee = self.spot_notional_entry * bps_to_fraction(self.spot_cost_policy.exchange_fee_bps)
        exit_notional = self.spot_quantity * self.spot_exit_price
        exit_fee = exit_notional * bps_to_fraction(self.spot_cost_policy.exchange_fee_bps)
        return entry_fee + exit_fee

    @property
    def spot_slippage_and_spread(self) -> Decimal:
        entry_slip = self.spot_notional_entry * bps_to_fraction(self.spot_cost_policy.spread_bps + self.spot_cost_policy.slippage_bps)
        exit_notional = self.spot_quantity * self.spot_exit_price
        exit_slip = exit_notional * bps_to_fraction(self.spot_cost_policy.spread_bps + self.spot_cost_policy.slippage_bps)
        return entry_slip + exit_slip

    @property
    def perp_fees(self) -> Decimal:
        entry_fee = self.perp_notional_entry * bps_to_fraction(self.perp_cost_policy.exchange_fee_bps)
        exit_notional = self.perp_quantity * self.perp_exit_price
        exit_fee = exit_notional * bps_to_fraction(self.perp_cost_policy.exchange_fee_bps)
        return entry_fee + exit_fee

    @property
    def perp_slippage_and_spread(self) -> Decimal:
        entry_slip = self.perp_notional_entry * bps_to_fraction(self.perp_cost_policy.spread_bps + self.perp_cost_policy.slippage_bps)
        exit_notional = self.perp_quantity * self.perp_exit_price
        exit_slip = exit_notional * bps_to_fraction(self.perp_cost_policy.spread_bps + self.perp_cost_policy.slippage_bps)
        return entry_slip + exit_slip

    @property
    def total_costs(self) -> Decimal:
        return (
            self.spot_fees
            + self.spot_slippage_and_spread
            + self.perp_fees
            + self.perp_slippage_and_spread
            + self.temporary_delta_loss_usd
            + self.rebalance_costs_usd
        )

    @property
    def basis_pnl(self) -> Decimal:
        """Net P&L from price movement between spot and perp."""
        return self.spot_pnl + self.perp_pnl

    @property
    def net_pnl(self) -> Decimal:
        """Full economic net P&L after all cash flows and friction."""
        return self.basis_pnl + self.total_funding_pnl - self.total_costs

    def to_decomposition_dict(self) -> dict[str, str | float]:
        return {
            "episode_id": self.episode_id,
            "asset": self.asset,
            "holding_hours": float(self.holding_hours),
            "spot_notional": float(self.spot_notional_entry),
            "perp_notional": float(self.perp_notional_entry),
            "spot_pnl": float(self.spot_pnl),
            "perp_pnl": float(self.perp_pnl),
            "basis_pnl": float(self.basis_pnl),
            "funding_pnl": float(self.total_funding_pnl),
            "funding_events_count": len(self.funding_events),
            "spot_fees": float(self.spot_fees),
            "spot_slippage": float(self.spot_slippage_and_spread),
            "perp_fees": float(self.perp_fees),
            "perp_slippage": float(self.perp_slippage_and_spread),
            "legging_friction": float(self.temporary_delta_loss_usd),
            "rebalance_costs": float(self.rebalance_costs_usd),
            "total_costs": float(self.total_costs),
            "net_pnl": float(self.net_pnl),
        }


@dataclass(frozen=True)
class RelativePerpPairEpisode:
    """Complete accounting for a 2-perp relative funding carry trade (e.g. BTC Perp vs ETH Perp)."""
    episode_id: str
    strategy_id: str
    entry_ts_ns: int
    exit_ts_ns: int
    
    # Leg 1 (e.g. BTC Perp)
    asset1_symbol: str
    asset1_side: int  # +1 long, -1 short
    asset1_entry_price: Decimal
    asset1_exit_price: Decimal
    asset1_quantity: Decimal
    asset1_cost_policy: DetailedCostPolicy
    
    # Leg 2 (e.g. ETH Perp)
    asset2_symbol: str
    asset2_side: int  # -1 short, +1 long
    asset2_entry_price: Decimal
    asset2_exit_price: Decimal
    asset2_quantity: Decimal
    asset2_cost_policy: DetailedCostPolicy

    # Funding events
    asset1_funding_events: tuple[FundingCashFlowEvent, ...] = field(default_factory=tuple)
    asset2_funding_events: tuple[FundingCashFlowEvent, ...] = field(default_factory=tuple)
    
    # Frictions
    legging_delay_ms: int = 0
    temporary_delta_loss_usd: Decimal = Decimal("0")

    @property
    def holding_hours(self) -> Decimal:
        diff_ns = self.exit_ts_ns - self.entry_ts_ns
        return Decimal(diff_ns) / Decimal(3_600_000_000_000)

    @property
    def asset1_notional_entry(self) -> Decimal:
        return self.asset1_quantity * self.asset1_entry_price

    @property
    def asset2_notional_entry(self) -> Decimal:
        return self.asset2_quantity * self.asset2_entry_price

    @property
    def gross_notional_entry(self) -> Decimal:
        return self.asset1_notional_entry + self.asset2_notional_entry

    @property
    def net_delta_entry(self) -> Decimal:
        return (Decimal(self.asset1_side) * self.asset1_notional_entry) + (Decimal(self.asset2_side) * self.asset2_notional_entry)

    @property
    def asset1_pnl(self) -> Decimal:
        return Decimal(self.asset1_side) * self.asset1_quantity * (self.asset1_exit_price - self.asset1_entry_price)

    @property
    def asset2_pnl(self) -> Decimal:
        return Decimal(self.asset2_side) * self.asset2_quantity * (self.asset2_exit_price - self.asset2_entry_price)

    @property
    def price_pnl(self) -> Decimal:
        return self.asset1_pnl + self.asset2_pnl

    @property
    def asset1_funding_pnl(self) -> Decimal:
        return sum((f.cash_flow_usd for f in self.asset1_funding_events), Decimal("0"))

    @property
    def asset2_funding_pnl(self) -> Decimal:
        return sum((f.cash_flow_usd for f in self.asset2_funding_events), Decimal("0"))

    @property
    def total_funding_pnl(self) -> Decimal:
        return self.asset1_funding_pnl + self.asset2_funding_pnl

    @property
    def asset1_costs(self) -> Decimal:
        notional_exit = self.asset1_quantity * self.asset1_exit_price
        fee_entry = self.asset1_notional_entry * bps_to_fraction(self.asset1_cost_policy.exchange_fee_bps)
        fee_exit = notional_exit * bps_to_fraction(self.asset1_cost_policy.exchange_fee_bps)
        slip_entry = self.asset1_notional_entry * bps_to_fraction(self.asset1_cost_policy.spread_bps + self.asset1_cost_policy.slippage_bps)
        slip_exit = notional_exit * bps_to_fraction(self.asset1_cost_policy.spread_bps + self.asset1_cost_policy.slippage_bps)
        return fee_entry + fee_exit + slip_entry + slip_exit

    @property
    def asset2_costs(self) -> Decimal:
        notional_exit = self.asset2_quantity * self.asset2_exit_price
        fee_entry = self.asset2_notional_entry * bps_to_fraction(self.asset2_cost_policy.exchange_fee_bps)
        fee_exit = notional_exit * bps_to_fraction(self.asset2_cost_policy.exchange_fee_bps)
        slip_entry = self.asset2_notional_entry * bps_to_fraction(self.asset2_cost_policy.spread_bps + self.asset2_cost_policy.slippage_bps)
        slip_exit = notional_exit * bps_to_fraction(self.asset2_cost_policy.spread_bps + self.asset2_cost_policy.slippage_bps)
        return fee_entry + fee_exit + slip_entry + slip_exit

    @property
    def total_costs(self) -> Decimal:
        return self.asset1_costs + self.asset2_costs + self.temporary_delta_loss_usd

    @property
    def net_pnl(self) -> Decimal:
        return self.price_pnl + self.total_funding_pnl - self.total_costs
