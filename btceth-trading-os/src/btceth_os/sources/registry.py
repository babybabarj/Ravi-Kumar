from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml
from ..instruments import SUPPORTED_INSTRUMENT_IDS

CANONICAL_INSTRUMENTS = SUPPORTED_INSTRUMENT_IDS


def validate_canonical_instrument(instrument_id: str) -> bool:
    """Validate the explicit supported instrument universe."""
    return instrument_id in CANONICAL_INSTRUMENTS


@dataclass(frozen=True)
class DatasetDefinition:
    dataset_id: str
    source: str
    market: str
    instrument: str
    source_dataset_name: str
    frequency: str
    raw_format: str
    expected_time_unit: str
    archive_support_status: str
    daily_support: str | bool | None
    monthly_support: str | bool | None
    checksum_support: str | bool | None
    canonical_schema_version: str
    rest_support: str | bool | None = "NOT_APPLICABLE"
    source_timestamp_policy: dict[str, Any] = field(default_factory=dict)
    quality_rules: list[str] = field(default_factory=list)
    retention_notes: str = ""

    def __post_init__(self) -> None:
        if not validate_canonical_instrument(self.instrument):
            raise ValueError(f"Unknown or non-canonical instrument: {self.instrument}")


def load_historical_datasets_registry(config_path: Path | str | None = None) -> list[DatasetDefinition]:
    """Load and parse the machine-readable historical datasets registry YAML."""
    if config_path is None:
        # Default relative to repository root
        root = Path(__file__).resolve().parents[3]
        config_path = root / "config" / "historical_datasets.yaml"
    p = Path(config_path)
    if not p.is_file():
        raise FileNotFoundError(f"Historical dataset registry not found at: {p}")
    raw_yaml = yaml.safe_load(p.read_text(encoding="utf-8"))
    datasets_raw = raw_yaml.get("datasets", [])
    out: list[DatasetDefinition] = []
    for d in datasets_raw:
        out.append(
            DatasetDefinition(
                dataset_id=d["dataset_id"],
                source=d["source"],
                market=d["market"],
                instrument=d["instrument"],
                source_dataset_name=d["source_dataset_name"],
                frequency=d.get("frequency", ""),
                raw_format=d.get("raw_format", "csv.zip"),
                expected_time_unit=d.get("expected_time_unit", "ms"),
                archive_support_status=d.get("archive_support_status", "UNVERIFIED_SOURCE_PATH"),
                daily_support=d.get("daily_support", "UNVERIFIED"),
                monthly_support=d.get("monthly_support", "UNVERIFIED"),
                checksum_support=d.get("checksum_support", "UNVERIFIED"),
                rest_support=d.get("rest_support", "NOT_APPLICABLE"),
                canonical_schema_version=str(d.get("canonical_schema_version", "1.0.0")),
                source_timestamp_policy=dict(d.get("source_timestamp_policy", {})),
                quality_rules=list(d.get("quality_rules", [])),
                retention_notes=str(d.get("retention_notes", "")),
            )
        )
    return out
