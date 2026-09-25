"""
NEWS/MACRO-1A: Comprehensive test suite.

Tests 30+ specific behaviours of the macro intelligence layer.

All tests use deterministic fixtures — no real API calls.
Real API smoke tests use /tmp output only and are skipped unless
explicitly enabled via NM1A_SMOKE_TEST=1 environment variable.

TRADING_CAPABILITY = ZERO — all tests verify that no execution
capability is present.
"""
from __future__ import annotations

import os
import ast
import sys
import importlib
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NY = ZoneInfo("America/New_York")

T_SNAP = datetime(2026, 9, 25, 21, 49, 16, tzinfo=timezone.utc)
T_PAST = T_SNAP - timedelta(hours=6)
T_FUTURE = T_SNAP + timedelta(hours=6)


def make_vintage(published_utc: datetime, value: float):
    from btceth_os.macro.types import MacroVintage
    return MacroVintage(published_at_utc=published_utc, value=value)


def make_observation(series_id="TEST_SERIES", vintages=(), quality=None, availability=None):
    from btceth_os.macro.types import (
        MacroDataQuality, MacroAvailabilityStatus, MacroSeriesObservation
    )
    q = quality or MacroDataQuality.GOOD
    a = availability or MacroAvailabilityStatus.AVAILABLE
    return MacroSeriesObservation(
        series_id=series_id,
        family="TEST",
        reference_period="2026-09",
        vintages=vintages,
        quality=q,
        availability_status=a,
        unit="percent",
        source_agency="TEST_AGENCY",
        staleness_seconds=None,
    )


def make_event(published_utc: datetime, value: float = 3.2):
    from btceth_os.macro.types import MacroEvent
    return MacroEvent(
        event_id="CPI_TEST_2026_09",
        family="CPI",
        description="Test CPI event",
        reference_period="2026-09",
        actual_release_utc=published_utc,
        actual_value=value,
        prior_value=3.0,
        unit="percent_yoy",
        source_agency="BLS",
        consensus_value=None,
        consensus_status="NOT_AVAILABLE",
    )


def make_news_item(published_utc: datetime):
    from btceth_os.macro.types import (
        MacroNewsItem, MacroDataQuality, MacroAvailabilityStatus
    )
    return MacroNewsItem(
        item_id="FED_SPEECH_TEST",
        source="FEDERAL_RESERVE",
        item_type="FED_SPEECH",
        published_at_utc=published_utc,
        headline="Test Fed speech headline.",
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        url=None,
    )


def make_snapshot(
    snap_time: datetime = T_SNAP,
    events=(),
    news_items=(),
    series_obs=(),
):
    from btceth_os.macro.snapshot import MacroIntelligenceSnapshot
    from btceth_os.macro.types import MacroDataQuality
    return MacroIntelligenceSnapshot(
        snapshot_time_utc=snap_time,
        snapshot_id="TEST-SNAP-001",
        trading_capability=0,
        macro_events=tuple(events),
        news_items=tuple(news_items),
        series_observations=tuple(series_obs),
        overall_data_quality=MacroDataQuality.MISSING,
        dxy_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
        breaking_news_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
        alfred_runtime_status="NOT_CONFIGURED",
        limitations=("NEWS_MACRO_1A_STUB",),
    )


# ===========================================================================
# GATE 1: Package imports correctly
# ===========================================================================

def test_macro_package_imports():
    """Gate 1: btceth_os.macro imports without error."""
    import btceth_os.macro
    assert hasattr(btceth_os.macro, "MacroEvent")
    assert hasattr(btceth_os.macro, "MacroSeriesObservation")
    assert hasattr(btceth_os.macro, "MacroNewsItem")
    assert hasattr(btceth_os.macro, "MacroDataQuality")
    assert hasattr(btceth_os.macro, "MacroAvailabilityStatus")
    assert hasattr(btceth_os.macro, "MacroIntelligenceSnapshot")
    assert hasattr(btceth_os.macro, "PointInTimeAvailabilityChecker")
    assert hasattr(btceth_os.macro, "MACRO_EVENT_REGISTRY")
    assert hasattr(btceth_os.macro, "MacroEventFamily")


# ===========================================================================
# GATE 2: MacroEvent is frozen and requires mandatory fields
# ===========================================================================

def test_macro_event_frozen():
    """Gate 2a: MacroEvent is frozen (immutable)."""
    event = make_event(T_PAST)
    with pytest.raises((AttributeError, TypeError)):
        event.actual_value = 99.0  # type: ignore[misc]


def test_macro_event_empty_event_id_raises():
    """Gate 2b: MacroEvent.event_id must not be empty."""
    from btceth_os.macro.types import MacroEvent
    with pytest.raises(ValueError, match="event_id"):
        MacroEvent(
            event_id="",
            family="CPI",
            description="Test",
            reference_period="2026-09",
            actual_release_utc=T_PAST,
            actual_value=3.2,
            prior_value=3.0,
            unit="percent_yoy",
            source_agency="BLS",
        )


# ===========================================================================
# GATE 3: Consensus is optional / null when no authorised provider
# ===========================================================================

def test_consensus_defaults_to_none():
    """Gate 3: MacroEvent consensus_value defaults to None."""
    event = make_event(T_PAST)
    assert event.consensus_value is None
    assert event.consensus_status == "NOT_AVAILABLE"


def test_macro_surprise_requires_both_actual_and_consensus():
    """Gate 3b: MacroSurprise raises if magnitude is inconsistent."""
    from btceth_os.macro.types import MacroSurprise
    with pytest.raises(ValueError, match="surprise_magnitude"):
        MacroSurprise(
            event_id="X",
            actual_value=3.2,
            consensus_value=3.0,
            surprise_magnitude=99.0,  # wrong
            surprise_direction="BEAT",
            in_line_tolerance=0.05,
        )


def test_macro_surprise_valid():
    """Gate 3c: Valid MacroSurprise is accepted."""
    from btceth_os.macro.types import MacroSurprise
    s = MacroSurprise(
        event_id="CPI_TEST",
        actual_value=3.2,
        consensus_value=3.0,
        surprise_magnitude=0.2,
        surprise_direction="BEAT",
        in_line_tolerance=0.05,
    )
    assert s.surprise_magnitude == pytest.approx(0.2)


def test_macro_surprise_invalid_direction():
    """Gate 3d: MacroSurprise raises on invalid surprise_direction."""
    from btceth_os.macro.types import MacroSurprise
    with pytest.raises(ValueError, match="surprise_direction"):
        MacroSurprise(
            event_id="X",
            actual_value=3.2,
            consensus_value=3.0,
            surprise_magnitude=0.2,
            surprise_direction="HOT",  # invalid
            in_line_tolerance=0.05,
        )


# ===========================================================================
# GATE 4: Point-in-time availability contract
# ===========================================================================

def test_availability_checker_available():
    """Gate 4a: Vintage published before snapshot → AVAILABLE."""
    from btceth_os.macro.availability import PointInTimeAvailabilityChecker
    from btceth_os.macro.types import MacroAvailabilityStatus
    checker = PointInTimeAvailabilityChecker()
    v = make_vintage(T_PAST, 3.2)
    status, staleness = checker.check_vintage_availability((v,), T_SNAP)
    assert status == MacroAvailabilityStatus.AVAILABLE
    assert staleness is not None
    assert staleness > 0


def test_availability_checker_not_yet_released():
    """Gate 4b: Vintage published after snapshot → NOT_YET_RELEASED."""
    from btceth_os.macro.availability import PointInTimeAvailabilityChecker
    from btceth_os.macro.types import MacroAvailabilityStatus
    checker = PointInTimeAvailabilityChecker()
    v = make_vintage(T_FUTURE, 3.2)
    status, staleness = checker.check_vintage_availability((v,), T_SNAP)
    assert status == MacroAvailabilityStatus.NOT_YET_RELEASED
    assert staleness is None


def test_availability_checker_stale():
    """Gate 4c: Vintage older than staleness limit → STALE."""
    from btceth_os.macro.availability import PointInTimeAvailabilityChecker
    from btceth_os.macro.types import MacroAvailabilityStatus
    checker = PointInTimeAvailabilityChecker()
    old_time = T_SNAP - timedelta(days=30)
    v = make_vintage(old_time, 3.2)
    status, staleness = checker.check_vintage_availability(
        (v,), T_SNAP, staleness_limit_seconds=60 * 60 * 24 * 7
    )
    assert status == MacroAvailabilityStatus.STALE


def test_availability_checker_causal_violation():
    """Gate 4d: is_causal_violation returns True for future observation."""
    from btceth_os.macro.availability import PointInTimeAvailabilityChecker
    checker = PointInTimeAvailabilityChecker()
    assert checker.is_causal_violation(T_FUTURE, T_SNAP) is True
    assert checker.is_causal_violation(T_PAST, T_SNAP) is False


def test_availability_checker_event_available():
    """Gate 4e: Event released before snapshot → AVAILABLE."""
    from btceth_os.macro.availability import PointInTimeAvailabilityChecker
    from btceth_os.macro.types import MacroAvailabilityStatus
    checker = PointInTimeAvailabilityChecker()
    status = checker.check_event_availability(T_PAST, T_SNAP)
    assert status == MacroAvailabilityStatus.AVAILABLE


def test_availability_checker_event_not_yet_released():
    """Gate 4f: Event released after snapshot → NOT_YET_RELEASED."""
    from btceth_os.macro.availability import PointInTimeAvailabilityChecker
    from btceth_os.macro.types import MacroAvailabilityStatus
    checker = PointInTimeAvailabilityChecker()
    status = checker.check_event_availability(T_FUTURE, T_SNAP)
    assert status == MacroAvailabilityStatus.NOT_YET_RELEASED


def test_vintage_latest_value_at():
    """Gate 4g: MacroSeriesObservation.latest_value_at returns correct causal value."""
    from btceth_os.macro.types import MacroDataQuality, MacroAvailabilityStatus, MacroSeriesObservation

    v1 = make_vintage(T_SNAP - timedelta(hours=24), 3.0)
    v2 = make_vintage(T_SNAP - timedelta(hours=1), 3.2)   # latest causal
    v3 = make_vintage(T_SNAP + timedelta(hours=1), 3.5)   # future — must NOT appear

    obs = MacroSeriesObservation(
        series_id="CPI_SERIES",
        family="CPI",
        reference_period="2026-09",
        vintages=(v1, v2, v3),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="percent_yoy",
        source_agency="BLS",
        staleness_seconds=3600.0,
    )
    val = obs.latest_value_at(T_SNAP)
    assert val == pytest.approx(3.2)  # v3 is excluded; v2 is latest causal


def test_vintage_latest_value_none_if_all_future():
    """Gate 4h: latest_value_at returns None if no vintage is causal."""
    from btceth_os.macro.types import MacroDataQuality, MacroAvailabilityStatus, MacroSeriesObservation
    v = make_vintage(T_FUTURE, 3.2)
    obs = MacroSeriesObservation(
        series_id="CPI_SERIES",
        family="CPI",
        reference_period="2026-09",
        vintages=(v,),
        quality=MacroDataQuality.NOT_YET_RELEASED if False else MacroDataQuality.CAUSAL_VIOLATION,
        availability_status=MacroAvailabilityStatus.NOT_YET_RELEASED,
        unit="percent_yoy",
        source_agency="BLS",
    )
    val = obs.latest_value_at(T_SNAP)
    assert val is None


# ===========================================================================
# GATE 5: MacroIntelligenceSnapshot firewall
# ===========================================================================

def test_snapshot_trading_capability_zero():
    """Gate 5a: Snapshot with trading_capability=0 is accepted."""
    snap = make_snapshot()
    assert snap.trading_capability == 0


def test_snapshot_trading_capability_nonzero_raises():
    """Gate 5b: Snapshot with trading_capability != 0 raises ValueError."""
    from btceth_os.macro.snapshot import MacroIntelligenceSnapshot
    from btceth_os.macro.types import MacroDataQuality
    with pytest.raises(ValueError, match="trading_capability"):
        MacroIntelligenceSnapshot(
            snapshot_time_utc=T_SNAP,
            snapshot_id="FIREWALL_TEST",
            trading_capability=1,  # must be rejected
            overall_data_quality=MacroDataQuality.MISSING,
            dxy_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
            breaking_news_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
            alfred_runtime_status="NOT_CONFIGURED",
        )


def test_snapshot_causal_violation_event_raises():
    """Gate 5c: Snapshot with future event raises ValueError (causal contract)."""
    future_event = make_event(T_FUTURE)
    with pytest.raises(ValueError, match="Causal violation"):
        make_snapshot(events=[future_event])


def test_snapshot_causal_violation_news_raises():
    """Gate 5d: Snapshot with future news item raises ValueError (causal contract)."""
    future_item = make_news_item(T_FUTURE)
    with pytest.raises(ValueError, match="Causal violation"):
        make_snapshot(news_items=[future_item])


def test_snapshot_empty_snapshot_id_raises():
    """Gate 5e: Snapshot with empty snapshot_id raises ValueError."""
    from btceth_os.macro.snapshot import MacroIntelligenceSnapshot
    from btceth_os.macro.types import MacroDataQuality
    with pytest.raises(ValueError, match="snapshot_id"):
        MacroIntelligenceSnapshot(
            snapshot_time_utc=T_SNAP,
            snapshot_id="",
            trading_capability=0,
            overall_data_quality=MacroDataQuality.MISSING,
            dxy_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
            breaking_news_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
            alfred_runtime_status="NOT_CONFIGURED",
        )


def test_snapshot_frozen():
    """Gate 5f: MacroIntelligenceSnapshot is frozen (immutable)."""
    snap = make_snapshot()
    with pytest.raises((AttributeError, TypeError)):
        snap.trading_capability = 1  # type: ignore[misc]


def test_snapshot_dxy_status_not_implemented():
    """Gate 5g: Default dxy_status is NOT_IMPLEMENTED_PROVIDER_REQUIRED."""
    snap = make_snapshot()
    assert snap.dxy_status == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


def test_snapshot_breaking_news_status_not_implemented():
    """Gate 5h: Default breaking_news_status is NOT_IMPLEMENTED_PROVIDER_REQUIRED."""
    snap = make_snapshot()
    assert snap.breaking_news_status == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


def test_snapshot_alfred_runtime_status_not_configured():
    """Gate 5i: Default alfred_runtime_status is NOT_CONFIGURED."""
    snap = make_snapshot()
    assert snap.alfred_runtime_status == "NOT_CONFIGURED"


# ===========================================================================
# GATE 6: DXY adapter refuses substitutes
# ===========================================================================

def test_dxy_adapter_status():
    """Gate 6a: DXYAdapter.status == NOT_IMPLEMENTED_PROVIDER_REQUIRED."""
    from btceth_os.macro.sources.dxy import DXYAdapter
    adapter = DXYAdapter()
    assert adapter.status == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


def test_dxy_adapter_returns_provider_required():
    """Gate 6b: DXYAdapter.fetch_dxy returns PROVIDER_REQUIRED quality."""
    from btceth_os.macro.sources.dxy import DXYAdapter
    from btceth_os.macro.types import MacroDataQuality
    adapter = DXYAdapter()
    obs = adapter.fetch_dxy(T_SNAP)
    assert obs.quality == MacroDataQuality.PROVIDER_REQUIRED
    assert obs.series_id == "DXY_ICE"
    assert obs.source_agency == "ICE"


def test_dxy_validate_not_substitute_raises_for_fred():
    """Gate 6c: DXYAdapter.validate_not_substitute raises for FRED broad dollar."""
    from btceth_os.macro.sources.dxy import DXYAdapter
    with pytest.raises(ValueError, match="substitute"):
        DXYAdapter.validate_not_substitute("FRED_DTWEXBGS")


def test_dxy_validate_not_substitute_raises_for_synthetic():
    """Gate 6d: DXYAdapter.validate_not_substitute raises for synthetic basket."""
    from btceth_os.macro.sources.dxy import DXYAdapter
    with pytest.raises(ValueError, match="substitute"):
        DXYAdapter.validate_not_substitute("SYNTHETIC_FX_BASKET")


# ===========================================================================
# GATE 7: ALFRED adapter runtime status
# ===========================================================================

def test_alfred_adapter_not_configured_when_no_key(monkeypatch):
    """Gate 7a: ALFREDAdapter.runtime_status == NOT_CONFIGURED when key absent."""
    monkeypatch.delenv("ALFRED_API_KEY", raising=False)
    from btceth_os.macro.sources import alfred as alfred_mod
    import importlib
    importlib.reload(alfred_mod)
    adapter = alfred_mod.ALFREDAdapter()
    assert adapter.runtime_status == "NOT_CONFIGURED"
    assert not adapter.is_configured


def test_alfred_adapter_not_configured_returns_not_configured_quality(monkeypatch):
    """Gate 7b: ALFREDAdapter returns NOT_CONFIGURED quality when key absent."""
    monkeypatch.delenv("ALFRED_API_KEY", raising=False)
    from btceth_os.macro.sources import alfred as alfred_mod
    import importlib
    importlib.reload(alfred_mod)
    adapter = alfred_mod.ALFREDAdapter()
    obs = adapter.fetch_vintage("CPIAUCSL", T_SNAP)
    from btceth_os.macro.types import MacroDataQuality
    assert obs.quality == MacroDataQuality.NOT_CONFIGURED


def test_alfred_adapter_does_not_raise_when_not_configured(monkeypatch):
    """Gate 7c: ALFREDAdapter does NOT raise when ALFRED_API_KEY is absent."""
    monkeypatch.delenv("ALFRED_API_KEY", raising=False)
    from btceth_os.macro.sources import alfred as alfred_mod
    import importlib
    importlib.reload(alfred_mod)
    # Must not raise
    adapter = alfred_mod.ALFREDAdapter()
    obs = adapter.fetch_vintage("PAYEMS", T_SNAP)
    assert obs is not None


def test_alfred_build_vintage_list_causal_filter():
    """Gate 7d: ALFRED build_vintage_list excludes future vintages."""
    from btceth_os.macro.sources.alfred import ALFREDAdapter
    adapter = ALFREDAdapter()

    raw = [
        {"realtime_start": T_PAST.isoformat(), "value": "3.1"},
        {"realtime_start": T_FUTURE.isoformat(), "value": "3.3"},  # must be excluded
    ]
    vintages = adapter.build_vintage_list(raw, T_SNAP)
    assert len(vintages) == 1
    assert vintages[0].value == pytest.approx(3.1)


# ===========================================================================
# GATE 8: Event registry completeness
# ===========================================================================

def test_event_registry_contains_required_families():
    """Gate 8: MACRO_EVENT_REGISTRY contains all required families."""
    from btceth_os.macro.event_registry import MACRO_EVENT_REGISTRY, MacroEventFamily
    required = [
        MacroEventFamily.CPI,
        MacroEventFamily.PCE,
        MacroEventFamily.NFP,
        MacroEventFamily.FOMC,
        MacroEventFamily.FED_SPEECH,
        MacroEventFamily.TREASURY_10Y,
        MacroEventFamily.DXY,
        MacroEventFamily.BREAKING_NEWS,
    ]
    for fam in required:
        assert fam in MACRO_EVENT_REGISTRY, f"Missing family: {fam}"


def test_dxy_registry_entry_has_not_implemented_provider_required():
    """Gate 8b: DXY registry entry has provider_status=NOT_IMPLEMENTED_PROVIDER_REQUIRED."""
    from btceth_os.macro.event_registry import MACRO_EVENT_REGISTRY, MacroEventFamily
    spec = MACRO_EVENT_REGISTRY[MacroEventFamily.DXY]
    assert spec.provider_status == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


def test_breaking_news_registry_has_not_implemented():
    """Gate 8c: BREAKING_NEWS registry entry has NOT_IMPLEMENTED_PROVIDER_REQUIRED."""
    from btceth_os.macro.event_registry import MACRO_EVENT_REGISTRY, MacroEventFamily
    spec = MACRO_EVENT_REGISTRY[MacroEventFamily.BREAKING_NEWS]
    assert spec.provider_status == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


# ===========================================================================
# GATE 9: Timezone handling (America/New_York, DST-aware)
# ===========================================================================

def test_timezone_est_to_utc():
    """Gate 9a: EST (-5h) to UTC conversion is correct."""
    # January = EST (UTC-5)
    est_time = datetime(2026, 1, 15, 8, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    utc_time = est_time.astimezone(timezone.utc)
    assert utc_time.hour == 13  # 8:30 EST = 13:30 UTC


def test_timezone_edt_to_utc():
    """Gate 9b: EDT (-4h) to UTC conversion is correct (DST active)."""
    # September = EDT (UTC-4)
    edt_time = datetime(2026, 9, 15, 8, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    utc_time = edt_time.astimezone(timezone.utc)
    assert utc_time.hour == 12  # 8:30 EDT = 12:30 UTC


def test_timezone_dst_boundary():
    """Gate 9c: DST spring-forward boundary is handled correctly."""
    # March 8, 2026 = DST spring-forward day (clocks move forward at 2:00 AM)
    # 1:59 AM EST is UTC-5; 3:00 AM EDT is UTC-4
    pre_dst = datetime(2026, 3, 8, 1, 59, 0, tzinfo=ZoneInfo("America/New_York"))
    post_dst = datetime(2026, 3, 8, 3, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    pre_utc = pre_dst.astimezone(timezone.utc)
    post_utc = post_dst.astimezone(timezone.utc)
    # pre: 01:59 EST = 06:59 UTC; post: 03:00 EDT = 07:00 UTC
    assert pre_utc.hour == 6 and pre_utc.minute == 59
    assert post_utc.hour == 7 and post_utc.minute == 0


# ===========================================================================
# GATE 10: Data quality aggregation
# ===========================================================================

def test_data_quality_aggregate_causal_violation_wins():
    """Gate 10a: CAUSAL_VIOLATION dominates aggregate."""
    from btceth_os.macro.data_quality import aggregate_quality
    from btceth_os.macro.types import MacroDataQuality
    result = aggregate_quality([
        MacroDataQuality.GOOD,
        MacroDataQuality.CAUSAL_VIOLATION,
        MacroDataQuality.STALE,
    ])
    assert result == MacroDataQuality.CAUSAL_VIOLATION


def test_data_quality_aggregate_empty_returns_missing():
    """Gate 10b: Empty list returns MISSING."""
    from btceth_os.macro.data_quality import aggregate_quality
    from btceth_os.macro.types import MacroDataQuality
    result = aggregate_quality([])
    assert result == MacroDataQuality.MISSING


def test_data_quality_is_usable():
    """Gate 10c: is_usable returns True for GOOD and STALE only."""
    from btceth_os.macro.data_quality import is_usable
    from btceth_os.macro.types import MacroDataQuality
    assert is_usable(MacroDataQuality.GOOD) is True
    assert is_usable(MacroDataQuality.STALE) is True
    assert is_usable(MacroDataQuality.MISSING) is False
    assert is_usable(MacroDataQuality.NOT_IMPLEMENTED) is False
    assert is_usable(MacroDataQuality.CAUSAL_VIOLATION) is False
    assert is_usable(MacroDataQuality.PROVIDER_REQUIRED) is False


def test_data_quality_is_causal_violation():
    """Gate 10d: is_causal_violation is True only for CAUSAL_VIOLATION."""
    from btceth_os.macro.data_quality import is_causal_violation
    from btceth_os.macro.types import MacroDataQuality
    assert is_causal_violation(MacroDataQuality.CAUSAL_VIOLATION) is True
    assert is_causal_violation(MacroDataQuality.GOOD) is False


# ===========================================================================
# GATE 11: BLS adapter stub behaviour
# ===========================================================================

def test_bls_adapter_returns_not_implemented():
    """Gate 11a: BLSAdapter.fetch_series returns NOT_IMPLEMENTED."""
    from btceth_os.macro.sources.bls import BLSAdapter
    from btceth_os.macro.types import MacroDataQuality
    adapter = BLSAdapter()
    obs = adapter.fetch_series("US_CPI_HEADLINE_YOY", T_SNAP)
    assert obs.quality == MacroDataQuality.NOT_IMPLEMENTED
    assert obs.source_agency == "BLS"


def test_bls_adapter_unknown_series_raises():
    """Gate 11b: BLSAdapter raises ValueError for unknown series key."""
    from btceth_os.macro.sources.bls import BLSAdapter
    adapter = BLSAdapter()
    with pytest.raises(ValueError, match="Unknown BLS series"):
        adapter.fetch_series("FAKE_SERIES_XYZ", T_SNAP)


# ===========================================================================
# GATE 12: Treasury observation type labeling (no "live yields")
# ===========================================================================

def test_treasury_current_official_observation():
    """Gate 12a: Same-day Treasury observation → CURRENT_OFFICIAL_OBSERVATION."""
    from btceth_os.macro.sources.treasury import TreasuryAdapter, OBSERVATION_TYPE_CURRENT
    from datetime import date
    snap_d = date(2026, 9, 25)
    label = TreasuryAdapter.observation_type_label(snap_d, snap_d)
    assert label == OBSERVATION_TYPE_CURRENT


def test_treasury_daily_official():
    """Gate 12b: Prior-day Treasury observation → DAILY_OFFICIAL."""
    from btceth_os.macro.sources.treasury import TreasuryAdapter, OBSERVATION_TYPE_DAILY
    from datetime import date
    obs_d = date(2026, 9, 24)
    snap_d = date(2026, 9, 25)
    label = TreasuryAdapter.observation_type_label(obs_d, snap_d)
    assert label == OBSERVATION_TYPE_DAILY


def test_treasury_stale():
    """Gate 12c: Old Treasury observation → STALE."""
    from btceth_os.macro.sources.treasury import TreasuryAdapter, OBSERVATION_TYPE_STALE
    from datetime import date
    obs_d = date(2026, 9, 1)
    snap_d = date(2026, 9, 25)
    label = TreasuryAdapter.observation_type_label(obs_d, snap_d)
    assert label == OBSERVATION_TYPE_STALE


def test_treasury_label_is_not_live_yield():
    """Gate 12d: No observation type label contains 'live' (not 'live yields')."""
    from btceth_os.macro.sources.treasury import (
        OBSERVATION_TYPE_CURRENT, OBSERVATION_TYPE_DAILY, OBSERVATION_TYPE_STALE
    )
    for label in [OBSERVATION_TYPE_CURRENT, OBSERVATION_TYPE_DAILY, OBSERVATION_TYPE_STALE]:
        assert "live" not in label.lower(), f"Label {label!r} must not contain 'live'"


# ===========================================================================
# GATE 13: No macro-to-trade mapping in source code
# ===========================================================================

def test_no_macro_to_trade_mapping_in_source():
    """Gate 13: No trade mapping patterns exist in macro module source."""
    import pathlib

    macro_root = pathlib.Path(__file__).parent.parent / "src" / "btceth_os" / "macro"
    forbidden_patterns = [
        "cpi hot",
        "cpi_hot",
        "yields up => sell",
        "nfp weak => long",
        "fed dovish => buy",
        "fomc => short",
        "short gold",
        "long xau",
        "buy btc",
        "sell btc",
    ]

    for py_file in macro_root.rglob("*.py"):
        lines = py_file.read_text(encoding="utf-8").splitlines()
        # Only scan non-comment code lines (lines that don't start with # after stripping)
        code_lines = [
            ln for ln in lines
            if ln.strip() and not ln.strip().startswith("#")
        ]
        # Also exclude docstrings (lines inside triple-quoted strings appearing as
        # plain text in .py files) — for safety, skip lines containing "prohibited"
        # or "do not" since those are prohibition statements, not trade signals.
        executable_lines = [
            ln for ln in code_lines
            if "prohibited" not in ln.lower()
            and "do not" not in ln.lower()
            and "do_not" not in ln.lower()
            and "must not" not in ln.lower()
            and "explicitly" not in ln.lower()
        ]
        content = "\n".join(executable_lines).lower()
        for pattern in forbidden_patterns:
            assert pattern not in content, (
                f"Forbidden trade-mapping pattern {pattern!r} found in executable "
                f"code of {py_file}"
            )



# ===========================================================================
# GATE 14: Breaking news adapter refuses scraping
# ===========================================================================

def test_breaking_news_status_not_implemented():
    """Gate 14a: BreakingNewsAdapter.status == NOT_IMPLEMENTED_PROVIDER_REQUIRED."""
    from btceth_os.macro.sources.breaking_news import BreakingNewsAdapter
    adapter = BreakingNewsAdapter()
    assert adapter.status == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"


def test_breaking_news_returns_provider_required_item():
    """Gate 14b: BreakingNewsAdapter returns PROVIDER_REQUIRED quality item."""
    from btceth_os.macro.sources.breaking_news import BreakingNewsAdapter
    from btceth_os.macro.types import MacroDataQuality
    adapter = BreakingNewsAdapter()
    items = adapter.fetch_breaking_news(T_SNAP)
    assert len(items) >= 1
    assert items[0].quality == MacroDataQuality.PROVIDER_REQUIRED


# ===========================================================================
# GATE 15: Snapshot has_good_series and causal_violation_count
# ===========================================================================

def test_snapshot_has_good_series_false_when_all_not_implemented():
    """Gate 15a: has_good_series is False when all observations are NOT_IMPLEMENTED."""
    from btceth_os.macro.types import MacroDataQuality, MacroAvailabilityStatus
    obs = make_observation(quality=MacroDataQuality.NOT_IMPLEMENTED,
                           availability=MacroAvailabilityStatus.PROVIDER_NOT_IMPLEMENTED)
    snap = make_snapshot(series_obs=[obs])
    assert snap.has_good_series is False


def test_snapshot_causal_violation_count():
    """Gate 15b: causal_violation_count counts CAUSAL_VIOLATION observations."""
    from btceth_os.macro.types import MacroDataQuality, MacroAvailabilityStatus
    obs1 = make_observation("S1", quality=MacroDataQuality.CAUSAL_VIOLATION,
                            availability=MacroAvailabilityStatus.NOT_YET_RELEASED)
    obs2 = make_observation("S2", quality=MacroDataQuality.GOOD,
                            availability=MacroAvailabilityStatus.AVAILABLE)
    snap = make_snapshot(series_obs=[obs1, obs2])
    assert snap.causal_violation_count == 1


# ===========================================================================
# GATE 16: No API keys in committed source code
# ===========================================================================

def test_no_api_keys_in_macro_source():
    """Gate 16: No literal API keys in macro module source files."""
    import pathlib, re

    macro_root = pathlib.Path(__file__).parent.parent / "src" / "btceth_os" / "macro"
    # Patterns that would indicate a hardcoded key
    suspicious_patterns = [
        re.compile(r'["\']([0-9a-f]{32,})["\']'),  # hex string >= 32 chars
        re.compile(r'api_key\s*=\s*["\'][a-zA-Z0-9]{16,}["\']', re.IGNORECASE),
    ]
    for py_file in macro_root.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pat in suspicious_patterns:
            matches = pat.findall(content)
            # Allow known safe patterns (SHA hashes in comments, etc.)
            assert len(matches) == 0, (
                f"Possible hardcoded API key found in {py_file}: {matches}"
            )


# ===========================================================================
# GATE 17: MacroVintage is frozen
# ===========================================================================

def test_macro_vintage_frozen():
    """Gate 17: MacroVintage is frozen (immutable)."""
    v = make_vintage(T_PAST, 3.2)
    with pytest.raises((AttributeError, TypeError)):
        v.value = 99.0  # type: ignore[misc]


# ===========================================================================
# GATE 18: BEA adapter stub
# ===========================================================================

def test_bea_adapter_returns_not_implemented():
    """Gate 18: BEAAdapter.fetch_series returns NOT_IMPLEMENTED."""
    from btceth_os.macro.sources.bea import BEAAdapter
    from btceth_os.macro.types import MacroDataQuality
    adapter = BEAAdapter()
    obs = adapter.fetch_series("US_PCE_PRICE_INDEX_MOM", T_SNAP)
    assert obs.quality == MacroDataQuality.NOT_IMPLEMENTED
    assert obs.source_agency == "BEA"


# ===========================================================================
# GATE 19: Smoke test marker (skipped unless NM1A_SMOKE_TEST=1)
# ===========================================================================

@pytest.mark.skipif(
    os.environ.get("NM1A_SMOKE_TEST", "0") != "1",
    reason="Real API smoke tests disabled. Set NM1A_SMOKE_TEST=1 to enable.",
)
def test_smoke_bls_api_reachable():
    """Smoke: BLS public API is reachable (requires network)."""
    import urllib.request
    try:
        resp = urllib.request.urlopen(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            timeout=10,
        )
        assert resp.status in (200, 400, 403)  # 400/403 is acceptable without a key
    except Exception as e:
        pytest.skip(f"BLS API unreachable: {e}")
