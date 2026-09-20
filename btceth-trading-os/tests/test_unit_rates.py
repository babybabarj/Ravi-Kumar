from __future__ import annotations

from decimal import Decimal
import pytest

from btceth_os.research.unit_rates import (
    bps_to_fraction,
    fraction_to_bps,
    fraction_to_percent,
    percent_to_fraction,
)


def test_bps_to_fraction_exact():
    assert bps_to_fraction(1) == Decimal("0.0001")
    assert bps_to_fraction(4) == Decimal("0.0004")
    assert bps_to_fraction(30) == Decimal("0.0030")
    assert bps_to_fraction(40) == Decimal("0.0040")
    assert bps_to_fraction("0.5") == Decimal("0.00005")


def test_fraction_to_bps_exact():
    assert fraction_to_bps("0.0001") == Decimal("1")
    assert fraction_to_bps("0.0004") == Decimal("4")
    assert fraction_to_bps("0.0030") == Decimal("30")
    assert fraction_to_bps("0.0040") == Decimal("40")


def test_percent_conversions():
    assert percent_to_fraction(1) == Decimal("0.01")
    assert percent_to_fraction("0.04") == Decimal("0.0004")
    assert percent_to_fraction("0.40") == Decimal("0.0040")
    assert fraction_to_percent(Decimal("0.0004")) == Decimal("0.04")
    assert fraction_to_percent(Decimal("0.0040")) == Decimal("0.40")


def test_round_trip_conversions():
    for bps in [0.1, 1.0, 5.0, 15.0, 30.0, 40.0, 100.0, 250.0]:
        d_bps = Decimal(str(bps))
        frac = bps_to_fraction(d_bps)
        recovered = fraction_to_bps(frac)
        assert recovered == d_bps
