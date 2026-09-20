from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from .unit_rates import TEN_THOUSAND, bps_to_fraction


@dataclass(frozen=True)
class DetailedCostPolicy:
    """Explicit, auditable transaction cost specification separating exchange fee, spread, and slippage."""

    instrument_type: str  # "PERP" or "SPOT"
    exchange_fee_bps: Decimal
    spread_bps: Decimal
    slippage_bps: Decimal
    include_funding: bool = True

    @property
    def total_turnover_rate(self) -> Decimal:
        """Total one-way cost rate per unit turnover (fraction of notional)."""
        return bps_to_fraction(self.exchange_fee_bps + self.spread_bps + self.slippage_bps)


# Predefined canonical cost profiles
# Base: VIP0 Binance standard (Perp: 5 bps taker fee, 1 bp spread, 4 bps slippage = 10 bps one-way)
BASE_PERP_COST = DetailedCostPolicy(
    instrument_type="PERP",
    exchange_fee_bps=Decimal("5.0"),
    spread_bps=Decimal("1.0"),
    slippage_bps=Decimal("4.0"),
    include_funding=True,
)

# Stressed Perp: 10 bps taker fee, 3 bps spread, 12 bps slippage = 25 bps one-way (50 bps round-trip)
STRESSED_PERP_COST = DetailedCostPolicy(
    instrument_type="PERP",
    exchange_fee_bps=Decimal("10.0"),
    spread_bps=Decimal("3.0"),
    slippage_bps=Decimal("12.0"),
    include_funding=True,
)

# Base Spot: 10 bps taker fee, 1 bp spread, 4 bps slippage = 15 bps one-way (30 bps round-trip, NO funding)
BASE_SPOT_COST = DetailedCostPolicy(
    instrument_type="SPOT",
    exchange_fee_bps=Decimal("10.0"),
    spread_bps=Decimal("1.0"),
    slippage_bps=Decimal("4.0"),
    include_funding=False,
)

# Stressed Spot: 20 bps taker fee, 3 bps spread, 12 bps slippage = 35 bps one-way (70 bps round-trip, NO funding)
STRESSED_SPOT_COST = DetailedCostPolicy(
    instrument_type="SPOT",
    exchange_fee_bps=Decimal("20.0"),
    spread_bps=Decimal("3.0"),
    slippage_bps=Decimal("12.0"),
    include_funding=False,
)


def compute_funding_cash_flow(
    position: int,  # 1 for long, -1 for short, 0 for flat
    funding_rate: Decimal | float,
) -> Decimal:
    """Calculate point-in-time funding cash flow according to Binance USD-M Perp settlement rules.
    
    Settlement semantics:
      - Long position (position = +1):
          pays funding if funding_rate > 0 (cash flow = -funding_rate)
          receives funding if funding_rate < 0 (cash flow = +|funding_rate|)
      - Short position (position = -1):
          receives funding if funding_rate > 0 (cash flow = +funding_rate)
          pays funding if funding_rate < 0 (cash flow = -|funding_rate|)
      - Flat (position = 0): zero cash flow.
    
    Returns:
      Decimal cash flow rate relative to notional (positive = cash received, negative = cash paid).
    """
    if position == 0:
        return Decimal("0")

    rate_d = Decimal(str(funding_rate))
    # Net cash flow to equity: -1 * position * funding_rate
    return Decimal(-position) * rate_d
