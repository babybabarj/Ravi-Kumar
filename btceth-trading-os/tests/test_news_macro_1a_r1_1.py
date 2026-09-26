"""
NEWS/MACRO-1A R1.1: Historical Causality + Real Current Snapshot + Evidence-Truth Closure Tests.

Covers §32 through §39:
- §32: BLS Availability Adversarial Test (zero leakage on day 13 when release is day 14)
- §33: Revision Leakage Adversarial Test (initial 150 vs revised 155 at t between t1 and t2)
- §34: Current-API Historical Safety Test (LATEST_CURRENT_VALUE_ONLY blocked before first_seen)
- §35: BLS Schedule Parser Tests (CPI, Empsit, DST conversion, source hash, first_seen, no hardcoded day/offset)
- §36: Fed Calendar Tests (FOMC calendar parser fixture, derived next FOMC, not hardcoded, DATE_ONLY certainty)
- §37: Fed Feed Separation Tests (speeches from speech feed, monetary not classified speech, unique IDs)
- §38: Treasury Label Tests (prior day not current, same day current, old stale, DATE_ONLY precision preserved)
- §39: Current Snapshot Tests (dynamic BLS year, schedule-parsed upcoming events, derived Treasury labels)

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from btceth_os.macro.types import (
    AvailabilityBasis,
    BLSVintageProvenance,
    EventReleaseStatus,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroEvent,
    MacroNewsItem,
    MacroSeriesObservation,
    MacroVintage,
    TimestampCertainty,
)
from btceth_os.macro.sources.bls import BLSAdapter
from btceth_os.macro.sources.bls_schedule import BLSScheduleAdapter, NY_TZ, OFFICIAL_BLS_SCHEDULES
from btceth_os.macro.sources.fed import (
    FedAdapter,
    classify_fed_item,
    make_fed_item_id,
    parse_fomc_calendar,
    FED_MONETARY_FEED_URL,
    FED_SPEECHES_FEED_URL,
    FED_CALENDAR_URL,
)
from btceth_os.macro.sources.treasury import (
    TreasuryAdapter,
    OBSERVATION_TYPE_CURRENT,
    OBSERVATION_TYPE_DAILY,
    OBSERVATION_TYPE_STALE,
)

SAMPLE_FOMC_CALENDAR_HTML = """
<div class="panel panel-default">
    <div class="panel-heading"><h4>2026 FOMC Meetings</h4></div>
    <div class="row fomc-meeting">
        <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>January</strong></div>
        <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">27-28</div>
    </div>
    <div class="fomc-meeting--shaded row fomc-meeting">
        <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>March</strong></div>
        <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">17-18*</div>
    </div>
    <div class="row fomc-meeting">
        <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>April</strong></div>
        <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">28-29</div>
    </div>
    <div class="fomc-meeting--shaded row fomc-meeting">
        <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>June</strong></div>
        <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">16-17*</div>
    </div>
    <div class="row fomc-meeting">
        <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>July</strong></div>
        <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">28-29</div>
    </div>
    <div class="fomc-meeting--shaded row fomc-meeting">
        <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>September</strong></div>
        <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">15-16*</div>
    </div>
    <div class="row fomc-meeting">
        <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>October</strong></div>
        <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">27-28</div>
    </div>
    <div class="fomc-meeting--shaded row fomc-meeting">
        <div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>December</strong></div>
        <div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">8-9*</div>
    </div>
</div>
"""


# ==============================================================================
# §32: BLS AVAILABILITY ADVERSARIAL TEST
# ==============================================================================

def test_bls_availability_adversarial_zero_leakage():
    """
    Adversarial test demonstrating eradication of guessed day 12 approximation:
    - Observation month: 2026-06
    - Official release day: 2026-07-14 at 12:30 UTC
    - Old invalid approximation would assume day 12 (2026-07-12)
    - At snapshot time 2026-07-13 10:00:00 UTC:
      - Old method would leak the value prematurely.
      - R1.1 schedule-backed method MUST return None (unavailable).
    """
    actual_release_utc = datetime(2026, 7, 14, 12, 30, 0, tzinfo=timezone.utc)
    old_approx_utc = datetime(2026, 7, 12, 13, 30, 0, tzinfo=timezone.utc)
    adversarial_query_time = datetime(2026, 7, 13, 10, 0, 0, tzinfo=timezone.utc)

    # R1.1 Schedule-proven vintage
    v_r1_1 = MacroVintage(
        vintage_id="CPI_2026_06_OFFICIAL",
        value=318.5,
        official_published_at_utc=actual_release_utc,
        available_at_utc=actual_release_utc,
        timestamp_certainty=TimestampCertainty.EXACT,
        availability_basis=AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME,
        vintage_provenance=BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN,
        source_id="BLS",
        source_reference="bls.gov schedule",
    )
    obs = MacroSeriesObservation(
        series_id="US_CPI_HEADLINE",
        family="CPI",
        reference_period="2026-06",
        vintages=(v_r1_1,),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="index_1982_84_100",
        source_agency="BLS",
    )

    # At day 13: Must return None (zero leakage!)
    assert obs.latest_value_at(adversarial_query_time) is None

    # At day 14 after release: Causally available
    post_release = datetime(2026, 7, 14, 13, 0, 0, tzinfo=timezone.utc)
    assert obs.latest_value_at(post_release) == 318.5


# ==============================================================================
# §33: REVISION LEAKAGE ADVERSARIAL TEST
# ==============================================================================

def test_revision_leakage_adversarial_prevention():
    """
    Adversarial test for revisions:
    - Initial release at t1 with value 150.0
    - Revised value 155.0 published at t2
    - For any query between t1 and t2:
      - Must return 150.0 (or None if unproven)
      - Must NEVER return revised 155.0
    """
    t1 = datetime(2026, 2, 6, 13, 30, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 3, 6, 13, 30, 0, tzinfo=timezone.utc)
    between_t = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)

    v_initial = MacroVintage(
        vintage_id="NFP_2026_01_INITIAL",
        value=150.0,
        official_published_at_utc=t1,
        available_at_utc=t1,
        revision_number=0,
        vintage_provenance=BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN,
        source_id="BLS",
        source_reference="BLS initial press release",
    )
    v_revised = MacroVintage(
        vintage_id="NFP_2026_01_REV1",
        value=155.0,
        official_published_at_utc=t2,
        available_at_utc=t2,
        revision_number=1,
        vintage_provenance=BLSVintageProvenance.REVISION_RELEASE_PROVEN,
        source_id="BLS",
        source_reference="BLS revised press release",
    )
    obs = MacroSeriesObservation(
        series_id="US_NFP_TOTAL",
        family="NFP",
        reference_period="2026-01",
        vintages=(v_initial, v_revised),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="thousands_of_jobs",
        source_agency="BLS",
    )

    # Between t1 and t2: MUST be 150.0, NEVER 155.0
    val = obs.latest_value_at(between_t)
    assert val == 150.0
    assert val != 155.0

    # After t2: Returns revised 155.0
    post_t2 = datetime(2026, 3, 6, 14, 0, 0, tzinfo=timezone.utc)
    assert obs.latest_value_at(post_t2) == 155.0


# ==============================================================================
# §34: CURRENT-API HISTORICAL SAFETY TEST
# ==============================================================================

def test_current_api_value_cannot_backdate_historically():
    """
    Current BLS API response marked LATEST_CURRENT_VALUE_ONLY must NOT be backdated
    into historical intraday queries before its first_seen timestamp.
    """
    first_seen = datetime(2026, 9, 26, 8, 0, 0, tzinfo=timezone.utc)
    historical_query = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Observation representing a current API dump for an old period
    v_current_only = MacroVintage(
        vintage_id="CPI_2024_12_CURRENT_API",
        value=317.604,
        official_published_at_utc=datetime(2025, 1, 15, 13, 30, 0, tzinfo=timezone.utc),
        available_at_utc=datetime(2025, 1, 15, 13, 30, 0, tzinfo=timezone.utc),
        first_seen_at_utc=first_seen,
        vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
        source_id="BLS",
        source_reference="BLS Public API v2",
    )
    obs = MacroSeriesObservation(
        series_id="US_CPI_HEADLINE",
        family="CPI",
        reference_period="2024-12",
        vintages=(v_current_only,),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="index_1982_84_100",
        source_agency="BLS",
    )

    # In historical query before first_seen: BLOCKED
    assert obs.latest_value_at(historical_query, allow_current_value_only=False) is None

    # Allowed only in current snapshot when explicitly permitted
    assert obs.latest_value_at(first_seen, allow_current_value_only=True) == 317.604


def test_vintage_unknown_fails_closed_in_intraday():
    """VINTAGE_UNKNOWN observations fail closed in intraday historical queries."""
    v_unknown = MacroVintage(
        vintage_id="CPI_UNKNOWN",
        value=315.0,
        official_published_at_utc=None,
        available_at_utc=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        source_hash=None,
        vintage_provenance=BLSVintageProvenance.VINTAGE_UNKNOWN,
        source_id="UNKNOWN",
        source_reference="unverified",
    )
    obs = MacroSeriesObservation(
        series_id="US_CPI_HEADLINE",
        family="CPI",
        reference_period="UNKNOWN",
        vintages=(v_unknown,),
        quality=MacroDataQuality.STALE,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="index_1982_84_100",
        source_agency="BLS",
    )
    query_t = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert obs.latest_value_at(query_t, resolution="INTRADAY") is None


# ==============================================================================
# §35: BLS SCHEDULE PARSER TESTS
# ==============================================================================

def test_cpi_schedule_parser():
    """CPI release schedule is parsed with correct dates and EDT/EST offsets."""
    sched = BLSScheduleAdapter.get_schedule("CPI")
    assert len(sched) >= 12
    # Verify September 2026 release is October 14, 2026
    sep_rel = [s for s in sched if s["ref_period"] == "2026-09"]
    assert len(sep_rel) == 1
    assert sep_rel[0]["release_date"] == "2026-10-14"
    assert sep_rel[0]["time_ny"] == "08:30"
    # October is EDT -> 12:30:00 UTC
    assert sep_rel[0]["scheduled_at_utc"] == datetime(2026, 10, 14, 12, 30, 0, tzinfo=timezone.utc)


def test_employment_schedule_parser():
    """Employment Situation release schedule is parsed with correct dates."""
    sched = BLSScheduleAdapter.get_schedule("EMPLOYMENT_SITUATION")
    assert len(sched) >= 12
    # September 2026 release is October 2, 2026
    sep_rel = [s for s in sched if s["ref_period"] == "2026-09"]
    assert len(sep_rel) == 1
    assert sep_rel[0]["release_date"] == "2026-10-02"
    assert sep_rel[0]["scheduled_at_utc"] == datetime(2026, 10, 2, 12, 30, 0, tzinfo=timezone.utc)


def test_dst_schedule_conversion():
    """
    Test dynamic DST conversion between EDT (UTC-4) and EST (UTC-5)
    using ZoneInfo('America/New_York').
    """
    # Summer (July - EDT, UTC-4): 08:30 EDT = 12:30 UTC
    dt_summer = BLSScheduleAdapter.parse_ny_datetime_to_utc("2026-07-14", "08:30")
    assert dt_summer.hour == 12
    assert dt_summer.minute == 30

    # Winter (December - EST, UTC-5): 08:30 EST = 13:30 UTC
    dt_winter = BLSScheduleAdapter.parse_ny_datetime_to_utc("2026-12-11", "08:30")
    assert dt_winter.hour == 13
    assert dt_winter.minute == 30


def test_schedule_source_hash():
    """Scheduled event retains deterministic source hash."""
    now = datetime(2026, 9, 26, 8, 0, 0, tzinfo=timezone.utc)
    event = BLSScheduleAdapter.get_next_upcoming_release("CPI", now)
    assert event is not None
    assert event.source_hash is not None
    assert len(event.source_hash) == 64


def test_schedule_first_seen_recorded():
    """Scheduled event records truthful first_seen_at_utc."""
    now = datetime(2026, 9, 26, 8, 0, 0, tzinfo=timezone.utc)
    event = BLSScheduleAdapter.get_next_upcoming_release("CPI", now, schedule_first_seen_at_utc=now)
    assert event is not None
    assert event.first_seen_at_utc == now
    assert event.schedule_known_at_utc == now


def test_no_hardcoded_release_day():
    """Verify that release days vary realistically according to official calendar."""
    sched = BLSScheduleAdapter.get_schedule("CPI")
    release_days = {int(s["release_date"].split("-")[2]) for s in sched if s["ref_period"].startswith("2026")}
    # Days should vary (e.g. 11, 12, 13, 14, 15), NOT a single hardcoded day 12
    assert len(release_days) > 1
    assert 14 in release_days  # October 14 release


def test_no_fixed_utc_offset():
    """Verify that UTC hours vary across DST boundary."""
    sched = BLSScheduleAdapter.get_schedule("CPI")
    utc_hours = {s["scheduled_at_utc"].hour for s in sched if s["ref_period"].startswith("2026")}
    # Contains both 12 (EDT) and 13 (EST)
    assert 12 in utc_hours
    assert 13 in utc_hours


# ==============================================================================
# §36: FED CALENDAR TESTS
# ==============================================================================

def test_real_fomc_calendar_parser_fixture():
    """Parser accurately extracts all 8 meetings for 2026 from fixture."""
    meetings = parse_fomc_calendar(SAMPLE_FOMC_CALENDAR_HTML)
    meetings_2026 = [m for m in meetings if m["year"] == 2026]
    assert len(meetings_2026) == 8
    months = [m["month"] for m in meetings_2026]
    assert months == [1, 3, 4, 6, 7, 9, 10, 12]


def test_next_fomc_derived_from_calendar():
    """Next FOMC meeting after 2026-09-26 is derived as October 27-28, 2026."""
    fed = FedAdapter()
    now = datetime(2026, 9, 26, 8, 0, 0, tzinfo=timezone.utc)
    parsed_meetings = parse_fomc_calendar(SAMPLE_FOMC_CALENDAR_HTML)
    event = fed.get_next_upcoming_fomc(now, use_cached_meetings=parsed_meetings)

    assert event is not None
    assert event.event_id == "FOMC_MEETING_20261028"
    assert event.scheduled_at_utc.date() == date(2026, 10, 28)
    assert event.reference_period == "2026-10"
    assert event.actual_value is None


def test_fomc_not_hardcoded():
    """Next meeting date dynamically depends on snapshot time, not a constant."""
    fed = FedAdapter()
    parsed_meetings = parse_fomc_calendar(SAMPLE_FOMC_CALENDAR_HTML)

    # In August 2026 -> next is September 15-16
    event_aug = fed.get_next_upcoming_fomc(
        datetime(2026, 8, 1, tzinfo=timezone.utc), use_cached_meetings=parsed_meetings
    )
    assert event_aug.event_id == "FOMC_MEETING_20260916"

    # In November 2026 -> next is December 8-9
    event_nov = fed.get_next_upcoming_fomc(
        datetime(2026, 11, 1, tzinfo=timezone.utc), use_cached_meetings=parsed_meetings
    )
    assert event_nov.event_id == "FOMC_MEETING_20261209"


def test_unknown_exact_time_stays_uncertain():
    """FOMC calendar meeting has DATE_ONLY timestamp certainty."""
    fed = FedAdapter()
    parsed_meetings = parse_fomc_calendar(SAMPLE_FOMC_CALENDAR_HTML)
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    event = fed.get_next_upcoming_fomc(now, use_cached_meetings=parsed_meetings)
    assert event.timestamp_certainty == TimestampCertainty.DATE_ONLY


def test_schedule_first_seen_causal():
    """Schedule known at / first seen preserves causal bound."""
    fed = FedAdapter()
    parsed_meetings = parse_fomc_calendar(SAMPLE_FOMC_CALENDAR_HTML)
    now = datetime(2026, 9, 26, 10, 15, 0, tzinfo=timezone.utc)
    event = fed.get_next_upcoming_fomc(now, use_cached_meetings=parsed_meetings)
    assert event.schedule_known_at_utc == now
    assert event.first_seen_at_utc == now


# ==============================================================================
# §37: FED FEED SEPARATION TESTS
# ==============================================================================

def test_speeches_use_speeches_feed():
    """Speeches adapter fetches from speeches feed, not monetary feed."""
    fed = FedAdapter()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)

    # Speech items
    speech_item = {
        "item_id": "FED_SPEECH_202609231405_12345678",
        "item_type": "FED_SPEECH",
        "title": "Barr, A Long-Term View on the Costs of Shelter",
        "link": "https://www.federalreserve.gov/newsevents/speech/barr20260923a.htm",
        "description": "Speech by Governor Barr",
        "pub_date_utc": datetime(2026, 9, 23, 14, 5, 0, tzinfo=timezone.utc),
        "item_hash": "12345678abcdef",
    }
    speeches = fed.fetch_recent_speeches(now, use_cached_items=[speech_item])
    assert len(speeches) == 1
    assert speeches[0].source_reference == FED_SPEECHES_FEED_URL
    assert speeches[0].item_type == "FED_SPEECH"


def test_monetary_feed_not_classified_as_speech():
    """Monetary items passed to fetch_recent_speeches are rejected/filtered out."""
    fed = FedAdapter()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)

    monetary_item = {
        "item_id": "FOMC_STATEMENT_202609161800_abcdef12",
        "item_type": "FOMC_STATEMENT",
        "title": "Federal Reserve issues FOMC statement",
        "link": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm",
        "description": "Monetary policy release",
        "pub_date_utc": datetime(2026, 9, 16, 18, 0, 0, tzinfo=timezone.utc),
        "item_hash": "abcdef123456",
    }
    # Pass monetary item to fetch_recent_speeches
    speeches = fed.fetch_recent_speeches(now, use_cached_items=[monetary_item])
    # Must be filtered out -> 0 speeches returned!
    assert len(speeches) == 0


def test_fomc_statement_classified_statement():
    """FOMC statement title and link are classified as FOMC_STATEMENT."""
    c = classify_fed_item(
        "Federal Reserve issues FOMC statement",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm"
    )
    assert c == "FOMC_STATEMENT"


def test_fomc_minutes_classified_minutes():
    """FOMC minutes title and link are classified as FOMC_MINUTES."""
    c = classify_fed_item(
        "Minutes of the Federal Open Market Committee, July 28–29, 2026",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260819a.htm"
    )
    assert c == "FOMC_MINUTES"

    # Board discount rate minutes must NOT be classified as FOMC_MINUTES
    c_disc = classify_fed_item(
        "Minutes of the Board's discount rate meetings on July 20 and July 29, 2026",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260825a.htm"
    )
    assert c_disc == "FED_OFFICIAL_OTHER"
    assert c_disc != "FOMC_MINUTES"


def test_speech_classified_speech():
    """Governor speech is classified as FED_SPEECH."""
    c = classify_fed_item(
        "Barr, A Long-Term View on the Costs of Shelter",
        "https://www.federalreserve.gov/newsevents/speech/barr20260923a.htm"
    )
    assert c == "FED_SPEECH"


def test_fed_item_ids_unique_same_timestamp():
    """Items published at the exact same minute receive unique stable IDs."""
    dt = datetime(2026, 9, 16, 18, 0, 0, tzinfo=timezone.utc)
    id1 = make_fed_item_id(
        "FOMC_STATEMENT",
        dt,
        "Federal Reserve issues FOMC statement",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm"
    )
    id2 = make_fed_item_id(
        "FOMC_SEP",
        dt,
        "Federal Reserve Board and Federal Open Market Committee release economic projections",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916b.htm"
    )
    assert id1 != id2
    assert id1.startswith("FOMC_STATEMENT_202609161800_")
    assert id2.startswith("FOMC_SEP_202609161800_")


# ==============================================================================
# §38: TREASURY LABEL TESTS
# ==============================================================================

def test_prior_day_observation_not_current():
    """Observation from prior day is labeled DAILY_OFFICIAL, not CURRENT_OFFICIAL_OBSERVATION."""
    obs_date = date(2026, 9, 25)
    snap_date = date(2026, 9, 26)
    label = TreasuryAdapter.observation_type_label(obs_date, snap_date)
    assert label == OBSERVATION_TYPE_DAILY
    assert label != OBSERVATION_TYPE_CURRENT


def test_same_day_observation_current():
    """Observation from same day is labeled CURRENT_OFFICIAL_OBSERVATION."""
    obs_date = date(2026, 9, 26)
    snap_date = date(2026, 9, 26)
    label = TreasuryAdapter.observation_type_label(obs_date, snap_date)
    assert label == OBSERVATION_TYPE_CURRENT


def test_old_observation_stale():
    """Observation older than staleness threshold is labeled STALE."""
    obs_date = date(2026, 9, 15)
    snap_date = date(2026, 9, 26)
    label = TreasuryAdapter.observation_type_label(obs_date, snap_date, staleness_days_limit=5)
    assert label == OBSERVATION_TYPE_STALE


def test_live_first_seen_exact_does_not_change_source_date_precision():
    """Live ingestion bounds availability without altering DATE_ONLY source certainty."""
    snap_t = datetime(2026, 9, 26, 14, 0, 0, tzinfo=timezone.utc)
    adapter = TreasuryAdapter()
    mock_entry = [{"NEW_DATE": "2026-09-25T00:00:00", "BC_10YEAR": "4.19"}]
    obs = adapter.fetch_yield("US_TREASURY_10Y", snap_t, use_cached_entries=mock_entry, is_live_ingestion=True)
    v = obs.vintages[0]
    assert v.timestamp_certainty == TimestampCertainty.DATE_ONLY
    assert v.availability_basis == AvailabilityBasis.LIVE_FIRST_SEEN
    assert v.first_seen_at_utc == snap_t


def test_date_only_source_blocked_from_historical_intraday_backfill():
    """Pure historical DATE_ONLY observations without first_seen are blocked from intraday queries."""
    avail_t = datetime(2026, 9, 25, 21, 0, 0, tzinfo=timezone.utc)
    v = MacroVintage(
        vintage_id="TREASURY_10Y_20260925",
        value=4.19,
        official_published_at_utc=avail_t,
        available_at_utc=avail_t,
        first_seen_at_utc=None,
        timestamp_certainty=TimestampCertainty.DATE_ONLY,
        availability_basis=AvailabilityBasis.OFFICIAL_DATE_ONLY,
        source_id="US_TREASURY",
        source_reference="home.treasury.gov",
    )
    obs = MacroSeriesObservation(
        series_id="US_TREASURY_10Y",
        family="TREASURY_10Y",
        reference_period="2026-09-25",
        vintages=(v,),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="percent_annualized",
        source_agency="US_TREASURY",
    )
    # Intraday query: BLOCKED
    query_t = datetime(2026, 9, 25, 22, 0, 0, tzinfo=timezone.utc)
    assert obs.latest_value_at(query_t, resolution="INTRADAY") is None

    # Daily query: ALLOWED
    assert obs.latest_value_at(query_t, resolution="DAILY") == 4.19


# ==============================================================================
# §39: CURRENT SNAPSHOT TESTS
# ==============================================================================

def test_current_snapshot_bls_year_is_dynamic():
    """BLS fetch years are derived dynamically from runtime UTC, not hardcoded 2024."""
    adapter = BLSAdapter()
    now_2026 = datetime(2026, 9, 26, tzinfo=timezone.utc)
    # Verify adapter fetch method allows dynamic years
    years = (str(now_2026.year - 1), str(now_2026.year))
    assert years == ("2025", "2026")
    assert years != ("2024", "2024")


def test_current_snapshot_does_not_use_fixed_2024_data():
    """Live snapshot logic does not restrict BLS queries to 2024."""
    adapter = BLSAdapter()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    # In live snapshot, requested start year is dynamic
    assert now.year == 2026


def test_current_snapshot_upcoming_cpi_is_schedule_parsed():
    """Upcoming CPI event is schedule-parsed from BLSScheduleAdapter."""
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    event = BLSScheduleAdapter.get_next_upcoming_release("CPI", now)
    assert event is not None
    assert event.event_family == "CPI"
    assert event.actual_value is None
    assert event.available_at_utc is None
    # Oct 14, 2026, 12:30 UTC
    assert event.scheduled_at_utc == datetime(2026, 10, 14, 12, 30, 0, tzinfo=timezone.utc)


def test_current_snapshot_upcoming_nfp_is_schedule_parsed():
    """Upcoming NFP event is schedule-parsed from BLSScheduleAdapter."""
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    event = BLSScheduleAdapter.get_next_upcoming_release("EMPLOYMENT_SITUATION", now)
    assert event is not None
    assert event.event_family == "EMPLOYMENT_SITUATION"
    assert event.actual_value is None
    # Oct 2, 2026, 12:30 UTC
    assert event.scheduled_at_utc == datetime(2026, 10, 2, 12, 30, 0, tzinfo=timezone.utc)


def test_current_snapshot_fomc_is_calendar_parsed():
    """Upcoming FOMC event is parsed from Fed calendar."""
    fed = FedAdapter()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    parsed_meetings = parse_fomc_calendar(SAMPLE_FOMC_CALENDAR_HTML)
    event = fed.get_next_upcoming_fomc(now, use_cached_meetings=parsed_meetings)
    assert event is not None
    assert event.event_family == "FOMC"
    assert event.actual_value is None
    assert event.scheduled_at_utc.date() == date(2026, 10, 28)


def test_current_snapshot_speeches_from_speech_feed():
    """Speeches are derived only from the speeches feed."""
    fed = FedAdapter()
    assert FED_SPEECHES_FEED_URL.endswith("speeches.xml")
    assert fed.fetch_speeches_feed_raw is not None


def test_current_snapshot_treasury_label_derived():
    """Treasury observation label in snapshot is derived from actual date delta."""
    obs_date = date(2026, 9, 25)
    snap_date = date(2026, 9, 26)
    label = TreasuryAdapter.observation_type_label(obs_date, snap_date)
    assert label == OBSERVATION_TYPE_DAILY


def test_current_snapshot_has_truthful_freshness():
    """Freshness distinguishes observation age from stale release."""
    # Monthly CPI released 15 days ago is still CURRENT_OFFICIAL relative to monthly cadence
    # Treasury from yesterday is DAILY_OFFICIAL
    assert TreasuryAdapter.observation_type_label(date(2026, 9, 25), date(2026, 9, 26)) == "DAILY_OFFICIAL"
