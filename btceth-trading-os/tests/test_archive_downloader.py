from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import urllib.error
import zipfile

import pytest

from btceth_os.sources.binance.archive_downloader import (
    ArchiveChecksumError,
    ArchiveDownloader,
    ArchiveObjectMissing,
    ArchiveZipIntegrityError,
    parse_checksum_sidecar,
)
from btceth_os.sources.binance.models import ArchiveObjectSpec


class FakeResponse:
    def __init__(self, payload: bytes, *, headers: dict[str, str] | None = None, fail_after_reads: int | None = None):
        self.payload = payload
        self.headers = headers or {"content-length": str(len(payload))}
        self.fail_after_reads = fail_after_reads
        self.read_calls: list[int] = []
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, amount: int = -1) -> bytes:
        self.read_calls.append(amount)
        if self.fail_after_reads is not None and len(self.read_calls) > self.fail_after_reads:
            raise OSError("simulated network disconnect")
        if amount < 0:
            amount = len(self.payload) - self.offset
        chunk = self.payload[self.offset : self.offset + amount]
        self.offset += len(chunk)
        return chunk


class FakeOpener:
    def __init__(self, responses: dict[str, list[object]]):
        self.responses = {url: list(items) for url, items in responses.items()}
        self.calls: list[str] = []

    def __call__(self, request, *, timeout: float):
        url = request.full_url
        self.calls.append(url)
        item = self.responses[url].pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def spec() -> ArchiveObjectSpec:
    filename = "BTCUSDT-1m-2024-11.zip"
    return ArchiveObjectSpec(
        source="binance",
        market="spot",
        dataset_id="BINANCE:SPOT:BTCUSDT:KLINES_1M",
        source_dataset_name="klines",
        instrument="BINANCE:SPOT:BTCUSDT",
        symbol="BTCUSDT",
        cadence="monthly",
        interval="1m",
        period_key="2024-11",
        period_start_utc="2024-11-01T00:00:00+00:00",
        period_end_utc="2024-11-30T23:59:59.999999+00:00",
        archive_url="https://example.test/archive.zip",
        checksum_url="https://example.test/archive.zip.CHECKSUM",
        archive_filename=filename,
        checksum_filename=f"{filename}.CHECKSUM",
        expected_timestamp_policy={"type": "date_versioned"},
        support_status="VERIFIED_TRUE",
        discovery_evidence_id="test",
    )


def zip_payload(contents: bytes = b"open_time,open\n1730419200000,1\n") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BTCUSDT-1m-2024-11.csv", contents)
    return stream.getvalue()


def checksum(payload: bytes, filename: str) -> bytes:
    return f"{hashlib.sha256(payload).hexdigest()}  {filename}\n".encode()


def downloader(tmp_path: Path, opener: FakeOpener, **kwargs) -> ArchiveDownloader:
    return ArchiveDownloader(tmp_path, opener=opener, sleep=lambda _: None, chunk_size=97, **kwargs)


def test_parse_checksum_requires_exact_digest_and_filename():
    digest = "a" * 64
    assert parse_checksum_sidecar(f"{digest}  archive.zip\n".encode(), "archive.zip") == digest
    with pytest.raises(ArchiveChecksumError):
        parse_checksum_sidecar(b"not-a-digest  archive.zip\n", "archive.zip")
    with pytest.raises(ArchiveChecksumError):
        parse_checksum_sidecar(f"{digest}  another.zip\n".encode(), "archive.zip")


def test_streams_verifies_promotes_and_records_receipt(tmp_path: Path):
    requested = spec()
    payload = zip_payload(os.urandom(20_000))
    archive = FakeResponse(payload, headers={"content-length": str(len(payload)), "etag": '"v1"', "last-modified": "now"})
    opener = FakeOpener({requested.checksum_url: [FakeResponse(checksum(payload, requested.archive_filename))], requested.archive_url: [archive]})

    result = downloader(tmp_path, opener).download(requested)

    assert result.status == "DOWNLOADED"
    assert result.local_path is not None and Path(result.local_path).is_file()
    assert result.receipt_path is not None
    assert json.loads(Path(result.receipt_path).read_text())["physical_sha256"] == hashlib.sha256(payload).hexdigest()
    assert max(archive.read_calls) == 97
    assert not list(tmp_path.rglob("*.part"))


def test_bad_checksum_never_promotes_final_file(tmp_path: Path):
    requested = spec()
    payload = zip_payload()
    opener = FakeOpener({
        requested.checksum_url: [FakeResponse(checksum(b"different", requested.archive_filename))],
        requested.archive_url: [FakeResponse(payload)],
    })

    with pytest.raises(ArchiveChecksumError, match="mismatch"):
        downloader(tmp_path, opener).download(requested)
    assert not list(tmp_path.rglob("*.zip"))
    assert list(tmp_path.rglob("*.part"))


def test_corrupt_zip_never_promotes_final_file(tmp_path: Path):
    requested = spec()
    payload = b"not a zip"
    opener = FakeOpener({
        requested.checksum_url: [FakeResponse(checksum(payload, requested.archive_filename))],
        requested.archive_url: [FakeResponse(payload)],
    })

    with pytest.raises(ArchiveZipIntegrityError):
        downloader(tmp_path, opener).download(requested)
    assert not list(tmp_path.rglob("*.zip"))
    assert list(tmp_path.rglob("*.part"))


def test_disconnect_retries_from_a_part_file_and_succeeds(tmp_path: Path):
    requested = spec()
    payload = zip_payload(os.urandom(500))
    opener = FakeOpener({
        requested.checksum_url: [FakeResponse(checksum(payload, requested.archive_filename))],
        requested.archive_url: [FakeResponse(payload, fail_after_reads=1), FakeResponse(payload)],
    })

    result = downloader(tmp_path, opener, max_retries=1).download(requested)
    assert result.status == "DOWNLOADED"
    assert opener.calls.count(requested.archive_url) == 2
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize("status", [429, 503])
def test_retryable_http_failures_are_retried(status: int, tmp_path: Path):
    requested = spec()
    payload = zip_payload()
    retryable = urllib.error.HTTPError(requested.checksum_url, status, "retry", {"retry-after": "0"}, None)
    opener = FakeOpener({
        requested.checksum_url: [retryable, FakeResponse(checksum(payload, requested.archive_filename))],
        requested.archive_url: [FakeResponse(payload)],
    })

    assert downloader(tmp_path, opener, max_retries=1).download(requested).status == "DOWNLOADED"
    assert opener.calls.count(requested.checksum_url) == 2


def test_404_is_explicit_and_optional_objects_can_be_classified(tmp_path: Path):
    requested = spec()
    missing = urllib.error.HTTPError(requested.checksum_url, 404, "missing", {}, None)
    with pytest.raises(ArchiveObjectMissing):
        downloader(tmp_path, FakeOpener({requested.checksum_url: [missing]})).download(requested)

    optional = downloader(tmp_path, FakeOpener({requested.checksum_url: [missing]})).download(requested, missing_is_expected=True)
    assert optional.status == "SOURCE_OBJECT_MISSING"
    assert optional.local_path is None


def test_existing_valid_object_is_idempotent(tmp_path: Path):
    requested = spec()
    payload = zip_payload()
    first = FakeOpener({
        requested.checksum_url: [FakeResponse(checksum(payload, requested.archive_filename))],
        requested.archive_url: [FakeResponse(payload)],
    })
    initial = downloader(tmp_path, first).download(requested)
    second = FakeOpener({requested.checksum_url: [FakeResponse(checksum(payload, requested.archive_filename))]})

    result = downloader(tmp_path, second).download(requested)
    assert result.status == "EXISTING_VALID"
    assert result.local_path == initial.local_path
    assert second.calls == [requested.checksum_url]


def test_changed_source_bytes_are_preserved_as_distinct_raw_objects(tmp_path: Path):
    requested = spec()
    first_payload = zip_payload(b"first")
    second_payload = zip_payload(b"second")
    first = FakeOpener({
        requested.checksum_url: [FakeResponse(checksum(first_payload, requested.archive_filename))],
        requested.archive_url: [FakeResponse(first_payload)],
    })
    second = FakeOpener({
        requested.checksum_url: [FakeResponse(checksum(second_payload, requested.archive_filename))],
        requested.archive_url: [FakeResponse(second_payload)],
    })

    one = downloader(tmp_path, first).download(requested)
    two = downloader(tmp_path, second).download(requested)
    assert one.local_path != two.local_path
    assert len(list(tmp_path.rglob("*.zip"))) == 2


def test_invalid_existing_file_is_quarantined_before_redownload(tmp_path: Path):
    requested = spec()
    payload = zip_payload()
    first = FakeOpener({
        requested.checksum_url: [FakeResponse(checksum(payload, requested.archive_filename))],
        requested.archive_url: [FakeResponse(payload)],
    })
    initial = downloader(tmp_path, first).download(requested)
    Path(initial.local_path).write_bytes(b"tampered")
    second = FakeOpener({
        requested.checksum_url: [FakeResponse(checksum(payload, requested.archive_filename))],
        requested.archive_url: [FakeResponse(payload)],
    })

    result = downloader(tmp_path, second).download(requested)
    assert result.status == "DOWNLOADED"
    assert list(tmp_path.rglob("*.invalid.*"))
