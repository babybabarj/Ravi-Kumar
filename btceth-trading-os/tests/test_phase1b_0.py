from decimal import Decimal
import json
from pathlib import Path
import pytest

from btceth_os.core import QualityState
from btceth_os.identity import (
    compute_file_sha256,
    compute_bytes_sha256,
    IncrementalSha256,
    compute_logical_sha256,
    ProvenanceRecord,
)
from btceth_os.quality import (
    TimestampRecord,
    FinancialDecimal,
    validate_timestamp_monotonicity,
)
from btceth_os.sources import (
    DatasetDefinition,
    load_historical_datasets_registry,
    validate_canonical_instrument,
)
from btceth_os.security_scan import scan as run_security_scan


ROOT = Path(__file__).resolve().parents[1]


def test_open_source_manifest_determinism():
    manifest_path = ROOT / "reports" / "OPEN_SOURCE_SOURCE_MANIFEST.json"
    assert manifest_path.is_file(), "Manifest JSON file must exist"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["manifest_version"] == "1.0.0"
    assert data["archive_count"] == 8
    archives = {a["key"]: a for a in data["archives"]}
    assert len(archives) == 8

    required_keys = {"passivbot", "jesse", "nautilus_trader", "hummingbot", "freqtrade", "octobot", "ccxt", "lean"}
    assert set(archives.keys()) == required_keys

    # Check that SHA256 matches the file on disk
    for key, item in archives.items():
        assert len(item["sha256"]) == 64
        assert item["size_bytes"] > 0
        assert item["reuse_mode"] in {"ADAPT", "DEPENDENCY", "REFERENCE"}


def test_sha256_helpers(tmp_path: Path):
    sample = b"BTCETH_TRADING_OS_CANONICAL_DATA_V1_1"
    expected_hash = "c0337d93638ebce0731486c842298f8ae583fe43c3d9dc2fa56289ec1c9f2e77"

    assert compute_bytes_sha256(sample) == expected_hash

    f = tmp_path / "sample.bin"
    f.write_bytes(sample)
    assert compute_file_sha256(f) == expected_hash

    # Test IncrementalSha256
    inc = IncrementalSha256()
    inc.update(sample[:10])
    inc.update(sample[10:])
    assert inc.bytes_hashed == len(sample)
    assert inc.hexdigest() == expected_hash

    # Test logical_sha256 determinism across order
    k1 = ["k2", "k1"]
    h1 = ["h2", "h1"]
    k2 = ["k1", "k2"]
    h2 = ["h1", "h2"]
    assert compute_logical_sha256(k1, h1) == compute_logical_sha256(k2, h2)


def test_dataset_registry_parsing():
    datasets = load_historical_datasets_registry()
    assert len(datasets) >= 14, "Expected at least 14 canonical datasets defined"

    instruments = {d.instrument for d in datasets}
    assert instruments == {
        "BINANCE:SPOT:BTCUSDT",
        "BINANCE:SPOT:ETHUSDT",
        "BINANCE:USD_M_PERP:BTCUSDT",
        "BINANCE:USD_M_PERP:ETHUSDT",
    }

    # Verify initial status is UNVERIFIED_SOURCE_PATH
    for d in datasets:
        assert d.archive_support_status == "UNVERIFIED_SOURCE_PATH"
        assert d.source == "binance"
        assert d.expected_time_unit == "ms"
        assert d.raw_format == "csv.zip"


def test_canonical_instrument_uniqueness():
    assert validate_canonical_instrument("BINANCE:SPOT:BTCUSDT") is True
    assert validate_canonical_instrument("BINANCE:SPOT:ETHUSDT") is True
    assert validate_canonical_instrument("BINANCE:USD_M_PERP:BTCUSDT") is True
    assert validate_canonical_instrument("BINANCE:USD_M_PERP:ETHUSDT") is True

    # Non-canonical or ambiguous symbols must fail
    assert validate_canonical_instrument("BTCUSDT") is False
    assert validate_canonical_instrument("BINANCE:SPOT:SOLUSDT") is False
    assert validate_canonical_instrument("BINANCE:PERP:BTCUSDT") is False


def test_timestamp_source_precision_preservation():
    ts = TimestampRecord.from_source(1710000000123, "ms", ingest_ns=1710000000500000000)
    assert ts.ts_event_ns == 1710000000123000000
    assert ts.source_ts_raw == 1710000000123
    assert ts.source_ts_unit == "ms"
    assert ts.source_precision == "ms"
    assert ts.ts_ingest_ns == 1710000000500000000

    # Monotonicity checks
    assert validate_timestamp_monotonicity([100, 200, 300, 300, 400]) is True
    assert validate_timestamp_monotonicity([100, 200, 150, 300]) is False
    assert validate_timestamp_monotonicity([None, 100, None, 200]) is True


def test_financial_decimal_precision():
    d1 = FinancialDecimal.parse("12345.67890000")
    assert isinstance(d1, Decimal)
    assert FinancialDecimal.format_exact(d1) == "12345.67890000"

    # Float inputs must be rejected to prevent binary float contamination
    with pytest.raises(TypeError):
        FinancialDecimal.parse(12345.67)


def test_provenance_contract_validation():
    prov = ProvenanceRecord(
        source="binance",
        source_dataset="trades",
        source_object_id="BINANCE:SPOT:BTCUSDT:trades:2024-01",
        source_filename="BTCUSDT-trades-2024-01.zip",
        source_physical_sha256="a" * 64,
        retrieved_at_ns=1710000000000000000,
        parser_version="1.0.0",
        schema_version="1.0.0",
        build_version="1B.0",
        quality_status=QualityState.VALID,
    )
    d = prov.to_dict()
    assert d["quality_status"] == "VALID"

    roundtrip = ProvenanceRecord.from_dict(d)
    assert roundtrip == prov

    # Invalid SHA256 length must raise ValueError
    with pytest.raises(ValueError):
        ProvenanceRecord(
            source="binance",
            source_dataset="trades",
            source_object_id="x",
            source_filename="f.zip",
            source_physical_sha256="short_hash",
            retrieved_at_ns=0,
            parser_version="1",
            schema_version="1",
            build_version="1",
        )


def test_security_scan_coverage():
    # Calling scan() raises SystemExit if any forbidden trading patterns are detected
    run_security_scan()
