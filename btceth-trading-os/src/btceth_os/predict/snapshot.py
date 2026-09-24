"""Predictive Research Snapshot and Output Firewall for PRED-1A.

Provides:
  1. PredictiveResearchSnapshot schema for non-executable research predictions.
  2. Prediction output firewall: recursively rejects any execution, trade direction,
     order sizing, or stop/target semantics.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Sequence


FORBIDDEN_EXECUTION_TOKENS = {
    "BUY", "SELL", "LONG", "SHORT", "ENTRY", "EXIT", "STOP",
    "TAKE_PROFIT", "POSITION_SIZE", "LEVERAGE", "ORDER", "TRADE",
    "SL", "TP", "R:R", "POSITION", "SIGNAL",
}


class ExecutionFieldForbiddenError(ValueError):
    """Raised when an execution or trade action field is detected in predictive outputs."""
    pass


ExecutionLeakageError = ExecutionFieldForbiddenError


def assert_no_execution_fields_predictive(payload: Any, path: str = "root") -> None:
    """Recursively validates that payload contains no trade execution directives."""
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            k_clean = str(k).upper().strip()
            # Normalize punctuation
            k_norm = re.sub(r"[^A-Z0-9]", "_", k_clean)
            tokens = set(filter(None, k_norm.split("_")))

            for tok in FORBIDDEN_EXECUTION_TOKENS:
                if tok in tokens or k_clean == tok:
                    raise ExecutionFieldForbiddenError(
                        f"FIREWALL VIOLATION: Forbidden execution key '{k}' found at {path}.{k}"
                    )
            if k_clean in ("TARGET", "PRICE_TARGET", "PROFIT_TARGET", "TARGET_PRICE"):
                raise ExecutionFieldForbiddenError(
                    f"FIREWALL VIOLATION: Forbidden trade target key '{k}' found at {path}.{k}"
                )

            assert_no_execution_fields_predictive(v, f"{path}.{k}")

    elif isinstance(payload, (list, tuple, set)):
        for idx, item in enumerate(payload):
            if isinstance(item, str):
                item_clean = item.upper().strip()
                item_norm = re.sub(r"[^A-Z0-9]", "_", item_clean)
                tokens = set(filter(None, item_norm.split("_")))
                for tok in FORBIDDEN_EXECUTION_TOKENS:
                    if tok in tokens or item_clean == tok:
                        raise ExecutionFieldForbiddenError(
                            f"FIREWALL VIOLATION: Forbidden execution value '{item}' found at {path}[{idx}]"
                        )
                if item_clean in ("TARGET", "PRICE_TARGET", "PROFIT_TARGET", "TARGET_PRICE"):
                    raise ExecutionFieldForbiddenError(
                        f"FIREWALL VIOLATION: Forbidden trade target value '{item}' found at {path}[{idx}]"
                    )
            assert_no_execution_fields_predictive(item, f"{path}[{idx}]")

    elif isinstance(payload, str):
        p_clean = payload.upper().strip()
        p_norm = re.sub(r"[^A-Z0-9]", "_", p_clean)
        tokens = set(filter(None, p_norm.split("_")))
        for tok in FORBIDDEN_EXECUTION_TOKENS:
            if tok in tokens or p_clean == tok:
                raise ExecutionFieldForbiddenError(
                    f"FIREWALL VIOLATION: Forbidden execution string value '{payload}' found at {path}"
                )
        if p_clean in ("TARGET", "PRICE_TARGET", "PROFIT_TARGET", "TARGET_PRICE"):
            raise ExecutionFieldForbiddenError(
                f"FIREWALL VIOLATION: Forbidden trade target string value '{payload}' found at {path}"
            )


@dataclass(frozen=True)
class PredictiveResearchSnapshot:
    asset: str
    timestamp_utc: str
    model_id: str
    target_id: str
    prediction: float
    prediction_units: str
    model_version: str
    feature_set_id: str
    research_only: bool = True
    uncertainties: List[str] = None

    def __post_init__(self) -> None:
        if self.uncertainties is None:
            object.__setattr__(self, "uncertainties", [])
        if not self.research_only:
            raise ValueError("research_only must be True for predictive snapshots.")
        # Firewall validation
        assert_no_execution_fields_predictive(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
