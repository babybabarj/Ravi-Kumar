from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .archive_downloader import ArchiveDownloadResult


DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS archive_objects (
    source_url TEXT NOT NULL,
    physical_sha256 TEXT NOT NULL,
    source TEXT NOT NULL,
    market TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    source_dataset_name TEXT NOT NULL,
    instrument TEXT NOT NULL,
    symbol TEXT NOT NULL,
    cadence TEXT NOT NULL,
    period_key TEXT NOT NULL,
    archive_filename TEXT NOT NULL,
    local_path TEXT NOT NULL,
    official_checksum TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    PRIMARY KEY (source_url, physical_sha256)
);
CREATE TABLE IF NOT EXISTS archive_retrievals (
    source_url TEXT NOT NULL,
    physical_sha256 TEXT NOT NULL,
    retrieved_at_utc TEXT NOT NULL,
    content_length INTEGER NOT NULL,
    etag TEXT,
    last_modified TEXT,
    receipt_path TEXT NOT NULL,
    PRIMARY KEY (source_url, physical_sha256, retrieved_at_utc),
    FOREIGN KEY (source_url, physical_sha256)
        REFERENCES archive_objects(source_url, physical_sha256)
);
"""


@dataclass(frozen=True)
class ArchiveCatalogWrite:
    object_inserted: bool
    retrieval_inserted: bool
    physical_sha256: str


class ArchiveCatalog:
    """WAL-backed catalog of immutable historical RAW archive objects and receipts."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(DDL)
        self.db.commit()

    def record_download(self, result: ArchiveDownloadResult, *, quality_status: str = "VALID") -> ArchiveCatalogWrite:
        """Verify a downloader receipt and insert it without overwriting source history."""
        if result.status == "SOURCE_OBJECT_MISSING":
            raise ValueError("missing source objects cannot be catalogued as RAW evidence")
        if result.local_path is None or result.receipt_path is None:
            raise ValueError("a catalogued archive requires local bytes and a retrieval receipt")
        if result.physical_sha256 is None or result.official_checksum is None:
            raise ValueError("a catalogued archive requires physical and official checksums")
        if result.physical_sha256 != result.official_checksum:
            raise ValueError("physical SHA-256 does not match the official checksum")

        object_path = Path(result.local_path)
        receipt_path = Path(result.receipt_path)
        if not object_path.is_file() or not receipt_path.is_file():
            raise FileNotFoundError("archive bytes or receipt are missing")
        if _file_sha256(object_path) != result.physical_sha256:
            raise ValueError("local archive bytes do not match the claimed physical SHA-256")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("physical_sha256") != result.physical_sha256:
            raise ValueError("receipt physical SHA-256 does not match the archive result")
        if receipt.get("official_checksum") != result.official_checksum:
            raise ValueError("receipt official checksum does not match the archive result")

        spec = result.spec
        with self.db:
            object_cursor = self.db.execute(
                """
                INSERT OR IGNORE INTO archive_objects(
                    source_url,physical_sha256,source,market,dataset_id,source_dataset_name,
                    instrument,symbol,cadence,period_key,archive_filename,local_path,
                    official_checksum,quality_status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    spec.archive_url,
                    result.physical_sha256,
                    spec.source,
                    spec.market,
                    spec.dataset_id,
                    spec.source_dataset_name,
                    spec.instrument,
                    spec.symbol,
                    spec.cadence,
                    spec.period_key,
                    spec.archive_filename,
                    str(object_path),
                    result.official_checksum,
                    quality_status,
                ),
            )
            retrieval_cursor = self.db.execute(
                """
                INSERT OR IGNORE INTO archive_retrievals(
                    source_url,physical_sha256,retrieved_at_utc,content_length,etag,last_modified,receipt_path
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    spec.archive_url,
                    result.physical_sha256,
                    str(receipt.get("retrieved_at_utc", result.retrieved_at_utc)),
                    int(receipt.get("content_length", object_path.stat().st_size)),
                    receipt.get("etag"),
                    receipt.get("last_modified"),
                    str(receipt_path),
                ),
            )
        return ArchiveCatalogWrite(
            object_inserted=object_cursor.rowcount == 1,
            retrieval_inserted=retrieval_cursor.rowcount == 1,
            physical_sha256=result.physical_sha256,
        )

    def objects(self) -> list[dict[str, Any]]:
        columns = [description[0] for description in self.db.execute("SELECT * FROM archive_objects LIMIT 0").description]
        rows = self.db.execute(
            "SELECT * FROM archive_objects ORDER BY source,market,dataset_id,instrument,period_key,physical_sha256"
        ).fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def object_count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM archive_objects").fetchone()[0])

    def journal_mode(self) -> str:
        return str(self.db.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def close(self) -> None:
        self.db.close()


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
