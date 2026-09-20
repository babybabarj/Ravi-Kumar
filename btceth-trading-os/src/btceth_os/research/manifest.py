from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..identity.hashes import compute_logical_sha256


@dataclass(frozen=True)
class ResearchDatasetSpec:
    dataset_id: str
    instrument_id: str
    market: str
    period_key: str
    source_file_sha256: str
    silver_parquet_path: str
    rows_count: int
    start_ts_ns: int
    end_ts_ns: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchDatasetManifest:
    manifest_id: str
    dataset_version: str
    code_commit: str
    created_at_utc: str
    datasets: tuple[ResearchDatasetSpec, ...]
    dataset_logical_sha256: str
    is_ready: bool
    validation_notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "dataset_version": self.dataset_version,
            "code_commit": self.code_commit,
            "created_at_utc": self.created_at_utc,
            "dataset_logical_sha256": self.dataset_logical_sha256,
            "is_ready": self.is_ready,
            "validation_notes": list(self.validation_notes),
            "datasets": [d.to_dict() for d in self.datasets],
        }

    def write(self, path: Path | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return p

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchDatasetManifest:
        specs = tuple(
            ResearchDatasetSpec(**d) for d in data.get("datasets", [])
        )
        return cls(
            manifest_id=data["manifest_id"],
            dataset_version=data["dataset_version"],
            code_commit=data["code_commit"],
            created_at_utc=data["created_at_utc"],
            datasets=specs,
            dataset_logical_sha256=data["dataset_logical_sha256"],
            is_ready=data["is_ready"],
            validation_notes=tuple(data.get("validation_notes", [])),
        )


def build_manifest(
    datasets: list[ResearchDatasetSpec],
    *,
    dataset_version: str = "1.1.0",
    code_commit: str = "HEAD",
    validation_notes: list[str] | None = None,
) -> ResearchDatasetManifest:
    """Deterministically compile a frozen research dataset manifest with logical SHA-256."""
    notes = validation_notes or []
    # Build pairs of (record_key, payload_hash) for logical hash calculation
    pairs: list[tuple[str, str]] = []
    for d in datasets:
        key = f"{d.dataset_id}:{d.instrument_id}:{d.period_key}:{d.start_ts_ns}:{d.end_ts_ns}:{d.rows_count}"
        pairs.append((key, d.source_file_sha256))

    logical_sha256 = compute_logical_sha256(pairs) if pairs else hashlib.sha256(b"empty").hexdigest()
    manifest_id = f"MANIFEST_{logical_sha256[:16]}"
    is_ready = len(datasets) > 0 and all(d.rows_count > 0 for d in datasets)

    return ResearchDatasetManifest(
        manifest_id=manifest_id,
        dataset_version=dataset_version,
        code_commit=code_commit,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        datasets=tuple(datasets),
        dataset_logical_sha256=logical_sha256,
        is_ready=is_ready,
        validation_notes=tuple(notes),
    )
