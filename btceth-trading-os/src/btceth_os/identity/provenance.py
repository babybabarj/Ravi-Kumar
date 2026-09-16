from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
from ..core import QualityState, now_ns


@dataclass(frozen=True)
class ProvenanceRecord:
    """Immutable provenance record connecting a canonical partition to exact RAW upstream evidence."""

    source: str
    source_dataset: str
    source_object_id: str
    source_filename: str
    source_physical_sha256: str
    retrieved_at_ns: int
    parser_version: str
    schema_version: str
    build_version: str
    quality_status: QualityState = QualityState.VALID

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("source cannot be empty")
        if not self.source_dataset:
            raise ValueError("source_dataset cannot be empty")
        if not self.source_filename:
            raise ValueError("source_filename cannot be empty")
        if len(self.source_physical_sha256) != 64:
            raise ValueError(f"invalid SHA-256 digest length: {self.source_physical_sha256}")
        if not isinstance(self.quality_status, QualityState):
            raise TypeError(f"quality_status must be a QualityState enum, got {type(self.quality_status)}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quality_status"] = self.quality_status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceRecord:
        d = data.copy()
        if isinstance(d.get("quality_status"), str):
            d["quality_status"] = QualityState(d["quality_status"])
        return cls(**d)
