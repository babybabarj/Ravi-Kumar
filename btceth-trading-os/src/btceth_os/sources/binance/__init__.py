"""Binance official historical archive discovery, path definitions, and request planning.
"""
from __future__ import annotations

from .models import ArchiveObjectSpec, DiscoveryEvidence
from .archive_paths import build_archive_paths, BinancePathError
from .archive_planner import plan_archive_requests
from .archive_downloader import (
    ArchiveChecksumError,
    ArchiveDownloadError,
    ArchiveDownloadResult,
    ArchiveDownloader,
    ArchiveObjectMissing,
    ArchiveTransportError,
    ArchiveZipIntegrityError,
)
from .archive_catalog import ArchiveCatalog, ArchiveCatalogWrite

__all__ = [
    "ArchiveObjectSpec",
    "DiscoveryEvidence",
    "build_archive_paths",
    "BinancePathError",
    "plan_archive_requests",
    "ArchiveChecksumError",
    "ArchiveDownloadError",
    "ArchiveDownloadResult",
    "ArchiveDownloader",
    "ArchiveObjectMissing",
    "ArchiveTransportError",
    "ArchiveZipIntegrityError",
    "ArchiveCatalog",
    "ArchiveCatalogWrite",
]
