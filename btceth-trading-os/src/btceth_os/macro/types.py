"""
NEWS/MACRO-1A: Core dataclass types.

All data classes are immutable (frozen=True).

TRADING_CAPABILITY = ZERO — these types describe macro observations only.
They must NOT contain entry/exit signals, position sizes, or trade instructions.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class MacroDataQuality(str, enum.Enum):
    """
    Fail-closed quality states for macro data.

    GOOD              — observation is causal and complete.
    STALE             — observation is available but outside recency window.
    MISSING           — no observation available for this period.
    VINTAGE_AMBIGUOUS — multiple revisions exist; exact revision unknown for t.
    NOT_CONFIGURED    — provider credentials or configuration are absent.
    NOT_IMPLEMENTED   — provider integration not yet built.
    PROVIDER_REQUIRED — data type exists but no authorised provider is configured.
    CAUSAL_VIOLATION  — observation published_at_utc > snapshot_time_utc (blocked).
    """

    GOOD = "GOOD"
    STALE = "STALE"
    MISSING = "MISSING"
    VINTAGE_AMBIGUOUS = "VINTAGE_AMBIGUOUS"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    PROVIDER_REQUIRED = "PROVIDER_REQUIRED"
    CAUSAL_VIOLATION = "CAUSAL_VIOLATION"


class MacroAvailabilityStatus(str, enum.Enum):
    """
    Point-in-time availability verdict for a macro observation.

    AVAILABLE              — the observation is causally available at snapshot_time.
    NOT_YET_RELEASED       — the observation's published_at_utc is after snapshot_time.
    PROVIDER_NOT_CONFIGURED — no provider credentials; data could not be fetched.
    PROVIDER_NOT_IMPLEMENTED — integration not yet built for this data family.
    STALE                  — the observation is available but older than the recency limit.
    """

    AVAILABLE = "AVAILABLE"
    NOT_YET_RELEASED = "NOT_YET_RELEASED"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_NOT_IMPLEMENTED = "PROVIDER_NOT_IMPLEMENTED"
    STALE = "STALE"


class TimestampCertainty(str, enum.Enum):
    """
    Certainty of the publication timestamp.

    EXACT           — exact verified publication time (e.g. 08:30:00 US/Eastern).
                      Potentially usable for intraday historical reconstruction.
    DATE_ONLY       — only the calendar date is known; exact intraday time is unverified.
                      BLOCKED_FROM_INTRADAY_HISTORICAL_USE.
    TIME_UNCERTAIN  — release window is known but precise second/minute is uncertain.
                      BLOCKED_FROM_INTRADAY_HISTORICAL_USE.
    UNKNOWN         — publication timestamp is unknown or unverifiable.
                      BLOCKED_FROM_INTRADAY_HISTORICAL_USE.
    """

    EXACT = "EXACT"
    DATE_ONLY = "DATE_ONLY"
    TIME_UNCERTAIN = "TIME_UNCERTAIN"
    UNKNOWN = "UNKNOWN"


class AvailabilityBasis(str, enum.Enum):
    """
    Provenance basis for the availability timestamp.

    OFFICIAL_EXACT_PUBLICATION_TIME — from official releasing agency publication metadata.
    LIVE_FIRST_SEEN                — from live observation collector receipt timestamp.
    OFFICIAL_DATE_ONLY             — from official daily observation release date.
    SCHEDULE_METADATA              — from scheduled announcement metadata.
    UNKNOWN                        — unknown availability basis.
    """

    OFFICIAL_EXACT_PUBLICATION_TIME = "OFFICIAL_EXACT_PUBLICATION_TIME"
    LIVE_FIRST_SEEN = "LIVE_FIRST_SEEN"
    OFFICIAL_DATE_ONLY = "OFFICIAL_DATE_ONLY"
    SCHEDULE_METADATA = "SCHEDULE_METADATA"
    UNKNOWN = "UNKNOWN"


class EventReleaseStatus(str, enum.Enum):
    """
    Release status of a macro event as of a specific point in time.

    SCHEDULED_NOT_RELEASED — schedule is known, but actual release has not yet occurred.
    RELEASED               — release has occurred and actual value is available.
    NOT_YET_KNOWN          — event schedule was not known at snapshot time.
    TIMESTAMP_UNCERTAIN    — timestamp certainty insufficient for requested resolution.
    NOT_AVAILABLE          — data or schedule unavailable.
    """

    SCHEDULED_NOT_RELEASED = "SCHEDULED_NOT_RELEASED"
    RELEASED = "RELEASED"
    NOT_YET_KNOWN = "NOT_YET_KNOWN"
    TIMESTAMP_UNCERTAIN = "TIMESTAMP_UNCERTAIN"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class BLSVintageProvenance(str, enum.Enum):
    """
    Vintage provenance classification for official series observations (§11).

    ORIGINAL_RELEASE_PROVEN   — initial release verified with official publication timestamp.
    REVISION_RELEASE_PROVEN   — official subsequent revision verified with official release timestamp.
    LATEST_CURRENT_VALUE_ONLY — current API value; usable descriptively in current snapshot,
                                but MUST NOT be backdated into historical intraday features.
    VINTAGE_UNKNOWN           — vintage cannot be proven; blocked fail-closed.
    """

    ORIGINAL_RELEASE_PROVEN = "ORIGINAL_RELEASE_PROVEN"
    REVISION_RELEASE_PROVEN = "REVISION_RELEASE_PROVEN"
    LATEST_CURRENT_VALUE_ONLY = "LATEST_CURRENT_VALUE_ONLY"
    VINTAGE_UNKNOWN = "VINTAGE_UNKNOWN"


class BLSSourceEvidenceType(str, enum.Enum):
    """
    Explicit source evidence classification for BLS data (§25).
    Determines vintage provenance objectively from source evidence type,
    NOT from caller intent or boolean switches.

    CURRENT_BLS_API               — raw payload fetched from current BLS API v2;
                                    always defaults to LATEST_CURRENT_VALUE_ONLY.
    ARCHIVED_BLS_INITIAL_RELEASE  — independently archived original release artifact;
                                    proves ORIGINAL_RELEASE_PROVEN.
    ARCHIVED_BLS_REVISION_RELEASE — independently archived revision release artifact;
                                    proves REVISION_RELEASE_PROVEN.
    FROZEN_TEST_FIXTURE           — local test fixture for deterministic testing.
    """

    CURRENT_BLS_API = "CURRENT_BLS_API"
    ARCHIVED_BLS_INITIAL_RELEASE = "ARCHIVED_BLS_INITIAL_RELEASE"
    ARCHIVED_BLS_REVISION_RELEASE = "ARCHIVED_BLS_REVISION_RELEASE"
    FROZEN_TEST_FIXTURE = "FROZEN_TEST_FIXTURE"


class BLSArchiveType(str, enum.Enum):
    """
    Type of archived BLS release artifact (§15).
    """

    INITIAL_RELEASE = "INITIAL_RELEASE"
    REVISION_RELEASE = "REVISION_RELEASE"


class ArchivedEvidenceValidationError(ValueError):
    """
    Raised when an archived vintage evidence artifact fails structural validation (§16, §17).
    """

    pass


def validate_archived_bls_vintage_evidence(
    evidence: Any,
    target_series_id: Optional[str] = None,
    target_reference_period: Optional[str] = None,
    expected_archive_type: Optional[BLSArchiveType] = None,
) -> bool:
    """
    Validate all structural requirements for archived BLS vintage evidence (§13-§19).
    Raises ArchivedEvidenceValidationError if any requirement is not met.
    """
    if evidence is None:
        raise ArchivedEvidenceValidationError("Archived evidence must not be None.")

    val = getattr(evidence, "value", None)
    if val is None or not isinstance(val, (int, float)) or isinstance(val, bool):
        raise ArchivedEvidenceValidationError("Archived evidence value must be numeric.")
    import math

    if math.isnan(val) or math.isinf(val):
        raise ArchivedEvidenceValidationError("Archived evidence value must not be NaN or Inf.")

    series_id = getattr(evidence, "series_id", None)
    if not series_id or not isinstance(series_id, str):
        raise ArchivedEvidenceValidationError("Archived evidence series_id must be non-empty string.")
    if target_series_id is not None and series_id != target_series_id:
        raise ArchivedEvidenceValidationError(
            f"Archived evidence series_id {series_id!r} does not match target series_id {target_series_id!r}."
        )

    ref_period = getattr(evidence, "reference_period", None)
    if not ref_period or not isinstance(ref_period, str):
        raise ArchivedEvidenceValidationError("Archived evidence reference_period must be non-empty string.")
    if target_reference_period is not None and ref_period != target_reference_period:
        raise ArchivedEvidenceValidationError(
            f"Archived evidence reference_period {ref_period!r} does not match target reference_period {target_reference_period!r}."
        )

    official_url = getattr(evidence, "official_source_url", None)
    if not official_url or not isinstance(official_url, str):
        raise ArchivedEvidenceValidationError("Archived evidence official_source_url must be non-empty string.")

    # Official source URL must use https and official BLS domain (§18)
    from urllib.parse import urlparse

    parsed_url = urlparse(official_url)
    if parsed_url.scheme != "https":
        raise ArchivedEvidenceValidationError(
            f"Archived evidence URL must use https scheme; got {parsed_url.scheme!r} in {official_url!r}"
        )
    netloc = parsed_url.netloc.lower().split(":")[0]
    if not (netloc == "bls.gov" or netloc.endswith(".bls.gov")):
        raise ArchivedEvidenceValidationError(
            f"Archived evidence URL must use official BLS domain (*.bls.gov); got {official_url!r}"
        )

    # Source raw sha256: exactly 64 lowercase or uppercase hex characters (§19)
    sha = getattr(evidence, "source_raw_sha256", None)
    if not sha or not isinstance(sha, str) or len(sha) != 64 or not all(c in "0123456789abcdefABCDEF" for c in sha):
        raise ArchivedEvidenceValidationError(
            f"Archived evidence source_raw_sha256 must be exactly 64 hex characters; got {sha!r}"
        )

    # Official published timestamp must be timezone-aware
    pub_utc = getattr(evidence, "official_published_at_utc", None)
    if pub_utc is None or not isinstance(pub_utc, datetime) or pub_utc.tzinfo is None:
        raise ArchivedEvidenceValidationError(
            "Archived evidence official_published_at_utc must be a timezone-aware datetime."
        )

    # Retrieved at timestamp is mandatory and must be timezone-aware (§16, §28)
    ret_utc = getattr(evidence, "retrieved_at_utc", None)
    if ret_utc is None:
        raise ArchivedEvidenceValidationError(
            "Archived evidence retrieved_at_utc is mandatory and must not be None."
        )
    if not isinstance(ret_utc, datetime) or ret_utc.tzinfo is None:
        raise ArchivedEvidenceValidationError(
            "Archived evidence retrieved_at_utc must be a timezone-aware datetime."
        )

    # Chronology validation: publication <= retrieval (§17, §28)
    pub_norm = pub_utc if pub_utc.tzinfo == timezone.utc else pub_utc.astimezone(timezone.utc)
    ret_norm = ret_utc if ret_utc.tzinfo == timezone.utc else ret_utc.astimezone(timezone.utc)
    if ret_norm < pub_norm:
        raise ArchivedEvidenceValidationError(
            f"Archived evidence retrieved_at_utc ({ret_norm.isoformat()}) cannot be "
            f"before official_published_at_utc ({pub_norm.isoformat()})."
        )

    arch_type = getattr(evidence, "archive_type", None)
    if not isinstance(arch_type, BLSArchiveType):
        try:
            arch_type = BLSArchiveType(arch_type)
        except (ValueError, TypeError):
            raise ArchivedEvidenceValidationError(
                f"Archived evidence archive_type must be a valid BLSArchiveType; got {arch_type!r}"
            )
    if expected_archive_type is not None and arch_type != expected_archive_type:
        raise ArchivedEvidenceValidationError(
            f"Archived evidence archive_type {arch_type!r} does not match expected {expected_archive_type!r}."
        )

    certainty = getattr(evidence, "timestamp_certainty", None)
    if certainty != TimestampCertainty.EXACT:
        raise ArchivedEvidenceValidationError(
            f"Archived evidence timestamp_certainty must be EXACT; got {certainty!r}"
        )

    return True


@dataclass(frozen=True)
class BLSArchivedVintageEvidence:
    """
    Mandatory structural evidence proving an archived BLS vintage (§15, §16).
    Enums alone cannot grant proven vintage status.
    """

    series_id: str
    reference_period: str
    value: float
    archive_type: BLSArchiveType
    official_source_url: str
    source_raw_sha256: str
    official_published_at_utc: datetime
    retrieved_at_utc: datetime
    timestamp_certainty: TimestampCertainty = TimestampCertainty.EXACT
    revision_number: int = 0
    revision_label: Optional[str] = None
    raw_fragment_hash: Optional[str] = None

    def __post_init__(self) -> None:
        validate_archived_bls_vintage_evidence(self)


def is_verified_historical_bls_vintage(v: Any) -> bool:
    """
    Canonical proof predicate for BLS historical intraday research usability (§8, §9, §21).
    True requires ALL:
    1. vintage_provenance in (ORIGINAL_RELEASE_PROVEN, REVISION_RELEASE_PROVEN)
    2. source_evidence_type is matching ARCHIVED_BLS_* type
    3. archived_evidence is not None and validates successfully
    4. timestamp_certainty == TimestampCertainty.EXACT
    5. available_at_utc is not None
    FROZEN_TEST_FIXTURE, CURRENT_BLS_API, and VINTAGE_UNKNOWN are strictly FALSE.
    """
    if v is None:
        return False
    src_type = getattr(v, "source_evidence_type", None)
    if src_type not in (
        BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE,
        BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE,
    ):
        return False
    prov = getattr(v, "vintage_provenance", None)
    if prov not in (
        BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN,
        BLSVintageProvenance.REVISION_RELEASE_PROVEN,
    ):
        return False
    arch_ev = getattr(v, "archived_evidence", None)
    if arch_ev is None:
        return False
    try:
        validate_archived_bls_vintage_evidence(arch_ev)
    except Exception:
        return False
    if getattr(v, "timestamp_certainty", None) != TimestampCertainty.EXACT:
        return False
    if getattr(v, "available_at_utc", None) is None:
        return False
    return True


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MacroEvent:
    """
    A single official macro data release or scheduled event.

    Separates scheduled event metadata from released actual values.
    Upcoming scheduled events can exist prior to release with actual_value=None.

    Parameters
    ----------
    event_id:
        Unique identifier, e.g. "CPI_US_MONTHLY_2026_09".
    event_family:
        Logical grouping, e.g. "CPI", "NFP", "FOMC".
    event_name:
        Human-readable label / title.
    reference_period:
        The period the data describes (ISO 8601 date string, e.g. "2026-09").
    source_id:
        Official releasing agency or provider ID, e.g. "BLS", "BEA", "FOMC".
    source_type:
        Origin type, e.g. "OFFICIAL_AGENCY", "CENTRAL_BANK".
    source_reference:
        Canonical URL or official publication title.
    source_hash:
        SHA-256 digest of the source announcement/table if available.
    scheduled_at_utc:
        The time the release was scheduled in advance (if known).
    schedule_known_at_utc:
        The time at which the release schedule itself became publicly known.
    official_published_at_utc:
        The time the release actually became public according to official agency.
    first_seen_at_utc:
        The time our system first ingested or received the release.
    available_at_utc:
        Causal point-in-time availability timestamp for actual_value.
    actual_value:
        The headline value as officially reported (None before release).
    previous_value:
        The previously reported value for the preceding period.
    revised_previous_value:
        The revised value for the preceding period reported concurrently.
    consensus_value:
        Analyst consensus estimate. MUST be None if no authorised provider
        supplies it — do not scrape, infer, or backfill.
    consensus_status:
        Describes consensus availability ("NOT_AVAILABLE" if none).
    revision_number:
        0 for initial release, 1+ for subsequent revisions.
    vintage_id:
        Identifier of the vintage if applicable.
    unit:
        Unit string, e.g. "index_1982_84_100", "percent_yoy", "thousands_jobs".
    timestamp_certainty:
        Certainty of release timing (EXACT, DATE_ONLY, etc.).
    availability_basis:
        Basis for available_at_utc (OFFICIAL_EXACT, LIVE_FIRST_SEEN, etc.).
    data_quality_status:
        Quality state (GOOD, STALE, etc.).
    """

    event_id: str
    event_family: str = ""
    event_name: str = ""
    reference_period: str = ""
    source_id: str = ""
    source_type: str = "OFFICIAL_AGENCY"
    source_reference: str = ""
    source_hash: Optional[str] = None
    scheduled_at_utc: Optional[datetime] = None
    schedule_known_at_utc: Optional[datetime] = None
    official_published_at_utc: Optional[datetime] = None
    first_seen_at_utc: Optional[datetime] = None
    available_at_utc: Optional[datetime] = None
    actual_value: Optional[float] = None
    previous_value: Optional[float] = None
    revised_previous_value: Optional[float] = None
    consensus_value: Optional[float] = None
    consensus_status: str = "NOT_AVAILABLE"
    revision_number: int = 0
    vintage_id: Optional[str] = None
    unit: str = ""
    timestamp_certainty: TimestampCertainty = TimestampCertainty.UNKNOWN
    availability_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    data_quality_status: MacroDataQuality = MacroDataQuality.GOOD

    # Legacy backward compatibility parameters
    family: Optional[str] = None
    description: Optional[str] = None
    source_agency: Optional[str] = None
    actual_release_utc: Optional[datetime] = None
    scheduled_release_utc: Optional[datetime] = None
    prior_value: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("MacroEvent.event_id must not be empty.")

        # Reconcile family / event_family
        eff_family = self.event_family or self.family or ""
        if not eff_family:
            raise ValueError("MacroEvent.event_family / family must not be empty.")
        object.__setattr__(self, "event_family", eff_family)
        object.__setattr__(self, "family", eff_family)

        # Reconcile source_id / source_agency
        eff_source = self.source_id or self.source_agency or ""
        if not eff_source:
            raise ValueError("MacroEvent.source_id / source_agency must not be empty.")
        object.__setattr__(self, "source_id", eff_source)
        object.__setattr__(self, "source_agency", eff_source)

        # Reconcile description / event_name
        eff_name = self.event_name or self.description or ""
        object.__setattr__(self, "event_name", eff_name)
        object.__setattr__(self, "description", eff_name)

        # Reconcile prior_value / previous_value
        eff_prev = self.previous_value if self.previous_value is not None else self.prior_value
        object.__setattr__(self, "previous_value", eff_prev)
        object.__setattr__(self, "prior_value", eff_prev)

        # Reconcile scheduled release
        eff_sched = self.scheduled_at_utc or self.scheduled_release_utc
        object.__setattr__(self, "scheduled_at_utc", eff_sched)
        object.__setattr__(self, "scheduled_release_utc", eff_sched)

        # Reconcile actual / official release / available_at
        eff_avail = self.available_at_utc or self.official_published_at_utc or self.actual_release_utc
        object.__setattr__(self, "available_at_utc", eff_avail)
        object.__setattr__(self, "official_published_at_utc", self.official_published_at_utc or eff_avail)
        object.__setattr__(self, "actual_release_utc", eff_avail)

    @property
    def status(self) -> EventReleaseStatus:
        if self.actual_value is not None:
            return EventReleaseStatus.RELEASED
        if self.scheduled_at_utc is not None:
            return EventReleaseStatus.SCHEDULED_NOT_RELEASED
        return EventReleaseStatus.NOT_AVAILABLE


@dataclass(frozen=True)
class MacroVintage:
    """
    A single revision of a macro series value with point-in-time provenance.

    Parameters
    ----------
    vintage_id:
        Unique identifier for this vintage revision.
    value:
        The numeric value as published in this vintage.
    official_published_at_utc:
        The UTC datetime when the official agency published this vintage.
    first_seen_at_utc:
        The UTC datetime when our system first ingested this vintage.
    available_at_utc:
        The point-in-time causal availability timestamp for this vintage.
    timestamp_certainty:
        Precision/certainty of the availability timestamp.
    availability_basis:
        Provenance basis (OFFICIAL_EXACT, LIVE_FIRST_SEEN, etc.).
    source_id:
        Releasing provider or agency identifier.
    source_reference:
        Canonical URL or source table reference.
    source_hash:
        SHA-256 digest of the source response if recorded.
    revision_number:
        0 for initial publication, 1 for first revision, etc.
    revision_label:
        Human-readable revision label (e.g. "advance", "preliminary", "final").
    """

    value: float
    vintage_id: str = ""
    official_published_at_utc: Optional[datetime] = None
    first_seen_at_utc: Optional[datetime] = None
    available_at_utc: Optional[datetime] = None
    timestamp_certainty: TimestampCertainty = TimestampCertainty.EXACT
    availability_basis: AvailabilityBasis = AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME
    source_id: str = ""
    source_reference: str = ""
    source_hash: Optional[str] = None
    revision_number: int = 0
    revision_label: Optional[str] = None
    vintage_provenance: Optional[BLSVintageProvenance] = None
    source_evidence_type: Optional[BLSSourceEvidenceType] = None
    archived_evidence: Optional[BLSArchivedVintageEvidence] = None

    # Legacy backward compatibility parameters
    published_at_utc: Optional[datetime] = None
    vintage_label: Optional[str] = None

    def __post_init__(self) -> None:
        eff_lbl = self.revision_label or self.vintage_label
        object.__setattr__(self, "revision_label", eff_lbl)
        object.__setattr__(self, "vintage_label", eff_lbl)

        # Section 5, 6, 7, 22, 23: Direct provenance bypass prevention
        if self.vintage_provenance == BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN:
            if (
                self.source_evidence_type != BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE
                or self.archived_evidence is None
            ):
                raise ArchivedEvidenceValidationError(
                    "Direct ORIGINAL_RELEASE_PROVEN without validated ARCHIVED_BLS_INITIAL_RELEASE "
                    "evidence is strictly forbidden."
                )
            validate_archived_bls_vintage_evidence(self.archived_evidence)
            if self.archived_evidence.archive_type != BLSArchiveType.INITIAL_RELEASE:
                raise ArchivedEvidenceValidationError(
                    "ARCHIVED_BLS_INITIAL_RELEASE requires archive_type=INITIAL_RELEASE"
                )

        elif self.vintage_provenance == BLSVintageProvenance.REVISION_RELEASE_PROVEN:
            if (
                self.source_evidence_type != BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE
                or self.archived_evidence is None
            ):
                raise ArchivedEvidenceValidationError(
                    "Direct REVISION_RELEASE_PROVEN without validated ARCHIVED_BLS_REVISION_RELEASE "
                    "evidence is strictly forbidden."
                )
            validate_archived_bls_vintage_evidence(self.archived_evidence)
            if self.archived_evidence.archive_type != BLSArchiveType.REVISION_RELEASE:
                raise ArchivedEvidenceValidationError(
                    "ARCHIVED_BLS_REVISION_RELEASE requires archive_type=REVISION_RELEASE"
                )

        # Frozen test fixture safety (§9, §24)
        if self.source_evidence_type == BLSSourceEvidenceType.FROZEN_TEST_FIXTURE:
            object.__setattr__(self, "vintage_provenance", BLSVintageProvenance.VINTAGE_UNKNOWN)

        # Section 12, 13, 14: CURRENT_BLS_API causal availability
        elif self.source_evidence_type == BLSSourceEvidenceType.CURRENT_BLS_API:
            # Descriptive metadata can preserve reference scheduled release date if provided
            eff_pub = self.official_published_at_utc or self.published_at_utc
            object.__setattr__(self, "official_published_at_utc", eff_pub)
            object.__setattr__(self, "published_at_utc", eff_pub)

            # Causal availability MUST strictly equal first_seen_at_utc (§12)
            eff_first_seen = self.first_seen_at_utc
            if eff_first_seen is None:
                eff_first_seen = self.available_at_utc or datetime.now(timezone.utc)
            if eff_first_seen.tzinfo is None:
                eff_first_seen = eff_first_seen.replace(tzinfo=timezone.utc)

            object.__setattr__(self, "first_seen_at_utc", eff_first_seen)
            object.__setattr__(self, "available_at_utc", eff_first_seen)
            object.__setattr__(self, "availability_basis", AvailabilityBasis.LIVE_FIRST_SEEN)
            object.__setattr__(self, "vintage_provenance", BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY)

        # Section 15, 16, 17, 18, 19, 20: Archived vintage proof enforcement
        elif self.source_evidence_type in (
            BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE,
            BLSSourceEvidenceType.ARCHIVED_BLS_REVISION_RELEASE,
        ):
            if self.archived_evidence is None:
                raise ArchivedEvidenceValidationError(
                    f"source_evidence_type {self.source_evidence_type.value} requires "
                    "validated BLSArchivedVintageEvidence object; enum alone is forbidden."
                )
            validate_archived_bls_vintage_evidence(self.archived_evidence)

            # Section 20: value must strictly come from archived evidence, not current API
            object.__setattr__(self, "value", float(self.archived_evidence.value))
            object.__setattr__(self, "official_published_at_utc", self.archived_evidence.official_published_at_utc)
            object.__setattr__(self, "available_at_utc", self.archived_evidence.official_published_at_utc)
            object.__setattr__(self, "published_at_utc", self.archived_evidence.official_published_at_utc)
            object.__setattr__(self, "timestamp_certainty", self.archived_evidence.timestamp_certainty)
            object.__setattr__(self, "availability_basis", AvailabilityBasis.OFFICIAL_EXACT_PUBLICATION_TIME)
            object.__setattr__(self, "source_hash", self.archived_evidence.source_raw_sha256)
            object.__setattr__(self, "source_reference", self.archived_evidence.official_source_url)

            if self.source_evidence_type == BLSSourceEvidenceType.ARCHIVED_BLS_INITIAL_RELEASE:
                if self.archived_evidence.archive_type != BLSArchiveType.INITIAL_RELEASE:
                    raise ArchivedEvidenceValidationError(
                        "ARCHIVED_BLS_INITIAL_RELEASE requires archive_type=INITIAL_RELEASE"
                    )
                object.__setattr__(self, "revision_number", 0)
                object.__setattr__(self, "vintage_provenance", BLSVintageProvenance.ORIGINAL_RELEASE_PROVEN)
            else:
                if self.archived_evidence.archive_type != BLSArchiveType.REVISION_RELEASE:
                    raise ArchivedEvidenceValidationError(
                        "ARCHIVED_BLS_REVISION_RELEASE requires archive_type=REVISION_RELEASE"
                    )
                object.__setattr__(self, "revision_number", self.archived_evidence.revision_number or 1)
                object.__setattr__(self, "vintage_provenance", BLSVintageProvenance.REVISION_RELEASE_PROVEN)

        else:
            eff_pub = self.official_published_at_utc or self.available_at_utc or self.published_at_utc
            eff_avail = self.available_at_utc or eff_pub
            object.__setattr__(self, "official_published_at_utc", eff_pub)
            object.__setattr__(self, "available_at_utc", eff_avail)
            object.__setattr__(self, "published_at_utc", eff_pub or eff_avail)

    @property
    def historical_intraday_usable(self) -> bool:
        """
        Historical intraday usable requires proven vintage and EXACT timestamp certainty (§8, §9, §21).
        LATEST_CURRENT_VALUE_ONLY, VINTAGE_UNKNOWN, and FROZEN_TEST_FIXTURE are strictly FALSE.
        """
        return is_verified_historical_bls_vintage(self)


@dataclass(frozen=True)
class MacroSeriesObservation:
    """
    A point-in-time observation of a macro data series with vintage history.

    Vintage model: append-only tuple of MacroVintage instances.
    Query: max(v for v in vintages if v.available_at_utc <= snapshot_time_utc).
    Never overwrite vintages; always append new revisions.
    """

    series_id: str
    family: str
    reference_period: str
    vintages: tuple[MacroVintage, ...]
    quality: MacroDataQuality
    availability_status: MacroAvailabilityStatus
    unit: str
    source_agency: str
    staleness_seconds: Optional[float] = None
    native_semantic_type: str = "UNKNOWN"
    transformation: Optional[str] = None

    def latest_value_at(
        self,
        snapshot_time_utc: datetime,
        required_certainty: Optional[TimestampCertainty] = None,
        allow_current_value_only: bool = False,
        resolution: str = "INTRADAY",
    ) -> Optional[float]:
        """
        Return the latest value causally available at snapshot_time_utc.

        Returns None if no vintage is available at or before snapshot_time_utc
        or if timestamp certainty or vintage provenance is insufficient.
        """
        if snapshot_time_utc.tzinfo is None:
            snapshot_time_utc = snapshot_time_utc.replace(tzinfo=timezone.utc)

        eligible = []
        for v in self.vintages:
            t = v.available_at_utc or v.published_at_utc
            if t is None:
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t <= snapshot_time_utc:
                if required_certainty is not None and v.timestamp_certainty != required_certainty:
                    continue
                # Date-only safety: Pure historical DATE_ONLY observations cannot be backfilled into intraday features
                if resolution == "INTRADAY" and v.timestamp_certainty == TimestampCertainty.DATE_ONLY:
                    if v.first_seen_at_utc is not None:
                        first_seen = v.first_seen_at_utc.replace(tzinfo=timezone.utc) if v.first_seen_at_utc.tzinfo is None else v.first_seen_at_utc
                        if snapshot_time_utc < first_seen:
                            continue
                    else:
                        continue

                # Vintage safety: LATEST_CURRENT_VALUE_ONLY cannot be backdated before first_seen
                if v.vintage_provenance == BLSVintageProvenance.LATEST_CURRENT_VALUE_ONLY:
                    if not allow_current_value_only:
                        continue
                    if v.first_seen_at_utc is not None:
                        first_seen = v.first_seen_at_utc.replace(tzinfo=timezone.utc) if v.first_seen_at_utc.tzinfo is None else v.first_seen_at_utc
                        if snapshot_time_utc < first_seen:
                            continue
                    else:
                        continue
                elif v.vintage_provenance == BLSVintageProvenance.VINTAGE_UNKNOWN and resolution == "INTRADAY":
                    # Section 11: VINTAGE_UNKNOWN is blocked from intraday historical queries
                    continue
                eligible.append((t, v))

        if not eligible:
            return None
        return max(eligible, key=lambda pair: pair[0])[1].value

    def get_historical_intraday_value(
        self,
        snapshot_time_utc: datetime,
    ) -> Optional[float]:
        """
        Hard historical research firewall (§21):
        Strictly refuses LATEST_CURRENT_VALUE_ONLY and VINTAGE_UNKNOWN.
        Only returns value if vintage is ORIGINAL_RELEASE_PROVEN or REVISION_RELEASE_PROVEN
        with EXACT timestamp certainty and available_at_utc <= snapshot_time_utc.
        """
        if snapshot_time_utc.tzinfo is None:
            snapshot_time_utc = snapshot_time_utc.replace(tzinfo=timezone.utc)
        eligible = []
        for v in self.vintages:
            t = v.available_at_utc or v.official_published_at_utc
            if t is None:
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t <= snapshot_time_utc:
                if not v.historical_intraday_usable:
                    continue
                eligible.append((t, v))
        if not eligible:
            return None
        return max(eligible, key=lambda pair: pair[0])[1].value

    def get_current_descriptive_value(
        self,
        as_of_utc: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Current descriptive context (§19, §21):
        Returns latest available value if as_of_utc >= first_seen_at_utc.
        Explicitly marked non-usable for historical intraday research.
        """
        if not self.vintages:
            return None
        if as_of_utc is not None:
            if as_of_utc.tzinfo is None:
                as_of_utc = as_of_utc.replace(tzinfo=timezone.utc)
            eligible = []
            for v in self.vintages:
                fs = v.first_seen_at_utc or v.available_at_utc
                if fs is not None:
                    if fs.tzinfo is None:
                        fs = fs.replace(tzinfo=timezone.utc)
                    if as_of_utc >= fs:
                        eligible.append(v)
            if not eligible:
                return None
            return eligible[-1].value
        return self.vintages[-1].value

    def __post_init__(self) -> None:
        if not self.series_id:
            raise ValueError("MacroSeriesObservation.series_id must not be empty.")


@dataclass(frozen=True)
class MacroNewsItem:
    """
    A single official news item or policy communication.

    IMPORTANT: Does NOT carry hawkish/dovish NLP scores, sentiment ratings,
    or LLM-generated interpretations. Strictly a data foundation object.
    Placeholder or status items do NOT carry fake publication timestamps.
    """

    item_id: str
    source: str
    item_type: str
    headline: str
    quality: MacroDataQuality
    availability_status: MacroAvailabilityStatus
    url: Optional[str] = None
    official_published_at_utc: Optional[datetime] = None
    first_seen_at_utc: Optional[datetime] = None
    available_at_utc: Optional[datetime] = None
    timestamp_certainty: TimestampCertainty = TimestampCertainty.UNKNOWN
    availability_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    source_reference: Optional[str] = None
    source_hash: Optional[str] = None

    # Legacy backward compatibility parameter
    published_at_utc: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("MacroNewsItem.item_id must not be empty.")
        if not self.headline:
            raise ValueError("MacroNewsItem.headline must not be empty.")

        eff_pub = self.official_published_at_utc or self.published_at_utc
        eff_avail = self.available_at_utc or eff_pub
        object.__setattr__(self, "official_published_at_utc", eff_pub)
        object.__setattr__(self, "available_at_utc", eff_avail)
        object.__setattr__(self, "published_at_utc", eff_pub or eff_avail)


@dataclass(frozen=True)
class MacroSurprise:
    """
    Computed surprise for a macro release.

    MUST only be created when BOTH actual and consensus values are legitimately
    available from authorised providers.
    """

    event_id: str
    actual_value: float
    consensus_value: float
    surprise_magnitude: float
    surprise_direction: str
    in_line_tolerance: float

    def __post_init__(self) -> None:
        allowed = {"BEAT", "MISS", "IN_LINE"}
        if self.surprise_direction not in allowed:
            raise ValueError(
                f"surprise_direction must be one of {allowed}; "
                f"got {self.surprise_direction!r}."
            )
        expected = round(self.actual_value - self.consensus_value, 10)
        if abs(expected - self.surprise_magnitude) > 1e-8:
            raise ValueError(
                "surprise_magnitude must equal actual_value - consensus_value."
            )


@dataclass(frozen=True)
class MacroSourceConflict:
    """
    Explicit record of disagreement between primary and secondary macro data sources.

    Both values are retained to preserve evidence truth.
    """

    field: str
    primary_source: str
    primary_value: Any
    secondary_source: str
    secondary_value: Any
    detected_at_utc: datetime
    resolution_policy: str = "PRIMARY_WINS"
    resolved_display_value: Any = None
    conflict_retained: bool = True


@dataclass(frozen=True)
class MacroEventView:
    """
    Point-in-time perspective of a MacroEvent as of snapshot_time.
    """

    event_id: str
    event_family: str
    event_name: str
    reference_period: str
    status: EventReleaseStatus
    scheduled_at_utc: Optional[datetime]
    available_at_utc: Optional[datetime]
    actual_value: Optional[float]
    consensus_value: Optional[float]
    unit: str
    timestamp_certainty: TimestampCertainty
    availability_basis: AvailabilityBasis
    data_quality: MacroDataQuality


@dataclass(frozen=True)
class MacroNewsView:
    """
    Point-in-time perspective of a MacroNewsItem as of snapshot_time.
    """

    item_id: str
    source: str
    item_type: str
    headline: str
    status: EventReleaseStatus
    available_at_utc: Optional[datetime]
    url: Optional[str]
    data_quality: MacroDataQuality
