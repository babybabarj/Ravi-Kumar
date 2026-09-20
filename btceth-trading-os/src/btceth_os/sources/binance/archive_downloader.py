# Adapted from Passivbot (https://github.com/enarjord/passivbot)
# Original file: src/binance_ohlcv_archive.py
# Archive: passivbot-master.zip (SHA256: bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468)
# License: The Unlicense (Public Domain)
# Adaptation: strict checksum parsing only. This module deliberately replaces
# Passivbot's in-memory archive reads with bounded streaming writes and atomic
# promotion into immutable RAW objects.

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from .models import ArchiveObjectSpec


CHECKSUM_MAX_BYTES = 64 * 1024
DEFAULT_CHUNK_SIZE = 1024 * 1024
_CHECKSUM_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?([^\s]+)\s*$")
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.:-]+$")


class ArchiveDownloadError(RuntimeError):
    """Base class for archive retrieval failures that must not promote RAW data."""


class ArchiveObjectMissing(ArchiveDownloadError):
    """The expected source object returned HTTP 404."""


class ArchiveChecksumError(ArchiveDownloadError):
    """The checksum sidecar or downloaded bytes failed strict verification."""


class ArchiveZipIntegrityError(ArchiveDownloadError):
    """The downloaded bytes do not form a readable ZIP archive."""


class ArchiveTransportError(ArchiveDownloadError):
    """A retryable transport failure exhausted the bounded retry budget."""


class _Response(Protocol):
    headers: Any

    def read(self, amount: int = -1) -> bytes: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool | None: ...


Opener = Callable[..., _Response]


@dataclass(frozen=True)
class ArchiveDownloadResult:
    status: Literal["DOWNLOADED", "EXISTING_VALID", "SOURCE_OBJECT_MISSING"]
    spec: ArchiveObjectSpec
    local_path: str | None
    receipt_path: str | None
    physical_sha256: str | None
    official_checksum: str | None
    content_length: int | None
    etag: str | None
    last_modified: str | None
    retrieved_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_checksum_sidecar(payload: bytes, expected_filename: str) -> str:
    """Return the exact SHA-256 from a single, filename-matching CHECKSUM sidecar."""
    try:
        text = payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ArchiveChecksumError("checksum sidecar is not UTF-8") from exc
    match = _CHECKSUM_LINE.fullmatch(text)
    if not match:
        raise ArchiveChecksumError("checksum sidecar must contain exactly '<sha256>  <filename>'")
    digest, filename = match.groups()
    if filename != expected_filename:
        raise ArchiveChecksumError(
            f"checksum sidecar names {filename!r}, expected {expected_filename!r}"
        )
    return digest.lower()


class ArchiveDownloader:
    """Fail-closed downloader for one planned official Binance archive object.

    Final filenames include the physical SHA-256. A later source rewrite therefore
    creates a new RAW object instead of overwriting previously preserved evidence.
    """

    def __init__(
        self,
        raw_root: Path | str,
        *,
        opener: Opener = urllib.request.urlopen,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.raw_root = Path(raw_root)
        self._opener = opener
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.chunk_size = chunk_size
        self._sleep = sleep

    def download(
        self,
        spec: ArchiveObjectSpec,
        *,
        missing_is_expected: bool = False,
    ) -> ArchiveDownloadResult:
        """Retrieve, verify, and atomically preserve one source object.

        A known optional object can request ``missing_is_expected`` and receive an
        explicit SOURCE_OBJECT_MISSING result; canonical planned objects otherwise
        fail closed on HTTP 404.
        """
        retrieved_at = _utc_now()
        try:
            checksum_bytes, _ = self._read_bounded(spec.checksum_url, CHECKSUM_MAX_BYTES)
        except ArchiveObjectMissing:
            if missing_is_expected:
                return ArchiveDownloadResult(
                    status="SOURCE_OBJECT_MISSING",
                    spec=spec,
                    local_path=None,
                    receipt_path=None,
                    physical_sha256=None,
                    official_checksum=None,
                    content_length=None,
                    etag=None,
                    last_modified=None,
                    retrieved_at_utc=retrieved_at,
                )
            raise

        official_checksum = parse_checksum_sidecar(checksum_bytes, spec.archive_filename)
        final_path = self._final_path(spec, official_checksum)
        receipt_path = Path(f"{final_path}.receipt.json")

        if final_path.exists():
            if self._is_valid_local_archive(final_path, official_checksum):
                return ArchiveDownloadResult(
                    status="EXISTING_VALID",
                    spec=spec,
                    local_path=str(final_path),
                    receipt_path=str(receipt_path) if receipt_path.exists() else None,
                    physical_sha256=official_checksum,
                    official_checksum=official_checksum,
                    content_length=final_path.stat().st_size,
                    etag=None,
                    last_modified=None,
                    retrieved_at_utc=retrieved_at,
                )
            self._quarantine_invalid(final_path)

        part_path = Path(f"{final_path}.part")
        actual_checksum, headers = self._stream_archive(spec.archive_url, part_path)
        if actual_checksum != official_checksum:
            raise ArchiveChecksumError(
                f"archive SHA-256 mismatch: expected {official_checksum}, got {actual_checksum}"
            )
        self._verify_zip(part_path)
        os.replace(part_path, final_path)

        result = ArchiveDownloadResult(
            status="DOWNLOADED",
            spec=spec,
            local_path=str(final_path),
            receipt_path=str(receipt_path),
            physical_sha256=actual_checksum,
            official_checksum=official_checksum,
            content_length=final_path.stat().st_size,
            etag=_header(headers, "etag"),
            last_modified=_header(headers, "last-modified"),
            retrieved_at_utc=retrieved_at,
        )
        self._write_receipt(receipt_path, result)
        return result

    def _read_bounded(self, url: str, limit: int) -> tuple[bytes, Any]:
        request = _public_request(url)
        for attempt in range(self.max_retries + 1):
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    chunks: list[bytes] = []
                    total = 0
                    while True:
                        chunk = response.read(min(self.chunk_size, limit + 1 - total))
                        if not chunk:
                            return b"".join(chunks), response.headers
                        total += len(chunk)
                        if total > limit:
                            raise ArchiveChecksumError(f"response from {url!r} exceeds {limit} bytes")
                        chunks.append(chunk)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise ArchiveObjectMissing(f"source object missing: {url}") from exc
                if exc.code not in (429,) and not 500 <= exc.code < 600:
                    raise ArchiveDownloadError(f"HTTP {exc.code} for {url}") from exc
                self._retry_or_raise(attempt, url, exc)
            except ArchiveChecksumError:
                raise
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                self._retry_or_raise(attempt, url, exc)
        raise AssertionError("unreachable")

    def _stream_archive(self, url: str, part_path: Path) -> tuple[str, Any]:
        request = _public_request(url)
        part_path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(self.max_retries + 1):
            try:
                hasher = hashlib.sha256()
                total = 0
                with self._opener(request, timeout=self.timeout_seconds) as response, open(part_path, "wb") as out:
                    while chunk := response.read(self.chunk_size):
                        out.write(chunk)
                        hasher.update(chunk)
                        total += len(chunk)
                    out.flush()
                    os.fsync(out.fileno())
                    expected_length = _content_length(response.headers)
                    if expected_length is not None and total != expected_length:
                        raise ArchiveTransportError(
                            f"truncated response from {url}: expected {expected_length} bytes, received {total}"
                        )
                    return hasher.hexdigest(), response.headers
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise ArchiveObjectMissing(f"source object missing: {url}") from exc
                if exc.code not in (429,) and not 500 <= exc.code < 600:
                    raise ArchiveDownloadError(f"HTTP {exc.code} for {url}") from exc
                self._retry_or_raise(attempt, url, exc)
            except ArchiveTransportError:
                if attempt >= self.max_retries:
                    raise
                self._sleep(_backoff_seconds(attempt))
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                self._retry_or_raise(attempt, url, exc)
        raise AssertionError("unreachable")

    def _retry_or_raise(self, attempt: int, url: str, exc: BaseException) -> None:
        if attempt >= self.max_retries:
            raise ArchiveTransportError(f"retry budget exhausted for {url}: {exc}") from exc
        self._sleep(_backoff_seconds(attempt, exc))

    def _final_path(self, spec: ArchiveObjectSpec, checksum: str) -> Path:
        components = (spec.source, spec.market, spec.source_dataset_name, spec.instrument, spec.cadence, spec.period_key)
        if any(not _SAFE_COMPONENT.fullmatch(component) for component in components):
            raise ValueError(f"unsafe archive identity in specification: {components!r}")
        filename = Path(spec.archive_filename)
        if filename.name != spec.archive_filename or filename.suffix != ".zip":
            raise ValueError(f"unsafe archive filename: {spec.archive_filename!r}")
        directory = self.raw_root.joinpath(*components)
        return directory / f"{filename.stem}.{checksum}.zip"

    @staticmethod
    def _is_valid_local_archive(path: Path, checksum: str) -> bool:
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(DEFAULT_CHUNK_SIZE), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != checksum:
            return False
        try:
            with zipfile.ZipFile(path) as archive:
                return bool(archive.namelist()) and archive.testzip() is None
        except zipfile.BadZipFile:
            return False

    @staticmethod
    def _verify_zip(path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as archive:
                if not archive.namelist():
                    raise ArchiveZipIntegrityError("archive contains no files")
                corrupt_member = archive.testzip()
                if corrupt_member is not None:
                    raise ArchiveZipIntegrityError(f"ZIP CRC failed for member {corrupt_member!r}")
        except zipfile.BadZipFile as exc:
            raise ArchiveZipIntegrityError("downloaded bytes are not a valid ZIP archive") from exc

    @staticmethod
    def _quarantine_invalid(path: Path) -> None:
        quarantine = path.with_name(f"{path.name}.invalid.{time.time_ns()}")
        os.replace(path, quarantine)

    @staticmethod
    def _write_receipt(path: Path, result: ArchiveDownloadResult) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        part_path = Path(f"{path}.part")
        with part_path.open("w", encoding="utf-8") as out:
            json.dump(result.to_dict(), out, sort_keys=True, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(part_path, path)


def _public_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": "BTCETH-OS-ArchiveDownloader/1.0"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _header(headers: Any, name: str) -> str | None:
    value = headers.get(name) if headers is not None else None
    return str(value) if value is not None else None


def _content_length(headers: Any) -> int | None:
    value = _header(headers, "content-length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ArchiveTransportError(f"invalid Content-Length header: {value!r}") from exc


def _backoff_seconds(attempt: int, error: BaseException | None = None) -> float:
    if isinstance(error, urllib.error.HTTPError):
        retry_after = _header(error.headers, "retry-after")
        if retry_after and retry_after.isdigit():
            return min(float(retry_after), 30.0)
    return min(0.5 * (2**attempt), 5.0)
