"""Future multi-leg strategy intent model for cash-and-carry and structural trades."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class LegIntent:
    """Specification for an individual execution leg."""
    market: str  # "BINANCE:SPOT" or "BINANCE:USD_M_PERP"
    symbol: str  # e.g. "BTCUSDT"
    side: str    # "BUY" or "SELL"
    order_type: str  # "MARKET" or "LIMIT"
    quantity: Decimal
    target_price: Decimal | None = None
    role: str = "PRIMARY"  # "PRIMARY" or "HEDGE"


@dataclass(frozen=True)
class MultiLegStrategyIntent:
    """Atomic multi-leg trading intent representing delta-neutral or relative carry structures."""
    strategy_id: str
    target_hedge_ratio: Decimal  # e.g. 1.0 for 1:1 delta hedge, or rolling beta
    leg_1: LegIntent
    leg_2: LegIntent
    
    # Execution & Risk Safeguards
    max_legging_delay_ms: int = 1000            # Maximum allowable fill delay between legs
    max_delta_mismatch_usd: Decimal = Decimal("500.0")  # Abort / neutralize if net unhedged delta exceeds threshold
    atomicity_policy: str = "ALL_OR_CANCEL_HEDGE"       # If second leg fails, immediately neutralize first leg
    
    # Economics & Hurdle
    expected_carry_bps: Decimal = Decimal("0")
    estimated_round_trip_cost_bps: Decimal = Decimal("0")
    entry_condition_summary: str = ""
    exit_condition_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "target_hedge_ratio": str(self.target_hedge_ratio),
            "leg_1": {
                "market": self.leg_1.market,
                "symbol": self.leg_1.symbol,
                "side": self.leg_1.side,
                "order_type": self.leg_1.order_type,
                "quantity": str(self.leg_1.quantity),
                "role": self.leg_1.role,
            },
            "leg_2": {
                "market": self.leg_2.market,
                "symbol": self.leg_2.symbol,
                "side": self.leg_2.side,
                "order_type": self.leg_2.order_type,
                "quantity": str(self.leg_2.quantity),
                "role": self.leg_2.role,
            },
            "max_legging_delay_ms": self.max_legging_delay_ms,
            "max_delta_mismatch_usd": str(self.max_delta_mismatch_usd),
            "atomicity_policy": self.atomicity_policy,
            "expected_carry_bps": str(self.expected_carry_bps),
            "estimated_round_trip_cost_bps": str(self.estimated_round_trip_cost_bps),
            "entry_condition_summary": self.entry_condition_summary,
            "exit_condition_summary": self.exit_condition_summary,
        }
