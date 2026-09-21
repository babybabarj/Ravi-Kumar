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


CHECKSUM_REGEX = re.compile(r"^([a-fA-F0-9]{64})\s+[\*]?(.*?)\s*$")


@dataclass(frozen=True)
class DownloadReceipt:
    spec: dict[str, Any]
    status: str  # DOWNLOADED, EXISTING_VALID, SOURCE_OBJECT_MISSING, SOURCE_MUTATION_DETECTED, CHECKSUM_FAILED
    http_archive_status: int | None
    http_checksum_status: int | None
    retrieved_at_utc: str
    archive_byte_size: int | None
    official_checksum: str | None
    computed_archive_sha256: str | None
    os_computed_sha256: str | None
    checksum_verified: bool
    local_archive_path: str | None
    local_receipt_path: str | None
    extracted_payload_path: str | None
    payload_byte_size: int | None
    payload_sha256: str | None
    payload_filename: str | None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


class ArchiveDownloader:
    """Production-grade streaming archive downloader enforcing Checksum-First and Bronze Immutability."""

    def __init__(
        self,
        bronze_root: Path,
        user_agent: str = "BTCETH-Trading-OS/Phase1B.2 (Historical Acquisition)",
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        opener: urllib.request.OpenerDirector | None = None,
    ):
        self.bronze_root = Path(bronze_root).resolve()
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.opener = opener or urllib.request.build_opener()

    def _open_url(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        for attempt in range(self.max_retries):
            try:
                return self.opener.open(req, timeout=self.timeout_seconds)
            except urllib.error.HTTPError as e:
                # 404 is not retryable
                if e.code == 404:
                    raise
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(0.5 * (2**attempt))
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(0.5 * (2**attempt))

    def fetch_checksum(self, checksum_url: str, expected_archive_filename: str) -> tuple[int, str]:
        """Fetch and parse official .CHECKSUM file. Returns (http_status, 64_hex_lowercase_sha256)."""
        try:
            with self._open_url(checksum_url) as resp:
                status = resp.status if hasattr(resp, "status") else 200
                content = resp.read().decode("utf-8", errors="replace").strip()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, ""
            raise ChecksumValidationError(f"HTTP error fetching checksum from {checksum_url}: {e}") from e

        match = CHECKSUM_REGEX.match(content)
        if not match:
            raise ChecksumValidationError(
                f"Malformed checksum response from {checksum_url}: {content!r}"
            )
        sha, fname = match.groups()
        sha = sha.lower()
        fname = fname.strip()
        if fname and fname != expected_archive_filename:
            raise ChecksumValidationError(
                f"Checksum target filename mismatch: expected '{expected_archive_filename}', got '{fname}' in {checksum_url}"
            )
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
                    spec=spec.to_dict(),
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
                )
            raise ArchiveNotFoundError(f"Archive checksum missing (HTTP 404): {spec.checksum_url}")

        # 2. Check for upstream source mutation if existing receipt exists
        if receipt_path.exists():
            try:
                prev_receipt = json.loads(receipt_path.read_text())
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
                while chunk := f.read(65536):
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
                    spec=spec.to_dict(),
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
                )
                receipt_path.write_text(json.dumps(receipt.to_dict(), indent=2) + "\n")
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
                http_archive_status = resp.status if hasattr(resp, "status") else 200
                hasher = hashlib.sha256()
                bytes_downloaded = 0
                with open(part_path, "wb") as f_part:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        hasher.update(chunk)
                        bytes_downloaded += len(chunk)
                        f_part.write(chunk)
        except urllib.error.HTTPError as e:
            if part_path.exists():
                part_path.unlink()
            if e.code == 404:
                if missing_is_expected:
                    return DownloadReceipt(
                        spec=spec.to_dict(),
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
            spec=spec.to_dict(),
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
        )
        receipt_path.write_text(json.dumps(receipt.to_dict(), indent=2) + "\n")
        return receipt
