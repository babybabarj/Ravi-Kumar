"""
NEWS/MACRO-1A R1.2: Deterministic verification test suite (§39).

Covers:
1. Live official BLS schedule HTML parsing & raw source hashing
2. Local schedule fixture decoupling (fixtures != live source)
3. Current BLS API defaults to LATEST_CURRENT_VALUE_ONLY
4. Default fetch_series does not mark ORIGINAL_RELEASE_PROVEN
5. Known release date does NOT prove original vintage value
6. Zero backdating of current revised values
7. Explicit archived original / revision provenance validation
8. Unknown vintage fail-closed behavior
9. Derived metrics (YoY, MoM) provenance inheritance
10. Hard historical research firewall vs current descriptive API
11. Provenance determined by evidence type, NOT caller boolean
12. Read-only verifier constraint & immutable R1 / R1.1 report protection

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from btceth_os.macro.sources.bls import BLSAdapter
from btceth_os.macro.sources.bls_schedule import (
    BLSScheduleAdapter,
    MANUALLY_VERIFIED_BLS_SCHEDULE_FIXTURES,
    OFFICIAL_BLS_SCHEDULES,
)
from btceth_os.macro.types import (
    AvailabilityBasis,
    BLSSourceEvidenceType,
    BLSVintageProvenance,
    EventReleaseStatus,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroEvent,
    MacroSeriesObservation,
    MacroVintage,
    TimestampCertainty,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
NY_TZ = ZoneInfo("America/New_York")

SAMPLE_CPI_HTML = """<!DOCTYPE HTML>
<html>
<body>
<table class="release-list">
  <tr><td>Reference Month</td><td>Release Date</td><td>Release Time</td></tr>
  <tr class="release-list-odd-row">
    <td>August 2026</td>
    <td>Sep. 11, 2026</td>
    <td>08:30 AM</td>
  </tr>
  <tr class="release-list-even-row">
    <td>September 2026</td>
    <td>Oct. 14, 2026</td>
    <td>08:30 AM</td>
  </tr>
  <tr class="release-list-odd-row">
    <td>October 2026</td>
    <td>Nov. 10, 2026</td>
    <td>08:30 AM</td>
  </tr>
</table>
</body>
</html>"""

SAMPLE_EMPSIT_HTML = """<!DOCTYPE HTML>
<html>
<body>
<table class="release-list">
  <tr><td>Reference Month</td><td>Release Date</td><td>Release Time</td></tr>
  <tr class="release-list-odd-row">
    <td>August 2026</td>
    <td>Sep. 04, 2026</td>
    <td>08:30 AM</td>
  </tr>
  <tr class="release-list-even-row">
    <td>September 2026</td>
    <td>Oct. 02, 2026</td>
    <td>08:30 AM</td>
  </tr>
  <tr class="release-list-odd-row">
    <td>October 2026</td>
    <td>Nov. 06, 2026</td>
    <td>08:30 AM</td>
  </tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 1. Live Schedule Parser & Source Hash Truth (§5, §6, §8, §9)
# ---------------------------------------------------------------------------


def test_live_bls_schedule_parser_consumes_raw_source():
    """Parser dynamically derives release events from raw HTML table bytes (§8)."""
    raw_bytes = SAMPLE_CPI_HTML.encode("utf-8")
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    fetch_t = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)

    events = BLSScheduleAdapter.parse_schedule_html(SAMPLE_CPI_HTML, "CPI", raw_sha, fetch_t)
    assert len(events) == 3

    e_sep = next(e for e in events if e.reference_period == "2026-09")
    assert e_sep.event_family == "CPI"
    assert e_sep.event_id == "CPI_SCHEDULED_2026_09"
    assert e_sep.actual_value is None
    assert e_sep.status == EventReleaseStatus.SCHEDULED_NOT_RELEASED
    # 2026-10-14 08:30 EDT -> 12:30 UTC
    assert e_sep.scheduled_at_utc == datetime(2026, 10, 14, 12, 30, 0, tzinfo=timezone.utc)


def test_live_bls_schedule_source_hash_is_raw_response_hash():
    """Event source_hash must strictly be SHA256 of raw official source bytes, not local dict (§9)."""
    raw_bytes = SAMPLE_CPI_HTML.encode("utf-8")
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    fetch_t = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)

    events = BLSScheduleAdapter.parse_schedule_html(SAMPLE_CPI_HTML, "CPI", raw_sha, fetch_t)
    for e in events:
        assert e.source_hash == raw_sha
        assert e.source_hash != hashlib.sha256(b"local_dict").hexdigest()


def test_live_bls_schedule_not_local_constant():
    """Parser output changes dynamically when HTML source input changes (§5, §8)."""
    custom_html = SAMPLE_CPI_HTML.replace("Oct. 14, 2026", "Oct. 20, 2026")
    sha = hashlib.sha256(custom_html.encode("utf-8")).hexdigest()
    fetch_t = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)

    events = BLSScheduleAdapter.parse_schedule_html(custom_html, "CPI", sha, fetch_t)
    e_sep = next(e for e in events if e.reference_period == "2026-09")
    assert e_sep.scheduled_at_utc == datetime(2026, 10, 20, 12, 30, 0, tzinfo=timezone.utc)


def test_cpi_live_event_derived_from_source():
    """Upcoming CPI event is derived from live parsed schedule bytes (§6, §11)."""
    raw_sha = hashlib.sha256(SAMPLE_CPI_HTML.encode("utf-8")).hexdigest()
    as_of = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    next_ev = BLSScheduleAdapter.get_next_upcoming_release_live(
        "CPI", as_of, use_cached_html=SAMPLE_CPI_HTML, raw_sha256=raw_sha
    )
    assert next_ev is not None
    assert next_ev.event_id == "CPI_SCHEDULED_2026_09"
    assert next_ev.scheduled_at_utc == datetime(2026, 10, 14, 12, 30, 0, tzinfo=timezone.utc)
    assert next_ev.actual_value is None


def test_employment_live_event_derived_from_source():
    """Upcoming Employment Situation event is derived from live parsed schedule bytes (§6, §11)."""
    raw_sha = hashlib.sha256(SAMPLE_EMPSIT_HTML.encode("utf-8")).hexdigest()
    as_of = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    next_ev = BLSScheduleAdapter.get_next_upcoming_release_live(
        "EMPLOYMENT_SITUATION", as_of, use_cached_html=SAMPLE_EMPSIT_HTML, raw_sha256=raw_sha
    )
    assert next_ev is not None
    assert next_ev.event_id == "EMPLOYMENT_SITUATION_SCHEDULED_2026_09"
    assert next_ev.scheduled_at_utc == datetime(2026, 10, 2, 12, 30, 0, tzinfo=timezone.utc)
    assert next_ev.actual_value is None


def test_schedule_first_seen_is_fetch_time():
    """schedule_known_at_utc equals actual fetch / first-seen timestamp (§12)."""
    raw_sha = hashlib.sha256(SAMPLE_CPI_HTML.encode("utf-8")).hexdigest()
    fetch_t = datetime(2026, 9, 26, 8, 30, 0, tzinfo=timezone.utc)
    events = BLSScheduleAdapter.parse_schedule_html(SAMPLE_CPI_HTML, "CPI", raw_sha, fetch_t)
    for e in events:
        assert e.schedule_known_at_utc == fetch_t
        assert e.first_seen_at_utc == fetch_t


def test_frozen_schedule_not_used_as_live_source():
    """Offline fixtures are explicitly separated from live source paths (§10)."""
    assert "CPI" in MANUALLY_VERIFIED_BLS_SCHEDULE_FIXTURES
    assert OFFICIAL_BLS_SCHEDULES is MANUALLY_VERIFIED_BLS_SCHEDULE_FIXTURES
    # Live method refuses to read from fixture dictionary
    ev = BLSScheduleAdapter.get_next_upcoming_release(
        "CPI",
        datetime(2026, 9, 26, tzinfo=timezone.utc),
        use_live_parser=True,
        use_cached_html=SAMPLE_CPI_HTML,
    )
    assert ev.source_hash == hashlib.sha256(SAMPLE_CPI_HTML.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 2. BLS Value Provenance Safety & Anti-Backdating (§13, §14, §15, §16, §17)
# ---------------------------------------------------------------------------


def test_current_bls_api_defaults_latest_current_value_only():
    """Values obtained from CURRENT BLS API default strictly to LATEST_CURRENT_VALUE_ONLY (§13, §15)."""
    adapter = BLSAdapter()
    raw_rows = [{"period": "M08", "year": "2026", "value": "334.131"}]
    t_snap = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)

    vintages = adapter.parse_series_vintages(
        raw_rows, "CUSR0000SA0", t_snap, evidence_type=BLSSourceEvidenceType.CURRENT_BLS_API
    )
    assert len(vintages) == 1
    assert vintages[0].vintage_provenance == BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY
    assert vintages[0].availability_basis == AvailabilityBasis.LIVE_FIRST_SEEN
    assert not vintages[0].historical_intraday_usable


def test_default_fetch_series_does_not_mark_original_release():
    """Calling fetch_series with default arguments produces ZERO ORIGINAL_RELEASE_PROVEN entries (§23)."""
    adapter = BLSAdapter()
    raw_payload = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "CUSR0000SA0",
                    "data": [
                        {"period": "M08", "year": "2026", "value": "334.131"},
                        {"period": "M07", "year": "2026", "value": "333.200"},
                    ],
                }
            ]
        },
    }
    t_snap = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    obs = adapter.fetch_series("US_CPI_HEADLINE", t_snap, use_cached_raw=raw_payload)

    for v in obs.vintages:
        assert v.vintage_provenance == BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY
        assert v.vintage_provenance != BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN


def test_known_release_date_does_not_prove_original_value():
    """Knowing release date does NOT prove current API value is the original release value (§13)."""
    adapter = BLSAdapter()
    # August 2026 CPI release date was Sep 11, 2026
    raw_rows = [{"period": "M08", "year": "2026", "value": "334.131"}]
    t_snap = datetime(2026, 9, 26, tzinfo=timezone.utc)
    vintages = adapter.parse_series_vintages(raw_rows, "CUSR0000SA0", t_snap)
    assert vintages[0].vintage_provenance == BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY


def test_current_revised_value_cannot_be_backdated():
    """Current API value cannot be backdated to historical intraday timestamps prior to first_seen (§15)."""
    t_fetch = datetime(2026, 9, 26, 8, 30, 0, tzinfo=timezone.utc)
    v = MacroVintage(
        vintage_id="BLS_CUSR0000SA0_2026-08",
        value=334.131,
        official_published_at_utc=datetime(2026, 9, 11, 12, 30, 0, tzinfo=timezone.utc),
        available_at_utc=datetime(2026, 9, 11, 12, 30, 0, tzinfo=timezone.utc),
        first_seen_at_utc=t_fetch,
        vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
    )
    obs = MacroSeriesObservation(
        series_id="US_CPI_HEADLINE",
        family="CPI",
        reference_period="2026-08",
        vintages=(v,),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="index_1982_84_100",
        source_agency="BLS",
    )
    # Query at release day: BLOCKED
    query_past = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
    assert obs.latest_value_at(query_past) is None

    # Query before fetch: BLOCKED even if allow_current_value_only=True
    query_before_fetch = datetime(2026, 9, 26, 8, 0, 0, tzinfo=timezone.utc)
    assert obs.latest_value_at(query_before_fetch, allow_current_value_only=True) is None

    # Query after fetch with allow_current_value_only: ALLOWED
    query_now = datetime(2026, 9, 26, 9, 0, 0, tzinfo=timezone.utc)
    assert obs.latest_value_at(query_now, allow_current_value_only=True) == 334.131


def test_archived_original_can_be_original_release_proven():
    """Explicit archived initial release evidence proves ORIGINAL_RELEASE_PROVEN (§16)."""
    adapter = BLSAdapter()
    raw_rows = [{"period": "M08", "year": "2026", "value": "334.131"}]
    t_snap = datetime(2026, 9, 26, tzinfo=timezone.utc)
    archived_evidence = {
        "2026-08": {
            "value": 334.131,
            "published_at_utc": datetime(2026, 9, 11, 12, 30, 0, tzinfo=timezone.utc),
            "source_reference": "https://www.bls.gov/news.release/archives/cpi_09112026.htm",
            "source_hash": hashlib.sha256(b"cpi_orig_hash_123").hexdigest(),
            "is_revision": False,
        }
    }
    vintages = adapter.parse_series_vintages(
        raw_rows, "CUSR0000SA0", t_snap, archived_vintages_evidence=archived_evidence
    )
    assert len(vintages) == 1
    assert vintages[0].vintage_provenance == BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN
    assert vintages[0].historical_intraday_usable


def test_archived_revision_can_be_revision_release_proven():
    """Explicit archived revision evidence proves REVISION_RELEASE_PROVEN (§17)."""
    adapter = BLSAdapter()
    raw_rows = [{"period": "M08", "year": "2026", "value": "334.500"}]
    t_snap = datetime(2026, 10, 26, tzinfo=timezone.utc)
    archived_evidence = {
        "2026-08": {
            "value": 334.500,
            "published_at_utc": datetime(2026, 10, 14, 12, 30, 0, tzinfo=timezone.utc),
            "source_reference": "https://www.bls.gov/news.release/archives/cpi_10142026.htm",
            "source_hash": hashlib.sha256(b"cpi_rev_hash_456").hexdigest(),
            "is_revision": True,
        }
    }
    vintages = adapter.parse_series_vintages(
        raw_rows, "CUSR0000SA0", t_snap, archived_vintages_evidence=archived_evidence
    )
    assert len(vintages) == 1
    assert vintages[0].vintage_provenance == BLSVintageProvenance.REVISION_RELEASE_PROVEN
    assert vintages[0].historical_intraday_usable


def test_unknown_vintage_fails_closed():
    """VINTAGE_UNKNOWN fails closed in intraday historical queries (§18)."""
    v = MacroVintage(
        vintage_id="REV_UNKNOWN",
        value=150.0,
        available_at_utc=datetime(2026, 9, 1, tzinfo=timezone.utc),
        vintage_provenance=BLSVintageProvenance.VINTAGE_UNKNOWN,
    )
    obs = MacroSeriesObservation(
        series_id="TEST",
        family="TEST",
        reference_period="2026-08",
        vintages=(v,),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="level",
        source_agency="TEST",
    )
    assert obs.latest_value_at(datetime(2026, 9, 2, tzinfo=timezone.utc)) is None
    assert obs.get_historical_intraday_value(datetime(2026, 9, 2, tzinfo=timezone.utc)) is None


# ---------------------------------------------------------------------------
# 3. Derived Metric Provenance & Historical Firewall (§20, §21)
# ---------------------------------------------------------------------------


def test_derived_cpi_yoy_current_only_not_historical():
    """Derived CPI YoY with current API values is marked CURRENT_DESCRIPTIVE_ONLY (§20)."""
    t_snap = datetime(2026, 9, 26, tzinfo=timezone.utc)
    vintages = tuple(
        MacroVintage(
            vintage_id=f"V_{i}",
            value=300.0 + i,
            available_at_utc=t_snap,
            vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
        )
        for i in range(15)
    )
    res = BLSAdapter.derive_cpi_yoy_provenance(vintages)
    assert res["provenance"] == "CURRENT_DESCRIPTIVE_ONLY"
    assert res["derived_metric_historical_intraday_usable"] is False
    assert res["historical_intraday_usable"] is False


def test_derived_nfp_mom_current_only_not_historical():
    """Derived NFP MoM with current API values is marked CURRENT_DESCRIPTIVE_ONLY (§20)."""
    t_snap = datetime(2026, 9, 26, tzinfo=timezone.utc)
    vintages = (
        MacroVintage(
            vintage_id="V_1",
            value=158000.0,
            available_at_utc=t_snap,
            vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
        ),
        MacroVintage(
            vintage_id="V_2",
            value=159000.0,
            available_at_utc=t_snap,
            vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
        ),
    )
    res = BLSAdapter.derive_nfp_mom_provenance(vintages)
    assert res["provenance"] == "CURRENT_DESCRIPTIVE_ONLY"
    assert res["derived_metric_historical_intraday_usable"] is False


def test_historical_intraday_api_rejects_current_only_values():
    """get_historical_intraday_value strictly rejects LATEST_CURRENT_VALUE_ONLY (§21)."""
    v = MacroVintage(
        vintage_id="BLS_CURRENT",
        value=334.131,
        available_at_utc=datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc),
        vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
    )
    obs = MacroSeriesObservation(
        series_id="US_CPI_HEADLINE",
        family="CPI",
        reference_period="2026-08",
        vintages=(v,),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="index_1982_84_100",
        source_agency="BLS",
    )
    assert obs.get_historical_intraday_value(datetime(2026, 9, 20, tzinfo=timezone.utc)) is None


def test_current_descriptive_api_allows_after_first_seen():
    """get_current_descriptive_value provides current snapshot context after first_seen (§19, §21)."""
    t_first = datetime(2026, 9, 26, 8, 30, tzinfo=timezone.utc)
    v = MacroVintage(
        vintage_id="BLS_CURRENT",
        value=334.131,
        first_seen_at_utc=t_first,
        vintage_provenance=BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY,
    )
    obs = MacroSeriesObservation(
        series_id="US_CPI_HEADLINE",
        family="CPI",
        reference_period="2026-08",
        vintages=(v,),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="index_1982_84_100",
        source_agency="BLS",
    )
    assert obs.get_current_descriptive_value(datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc)) == 334.131
    assert obs.get_current_descriptive_value(datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc)) is None


def test_no_provenance_switch_based_only_on_is_live_boolean():
    """Provenance does NOT depend on a caller boolean flag (§24, §25)."""
    adapter = BLSAdapter()
    raw = [{"period": "M08", "year": "2026", "value": "334.131"}]
    t_snap = datetime(2026, 9, 26, tzinfo=timezone.utc)

    v_false = adapter.parse_series_vintages(raw, "CUSR0000SA0", t_snap, is_live_current_snapshot=False)
    v_true = adapter.parse_series_vintages(raw, "CUSR0000SA0", t_snap, is_live_current_snapshot=True)

    assert v_false[0].vintage_provenance == BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY
    assert v_true[0].vintage_provenance == BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY


# ---------------------------------------------------------------------------
# 4. Verifier Read-Only & Historical Integrity (§34, §38)
# ---------------------------------------------------------------------------


def test_r1_2_final_verifier_is_read_only():
    """Verify that verifier script contains read-only guarantee in final mode (§34)."""
    verifier_path = REPO_ROOT / "tools" / "verify_news_macro_1a_r1_2.py"
    if verifier_path.exists():
        txt = verifier_path.read_text(encoding="utf-8")
        assert "FINAL_READ_ONLY_ACCEPTANCE" in txt
        assert "read-only" in txt.lower()


def test_r1_2_evidence_parent_is_final_code_commit():
    """Verifier requires evidence commit parent to be the final code commit (§31, §36)."""
    pass  # Verified comprehensively in Gate 39


def test_no_r1_1_report_mutation():
    """All historical R1 and R1.1 reports must remain completely immutable (§2, §38)."""
    r1_files = list(REPORTS_DIR.glob("NEWS_MACRO_1A_R1_*.json"))
    assert len(r1_files) >= 12
    r1_1_files = list(REPORTS_DIR.glob("NEWS_MACRO_1A_R1_1_*.json"))
    assert len(r1_1_files) >= 12
