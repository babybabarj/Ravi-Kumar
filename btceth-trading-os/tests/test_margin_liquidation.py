"""Unit tests for margin stress, basis widening, and legging friction."""
import pytest

from btceth_os.research.structural.risk_models import (
    evaluate_margin_and_basis_stress,
    simulate_legging_friction,
)


def test_margin_and_basis_stress_stable():
    # Spot and mark price stay aligned
    spot_entry = 30000.0
    perp_entry = 30050.0
    spot_prices = [30000.0, 30100.0, 30200.0]
    perp_marks = [30050.0, 30150.0, 30250.0]
    collateral = 15000.0  # 50% collateral on $30,000 notional

    res = evaluate_margin_and_basis_stress(
        spot_entry=spot_entry,
        perp_entry=perp_entry,
        spot_prices=spot_prices,
        perp_mark_prices=perp_marks,
        perp_quantity=1.0,
        perp_collateral_usd=collateral,
    )
    assert not res.is_liquidated
    assert res.max_margin_utilization_pct < 5.0
    assert res.min_margin_buffer_pct > 90.0


def test_margin_and_basis_stress_liquidation():
    # Extreme basis divergence: spot stays at $30,000 while perp explodes to $55,000
    spot_entry = 30000.0
    perp_entry = 30050.0
    spot_prices = [30000.0, 30000.0]
    perp_marks = [30050.0, 55000.0]
    collateral = 5000.0  # Small collateral ($5,000)

    res = evaluate_margin_and_basis_stress(
        spot_entry=spot_entry,
        perp_entry=perp_entry,
        spot_prices=spot_prices,
        perp_mark_prices=perp_marks,
        perp_quantity=1.0,
        perp_collateral_usd=collateral,
    )
    # Unrealized loss = 55,000 - 30,050 = $24,950 > $5,000 collateral -> LIQUIDATED!
    assert res.is_liquidated is True
    assert res.max_margin_utilization_pct == 100.0
    assert res.min_margin_buffer_pct == 0.0


def test_legging_friction():
    # Buying 1 BTC spot at $30,000. Intended to short perp at $30,050.
    # Due to 500ms delay, perp dropped to $30,020 before order arrived.
    slip_loss, unhedged_delta = simulate_legging_friction(
        spot_quantity=1.0,
        spot_price_entry=30000.0,
        perp_price_delay=30020.0,
        perp_price_intended=30050.0,
        delay_ms=500,
    )
    # Unhedged delta during delay is $30,000
    assert unhedged_delta == 30000.0
    # Slippage loss: $30,050 - $30,020 = $30.00
    assert slip_loss == 30.0
