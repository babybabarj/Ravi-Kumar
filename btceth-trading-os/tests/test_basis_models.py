"""Unit tests for basis dislocation models, z-scores, and velocity metrics."""
import math
import pytest

from btceth_os.research.structural.basis_metrics import (
    compute_basis_velocity,
    compute_mark_spot_basis,
    compute_mark_spot_basis_ratio,
    compute_perp_index_basis,
    compute_rolling_zscores,
    compute_trade_basis,
    compute_trade_basis_ratio,
)


def test_basis_calculations_zero_safe():
    assert compute_trade_basis_ratio(50000.0, 0.0) == 0.0
    assert compute_mark_spot_basis_ratio(50000.0, 0.0) == 0.0


def test_rolling_zscores():
    # 200 data points with steady mean=10, std=2, and last point spiked to 25
    series = [10.0] * 200
    for i in range(50, 150):
        series[i] += math.sin((i - 50) * 0.0314) * 2.0
    series[-1] = 25.0  # Spiked

    zscores = compute_rolling_zscores(series, window=50)
    assert len(zscores) == 200
    assert zscores[-1] > 2.0  # Extreme dislocation detected


def test_basis_velocity():
    series = [10.0, 12.0, 15.0, 18.0, 25.0]
    velocity = compute_basis_velocity(series, horizon_steps=2)
    assert len(velocity) == 5
    assert velocity[0] == 0.0
    assert velocity[1] == 0.0
    # velocity[2] = 15.0 - 10.0 = 5.0
    assert velocity[2] == 5.0
    # velocity[4] = 25.0 - 15.0 = 10.0
    assert velocity[4] == 10.0
