"""Contract Rule Epoch Registry for XAUUSDT and TradFi perpetual contracts.

Enforces:
- Historical rule epoch replay with primary-source provenance
- Explicit isolation of unknown fields (no retrospective backfilling from current snapshots)
- Cryptographic source hashing (physical and logical SHA-256)
- Monotonic chronological intervals with quarantine protection
- Separate funding_cap and funding_floor Decimals with full backwards compatibility
- Field-level provenance tracking preventing backward rule leakage
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any
import yaml


@dataclass(frozen=True)
class ContractRuleEpoch:
    epoch_id: str
    instrument_id: str
    effective_from_utc: str
    effective_to_utc: str | None
    funding_interval_seconds: int | None
    funding_interest_component: Decimal | None
    funding_cap_floor: Decimal | None
    price_index_method: str
    mark_price_method: str
    underlying_session_rules: str
    tradfi_session_rules: str
    tick_size: Decimal | None
    step_size: Decimal | None
    quantity_rules: dict[str, Any] | None
    margin_rules: dict[str, Any] | None
    source_url: str
    source_document_timestamp: str
    source_physical_sha256: str
    source_logical_sha256: str
    confidence: str
    unknown_fields: list[str] = field(default_factory=list)
    funding_cap: Decimal | None = None
    funding_floor: Decimal | None = None
    field_provenance: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Harmonize funding_cap_floor and (funding_cap, funding_floor)
        if self.funding_cap is None and self.funding_cap_floor is not None:
            object.__setattr__(self, "funding_cap", abs(self.funding_cap_floor))
        if self.funding_floor is None and self.funding_cap_floor is not None:
            object.__setattr__(self, "funding_floor", -abs(self.funding_cap_floor))
        if self.funding_cap_floor is None and self.funding_cap is not None:
            object.__setattr__(self, "funding_cap_floor", self.funding_cap)

    def is_effective_at(self, dt_utc: datetime) -> bool:
        start = datetime.fromisoformat(self.effective_from_utc).replace(tzinfo=timezone.utc)
        if dt_utc < start:
            return False
        if self.effective_to_utc is not None:
            end = datetime.fromisoformat(self.effective_to_utc).replace(tzinfo=timezone.utc)
            if dt_utc >= end:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch_id": self.epoch_id,
            "instrument_id": self.instrument_id,
            "effective_from_utc": self.effective_from_utc,
            "effective_to_utc": self.effective_to_utc,
            "funding_interval_seconds": self.funding_interval_seconds,
            "funding_interest_component": str(self.funding_interest_component) if self.funding_interest_component is not None else None,
            "funding_cap_floor": str(self.funding_cap_floor) if self.funding_cap_floor is not None else None,
            "funding_cap": str(self.funding_cap) if self.funding_cap is not None else None,
            "funding_floor": str(self.funding_floor) if self.funding_floor is not None else None,
            "price_index_method": self.price_index_method,
            "mark_price_method": self.mark_price_method,
            "underlying_session_rules": self.underlying_session_rules,
            "tradfi_session_rules": self.tradfi_session_rules,
            "tick_size": str(self.tick_size) if self.tick_size is not None else None,
            "step_size": str(self.step_size) if self.step_size is not None else None,
            "quantity_rules": self.quantity_rules,
            "margin_rules": self.margin_rules,
            "source_url": self.source_url,
            "source_document_timestamp": self.source_document_timestamp,
            "source_physical_sha256": self.source_physical_sha256,
            "source_logical_sha256": self.source_logical_sha256,
            "confidence": self.confidence,
            "unknown_fields": list(self.unknown_fields),
            "field_provenance": dict(self.field_provenance),
        }


class ContractRuleEpochRegistry:
    def __init__(self, epochs: list[ContractRuleEpoch]) -> None:
        self._epochs = sorted(
            epochs,
            key=lambda e: datetime.fromisoformat(e.effective_from_utc).replace(tzinfo=timezone.utc),
        )
        self._validate_chronology()

    @property
    def epochs(self) -> list[ContractRuleEpoch]:
        return list(self._epochs)

    def __len__(self) -> int:
        return len(self._epochs)

    def __iter__(self):
        return iter(self._epochs)

    def validate_chronology(self) -> bool:
        self._validate_chronology()
        return True

    def _validate_chronology(self) -> None:
        for i in range(len(self._epochs) - 1):
            curr = self._epochs[i]
            nxt = self._epochs[i + 1]
            if curr.effective_to_utc is None:
                raise ValueError(f"Epoch {curr.epoch_id} has no effective_to_utc but is followed by {nxt.epoch_id}")
            curr_end = datetime.fromisoformat(curr.effective_to_utc).replace(tzinfo=timezone.utc)
            nxt_start = datetime.fromisoformat(nxt.effective_from_utc).replace(tzinfo=timezone.utc)
            if curr_end != nxt_start:
                raise ValueError(
                    f"Epoch continuity gap/overlap between {curr.epoch_id} ({curr.effective_to_utc}) "
                    f"and {nxt.epoch_id} ({nxt.effective_from_utc})"
                )

    def get_epoch_for_timestamp(self, ts: str | int | float | datetime) -> ContractRuleEpoch | None:
        if isinstance(ts, (int, float)):
            if ts > 1e18:  # ns
                dt = datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
            elif ts > 1e11:  # ms
                dt = datetime.fromtimestamp(ts / 1e3, tz=timezone.utc)
            else:  # s
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str):
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        elif isinstance(ts, datetime):
            dt = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
        else:
            raise TypeError(f"Unsupported timestamp type: {type(ts)}")

        for epoch in self._epochs:
            if epoch.is_effective_at(dt):
                return epoch
        return None

    def get_epoch_by_id(self, epoch_id: str) -> ContractRuleEpoch | None:
        for epoch in self._epochs:
            if epoch.epoch_id == epoch_id:
                return epoch
        return None

    @classmethod
    def from_yaml(cls, path: Path | str) -> ContractRuleEpochRegistry:
        content = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        epochs: list[ContractRuleEpoch] = []
        for raw in data.get("epochs", []):
            epochs.append(
                ContractRuleEpoch(
                    epoch_id=raw["epoch_id"],
                    instrument_id=raw["instrument_id"],
                    effective_from_utc=raw["effective_from_utc"],
                    effective_to_utc=raw.get("effective_to_utc"),
                    funding_interval_seconds=raw.get("funding_interval_seconds"),
                    funding_interest_component=Decimal(str(raw["funding_interest_component"])) if raw.get("funding_interest_component") is not None else None,
                    funding_cap_floor=Decimal(str(raw["funding_cap_floor"])) if raw.get("funding_cap_floor") is not None else None,
                    price_index_method=raw["price_index_method"],
                    mark_price_method=raw["mark_price_method"],
                    underlying_session_rules=raw["underlying_session_rules"],
                    tradfi_session_rules=raw["tradfi_session_rules"],
                    tick_size=Decimal(str(raw["tick_size"])) if raw.get("tick_size") is not None else None,
                    step_size=Decimal(str(raw["step_size"])) if raw.get("step_size") is not None else None,
                    quantity_rules=raw.get("quantity_rules"),
                    margin_rules=raw.get("margin_rules"),
                    source_url=raw["source_url"],
                    source_document_timestamp=raw["source_document_timestamp"],
                    source_physical_sha256=raw["source_physical_sha256"],
                    source_logical_sha256=raw["source_logical_sha256"],
                    confidence=raw["confidence"],
                    unknown_fields=list(raw.get("unknown_fields", [])),
                    funding_cap=Decimal(str(raw["funding_cap"])) if raw.get("funding_cap") is not None else None,
                    funding_floor=Decimal(str(raw["funding_floor"])) if raw.get("funding_floor") is not None else None,
                    field_provenance=dict(raw.get("field_provenance", {})),
                )
            )
        return cls(epochs)
