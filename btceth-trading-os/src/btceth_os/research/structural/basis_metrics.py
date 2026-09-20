"""Basis definitions, metrics, and dislocation indicators (Pure Python stdlib)."""
from __future__ import annotations

from decimal import Decimal
import math
from typing import Sequence


def compute_trade_basis(perp_price: float | Decimal, spot_price: float | Decimal) -> float:
    """Raw price difference: Traded Perp - Traded Spot."""
    return float(perp_price) - float(spot_price)


def compute_trade_basis_ratio(perp_price: float | Decimal, spot_price: float | Decimal) -> float:
    """Normalized basis ratio: (Traded Perp - Traded Spot) / Traded Spot."""
    sp = float(spot_price)
    if sp <= 0:
        return 0.0
    return (float(perp_price) - sp) / sp


def compute_mark_spot_basis(mark_price: float | Decimal, spot_price: float | Decimal) -> float:
    """Mark price difference against Spot: Official Mark - Traded Spot."""
    return float(mark_price) - float(spot_price)


def compute_mark_spot_basis_ratio(mark_price: float | Decimal, spot_price: float | Decimal) -> float:
    """Normalized mark basis ratio: (Mark - Spot) / Spot."""
    sp = float(spot_price)
    if sp <= 0:
        return 0.0
    return (float(mark_price) - sp) / sp


def compute_perp_index_basis(perp_price: float | Decimal, index_price: float | Decimal) -> float:
    """Dislocation between Binance Perp and global Spot Index."""
    return float(perp_price) - float(index_price)


def compute_rolling_zscores(series: Sequence[float], window: int = 168) -> list[float]:
    """Compute rolling z-score across a given lookback window (e.g. 168 hours = 7 days)."""
    n = len(series)
    zscores = [0.0] * n
    if n < window:
        return zscores

    for i in range(window, n):
        sub = series[i - window : i]
        mean = sum(sub) / float(window)
        variance = sum((x - mean) ** 2 for x in sub) / float(window)
        std = math.sqrt(variance)
        if std > 1e-8:
            zscores[i] = (series[i] - mean) / std
        else:
            zscores[i] = 0.0
    return zscores


def compute_basis_velocity(basis_series: Sequence[float], horizon_steps: int = 4) -> list[float]:
    """Rate of change in basis over horizon_steps (e.g. 4 hours)."""
    n = len(basis_series)
    velocity = [0.0] * n
    if n <= horizon_steps:
        return velocity

    for i in range(horizon_steps, n):
        velocity[i] = basis_series[i] - basis_series[i - horizon_steps]
    return velocity
