from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

MarketKind = Literal["spot", "usdm"]
CadenceKind = Literal["monthly", "daily"]


@dataclass(frozen=True)
class ArchiveObjectSpec:
    """Canonical specification for an official historical Binance archive file object.
    Contains zero filesystem-local paths to preserve logical source identity.
    """
    source: str
    market: MarketKind
    dataset_id: str
    source_dataset_name: str
    instrument: str
    symbol: str
    cadence: CadenceKind
    interval: str | None
    period_key: str
    period_start_utc: str
    period_end_utc: str
    archive_url: str
    checksum_url: str
    archive_filename: str
    checksum_filename: str
    expected_timestamp_policy: dict[str, Any]
    support_status: str
    discovery_evidence_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as err:
            raise KeyError(key) from err

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return asdict(self).keys()

    def values(self):
        return asdict(self).values()

    def items(self):
        return asdict(self).items()


@dataclass(frozen=True)
class DiscoveryEvidence:
    """Cryptographic and HTTP metadata captured during public-network source reconnaissance."""
    evidence_id: str
    observed_at_utc: str
    source: str
    request_url: str
    request_method: str
    http_status: int
    content_length: int | None
    content_type: str | None
    etag: str | None
    last_modified: str | None
    checksum_observed: str | None
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
