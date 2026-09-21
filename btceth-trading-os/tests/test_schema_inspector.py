from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from btceth_os.sources.binance.schema_inspector import (
    FundingParserCatastrophicError,
    SchemaInspectionError,
    SchemaInspector,
    normalize_timestamp,
)


def test_funding_rate_parser_mandatory_specification():
    """Section 7: Mandatory Funding Parser Catastrophic Regression Test."""
    csv_text = (
        "calc_time,funding_interval_hours,last_funding_rate\n"
        "1732953600000,8,-0.00012359\n"
        "1732982400000,8,0.00010000\n"
    )

    records = SchemaInspector.parse_funding_rate_csv(csv_text)
    assert len(records) == 2

    # Assert exact types and values
    rec0 = records[0]
    assert rec0.calc_time_raw == 1732953600000
    assert rec0.funding_interval_hours == 8
    assert rec0.last_funding_rate == Decimal("-0.00012359")
    assert rec0.calc_time_utc == "2024-11-30T08:00:00+00:00"

    rec1 = records[1]
    assert rec1.calc_time_raw == 1732982400000
    assert rec1.funding_interval_hours == 8
    assert rec1.last_funding_rate == Decimal("0.00010000")
    assert rec1.calc_time_utc == "2024-11-30T16:00:00+00:00"


def test_funding_rate_parser_catastrophic_mutation_trap():
    """Section 7: Intentional mutation test proving that reading row[1] as rate fails catastrophically."""
    # Defective CSV where column 2 (last_funding_rate) is accidentally set to 8 (matching interval)
    defective_csv = (
        "calc_time,funding_interval_hours,last_funding_rate\n"
        "1732953600000,8,8\n"
    )

    with pytest.raises(FundingParserCatastrophicError, match=r"CATASTROPHIC PARSER DEFECT DETECTED.*equals funding_interval_hours"):
        SchemaInspector.parse_funding_rate_csv(defective_csv)


def test_funding_rate_parser_magnitude_catastrophic_rejection():
    """A funding rate exceeding realistic market bounds (>10%) must fail closed."""
    absurd_rate_csv = (
        "calc_time,funding_interval_hours,last_funding_rate\n"
        "1732953600000,8,0.25000000\n"
    )
    with pytest.raises(FundingParserCatastrophicError, match=r"exceeds maximum reasonable bound"):
        SchemaInspector.parse_funding_rate_csv(absurd_rate_csv)


def test_detect_header_vs_headerless():
    header_line = "open_time,open,high,low,close,volume"
    assert SchemaInspector.detect_header(header_line) is True

    headerless_kline = "1700000000000,50000.0,51000.0,49000.0,50500.0,10.5"
    assert SchemaInspector.detect_header(headerless_kline) is False

    header_funding = "calc_time,funding_interval_hours,last_funding_rate"
    assert SchemaInspector.detect_header(header_funding) is True

    headerless_funding = "1732953600000,8,-0.00012359"
    assert SchemaInspector.detect_header(headerless_funding) is False


def test_quality_probe_clean_data(tmp_path: Path):
    csv_file = tmp_path / "sample_klines.csv"
    csv_file.write_text(
        "open_time,open,high,low,close,volume\n"
        "1700000000000,50000,51000,49000,50500,10\n"
        "1700000060000,50500,51200,50200,51000,15\n"
        "1700000120000,51000,51500,50900,51400,20\n"
    )

    result = SchemaInspector.run_quality_probe(csv_file, "klines", expected_unit="ms")
    assert result.row_count == 3
    assert result.header_detected is True
    assert result.is_monotonic is True
    assert result.duplicate_timestamp_count == 0
    assert result.malformed_row_count == 0
    assert result.column_count_violations == 0
    assert result.price_violations == 0
    assert result.first_timestamp_raw == 1700000000000
    assert result.last_timestamp_raw == 1700000120000


def test_quality_probe_detects_anomalies(tmp_path: Path):
    csv_file = tmp_path / "anomalous_klines.csv"
    csv_file.write_text(
        "open_time,open,high,low,close,volume\n"
        "1700000060000,50000,51000,49000,50500,10\n"
        "1700000000000,-10.0,51200,50200,51000,15\n"  # Non-monotonic timestamp, negative price
        "1700000000000,51000,51500,50900,51400,20\n"   # Duplicate timestamp
        "corrupted_row\n"                                # Malformed / column violation
    )

    result = SchemaInspector.run_quality_probe(csv_file, "klines", expected_unit="ms")
    assert result.row_count == 4
    assert result.is_monotonic is False
    assert result.duplicate_timestamp_count == 1
    assert result.price_violations == 1
    assert result.column_count_violations == 1
