from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
import pytest

from btceth_os.sources.binance.archive_planner import (
    first_monday_after_month,
    monthly_archive_eligible,
    daily_archive_eligible,
    plan_archive_requests,
    plan_archive_requests_detailed,
)
from btceth_os.sources.registry import load_historical_datasets_registry


@pytest.fixture(scope="module")
def spot_btc_klines():
    datasets = load_historical_datasets_registry()
    for d in datasets:
        if d.dataset_id == "BINANCE:SPOT:BTCUSDT:KLINES_1M":
            return d
    raise RuntimeError("Dataset not found")


@pytest.fixture(scope="module")
def usdm_funding():
    datasets = load_historical_datasets_registry()
    for d in datasets:
        if d.dataset_id == "BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY":
            return d
    raise RuntimeError("Dataset not found")


def test_first_monday_calculation():
    # November 2024: December 1, 2024 was Sunday -> First Monday was Dec 2, 2024
    assert first_monday_after_month(2024, 11) == datetime(2024, 12, 2, tzinfo=timezone.utc)

    # August 2024: September 1, 2024 was Sunday -> First Monday was Sept 2, 2024
    assert first_monday_after_month(2024, 8) == datetime(2024, 9, 2, tzinfo=timezone.utc)

    # April 2024: May 1, 2024 was Wednesday -> First Monday was May 6, 2024
    assert first_monday_after_month(2024, 4) == datetime(2024, 5, 6, tzinfo=timezone.utc)

    # December 2024: January 1, 2025 was Wednesday -> First Monday was Jan 6, 2025
    assert first_monday_after_month(2024, 12) == datetime(2025, 1, 6, tzinfo=timezone.utc)


def test_monthly_archive_eligibility_boundary():
    # November 2024 first Monday was 2024-12-02 00:00:00 UTC
    before_mon = datetime(2024, 12, 1, 23, 59, 59, tzinfo=timezone.utc)
    on_mon = datetime(2024, 12, 2, 0, 0, 0, tzinfo=timezone.utc)

    assert not monthly_archive_eligible(2024, 11, as_of_utc=before_mon)
    assert monthly_archive_eligible(2024, 11, as_of_utc=on_mon)

    # Current/future month is never eligible
    assert not monthly_archive_eligible(2024, 12, as_of_utc=on_mon)


def test_daily_archive_eligibility():
    # Day 2024-11-15 is eligible on 2024-11-16 00:00:00 UTC (with lag=1)
    d = date(2024, 11, 15)
    assert not daily_archive_eligible(d, as_of_utc=datetime(2024, 11, 15, 23, 59, 59, tzinfo=timezone.utc))
    assert daily_archive_eligible(d, as_of_utc=datetime(2024, 11, 16, 0, 0, 0, tzinfo=timezone.utc))


def test_one_day_range(spot_btc_klines):
    specs = plan_archive_requests(
        spot_btc_klines,
        start="2024-11-15",
        end="2024-11-15",
        as_of_utc="2024-11-20",
    )
    assert len(specs) == 1
    assert specs[0].cadence == "daily"
    assert specs[0].period_key == "2024-11-15"
    assert specs[0].archive_filename == "BTCUSDT-1m-2024-11-15.zip"


def test_single_complete_month_prefers_monthly(spot_btc_klines):
    specs = plan_archive_requests(
        spot_btc_klines,
        start="2024-11-01",
        end="2024-11-30",
        as_of_utc="2024-12-10",
    )
    assert len(specs) == 1
    assert specs[0].cadence == "monthly"
    assert specs[0].period_key == "2024-11"
    assert specs[0].archive_filename == "BTCUSDT-1m-2024-11.zip"


def test_partial_first_month(spot_btc_klines):
    specs = plan_archive_requests(
        spot_btc_klines,
        start="2024-11-15",
        end="2024-12-31",
        as_of_utc="2025-01-10",
    )
    # Nov 15 to Nov 30 = 16 days (daily)
    # Dec 01 to Dec 31 = full month eligible (monthly)
    assert len(specs) == 17
    assert specs[0].cadence == "daily"
    assert specs[0].period_key == "2024-11-15"
    assert specs[15].period_key == "2024-11-30"
    assert specs[16].cadence == "monthly"
    assert specs[16].period_key == "2024-12"


def test_partial_final_month(spot_btc_klines):
    specs = plan_archive_requests(
        spot_btc_klines,
        start="2024-11-01",
        end="2024-12-15",
        as_of_utc="2025-01-10",
    )
    # Nov 01 to Nov 30 = full month (monthly)
    # Dec 01 to Dec 15 = 15 days (daily)
    assert len(specs) == 16
    assert specs[0].cadence == "monthly"
    assert specs[0].period_key == "2024-11"
    assert specs[1].cadence == "daily"
    assert specs[1].period_key == "2024-12-01"
    assert specs[15].period_key == "2024-12-15"


def test_multi_month_range(spot_btc_klines):
    specs = plan_archive_requests(
        spot_btc_klines,
        start="2024-09-01",
        end="2024-11-30",
        as_of_utc="2024-12-10",
    )
    assert len(specs) == 3
    assert [s.period_key for s in specs] == ["2024-09", "2024-10", "2024-11"]
    assert all(s.cadence == "monthly" for s in specs)


def test_year_boundary(spot_btc_klines):
    specs = plan_archive_requests(
        spot_btc_klines,
        start="2024-12-25",
        end="2025-01-05",
        as_of_utc="2025-01-10",
    )
    # Dec 25 to Dec 31 (7 days) + Jan 01 to Jan 05 (5 days) = 12 daily specs
    assert len(specs) == 12
    assert specs[0].period_key == "2024-12-25"
    assert specs[6].period_key == "2024-12-31"
    assert specs[7].period_key == "2025-01-01"
    assert specs[11].period_key == "2025-01-05"


def test_leap_day_and_lengths(spot_btc_klines):
    # Feb 2024 is leap year (29 days)
    specs_leap = plan_archive_requests(
        spot_btc_klines,
        start="2024-02-28",
        end="2024-03-01",
        as_of_utc="2024-03-10",
    )
    assert [s.period_key for s in specs_leap] == ["2024-02-28", "2024-02-29", "2024-03-01"]

    # Full Feb 2024 leap month
    specs_feb24 = plan_archive_requests(
        spot_btc_klines,
        start="2024-02-01",
        end="2024-02-29",
        as_of_utc="2024-03-10",
    )
    assert len(specs_feb24) == 1
    assert specs_feb24[0].period_key == "2024-02"

    # Full Feb 2023 non-leap month (28 days)
    specs_feb23 = plan_archive_requests(
        spot_btc_klines,
        start="2023-02-01",
        end="2023-02-28",
        as_of_utc="2023-03-10",
    )
    assert len(specs_feb23) == 1
    assert specs_feb23[0].period_key == "2023-02"


def test_funding_rate_monthly_only_and_unsupported_daily(usdm_funding):
    # Full eligible month -> 1 monthly spec
    plan = plan_archive_requests_detailed(
        usdm_funding,
        start="2024-11-01",
        end="2024-11-30",
        as_of_utc="2024-12-10",
    )
    assert len(plan.specs) == 1
    assert plan.specs[0].cadence == "monthly"
    assert plan.specs[0].archive_filename == "BTCUSDT-fundingRate-2024-11.zip"
    assert len(plan.unfulfilled) == 0

    # Partial month cannot be fulfilled by daily archives
    plan_partial = plan_archive_requests_detailed(
        usdm_funding,
        start="2024-11-15",
        end="2024-11-20",
        as_of_utc="2024-12-10",
    )
    assert len(plan_partial.specs) == 0
    assert len(plan_partial.unfulfilled) == 6
    assert all(u.status == "SOURCE_UNSUPPORTED" for u in plan_partial.unfulfilled)


def test_future_and_current_day_exclusion(spot_btc_klines):
    plan = plan_archive_requests_detailed(
        spot_btc_klines,
        start="2026-09-15",
        end="2026-09-18",
        as_of_utc="2026-09-16 12:00:00",
        daily_lag_days=1,
    )
    # 2026-09-15 is eligible (completed before as_of)
    # 2026-09-16 is current day (not yet completed) -> NOT_YET_AVAILABLE
    # 2026-09-17, 2026-09-18 are future -> NOT_YET_AVAILABLE
    assert len(plan.specs) == 1
    assert plan.specs[0].period_key == "2026-09-15"
    assert len(plan.unfulfilled) == 3
    assert all(u.status == "NOT_YET_AVAILABLE" for u in plan.unfulfilled)


def test_start_greater_than_end_raises(spot_btc_klines):
    with pytest.raises(ValueError, match="start.*must be <= end"):
        plan_archive_requests(
            spot_btc_klines,
            start="2024-11-20",
            end="2024-11-10",
            as_of_utc="2024-12-01",
        )


def test_non_overlap_mechanical_invariant(spot_btc_klines):
    """Mechanical invariant test: no single UTC day is covered by more than one ArchiveObjectSpec."""
    plan = plan_archive_requests_detailed(
        spot_btc_klines,
        start="2024-10-15",
        end="2024-12-15",
        as_of_utc="2025-01-10",
    )

    covered_days: set[date] = set()
    for spec in plan.specs:
        if spec.cadence == "monthly":
            y, m = [int(x) for x in spec.period_key.split("-")]
            _, num_days = calendar.monthrange(y, m)
            for day_num in range(1, num_days + 1):
                d = date(y, m, day_num)
                assert d not in covered_days, f"Day {d} duplicate coverage by monthly {spec.period_key}"
                covered_days.add(d)
        else:
            d = date.fromisoformat(spec.period_key)
            assert d not in covered_days, f"Day {d} duplicate coverage by daily {spec.period_key}"
            covered_days.add(d)

    # Total days covered:
    # Oct 15-31 = 17 days (daily)
    # Nov 01-30 = 30 days (monthly)
    # Dec 01-15 = 15 days (daily)
    # Total = 62 days
    assert len(covered_days) == 62


def test_as_of_determinism(spot_btc_klines):
    """Calling plan_archive_requests repeatedly with the same as_of_utc yields identical output."""
    res1 = plan_archive_requests(
        spot_btc_klines,
        start="2024-11-10",
        end="2024-12-20",
        as_of_utc="2025-01-10 15:30:00",
    )
    for _ in range(10):
        res_i = plan_archive_requests(
            spot_btc_klines,
            start="2024-11-10",
            end="2024-12-20",
            as_of_utc="2025-01-10 15:30:00",
        )
        assert res1 == res_i
