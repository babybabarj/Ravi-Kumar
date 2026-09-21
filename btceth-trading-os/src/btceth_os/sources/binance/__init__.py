"""Binance official historical archive discovery, path definitions, and request planning.
"""
from __future__ import annotations

from .models import ArchiveObjectSpec, DiscoveryEvidence
from .archive_paths import build_archive_paths, BinancePathError
from .archive_planner import plan_archive_requests
from .bronze import SafeZipExtractor, BronzeExtractionError, ZipTraversalSecurityError, CorruptArchiveError
from .archive_downloader import ArchiveDownloader, DownloadReceipt, ArchiveDownloaderError, ChecksumValidationError, SourceMutationDetectedError
from .schema_inspector import SchemaInspector, FundingRateRecord, QualityProbeResult, FundingParserCatastrophicError
from .funding_parity import FundingParityAuditor, FundingParityReport
from .timestamp_audit import TimestampPolicyAuditor, TimestampPolicyVerificationResult

__all__ = [
    "ArchiveObjectSpec",
    "DiscoveryEvidence",
    "build_archive_paths",
    "BinancePathError",
    "plan_archive_requests",
    "SafeZipExtractor",
    "BronzeExtractionError",
    "ZipTraversalSecurityError",
    "CorruptArchiveError",
    "ArchiveDownloader",
    "DownloadReceipt",
    "ArchiveDownloaderError",
    "ChecksumValidationError",
    "SourceMutationDetectedError",
    "SchemaInspector",
    "FundingRateRecord",
    "QualityProbeResult",
    "FundingParserCatastrophicError",
    "FundingParityAuditor",
    "FundingParityReport",
    "TimestampPolicyAuditor",
    "TimestampPolicyVerificationResult",
]
