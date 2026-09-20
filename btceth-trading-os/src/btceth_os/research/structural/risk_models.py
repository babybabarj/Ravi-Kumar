"""Risk modeling: margin utilization, liquidation proximity, basis widening, and legging delay (Pure stdlib)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


@dataclass(frozen=True)
class MarginStressResult:
    max_adverse_basis_widening_bps: float
    max_margin_utilization_pct: float
    min_margin_buffer_pct: float
    is_liquidated: bool
    temporary_delta_exposure_usd: float


def evaluate_margin_and_basis_stress(
    spot_entry: float,
    perp_entry: float,
    spot_prices: Sequence[float],
    perp_mark_prices: Sequence[float],
    perp_quantity: float,
    perp_collateral_usd: float,
    maintenance_margin_rate: float = 0.005,  # 0.5% standard Binance tier 1 maintenance margin
) -> MarginStressResult:
    """Stress test short-perp leg margin utilization and liquidation proximity under adverse basis widening."""
    n = min(len(spot_prices), len(perp_mark_prices))
    
    if n == 0 or perp_collateral_usd <= 0:
        return MarginStressResult(0.0, 0.0, 100.0, False, 0.0)

    initial_basis_bps = ((perp_entry - spot_entry) / spot_entry) * 10000.0 if spot_entry > 0 else 0.0
    
    max_adverse_widening_bps = 0.0
    max_utilization_pct = 0.0
    min_buffer_pct = 100.0
    liquidated = False

    for i in range(n):
        s_t = spot_prices[i]
        m_t = perp_mark_prices[i]
        
        # Current basis in bps
        current_basis_bps = ((m_t - s_t) / s_t) * 10000.0 if s_t > 0 else 0.0
        adverse_widening = current_basis_bps - initial_basis_bps
        if adverse_widening > max_adverse_widening_bps:
            max_adverse_widening_bps = adverse_widening

        # Short Perp P&L against mark price
        unrealized_loss = perp_quantity * (m_t - perp_entry)  # > 0 means loss for short
        maint_margin_req = (perp_quantity * m_t) * maintenance_margin_rate
        
        # Equity supporting perp
        perp_equity = perp_collateral_usd - unrealized_loss
        
        if perp_equity <= maint_margin_req:
            liquidated = True
            utilization = 100.0
            buffer = 0.0
        else:
            utilization = (maint_margin_req / perp_equity) * 100.0
            buffer = ((perp_equity - maint_margin_req) / perp_collateral_usd) * 100.0

        if utilization > max_utilization_pct:
            max_utilization_pct = utilization
        if buffer < min_buffer_pct:
            min_buffer_pct = buffer

    return MarginStressResult(
        max_adverse_basis_widening_bps=max_adverse_widening_bps,
        max_margin_utilization_pct=max_utilization_pct,
        min_margin_buffer_pct=max(0.0, min_buffer_pct),
        is_liquidated=liquidated,
        temporary_delta_exposure_usd=0.0,
    )


def simulate_legging_friction(
    spot_quantity: float,
    spot_price_entry: float,
    perp_price_delay: float,
    perp_price_intended: float,
    delay_ms: int = 500,
) -> tuple[float, float]:
    """Simulate execution friction when spot fills first and perp is delayed.
    
    Returns:
        (slippage_from_delay_usd, temporary_unhedged_delta_usd)
    """
    unhedged_delta_usd = spot_quantity * spot_price_entry
    adverse_move = perp_price_intended - perp_price_delay
    delay_loss_usd = max(0.0, spot_quantity * adverse_move)
    return delay_loss_usd, unhedged_delta_usd
