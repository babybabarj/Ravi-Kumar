from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .bronze import ExtractedPayloadInfo, SafeZipExtractor
from .models import ArchiveObjectSpec


class ArchiveDownloaderError(RuntimeError):
    """Base error for archive downloader operations."""
    pass


class ChecksumValidationError(ArchiveDownloaderError):
    """Raised when checksum verification fails or checksum file is malformed."""
    pass


class SourceMutationDetectedError(ArchiveDownloaderError):
    """Raised when an upstream archive's checksum has changed compared to previously verified state."""
    pass


class ArchiveNotFoundError(ArchiveDownloaderError):
    """Raised when an archive returns HTTP 404."""
    pass


# Backward compatibility aliases for legacy error types
ArchiveDownloadError = ArchiveDownloaderError
ArchiveChecksumError = ChecksumValidationError
ArchiveObjectMissing = ArchiveNotFoundError
ArchiveTransportError = ArchiveDownloaderError
ArchiveZipIntegrityError = ArchiveDownloaderError


CHECKSUM_REGEX = re.compile(r"^([a-fA-F0-9]{64})\s+[\*]?(.*?)\s*$")


@dataclass(frozen=True)
class DownloadReceipt:
    spec: Any = None  # dict or ArchiveObjectSpec
    status: str = "DOWNLOADED"  # DOWNLOADED, EXISTING_VALID, SOURCE_OBJECT_MISSING, SOURCE_MUTATION_DETECTED, CHECKSUM_FAILED
    http_archive_status: int | None = 200
    http_checksum_status: int | None = 200
    retrieved_at_utc: str = ""
    archive_byte_size: int | None = None
    official_checksum: str | None = None
    computed_archive_sha256: str | None = None
    os_computed_sha256: str | None = None
    checksum_verified: bool = True
    local_archive_path: str | None = None
    local_receipt_path: str | None = None
    extracted_payload_path: str | None = None
    payload_byte_size: int | None = None
    payload_sha256: str | None = None
    payload_filename: str | None = None
    error_message: str | None = None
    # Downstream compatibility fields
    local_path: str | None = None
    receipt_path: str | None = None
    physical_sha256: str | None = None
    content_length: int | None = None
    etag: str | None = None
    last_modified: str | None = None

    def __post_init__(self) -> None:
        if not self.local_path and self.local_archive_path:
            object.__setattr__(self, "local_path", self.local_archive_path)
        elif not self.local_archive_path and self.local_path:
            object.__setattr__(self, "local_archive_path", self.local_path)

        if not self.receipt_path and self.local_receipt_path:
            object.__setattr__(self, "receipt_path", self.local_receipt_path)
        elif not self.local_receipt_path and self.receipt_path:
            object.__setattr__(self, "local_receipt_path", self.receipt_path)

        if not self.physical_sha256 and self.computed_archive_sha256:
            object.__setattr__(self, "physical_sha256", self.computed_archive_sha256)
        elif not self.computed_archive_sha256 and self.physical_sha256:
            object.__setattr__(self, "computed_archive_sha256", self.physical_sha256)

        if not self.content_length and self.archive_byte_size:
            object.__setattr__(self, "content_length", self.archive_byte_size)
        elif not self.archive_byte_size and self.content_length:
            object.__setattr__(self, "archive_byte_size", self.content_length)

        if not self.os_computed_sha256 and self.computed_archive_sha256:
            object.__setattr__(self, "os_computed_sha256", self.computed_archive_sha256)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["local_path"] = self.local_path or self.local_archive_path
        d["receipt_path"] = self.receipt_path or self.local_receipt_path
        d["physical_sha256"] = self.physical_sha256 or self.computed_archive_sha256
        d["content_length"] = self.content_length or self.archive_byte_size
        return d


ArchiveDownloadResult = DownloadReceipt


def get_os_sha256(file_path: Path) -> str:
    """Independent operating-system checksum oracle using `shasum -a 256`."""
    res = subprocess.run(
        ["shasum", "-a", "256", str(file_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    parts = res.stdout.strip().split()
    if not parts or len(parts[0]) != 64:
        raise RuntimeError(f"Unexpected output from shasum: {res.stdout}")
    return parts[0].lower()


def parse_checksum_sidecar(payload: bytes, expected_filename: str) -> str:
    """Return the exact SHA-256 from a single, filename-matching CHECKSUM sidecar."""
    content = payload.decode("utf-8", errors="replace").strip()
    match = CHECKSUM_REGEX.match(content)
    if not match:
        raise ChecksumValidationError(f"Malformed checksum response: {content!r}")
    sha, fname = match.groups()
    sha = sha.lower()
    fname = fname.strip()
    if fname and fname != expected_filename:
        raise ChecksumValidationError(
            f"Checksum target filename mismatch: expected '{expected_filename}', got '{fname}'"
        )
    return sha


class ArchiveDownloader:
    """Production-grade streaming archive downloader enforcing Checksum-First and Bronze Immutability."""

    def __init__(
        self,
        raw_root: Path | str | None = None,
        *,
        bronze_root: Path | str | None = None,
        user_agent: str = "BTCETH-Trading-OS/Phase1B.2 (Historical Acquisition)",
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        opener: Any = None,
        chunk_size: int = 65536,
        sleep: Callable[[float], None] = time.sleep,
    ):
        target = bronze_root if bronze_root is not None else raw_root
        if target is None:
            raise ValueError("raw_root or bronze_root must be provided")
        self.bronze_root = Path(target).resolve()
        self.raw_root = self.bronze_root
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.opener = opener or urllib.request.build_opener()
        self.chunk_size = chunk_size
        self._sleep = sleep

    def _open_url(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        for attempt in range(self.max_retries + 1):
            try:
                if hasattr(self.opener, "open"):
                    return self.opener.open(req, timeout=self.timeout_seconds)
                return self.opener(req, timeout=self.timeout_seconds)
            except urllib.error.HTTPError as e:
                # 404 is not retryable
                if e.code == 404:
                    raise
                if attempt >= self.max_retries:
                    raise
                self._sleep(0.5 * (2**attempt))
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt >= self.max_retries:
                    raise
                self._sleep(0.5 * (2**attempt))
        raise AssertionError("unreachable")

    def fetch_checksum(self, checksum_url: str, expected_archive_filename: str) -> tuple[int, str]:
        """Fetch and parse official .CHECKSUM file. Returns (http_status, 64_hex_lowercase_sha256)."""
        try:
            with self._open_url(checksum_url) as resp:
                status = getattr(resp, "status", getattr(resp, "code", 200))
                content = resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, ""
            raise ChecksumValidationError(f"HTTP error fetching checksum from {checksum_url}: {e}") from e

        sha = parse_checksum_sidecar(content, expected_archive_filename)
        return status, sha

    def download(
        self,
        spec: ArchiveObjectSpec,
        extract: bool = True,
        missing_is_expected: bool = False,
    ) -> DownloadReceipt:
        """Acquire a canonical Binance archive object with Checksum First validation and safe Bronze extraction."""
        market_dir = "spot" if spec.market == "spot" else "futures_um"
        target_dir = self.bronze_root / "binance" / market_dir / spec.source_dataset_name / spec.symbol
        target_dir.mkdir(parents=True, exist_ok=True)

        archive_path = target_dir / spec.archive_filename
        receipt_path = target_dir / f"{spec.archive_filename}.receipt.json"

        # 1. Fetch official CHECKSUM sidecar first
        http_checksum_status, official_sha = self.fetch_checksum(spec.checksum_url, spec.archive_filename)
        retrieved_at = datetime.now(timezone.utc).isoformat()

        if http_checksum_status == 404:
            if missing_is_expected:
                return DownloadReceipt(
                    spec=spec,
                    status="SOURCE_OBJECT_MISSING",
                    http_archive_status=404,
                    http_checksum_status=404,
                    retrieved_at_utc=retrieved_at,
                    archive_byte_size=None,
                    official_checksum=None,
                    computed_archive_sha256=None,
                    os_computed_sha256=None,
                    checksum_verified=False,
                    local_archive_path=None,
                    local_receipt_path=None,
                    extracted_payload_path=None,
                    payload_byte_size=None,
                    payload_sha256=None,
                    payload_filename=None,
                    error_message=f"Checksum sidecar missing (HTTP 404) at {spec.checksum_url}",
                    local_path=None,
                    receipt_path=None,
                    physical_sha256=None,
                    content_length=None,
                )
            raise ArchiveNotFoundError(f"Archive checksum missing (HTTP 404): {spec.checksum_url}")

        # 2. Check for upstream source mutation if existing receipt exists
        if receipt_path.exists():
            try:
                prev_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                prev_official_sha = prev_receipt.get("official_checksum")
                if prev_official_sha and prev_official_sha != official_sha:
                    # Upstream mutation detected!
                    raise SourceMutationDetectedError(
                        f"SOURCE_MUTATION_DETECTED for {spec.archive_url}: "
                        f"previously verified SHA {prev_official_sha} != newly published SHA {official_sha}"
                    )
            except SourceMutationDetectedError:
                raise
            except Exception:
                pass  # Corrupted receipt will be refreshed

        part_path = target_dir / f"{spec.archive_filename}.part"

        # 3. Check for existing valid archive (Idempotency & Cache Hit)
        if archive_path.is_file() and archive_path.stat().st_size > 0:
            hasher = hashlib.sha256()
            with open(archive_path, "rb") as f:
                while chunk := f.read(self.chunk_size):
                    hasher.update(chunk)
            existing_sha = hasher.hexdigest().lower()
            if existing_sha == official_sha:
                if part_path.exists():
                    part_path.unlink()
                # Existing file is verified valid! Check extraction
                payload_info = None
                if extract:
                    expected_csv = spec.archive_filename.replace(".zip", ".csv")
                    payload_info = SafeZipExtractor.inspect_and_extract(
                        archive_path, target_dir, expected_payload_name=expected_csv
                    )
                os_sha = get_os_sha256(archive_path)
                receipt = DownloadReceipt(
                    spec=spec,
                    status="EXISTING_VALID",
                    http_archive_status=200,
                    http_checksum_status=http_checksum_status,
                    retrieved_at_utc=retrieved_at,
                    archive_byte_size=archive_path.stat().st_size,
                    official_checksum=official_sha,
                    computed_archive_sha256=existing_sha,
                    os_computed_sha256=os_sha,
                    checksum_verified=(existing_sha == official_sha == os_sha),
                    local_archive_path=str(archive_path),
                    local_receipt_path=str(receipt_path),
                    extracted_payload_path=payload_info.payload_path if payload_info else None,
                    payload_byte_size=payload_info.payload_byte_size if payload_info else None,
                    payload_sha256=payload_info.payload_sha256 if payload_info else None,
                    payload_filename=payload_info.payload_filename if payload_info else None,
                    local_path=str(archive_path),
                    receipt_path=str(receipt_path),
                    physical_sha256=existing_sha,
                    content_length=archive_path.stat().st_size,
                )
                receipt_path.write_text(json.dumps(receipt.to_dict(), indent=2) + "\n", encoding="utf-8")
                return receipt
            else:
                # Corrupted existing file: quarantine before re-download
                quarantine_name = f"{spec.archive_filename}.corrupted.{int(time.time())}"
                os.replace(archive_path, target_dir / quarantine_name)

        # 4. Streaming download into temporary .part file
        part_path = target_dir / f"{spec.archive_filename}.part"
        if part_path.exists():
            part_path.unlink()

        try:
            with self._open_url(spec.archive_url) as resp:
                http_archive_status = getattr(resp, "status", getattr(resp, "code", 200))
                headers = getattr(resp, "headers", None)
                etag = headers.get("etag") if headers else None
                last_modified = headers.get("last-modified") if headers else None
                hasher = hashlib.sha256()
                bytes_downloaded = 0
                with open(part_path, "wb") as f_part:
                    while True:
                        chunk = resp.read(self.chunk_size)
                        if not chunk:
                            break
                        hasher.update(chunk)
                        bytes_downloaded += len(chunk)
                        f_part.write(chunk)
                    f_part.flush()
                    os.fsync(f_part.fileno())
        except urllib.error.HTTPError as e:
            if part_path.exists():
                part_path.unlink()
            if e.code == 404:
                if missing_is_expected:
                    return DownloadReceipt(
                        spec=spec,
                        status="SOURCE_OBJECT_MISSING",
                        http_archive_status=404,
                        http_checksum_status=http_checksum_status,
                        retrieved_at_utc=retrieved_at,
                        archive_byte_size=None,
                        official_checksum=official_sha,
                        computed_archive_sha256=None,
                        os_computed_sha256=None,
                        checksum_verified=False,
                        local_archive_path=None,
                        local_receipt_path=None,
                        extracted_payload_path=None,
                        payload_byte_size=None,
                        payload_sha256=None,
                        payload_filename=None,
                        error_message=f"Archive file missing (HTTP 404) at {spec.archive_url}",
                        local_path=None,
                        receipt_path=None,
                        physical_sha256=None,
                        content_length=None,
                    )
                raise ArchiveNotFoundError(f"Archive file missing (HTTP 404): {spec.archive_url}") from e
            raise ArchiveDownloaderError(f"HTTP error downloading archive from {spec.archive_url}: {e}") from e

        # 5. Checksum verification of streamed bytes
        computed_sha = hasher.hexdigest().lower()
        if computed_sha != official_sha:
            if part_path.exists():
                part_path.unlink()
            raise ChecksumValidationError(
                f"Checksum mismatch for {spec.archive_url}: official={official_sha} vs computed={computed_sha}"
            )

        # 6. Atomic promotion .part -> .zip
        os.replace(part_path, archive_path)

        # 7. Independent OS Checksum Oracle reconciliation
        os_sha = get_os_sha256(archive_path)
        if os_sha != official_sha:
            archive_path.unlink()
            raise ChecksumValidationError(
                f"OS Checksum Oracle mismatch: shasum={os_sha} vs official={official_sha}"
            )

        # 8. Safe extraction
        payload_info = None
        if extract:
            expected_csv = spec.archive_filename.replace(".zip", ".csv")
            payload_info = SafeZipExtractor.inspect_and_extract(
                archive_path, target_dir, expected_payload_name=expected_csv
            )

        receipt = DownloadReceipt(
            spec=spec,
            status="DOWNLOADED",
            http_archive_status=http_archive_status,
            http_checksum_status=http_checksum_status,
            retrieved_at_utc=retrieved_at,
            archive_byte_size=archive_path.stat().st_size,
            official_checksum=official_sha,
            computed_archive_sha256=computed_sha,
            os_computed_sha256=os_sha,
            checksum_verified=(computed_sha == official_sha == os_sha),
            local_archive_path=str(archive_path),
            local_receipt_path=str(receipt_path),
            extracted_payload_path=payload_info.payload_path if payload_info else None,
            payload_byte_size=payload_info.payload_byte_size if payload_info else None,
            payload_sha256=payload_info.payload_sha256 if payload_info else None,
            payload_filename=payload_info.payload_filename if payload_info else None,
            local_path=str(archive_path),
            receipt_path=str(receipt_path),
            physical_sha256=computed_sha,
            content_length=archive_path.stat().st_size,
            etag=etag,
            last_modified=last_modified,
        )
        receipt_path.write_text(json.dumps(receipt.to_dict(), indent=2) + "\n", encoding="utf-8")
        return receipt
