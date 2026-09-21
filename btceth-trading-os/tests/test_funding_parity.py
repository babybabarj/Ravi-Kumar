from __future__ import annotations

from decimal import Decimal

from btceth_os.sources.binance.funding_parity import FundingParityAuditor
from btceth_os.sources.binance.schema_inspector import FundingRateRecord


def test_funding_parity_audit_matching_records():
    archive_records = [
        FundingRateRecord(
            calc_time_raw=1732953600000,
            calc_time_utc="2024-11-30T08:00:00+00:00",
            funding_interval_hours=8,
            last_funding_rate=Decimal("-0.00012359"),
        ),
        FundingRateRecord(
            calc_time_raw=1732982400000,
            calc_time_utc="2024-11-30T16:00:00+00:00",
            funding_interval_hours=8,
            last_funding_rate=Decimal("0.00010000"),
        ),
    ]

    rest_payload = [
        {
            "symbol": "BTCUSDT",
            "fundingTime": 1732953600000,
            "fundingRate": "-0.00012359",
            "markPrice": "96450.25",  # optional field
            "rateType": "standard",   # optional field
        },
        {
            "symbol": "BTCUSDT",
            "fundingTime": 1732982400000,
            "fundingRate": "0.00010000",
            "futureField": 12345,     # unknown future field
        },
    ]

    rest_items = FundingParityAuditor.parse_rest_response(rest_payload)
    report = FundingParityAuditor.audit_overlap("BTCUSDT", archive_records, rest_items)

    assert report.matched_count == 2
    assert report.rate_mismatch_count == 0
    assert report.archive_only_count == 0
    assert report.rest_only_count == 0
    assert "markPrice" in report.optional_fields_observed
    assert "rateType" in report.optional_fields_observed
    assert "futureField" in report.optional_fields_observed


def test_funding_parity_audit_detects_mismatch():
    archive_records = [
        FundingRateRecord(
            calc_time_raw=1732953600000,
            calc_time_utc="2024-11-30T08:00:00+00:00",
            funding_interval_hours=8,
            last_funding_rate=Decimal("-0.00012359"),
        ),
    ]

    rest_payload = [
        {
            "symbol": "BTCUSDT",
            "fundingTime": 1732953600000,
            "fundingRate": "0.00020000",  # Different rate!
        },
    ]

    rest_items = FundingParityAuditor.parse_rest_response(rest_payload)
    report = FundingParityAuditor.audit_overlap("BTCUSDT", archive_records, rest_items)

    assert report.matched_count == 0
    assert report.rate_mismatch_count == 1
    mismatch = report.rate_mismatches[0]
    assert mismatch["archive_rate"] == "-0.00012359"
    assert mismatch["rest_rate"] == "0.00020000"
