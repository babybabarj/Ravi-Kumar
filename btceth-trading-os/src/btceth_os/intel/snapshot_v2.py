"""Layer M: Intelligence Snapshot V2 and Enhanced Non-Executable Schema for INTEL-1B.

Produces enriched, machine-readable descriptive state records with:
- Formal data quality assessment & reasons
- Descriptive regime states across all dimensions
- State stability metadata (durations, transition metrics)
- Cross-asset context & clock alignment verification
- Feature availability status
- Explicit uncertainty enumerations

Inviolable Architecture Firewall:
Strictly prohibits execution fields, trade recommendations, and order directives
at both dataclass instantiation and dictionary serialization levels.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Set

from .snapshot import FORBIDDEN_EXECUTION_FIELDS, ExecutionFieldForbiddenError, assert_no_execution_fields

ADDITIONAL_FORBIDDEN_EXECUTION_FIELDS: Set[str] = {
    "TRADE",
    "EVALUATE_TRADE",
    "TAKE_TRADE",
    "GENERATE_SIGNAL",
    "ENTRY_ZONE",
    "STOP_LOSS_PRICE",
    "TAKE_PROFIT_PRICE",
    "TP1",
    "TP2",
    "RISK_REWARD",
    "TRADE_CONFIDENCE",
    "STRATEGY_RULE",
    "RECOMMENDATION",
}

ALL_FORBIDDEN_FIELDS: Set[str] = FORBIDDEN_EXECUTION_FIELDS | ADDITIONAL_FORBIDDEN_EXECUTION_FIELDS


def assert_no_execution_fields_v2(data: Mapping[str, Any], path: str = "") -> None:
    """Recursively validates that a dictionary contains zero executable trade directives under V2 rules."""
    for key, val in data.items():
        key_upper = str(key).upper()
        current_path = f"{path}.{key}" if path else str(key)
        if key_upper in ALL_FORBIDDEN_FIELDS:
            raise ExecutionFieldForbiddenError(
                f"FORBIDDEN EXECUTION FIELD: '{current_path}' is strictly prohibited in non-executable INTEL-1B schema."
            )
        # Also reject string values that represent raw execution orders
        if isinstance(val, str) and val.upper() in (
            "BUY", "SELL", "LONG", "SHORT", "OPEN_LONG", "OPEN_SHORT", "CLOSE_POSITION",
            "TAKE_PROFIT", "STOP_LOSS", "ENTRY_LONG", "ENTRY_SHORT"
        ):
            raise ExecutionFieldForbiddenError(
                f"FORBIDDEN EXECUTION VALUE: '{val}' at '{current_path}' is strictly prohibited in non-executable INTEL-1B schema."
            )
        if isinstance(val, dict):
            assert_no_execution_fields_v2(val, current_path)
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    assert_no_execution_fields_v2(item, f"{current_path}[{i}]")
                elif isinstance(item, str) and item.upper() in (
                    "BUY", "SELL", "LONG", "SHORT", "OPEN_LONG", "OPEN_SHORT"
                ):
                    raise ExecutionFieldForbiddenError(
                        f"FORBIDDEN EXECUTION VALUE: '{item}' in list at '{current_path}[{i}]'."
                    )


@dataclass(frozen=True)
class IntelligenceSnapshotV2:
    timestamp_ns: int
    asset: str
    data_quality: Dict[str, Any]
    market_state: Dict[str, Any]
    state_stability: Dict[str, Any]
    cross_asset_context: Dict[str, Any]
    feature_availability: Dict[str, Any]
    uncertainties: List[str] = field(default_factory=list)
    schema_version: str = "2.0.0"

    def __post_init__(self) -> None:
        raw_dict = asdict(self)
        assert_no_execution_fields_v2(raw_dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        assert_no_execution_fields_v2(d)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
