from __future__ import annotations

import hashlib
import io
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from btceth_os.sources.binance.archive_downloader import (
    ArchiveDownloader,
    ArchiveNotFoundError,
    ChecksumValidationError,
    SourceMutationDetectedError,
    get_os_sha256,
)
from btceth_os.sources.binance.models import ArchiveObjectSpec


class MockResponse:
    def __init__(self, data: bytes, status: int = 200):
        self.data = data
        self.status = status
        self.stream = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockOpener:
    def __init__(self, routes: dict[str, Any]):
        self.routes = routes
        self.calls: list[str] = []

    def open(self, req: urllib.request.Request | str, timeout: float = 20.0) -> Any:
        url = req.full_url if isinstance(req, urllib.request.Request) else req
        self.calls.append(url)
        if url in self.routes:
            handler = self.routes[url]
            if isinstance(handler, Exception):
                raise handler
            if callable(handler):
                return handler()
            return MockResponse(handler)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


def make_test_spec(
    market: str = "usdm",
    symbol: str = "BTCUSDT",
    dataset: str = "fundingRate",
    period: str = "2024-11",
) -> ArchiveObjectSpec:
    fname = f"{symbol}-{dataset}-{period}.zip"
    return ArchiveObjectSpec(
        source="binance",
        market=market,  # type: ignore
        dataset_id=f"BINANCE:USD_M_PERP:{symbol}:FUNDING_HISTORY",
        source_dataset_name=dataset,
        instrument="BTCUSDT",
        symbol=symbol,
        cadence="monthly",
        interval=None,
        period_key=period,
        period_start_utc="2024-11-01T00:00:00Z",
        period_end_utc="2024-11-30T23:59:59Z",
        archive_url=f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}/{fname}",
        checksum_url=f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}/{fname}.CHECKSUM",
        archive_filename=fname,
        checksum_filename=f"{fname}.CHECKSUM",
        expected_timestamp_policy={"unit": "ms"},
        support_status="CANONICAL",
        discovery_evidence_id="evidence-123",
    )


def make_zip_bytes(csv_name: str, csv_content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_name, csv_content)
    return buf.getvalue()


def test_download_valid_with_checksum_first(tmp_path: Path):
    spec = make_test_spec()
    csv_bytes = b"calc_time,funding_interval_hours,last_funding_rate\n1732953600000,8,-0.00012359\n"
    zip_bytes = make_zip_bytes(spec.archive_filename.replace(".zip", ".csv"), csv_bytes)
    sha256 = hashlib.sha256(zip_bytes).hexdigest()
    checksum_content = f"{sha256}  {spec.archive_filename}\n".encode("utf-8")

    opener = MockOpener({
        spec.checksum_url: checksum_content,
        spec.archive_url: zip_bytes,
    })

    downloader = ArchiveDownloader(bronze_root=tmp_path, opener=opener)
    receipt = downloader.download(spec)

    assert receipt.status == "DOWNLOADED"
    assert receipt.checksum_verified is True
    assert receipt.official_checksum == sha256
    assert receipt.computed_archive_sha256 == sha256
    assert receipt.os_computed_sha256 == sha256
    assert Path(receipt.local_archive_path).is_file()
    assert Path(receipt.extracted_payload_path).is_file()
    assert receipt.payload_sha256 == hashlib.sha256(csv_bytes).hexdigest()

    # Verify Checksum First: checksum_url was called before archive_url
    assert opener.calls[0] == spec.checksum_url
    assert opener.calls[1] == spec.archive_url


def test_download_checksum_mismatch_fails_closed(tmp_path: Path):
    spec = make_test_spec()
    zip_bytes = make_zip_bytes(spec.archive_filename.replace(".zip", ".csv"), b"dummy")
    checksum_content = f"{'0'*64}  {spec.archive_filename}\n".encode("utf-8")

    opener = MockOpener({
        spec.checksum_url: checksum_content,
        spec.archive_url: zip_bytes,
    })

    downloader = ArchiveDownloader(bronze_root=tmp_path, opener=opener)
    with pytest.raises(ChecksumValidationError, match=r"Checksum mismatch"):
        downloader.download(spec)

    # Invariant: No corrupted or unverified zip file is retained
    target_dir = tmp_path / "binance" / "futures_um" / spec.source_dataset_name / spec.symbol
    assert not (target_dir / spec.archive_filename).exists()
    assert not (target_dir / f"{spec.archive_filename}.part").exists()


def test_reject_malformed_checksum_sidecar(tmp_path: Path):
    spec = make_test_spec()
    opener = MockOpener({
        spec.checksum_url: b"this-is-not-a-sha256-digest",
    })
    downloader = ArchiveDownloader(bronze_root=tmp_path, opener=opener)
    with pytest.raises(ChecksumValidationError, match=r"Malformed checksum"):
        downloader.download(spec)


def test_reject_checksum_filename_mismatch(tmp_path: Path):
    spec = make_test_spec()
    sha256 = "a" * 64
    opener = MockOpener({
        spec.checksum_url: f"{sha256}  DIFFERENT_FILENAME.zip\n".encode("utf-8"),
    })
    downloader = ArchiveDownloader(bronze_root=tmp_path, opener=opener)
    with pytest.raises(ChecksumValidationError, match=r"Checksum target filename mismatch"):
        downloader.download(spec)


def test_download_404_handling(tmp_path: Path):
    spec = make_test_spec()
    opener = MockOpener({})
    downloader = ArchiveDownloader(bronze_root=tmp_path, opener=opener)

    # Unexpected missing raises ArchiveNotFoundError
    with pytest.raises(ArchiveNotFoundError):
        downloader.download(spec, missing_is_expected=False)

    # Expected missing returns structured receipt
    receipt = downloader.download(spec, missing_is_expected=True)
    assert receipt.status == "SOURCE_OBJECT_MISSING"
    assert receipt.http_archive_status == 404
    assert receipt.local_archive_path is None


def test_idempotency_cache_hit_avoids_redownload(tmp_path: Path):
    spec = make_test_spec()
    csv_bytes = b"calc_time,funding_interval_hours,last_funding_rate\n1732953600000,8,-0.00012359\n"
    zip_bytes = make_zip_bytes(spec.archive_filename.replace(".zip", ".csv"), csv_bytes)
    sha256 = hashlib.sha256(zip_bytes).hexdigest()
    checksum_content = f"{sha256}  {spec.archive_filename}\n".encode("utf-8")

    opener = MockOpener({
        spec.checksum_url: checksum_content,
        spec.archive_url: zip_bytes,
    })

    downloader = ArchiveDownloader(bronze_root=tmp_path, opener=opener)
    first_receipt = downloader.download(spec)
    assert first_receipt.status == "DOWNLOADED"
    assert len(opener.calls) == 2  # checksum + archive

    # Second call: Cache hit
    second_receipt = downloader.download(spec)
    assert second_receipt.status == "EXISTING_VALID"
    assert second_receipt.local_archive_path == first_receipt.local_archive_path
    # Checksum was checked, but archive_url was NOT requested again!
    assert len(opener.calls) == 3  # only 1 new call for checksum


def test_source_mutation_detection_fails_closed(tmp_path: Path):
    spec = make_test_spec()
    csv_bytes = b"data_v1"
    zip_bytes = make_zip_bytes(spec.archive_filename.replace(".zip", ".csv"), csv_bytes)
    sha256_v1 = hashlib.sha256(zip_bytes).hexdigest()

    opener = MockOpener({
        spec.checksum_url: f"{sha256_v1}  {spec.archive_filename}\n".encode("utf-8"),
        spec.archive_url: zip_bytes,
    })

    downloader = ArchiveDownloader(bronze_root=tmp_path, opener=opener)
    downloader.download(spec)

    # Now upstream mutates! Checksum returns sha256_v2
    sha256_v2 = "b" * 64
    mutated_opener = MockOpener({
        spec.checksum_url: f"{sha256_v2}  {spec.archive_filename}\n".encode("utf-8"),
    })
    mutated_downloader = ArchiveDownloader(bronze_root=tmp_path, opener=mutated_opener)

    with pytest.raises(SourceMutationDetectedError, match=r"SOURCE_MUTATION_DETECTED"):
        mutated_downloader.download(spec)
