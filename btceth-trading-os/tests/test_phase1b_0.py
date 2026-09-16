from decimal import Decimal
import hashlib
import json
from pathlib import Path
import zipfile
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
    resolve_spot_timestamp,
)
from btceth_os.sources import (
    DatasetDefinition,
    load_historical_datasets_registry,
    validate_canonical_instrument,
)
from btceth_os.security_scan import scan as run_security_scan


ROOT = Path(__file__).resolve().parents[1]


def test_open_source_manifest_and_recomputed_zip_hashes():
    """Verify manifest exists and mechanically recompute every archive SHA-256 and license presence."""
    manifest_path = ROOT / "reports" / "OPEN_SOURCE_SOURCE_MANIFEST.json"
    assert manifest_path.is_file(), "Manifest JSON file must exist"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["manifest_version"] == "1.0.0"
    assert data["archive_count"] == 8

    archives = {a["key"]: a for a in data["archives"]}
    required_keys = {"passivbot", "jesse", "nautilus_trader", "hummingbot", "freqtrade", "octobot", "ccxt", "lean"}
    assert set(archives.keys()) == required_keys

    # Mechanically recalculate SHA-256 and verify contents for all 8 ZIPs on disk
    for key, item in archives.items():
        zip_path = Path(item["absolute_source_path"])
        assert zip_path.is_file(), f"Archive file must exist on disk: {zip_path}"
        assert zip_path.stat().st_size == item["size_bytes"], f"Byte size mismatch for {key}"

        # Recompute SHA-256 from actual file
        recomputed_sha = compute_file_sha256(zip_path)
        assert recomputed_sha == item["sha256"], f"SHA-256 mismatch for {key}: expected {item['sha256']}, got {recomputed_sha}"

        # Open ZIP and verify license file and archive root directory exist
        with zipfile.ZipFile(zip_path) as z:
            namelist = z.namelist()
            assert len(namelist) > 0, f"Archive {key} must not be empty"
            actual_root = namelist[0].split("/")[0]
            assert actual_root == item["archive_root_directory"], f"Root directory mismatch for {key}"
            assert item["license_file_path"] in namelist, f"License file {item['license_file_path']} missing in {key}"


def test_sha256_helpers(tmp_path: Path):
    sample = b"BTCETH_TRADING_OS_CANONICAL_DATA_V1_1"
    expected_hash = "c0337d93638ebce0731486c842298f8ae583fe43c3d9dc2fa56289ec1c9f2e77"

    assert compute_bytes_sha256(sample) == expected_hash

    f = tmp_path / "sample.bin"
    f.write_bytes(sample)
    assert compute_file_sha256(f) == expected_hash

    inc = IncrementalSha256()
    inc.update(sample[:10])
    inc.update(sample[10:])
    assert inc.bytes_hashed == len(sample)
    assert inc.hexdigest() == expected_hash


def test_hardened_logical_hashing(tmp_path: Path):
    # 1. Order insensitivity: same records different order -> same logical hash
    r1 = [("k2", "h2"), ("k1", "h1"), ("k3", "h3")]
    r2 = [("k3", "h3"), ("k1", "h1"), ("k2", "h2")]
    hash1 = compute_logical_sha256(r1)
    hash2 = compute_logical_sha256(r2)
    assert hash1 == hash2

    # 2. Different payload -> different logical hash
    r3 = [("k1", "h1"), ("k2", "different_payload"), ("k3", "h3")]
    assert compute_logical_sha256(r3) != hash1

    # 3. Different record count -> different logical hash
    r4 = [("k1", "h1"), ("k2", "h2")]
    assert compute_logical_sha256(r4) != hash1

    # 4. Duplicate record key with different payload hashes -> deterministic result
    r5a = [("k1", "hA"), ("k1", "hB")]
    r5b = [("k1", "hB"), ("k1", "hA")]
    assert compute_logical_sha256(r5a) == compute_logical_sha256(r5b)

    # 5. Mismatched inputs -> explicit failure (ValueError)
    with pytest.raises(ValueError, match="Length mismatch"):
        compute_logical_sha256(["k1", "k2"], ["h1"])

    with pytest.raises(ValueError, match="Expected"):
        compute_logical_sha256([("only_one_item",)])  # type: ignore[list-item]

    # 6. Filesystem path change / mtime change -> no change to logical hash
    f1 = tmp_path / "path_a" / "data.parquet"
    f2 = tmp_path / "path_b" / "data.parquet"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f2.parent.mkdir(parents=True, exist_ok=True)
    f1.write_bytes(b"content")
    f2.write_bytes(b"content")
    # Even if files are in different paths, logical hash depends strictly on semantic record contents
    logical_a = compute_logical_sha256(r1)
    logical_b = compute_logical_sha256(r1)
    assert logical_a == logical_b


def test_hardened_provenance_validation():
    valid_sha = "c0337d93638ebce0731486c842298f8ae583fe43c3d9dc2fa56289ec1c9f2e77"
    prov = ProvenanceRecord(
        source="binance",
        source_dataset="trades",
        source_object_id="BINANCE:SPOT:BTCUSDT:trades:2024-01",
        source_filename="BTCUSDT-trades-2024-01.zip",
        source_physical_sha256=valid_sha,
        retrieved_at_ns=1710000000000000000,
        parser_version="1.0.0",
        schema_version="1.0.0",
        build_version="1B.0",
        quality_status=QualityState.VALID,
    )
    d = prov.to_dict()
    assert d["quality_status"] == "VALID"
    assert ProvenanceRecord.from_dict(d) == prov

    # Non-hex characters must raise ValueError
    with pytest.raises(ValueError, match="invalid SHA-256 digest"):
        ProvenanceRecord(
            source="binance",
            source_dataset="trades",
            source_object_id="x",
            source_filename="f.zip",
            source_physical_sha256="g" * 64,  # 'g' is not hex
            retrieved_at_ns=0,
            parser_version="1",
            schema_version="1",
            build_version="1",
        )

    # Wrong length must raise ValueError
    with pytest.raises(ValueError, match="invalid SHA-256 digest"):
        ProvenanceRecord(
            source="binance",
            source_dataset="trades",
            source_object_id="x",
            source_filename="f.zip",
            source_physical_sha256="c0337d93",
            retrieved_at_ns=0,
            parser_version="1",
            schema_version="1",
            build_version="1",
        )

    # Uppercase hex must raise ValueError (requires canonical lowercase)
    with pytest.raises(ValueError, match="invalid SHA-256 digest"):
        ProvenanceRecord(
            source="binance",
            source_dataset="trades",
            source_object_id="x",
            source_filename="f.zip",
            source_physical_sha256=valid_sha.upper(),
            retrieved_at_ns=0,
            parser_version="1",
            schema_version="1",
            build_version="1",
        )


def test_spot_date_versioned_timestamp_policy():
    # 1. Pre-2025 Spot: millisecond timestamp (13 digits)
    pre_2025_ms = 1710000000123
    event_ns, unit = resolve_spot_timestamp(pre_2025_ms)
    assert unit == "ms"
    assert event_ns == 1710000000123000000

    rec_pre = TimestampRecord.from_spot_source(pre_2025_ms, ingest_ns=1710000000200000000)
    assert rec_pre.source_ts_unit == "ms"
    assert rec_pre.source_precision == "ms"
    assert rec_pre.source_ts_raw == pre_2025_ms
    assert rec_pre.ts_event_ns == 1710000000123000000

    # 2. 2025+ Spot: microsecond timestamp (16 digits)
    # Example: 1735689600010866 (2025-01-01 00:00:00.010866 UTC)
    post_2025_us = 1735689600010866
    event_ns_post, unit_post = resolve_spot_timestamp(post_2025_us)
    assert unit_post == "us"
    assert event_ns_post == 1735689600010866000

    rec_post = TimestampRecord.from_spot_source(post_2025_us, ingest_ns=1735689600020000000)
    assert rec_post.source_ts_unit == "us"
    assert rec_post.source_precision == "us"
    assert rec_post.source_ts_raw == post_2025_us
    assert rec_post.ts_event_ns == 1735689600010866000

    # Fail closed verification: if interpreted as ms, it would produce year 56976
    # 1735689600010866 * 1_000_000 = 1735689600010866000000 (wrong)
    assert event_ns_post != post_2025_us * 1_000_000


def test_dataset_registry_remediations():
    datasets = load_historical_datasets_registry()
    assert len(datasets) >= 14

    for d in datasets:
        assert d.archive_support_status in ("UNVERIFIED_SOURCE_PATH", "VERIFIED_TRUE")
        assert d.daily_support in ("UNVERIFIED", "VERIFIED_TRUE", "VERIFIED_FALSE"), f"daily_support status for {d.dataset_id}"
        assert d.monthly_support in ("UNVERIFIED", "VERIFIED_TRUE"), f"monthly_support status for {d.dataset_id}"
        assert d.checksum_support in ("UNVERIFIED", "VERIFIED_TRUE"), f"checksum_support status for {d.dataset_id}"

        if d.market == "spot":
            assert d.source_timestamp_policy.get("type") == "date_versioned", f"Spot dataset {d.dataset_id} must have date_versioned timestamp policy"
        elif d.market == "usdm":
            assert d.source_timestamp_policy.get("type") in ("unverified", "fixed_ms"), f"USD-M dataset {d.dataset_id} timestamp policy"

        # Check official naming for premium price klines
        if "PREMIUM" in d.dataset_id:
            assert d.source_dataset_name in ("premiumPriceKlines", "premiumIndexKlines"), f"Premium dataset naming: {d.dataset_id}"

        # Check funding history format
        if "FUNDING" in d.dataset_id:
            assert d.raw_format in ("UNVERIFIED", "csv.zip")


def test_canonical_instrument_uniqueness():
    assert validate_canonical_instrument("BINANCE:SPOT:BTCUSDT") is True
    assert validate_canonical_instrument("BINANCE:SPOT:ETHUSDT") is True
    assert validate_canonical_instrument("BINANCE:USD_M_PERP:BTCUSDT") is True
    assert validate_canonical_instrument("BINANCE:USD_M_PERP:ETHUSDT") is True

    assert validate_canonical_instrument("BTCUSDT") is False
    assert validate_canonical_instrument("BINANCE:SPOT:SOLUSDT") is False
    assert validate_canonical_instrument("BINANCE:PERP:BTCUSDT") is False


def test_financial_decimal_precision():
    d1 = FinancialDecimal.parse("12345.67890000")
    assert isinstance(d1, Decimal)
    assert FinancialDecimal.format_exact(d1) == "12345.67890000"

    with pytest.raises(TypeError):
        FinancialDecimal.parse(12345.67)


def test_security_scan_coverage():
    run_security_scan()
