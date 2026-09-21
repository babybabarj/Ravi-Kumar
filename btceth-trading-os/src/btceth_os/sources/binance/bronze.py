from __future__ import annotations

import hashlib
import os
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class BronzeExtractionError(RuntimeError):
    """Raised when an archive fails safe extraction or security validation."""
    pass


class ZipTraversalSecurityError(BronzeExtractionError):
    """Raised when an archive member attempts directory traversal (e.g., ../, absolute path, symlink)."""
    pass


class CorruptArchiveError(BronzeExtractionError):
    """Raised when a ZIP archive is corrupted, truncated, or invalid."""
    pass


@dataclass(frozen=True)
class ExtractedPayloadInfo:
    payload_filename: str
    payload_path: str
    payload_byte_size: int
    payload_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SafeZipExtractor:
    """Production-grade safe ZIP extraction preventing Zip Slip, symlinks, and archive corruption."""

    @staticmethod
    def inspect_and_extract(
        zip_path: Path,
        destination_dir: Path,
        expected_payload_name: str | None = None,
    ) -> ExtractedPayloadInfo:
        zip_path = Path(zip_path)
        destination_dir = Path(destination_dir).resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)

        if not zip_path.is_file():
            raise FileNotFoundError(f"ZIP file does not exist: {zip_path}")
        if zip_path.stat().st_size == 0:
            raise CorruptArchiveError(f"ZIP file is empty (0 bytes): {zip_path}")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Test archive integrity
                bad_file = zf.testzip()
                if bad_file is not None:
                    raise CorruptArchiveError(f"ZIP archive CRC check failed on member: {bad_file}")

                infolist = zf.infolist()
                if not infolist:
                    raise CorruptArchiveError(f"ZIP archive contains zero members: {zip_path}")

                # Reject multi-member archives if they contain unexpected non-CSV files
                csv_members = [m for m in infolist if not m.is_dir()]
                if len(csv_members) != 1:
                    raise BronzeExtractionError(
                        f"Expected exactly 1 file member in archive, found {len(csv_members)}: {[m.filename for m in csv_members]}"
                    )

                member = csv_members[0]
                member_name = member.filename

                # 1. Path traversal checks (../, ..\, leading slash, drive letters, null bytes)
                if "\x00" in member_name:
                    raise ZipTraversalSecurityError(f"Null byte detected in member filename: {member_name!r}")
                if member_name.startswith("/") or member_name.startswith("\\"):
                    raise ZipTraversalSecurityError(f"Absolute path member detected: {member_name}")
                if ".." in member_name.replace("\\", "/").split("/"):
                    raise ZipTraversalSecurityError(f"Directory traversal (..) detected in member: {member_name}")
                if ":" in member_name:
                    raise ZipTraversalSecurityError(f"Drive letter or stream separator detected in member: {member_name}")

                # 2. Symlink detection (Unix mode 0o120000)
                unix_mode = member.external_attr >> 16
                if (unix_mode & 0o170000) == 0o120000:
                    raise ZipTraversalSecurityError(f"Symlink member rejected: {member_name}")

                # 3. Payload filename validation
                norm_filename = Path(member_name).name
                if not norm_filename.endswith(".csv"):
                    raise BronzeExtractionError(f"Expected .csv member, found: {norm_filename}")

                if expected_payload_name is not None and norm_filename != expected_payload_name:
                    raise BronzeExtractionError(
                        f"Payload filename mismatch: expected '{expected_payload_name}', found '{norm_filename}'"
                    )

                # 4. Canonical extraction target path containment
                target_path = (destination_dir / norm_filename).resolve()
                try:
                    common = os.path.commonpath([str(destination_dir), str(target_path)])
                except ValueError:
                    raise ZipTraversalSecurityError(f"Path outside extraction destination: {target_path}")
                if common != str(destination_dir):
                    raise ZipTraversalSecurityError(f"Path outside extraction destination: {target_path}")

                # 5. Safe streaming extraction and hashing
                hasher = hashlib.sha256()
                byte_count = 0
                temp_extract_path = destination_dir / f"{norm_filename}.extract.part"
                try:
                    with zf.open(member, "r") as src, open(temp_extract_path, "wb") as dst:
                        while True:
                            chunk = src.read(65536)
                            if not chunk:
                                break
                            hasher.update(chunk)
                            byte_count += len(chunk)
                            dst.write(chunk)
                    os.replace(temp_extract_path, target_path)
                finally:
                    if temp_extract_path.exists():
                        temp_extract_path.unlink()

                return ExtractedPayloadInfo(
                    payload_filename=norm_filename,
                    payload_path=str(target_path),
                    payload_byte_size=byte_count,
                    payload_sha256=hasher.hexdigest(),
                )

        except zipfile.BadZipFile as e:
            raise CorruptArchiveError(f"Invalid or corrupted ZIP file {zip_path}: {e}") from e
