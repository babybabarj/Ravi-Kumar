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
from .archive_parser import ArchiveSchemaError, BronzeRecord, iter_bronze_records
from .historical_silver import SilverBuildError, write_historical_silver
from .bronze import SafeZipExtractor, BronzeExtractionError, ZipTraversalSecurityError, CorruptArchiveError
from .schema_inspector import SchemaInspector, FundingRateRecord, QualityProbeResult, FundingParserCatastrophicError
from .funding_parity import FundingParityAuditor, FundingParityReport
from .timestamp_audit import TimestampPolicyAuditor, TimestampPolicyVerificationResult

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
    "ArchiveSchemaError",
    "BronzeRecord",
    "iter_bronze_records",
    "SilverBuildError",
    "write_historical_silver",
    "BinanceCredentials",
    "BinanceReadOnlyClient",
    "BinanceReadOnlyError",
    "BinanceAccountSnapshot",
    "read_spot_account",
    "read_usdm_account",
    "SafeZipExtractor",
    "BronzeExtractionError",
    "ZipTraversalSecurityError",
    "CorruptArchiveError",
    "SchemaInspector",
    "FundingRateRecord",
    "QualityProbeResult",
    "FundingParserCatastrophicError",
    "FundingParityAuditor",
    "FundingParityReport",
    "TimestampPolicyAuditor",
    "TimestampPolicyVerificationResult",
]
