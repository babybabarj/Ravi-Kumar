from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from btceth_os.sources.binance.archive_catalog import ArchiveCatalog
from btceth_os.sources.binance.archive_downloader import ArchiveDownloadResult
from btceth_os.sources.binance.models import ArchiveObjectSpec


def spec() -> ArchiveObjectSpec:
    return ArchiveObjectSpec(
        source="binance", market="usdm", dataset_id="BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY",
        source_dataset_name="fundingRate", instrument="BINANCE:USD_M_PERP:BTCUSDT", symbol="BTCUSDT",
        cadence="monthly", interval=None, period_key="2024-11",
        period_start_utc="2024-11-01T00:00:00+00:00", period_end_utc="2024-11-30T23:59:59.999999+00:00",
        archive_url="https://example.test/BTCUSDT-fundingRate-2024-11.zip",
        checksum_url="https://example.test/BTCUSDT-fundingRate-2024-11.zip.CHECKSUM",
        archive_filename="BTCUSDT-fundingRate-2024-11.zip", checksum_filename="BTCUSDT-fundingRate-2024-11.zip.CHECKSUM",
        expected_timestamp_policy={"type": "fixed_ms"}, support_status="VERIFIED_TRUE", discovery_evidence_id="test",
    )


def receipt_result(tmp_path: Path, payload: bytes, *, retrieved_at: str = "2026-09-21T00:00:00+00:00") -> ArchiveDownloadResult:
    digest = hashlib.sha256(payload).hexdigest()
    archive = tmp_path / f"object.{digest}.zip"
    archive.write_bytes(payload)
    receipt = Path(f"{archive}.receipt.json")
    result = ArchiveDownloadResult(
        status="DOWNLOADED", spec=spec(), local_path=str(archive), receipt_path=str(receipt),
        physical_sha256=digest, official_checksum=digest, content_length=len(payload), etag='"v1"',
        last_modified="Tue, 17 Dec 2024 12:45:32 GMT", retrieved_at_utc=retrieved_at,
    )
    receipt.write_text(json.dumps(result.to_dict()))
    return result


def test_catalog_records_immutable_object_and_wal_receipt(tmp_path: Path):
    catalog = ArchiveCatalog(tmp_path / "archive_catalog.sqlite")
    result = receipt_result(tmp_path, b"archive bytes")
    write = catalog.record_download(result)

    assert write.object_inserted and write.retrieval_inserted
    assert catalog.journal_mode() == "wal"
    assert catalog.objects()[0]["physical_sha256"] == result.physical_sha256
    catalog.close()


def test_catalog_is_idempotent_for_an_existing_receipt(tmp_path: Path):
    catalog = ArchiveCatalog(tmp_path / "archive_catalog.sqlite")
    result = receipt_result(tmp_path, b"archive bytes")
    assert catalog.record_download(result).object_inserted
    duplicate = catalog.record_download(result)
    assert not duplicate.object_inserted and not duplicate.retrieval_inserted
    assert catalog.object_count() == 1
    catalog.close()


def test_catalog_preserves_changed_source_bytes_and_sorts_deterministically(tmp_path: Path):
    catalog = ArchiveCatalog(tmp_path / "archive_catalog.sqlite")
    first = receipt_result(tmp_path, b"first", retrieved_at="2026-09-21T00:00:00+00:00")
    second = receipt_result(tmp_path, b"second", retrieved_at="2026-09-21T00:01:00+00:00")
    catalog.record_download(second)
    catalog.record_download(first)

    assert catalog.object_count() == 2
    assert [row["physical_sha256"] for row in catalog.objects()] == sorted(
        [first.physical_sha256, second.physical_sha256]
    )
    catalog.close()


def test_catalog_rejects_tampered_archive_bytes(tmp_path: Path):
    catalog = ArchiveCatalog(tmp_path / "archive_catalog.sqlite")
    result = receipt_result(tmp_path, b"original")
    Path(result.local_path).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="physical SHA-256"):
        catalog.record_download(result)
    assert catalog.object_count() == 0
    catalog.close()
