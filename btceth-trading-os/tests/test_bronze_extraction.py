from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from btceth_os.sources.binance.bronze import (
    BronzeExtractionError,
    CorruptArchiveError,
    SafeZipExtractor,
    ZipTraversalSecurityError,
)


def create_zip(tmp_path: Path, filename: str, member_name: str, content: bytes, extra_members: dict[str, bytes] | None = None) -> Path:
    zip_path = tmp_path / filename
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, content)
        if extra_members:
            for extra_name, extra_content in extra_members.items():
                zf.writestr(extra_name, extra_content)
    return zip_path


def test_safe_zip_extraction_valid(tmp_path: Path):
    dest = tmp_path / "extracted"
    csv_bytes = b"open_time,open,high,low,close\n1700000000000,50000,51000,49000,50500\n"
    zip_file = create_zip(tmp_path, "BTCUSDT-1m-2024-01.zip", "BTCUSDT-1m-2024-01.csv", csv_bytes)

    info = SafeZipExtractor.inspect_and_extract(
        zip_file, dest, expected_payload_name="BTCUSDT-1m-2024-01.csv"
    )
    assert info.payload_filename == "BTCUSDT-1m-2024-01.csv"
    assert Path(info.payload_path).is_file()
    assert Path(info.payload_path).read_bytes() == csv_bytes
    assert info.payload_byte_size == len(csv_bytes)


def test_reject_directory_traversal_dot_dot(tmp_path: Path):
    dest = tmp_path / "extracted"
    zip_file = create_zip(tmp_path, "evil_traversal.zip", "../../../evil.csv", b"hacked")

    with pytest.raises(ZipTraversalSecurityError, match=r"Directory traversal \(\.\.\) detected"):
        SafeZipExtractor.inspect_and_extract(zip_file, dest)


def test_reject_absolute_path_member(tmp_path: Path):
    dest = tmp_path / "extracted"
    zip_file = create_zip(tmp_path, "evil_abs.zip", "/etc/passwd.csv", b"hacked")

    with pytest.raises(ZipTraversalSecurityError, match=r"Absolute path member detected"):
        SafeZipExtractor.inspect_and_extract(zip_file, dest)


def test_reject_null_byte_member(tmp_path: Path):
    dest = tmp_path / "extracted"
    zip_path = tmp_path / "evil_null.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dummy_name_123.csv", b"hacked")
    raw = buf.getvalue().replace(b"dummy_name_123.csv", b"dummy\x00name_123.csv")
    zip_path.write_bytes(raw)

    with pytest.raises(BronzeExtractionError):
        SafeZipExtractor.inspect_and_extract(zip_path, dest)


def test_reject_symlink_member(tmp_path: Path):
    dest = tmp_path / "extracted"
    zip_path = tmp_path / "evil_symlink.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zinfo = zipfile.ZipInfo("link.csv")
        # 0o120777 indicates a symlink on Unix
        zinfo.external_attr = 0o120777 << 16
        zf.writestr(zinfo, "/etc/passwd")

    with pytest.raises(ZipTraversalSecurityError, match=r"Symlink member rejected"):
        SafeZipExtractor.inspect_and_extract(zip_path, dest)


def test_reject_empty_zip(tmp_path: Path):
    dest = tmp_path / "extracted"
    empty_zip = tmp_path / "empty.zip"
    empty_zip.write_bytes(b"")

    with pytest.raises(CorruptArchiveError, match=r"empty"):
        SafeZipExtractor.inspect_and_extract(empty_zip, dest)


def test_reject_corrupt_zip(tmp_path: Path):
    dest = tmp_path / "extracted"
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"PK\x03\x04not-a-valid-zip-file-data")

    with pytest.raises(CorruptArchiveError, match=r"Invalid or corrupted ZIP"):
        SafeZipExtractor.inspect_and_extract(corrupt_zip, dest)


def test_reject_multiple_members(tmp_path: Path):
    dest = tmp_path / "extracted"
    zip_file = create_zip(
        tmp_path,
        "multi.zip",
        "BTCUSDT-1m-2024-01.csv",
        b"data",
        extra_members={"extra.csv": b"surprise"},
    )

    with pytest.raises(BronzeExtractionError, match=r"Expected exactly 1 file member"):
        SafeZipExtractor.inspect_and_extract(zip_file, dest)


def test_reject_mismatched_payload_filename(tmp_path: Path):
    dest = tmp_path / "extracted"
    zip_file = create_zip(tmp_path, "BTCUSDT.zip", "ETHUSDT-1m.csv", b"data")

    with pytest.raises(BronzeExtractionError, match=r"Payload filename mismatch"):
        SafeZipExtractor.inspect_and_extract(zip_file, dest, expected_payload_name="BTCUSDT-1m.csv")
