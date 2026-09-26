"""
NEWS/MACRO-1A R1.4: Final BLS Archive-Proof Integrity & Status Truth Verification Suite (§45).

Tests:
1. test_direct_original_provenance_without_archive_rejected
2. test_direct_revision_provenance_without_archive_rejected
3. test_frozen_fixture_never_historical_intraday_usable
4. test_plain_archive_dict_rejected
5. test_archive_missing_retrieved_at_rejected
6. test_archive_naive_retrieved_at_rejected
7. test_archive_retrieved_before_publication_rejected
8. test_archive_series_id_mismatch_rejected
9. test_archive_reference_period_mismatch_rejected
10. test_archive_type_source_type_mismatch_rejected
11. test_archive_http_url_rejected
12. test_archive_spoof_bls_domain_rejected
13. test_archive_valid_https_bls_domain_passes_structure
14. test_current_bls_api_still_latest_current_only
15. test_current_bls_available_at_still_equals_first_seen
16. test_current_bls_historical_intraday_still_blocked
17. test_rate_limit_still_zero_records
18. test_rate_limit_never_creates_derived_metrics
19. test_top_level_status_not_verified_when_active_phase_failed
20. test_source_gate_pending_is_not_verified
21. test_full_verified_status_only_when_source_gate_passes

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from btceth_os.macro.sources.bls import (
    BLSAdapter,
    BLSResponseValidationStatus,
    validate_bls_live_response,
)
from btceth_os.macro.status import aggregate_macro_status
from btceth_os.macro.types import (
    ArchivedEvidenceValidationError,
    AvailabilityBasis,
    BLSArchiveType,
    BLSArchivedVintageEvidence,
    BLSSourceEvidenceType,
    BLSVintageProvenance,
    MacroAvailabilityStatus,
    MacroDataQuality,
    MacroSeriesObservation,
    MacroVintage,
    TimestampCertainty,
    validate_archived_bls_vintage_evidence,
)


# 1. test_direct_original_provenance_without_archive_rejected
def test_direct_original_provenance_without_archive_rejected():
    """Direct construction with ORIGINAL_RELEASE_PROVEN without validated archive proof is rejected (§5, §6, §22)."""
    with pytest.raises(ArchivedEvidenceValidationError):
        MacroVintage(
            value=150.0,
            vintage_provenance=BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN,
            timestamp_certainty=TimestampCertainty.EXACT,
            source_evidence_type=None,
            archived_evidence=None,
        )


# 2. test_direct_revision_provenance_without_archive_rejected
def test_direct_revision_provenance_without_archive_rejected():
    """Direct construction with REVISION_RELEASE_PROVEN without validated archive proof is rejected (§5, §6, §23)."""
    with pytest.raises(ArchivedEvidenceValidationError):
        MacroVintage(
            value=155.0,
            vintage_provenance=BLSVintageProvenance.REVISION_RELEASE_PROVEN,
            timestamp_certainty=TimestampCertainty.EXACT,
            source_evidence_type=None,
            archived_evidence=None,
        )


# 3. test_frozen_fixture_never_historical_intraday_usable
def test_frozen_fixture_never_historical_intraday_usable():
    """FROZEN_TEST_FIXTURE must never be historical_intraday_usable in production (§9, §24)."""
    t = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    v = MacroVintage(
        value=100.0,
        source_evidence_type=BLSSourceEvidenceType.FROZEN_TEST_FIXTURE,
        available_at_utc=t,
        official_published_at_utc=t,
        timestamp_certainty=TimestampCertainty.EXACT,
    )
    assert v.historical_intraday_usable is False
    obs = MacroSeriesObservation(
        series_id="CUSR0000SA0",
        family="CPI",
        reference_period="2026-08",
        vintages=(v,),
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="index",
        source_agency="BLS",
    )
    assert obs.get_historical_intraday_value(t) is None


# 4. test_plain_archive_dict_rejected
def test_plain_archive_dict_rejected():
    """Plain dictionary archive evidence is rejected; proof must not be manufactured (§10, §11, §25)."""
    adapter = BLSAdapter()
    raw_rows = [{"period": "M08", "year": "2026", "value": "150.0"}]
    t_snap = datetime(2026, 9, 26, tzinfo=timezone.utc)
    with pytest.raises(ArchivedEvidenceValidationError):
        adapter.parse_series_vintages(
            raw_rows,
            "CUSR0000SA0",
            t_snap,
            archived_vintages_evidence={"2026-08": {"source_hash": "a" * 64}},  # type: ignore
        )


# 5. test_archive_missing_retrieved_at_rejected
def test_archive_missing_retrieved_at_rejected():
    """retrieved_at_utc is mandatory and cannot be None (§16, §28)."""
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    with pytest.raises((ArchivedEvidenceValidationError, TypeError)):
        BLSArchivedVintageEvidence(
            series_id="CUSR0000SA0",
            reference_period="2026-08",
            value=315.5,
            archive_type=BLSArchiveType.INITIAL_RELEASE,
            official_source_url="https://www.bls.gov/news.release/cpi.htm",
            source_raw_sha256="a" * 64,
            official_published_at_utc=t_pub,
            retrieved_at_utc=None,  # type: ignore
        )


# 6. test_archive_naive_retrieved_at_rejected
def test_archive_naive_retrieved_at_rejected():
    """retrieved_at_utc must be timezone-aware (§16, §28)."""
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    with pytest.raises(ArchivedEvidenceValidationError):
        BLSArchivedVintageEvidence(
            series_id="CUSR0000SA0",
            reference_period="2026-08",
            value=315.5,
            archive_type=BLSArchiveType.INITIAL_RELEASE,
            official_source_url="https://www.bls.gov/news.release/cpi.htm",
            source_raw_sha256="a" * 64,
            official_published_at_utc=t_pub,
            retrieved_at_utc=datetime(2026, 9, 11, 13, 0),  # Naive
        )


# 7. test_archive_retrieved_before_publication_rejected
def test_archive_retrieved_before_publication_rejected():
    """retrieved_at_utc cannot precede official_published_at_utc (§17, §28)."""
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    t_ret_early = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ArchivedEvidenceValidationError):
        BLSArchivedVintageEvidence(
            series_id="CUSR0000SA0",
            reference_period="2026-08",
            value=315.5,
            archive_type=BLSArchiveType.INITIAL_RELEASE,
            official_source_url="https://www.bls.gov/news.release/cpi.htm",
            source_raw_sha256="a" * 64,
            official_published_at_utc=t_pub,
            retrieved_at_utc=t_ret_early,
        )


# 8. test_archive_series_id_mismatch_rejected
def test_archive_series_id_mismatch_rejected():
    """Archived evidence series_id must match target series_id (§13, §26)."""
    adapter = BLSAdapter()
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    t_ret = datetime(2026, 9, 11, 13, 0, tzinfo=timezone.utc)
    proof = BLSArchivedVintageEvidence(
        series_id="CES0000000001",  # Mismatch: CPI vs NFP
        reference_period="2026-08",
        value=315.5,
        archive_type=BLSArchiveType.INITIAL_RELEASE,
        official_source_url="https://www.bls.gov/news.release/cpi.htm",
        source_raw_sha256="a" * 64,
        official_published_at_utc=t_pub,
        retrieved_at_utc=t_ret,
    )
    raw_rows = [{"period": "M08", "year": "2026", "value": "315.5"}]
    with pytest.raises(ArchivedEvidenceValidationError):
        adapter.parse_series_vintages(
            raw_rows,
            "CUSR0000SA0",
            datetime(2026, 9, 26, tzinfo=timezone.utc),
            archived_vintages_evidence={"2026-08": proof},
        )


# 9. test_archive_reference_period_mismatch_rejected
def test_archive_reference_period_mismatch_rejected():
    """Archived evidence reference_period must match parsed period (§14, §27)."""
    adapter = BLSAdapter()
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    t_ret = datetime(2026, 9, 11, 13, 0, tzinfo=timezone.utc)
    proof = BLSArchivedVintageEvidence(
        series_id="CUSR0000SA0",
        reference_period="2026-07",  # Mismatch: 07 vs 08
        value=315.5,
        archive_type=BLSArchiveType.INITIAL_RELEASE,
        official_source_url="https://www.bls.gov/news.release/cpi.htm",
        source_raw_sha256="a" * 64,
        official_published_at_utc=t_pub,
        retrieved_at_utc=t_ret,
    )
    raw_rows = [{"period": "M08", "year": "2026", "value": "315.5"}]
    with pytest.raises(ArchivedEvidenceValidationError):
        adapter.parse_series_vintages(
            raw_rows,
            "CUSR0000SA0",
            datetime(2026, 9, 26, tzinfo=timezone.utc),
            archived_vintages_evidence={"2026-08": proof},
        )


# 10. test_archive_type_source_type_mismatch_rejected
def test_archive_type_source_type_mismatch_rejected():
    """Archive type must strictly match evidence type (§15)."""
    adapter = BLSAdapter()
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    t_ret = datetime(2026, 9, 11, 13, 0, tzinfo=timezone.utc)
    proof_init = BLSArchivedVintageEvidence(
        series_id="CUSR0000SA0",
        reference_period="2026-08",
        value=315.5,
        archive_type=BLSArchiveType.INITIAL_RELEASE,
        official_source_url="https://www.bls.gov/news.release/cpi.htm",
        source_raw_sha256="a" * 64,
        official_published_at_utc=t_pub,
        retrieved_at_utc=t_ret,
    )
    raw_rows = [{"period": "M08", "year": "2026", "value": "315.5"}]
    with pytest.raises(ArchivedEvidenceValidationError):
        adapter.parse_series_vintages(
            raw_rows,
            "CUSR0000SA0",
            datetime(2026, 9, 26, tzinfo=timezone.utc),
            source_evidence_type=BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE,  # Mismatch
            archived_vintages_evidence={"2026-08": proof_init},
        )


# 11. test_archive_http_url_rejected
def test_archive_http_url_rejected():
    """HTTP scheme is strictly rejected; must be HTTPS (§18)."""
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    t_ret = datetime(2026, 9, 11, 13, 0, tzinfo=timezone.utc)
    with pytest.raises(ArchivedEvidenceValidationError):
        BLSArchivedVintageEvidence(
            series_id="CUSR0000SA0",
            reference_period="2026-08",
            value=315.5,
            archive_type=BLSArchiveType.INITIAL_RELEASE,
            official_source_url="http://www.bls.gov/news.release/cpi.htm",
            source_raw_sha256="a" * 64,
            official_published_at_utc=t_pub,
            retrieved_at_utc=t_ret,
        )


# 12. test_archive_spoof_bls_domain_rejected
def test_archive_spoof_bls_domain_rejected():
    """Spoofed BLS domains and IP literals are strictly rejected (§18)."""
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    t_ret = datetime(2026, 9, 11, 13, 0, tzinfo=timezone.utc)
    for bad_url in [
        "https://bls.gov.evil.com/cpi.htm",
        "https://evilbls.gov/cpi.htm",
        "https://127.0.0.1/cpi.htm",
        "https://localhost/cpi.htm",
        "https://example.com/cpi.htm",
    ]:
        with pytest.raises(ArchivedEvidenceValidationError):
            BLSArchivedVintageEvidence(
                series_id="CUSR0000SA0",
                reference_period="2026-08",
                value=315.5,
                archive_type=BLSArchiveType.INITIAL_RELEASE,
                official_source_url=bad_url,
                source_raw_sha256="a" * 64,
                official_published_at_utc=t_pub,
                retrieved_at_utc=t_ret,
            )


# 13. test_archive_valid_https_bls_domain_passes_structure
def test_archive_valid_https_bls_domain_passes_structure():
    """Valid HTTPS official BLS URL passes structural validation (§18)."""
    t_pub = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
    t_ret = datetime(2026, 9, 11, 13, 0, tzinfo=timezone.utc)
    proof = BLSArchivedVintageEvidence(
        series_id="CUSR0000SA0",
        reference_period="2026-08",
        value=315.5,
        archive_type=BLSArchiveType.INITIAL_RELEASE,
        official_source_url="https://www.bls.gov/news.release/archives/cpi_09112026.htm",
        source_raw_sha256="a" * 64,
        official_published_at_utc=t_pub,
        retrieved_at_utc=t_ret,
        timestamp_certainty=TimestampCertainty.EXACT,
    )
    assert validate_archived_bls_vintage_evidence(proof) is True


# 14. test_current_bls_api_still_latest_current_only
def test_current_bls_api_still_latest_current_only():
    """CURRENT_BLS_API observations default strictly to LATEST_CURRENT_VALUE_ONLY (§29)."""
    adapter = BLSAdapter()
    t_snap = datetime(2026, 9, 26, tzinfo=timezone.utc)
    raw_rows = [{"period": "M08", "year": "2026", "value": "315.5"}]
    vintages = adapter.parse_series_vintages(
        raw_rows, "CUSR0000SA0", t_snap, source_evidence_type=BLSSourceEvidenceType.CURRENT_BLS_API
    )
    assert len(vintages) == 1
    assert vintages[0].vintage_provenance == BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY


# 15. test_current_bls_available_at_still_equals_first_seen
def test_current_bls_available_at_still_equals_first_seen():
    """available_at_utc strictly equals first_seen_at_utc for current API values (§29)."""
    adapter = BLSAdapter()
    t_snap = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    raw_rows = [{"period": "M08", "year": "2026", "value": "315.5"}]
    vintages = adapter.parse_series_vintages(
        raw_rows, "CUSR0000SA0", t_snap, source_evidence_type=BLSSourceEvidenceType.CURRENT_BLS_API
    )
    assert vintages[0].available_at_utc == t_snap
    assert vintages[0].first_seen_at_utc == t_snap
    assert vintages[0].availability_basis == AvailabilityBasis.LIVE_FIRST_SEEN


# 16. test_current_bls_historical_intraday_still_blocked
def test_current_bls_historical_intraday_still_blocked():
    """Current API observations are strictly blocked from historical intraday research (§29)."""
    adapter = BLSAdapter()
    t_snap = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    raw_rows = [{"period": "M08", "year": "2026", "value": "315.5"}]
    vintages = adapter.parse_series_vintages(
        raw_rows, "CUSR0000SA0", t_snap, source_evidence_type=BLSSourceEvidenceType.CURRENT_BLS_API
    )
    assert vintages[0].historical_intraday_usable is False
    obs = MacroSeriesObservation(
        series_id="CUSR0000SA0",
        family="CPI",
        reference_period="2026-08",
        vintages=vintages,
        quality=MacroDataQuality.GOOD,
        availability_status=MacroAvailabilityStatus.AVAILABLE,
        unit="index",
        source_agency="BLS",
    )
    assert obs.get_historical_intraday_value(t_snap) is None


# 17. test_rate_limit_still_zero_records
def test_rate_limit_still_zero_records():
    """Rate-limited response returns 0 records and RATE_LIMITED status with zero fallback (§30)."""
    rate_limit_payload = {
        "status": "REQUEST_NOT_PROCESSED",
        "responseTime": 0,
        "message": ["daily threshold for total number of requests has been reached"],
        "Results": {},
    }
    raw_bytes = json.dumps(rate_limit_payload).encode("utf-8")
    status, msg, cnt = validate_bls_live_response(200, raw_bytes, rate_limit_payload, ["CUSR0000SA0"])
    assert status == BLSResponseValidationStatus.RATE_LIMITED
    assert cnt == 0


# 18. test_rate_limit_never_creates_derived_metrics
def test_rate_limit_never_creates_derived_metrics():
    """Derived CPI YoY and NFP MoM return NOT_AVAILABLE when vintages are empty (§30)."""
    info_cpi = BLSAdapter.derive_cpi_yoy_provenance(())
    assert info_cpi["value"] is None
    assert info_cpi["provenance"] == "NOT_AVAILABLE"
    info_nfp = BLSAdapter.derive_nfp_mom_provenance(())
    assert info_nfp["value"] is None
    assert info_nfp["provenance"] == "NOT_AVAILABLE"


# 19. test_top_level_status_not_verified_when_active_phase_failed
def test_top_level_status_not_verified_when_active_phase_failed():
    """If remediation failed, top-level status must never report VERIFIED (§31, §32)."""
    st = aggregate_macro_status("REMEDIATION_REQUIRED", "RATE_LIMITED")
    assert st["news_macro_1a_status"] != "VERIFIED"
    assert st["news_macro_1a_status"] == "REMEDIATION_REQUIRED"
    assert st["news_macro_1a_r1_4_status"] == "REMEDIATION_REQUIRED"


# 20. test_source_gate_pending_is_not_verified
def test_source_gate_pending_is_not_verified():
    """When code is verified but source is rate-limited, status is SOURCE_GATE_PENDING (§32, §33)."""
    st = aggregate_macro_status("VERIFIED", "BLS_DATA_API_RATE_LIMITED")
    assert st["news_macro_1a_status"] != "VERIFIED"
    assert st["news_macro_1a_status"] == "SOURCE_GATE_PENDING"
    assert st["news_macro_1a_r1_4_code_status"] == "VERIFIED"
    assert st["news_macro_1a_r1_4_source_status"] == "BLS_DATA_API_RATE_LIMITED"


# 21. test_full_verified_status_only_when_source_gate_passes
def test_full_verified_status_only_when_source_gate_passes():
    """Full VERIFIED status is produced only when code AND source gates both pass (§32, §53)."""
    st = aggregate_macro_status("VERIFIED", "VERIFIED")
    assert st["news_macro_1a_status"] == "VERIFIED"
    assert st["news_macro_1a_r1_4_status"] == "VERIFIED"
