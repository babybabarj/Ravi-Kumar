"""Layer E: Intelligence Snapshot and Non-Executable Schema Validation for INTEL-1A.

Produces machine-readable descriptive state records for consumption by research analytics.
Strictly prohibits execution fields at both schema and validator levels.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Set

FORBIDDEN_EXECUTION_FIELDS: Set[str] = {
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "ENTRY",
    "EXIT",
    "ENTRY_PRICE",
    "EXIT_PRICE",
    "ORDER",
    "ORDERS",
    "ORDER_TYPE",
    "POSITION",
    "POSITION_SIZE",
    "LEVERAGE",
    "STOP_LOSS",
    "TAKE_PROFIT",
    "TARGET_PRICE",
    "SIGNAL",
    "EXECUTION_INSTRUCTION",
    "TRADE_DIRECTION",
    "EXECUTE",
}


class ExecutionFieldForbiddenError(ValueError):
    """Raised when an execution or trade signal field is detected in an intelligence snapshot."""
    pass


def assert_no_execution_fields(data: Mapping[str, Any], path: str = "") -> None:
    """Recursively validates that a dictionary contains zero executable trade directives."""
    for key, val in data.items():
        key_upper = str(key).upper()
        current_path = f"{path}.{key}" if path else str(key)
        if key_upper in FORBIDDEN_EXECUTION_FIELDS:
            raise ExecutionFieldForbiddenError(
                f"FORBIDDEN EXECUTION FIELD: '{current_path}' is prohibited in non-executable INTEL-1A schema."
            )
        # Also reject string values that represent raw execution orders
        if isinstance(val, str) and val.upper() in ("BUY", "SELL", "LONG", "SHORT", "OPEN_LONG", "OPEN_SHORT", "CLOSE_POSITION"):
            raise ExecutionFieldForbiddenError(
                f"FORBIDDEN EXECUTION VALUE: '{val}' at '{current_path}' is prohibited in non-executable INTEL-1A schema."
            )
        if isinstance(val, dict):
            assert_no_execution_fields(val, current_path)
        elif isinstance(val, list):
            for idx, item in enumerate(val):
                if isinstance(item, dict):
                    assert_no_execution_fields(item, f"{current_path}[{idx}]")


@dataclass(frozen=True)
class IntelligenceSnapshot:
    timestamp_utc: str
    asset: str
    feature_set: str
    market_quality: str
    trend_state: str
    volatility_state: str
    activity_state: str
    funding_state: str
    session_state: str
    features: Dict[str, Any]
    cross_asset_context: Dict[str, Any] = field(default_factory=dict)
    uncertainties: List[str] = field(default_factory=list)
    data_quality_reasons: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Validate schema fields
        d = asdict(self)
        assert_no_execution_fields(d)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        assert_no_execution_fields(d)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)
