from __future__ import annotations

from decimal import Decimal

ONE = Decimal("1")
TEN_THOUSAND = Decimal("10000")
ONE_HUNDRED = Decimal("100")


def bps_to_fraction(bps: float | Decimal | str) -> Decimal:
    """Convert basis points to unit decimal fraction.
    
    Example:
        1 bp   -> 0.0001
        4 bps  -> 0.0004
        30 bps -> 0.0030
        40 bps -> 0.0040
    """
    return Decimal(str(bps)) / TEN_THOUSAND


def fraction_to_bps(fraction: float | Decimal | str) -> Decimal:
    """Convert unit decimal fraction to basis points.
    
    Example:
        0.0001 -> 1.0 bp
        0.0004 -> 4.0 bps
        0.0030 -> 30.0 bps
        0.0040 -> 40.0 bps
    """
    return Decimal(str(fraction)) * TEN_THOUSAND


def percent_to_fraction(pct: float | Decimal | str) -> Decimal:
    """Convert percentage (0-100) to unit decimal fraction (0-1).
    
    Example:
        1.0% -> 0.01
        0.04% -> 0.0004
        0.40% -> 0.0040
    """
    return Decimal(str(pct)) / ONE_HUNDRED


def fraction_to_percent(fraction: float | Decimal | str) -> Decimal:
    """Convert unit decimal fraction (0-1) to percentage (0-100)."""
    return Decimal(str(fraction)) * ONE_HUNDRED
