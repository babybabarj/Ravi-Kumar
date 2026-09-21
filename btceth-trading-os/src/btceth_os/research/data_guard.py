from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "artifacts" / "research" / "holdout_access_ledger.jsonl"

# The Locked Historical Holdout is strictly:
# 2024-01-01 00:00:00 UTC to 2024-11-30 23:59:59 UTC
HOLDOUT_WINDOW_START_NS = 1704067200_000_000_000  # 2024-01-01T00:00:00Z
HOLDOUT_WINDOW_END_NS   = 1733011199_999_999_999  # 2024-11-30T23:59:59.999999999Z


class DatasetRole(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"                  # 2020 - 2022
    VALIDATION = "VALIDATION"                    # 2023
    LOCKED_HOLDOUT = "LOCKED_HOLDOUT"            # 2024-01-01 to 2024-11-30
    PROSPECTIVE_FORWARD = "PROSPECTIVE_FORWARD"  # 2025 onwards / prospective
    SHADOW = "SHADOW"                            # Live shadow execution
    PAPER = "PAPER"                              # Live paper execution


class ResearchOperation(str, Enum):
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    FEATURE_SELECTION = "feature_selection"
    PARAMETER_TUNING = "parameter_tuning"
    STRATEGY_SELECTION = "strategy_family_selection"
    THRESHOLD_TUNING = "threshold_tuning"
    BACKTEST = "backtest"
    PROSPECTIVE_VALIDATION = "prospective_validation"
    FINAL_HOLDOUT_AUDIT = "final_holdout_audit"  # Requires formal owner unlock


class HoldoutAccessDeniedError(PermissionError):
    """Raised when an unauthorized research operation attempts to access the locked historical holdout."""
    pass


def log_guard_event(
    operation: str,
    dataset_id: str,
    dataset_version: str,
    role: str,
    start_ns: Optional[int],
    end_ns: Optional[int],
    decision: str,  # "ALLOWED" or "BLOCKED"
    reason: str,
    research_generation: str = "ROUND3B",
) -> None:
    """Record an append-only entry in the research access ledger."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "operation": str(operation),
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "dataset_role": str(role),
        "requested_start_ns": start_ns,
        "requested_end_ns": end_ns,
        "requested_start_utc": datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc).isoformat() if start_ns else None,
        "requested_end_utc": datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc).isoformat() if end_ns else None,
        "decision": decision,
        "reason": reason,
        "research_generation": research_generation,
    }
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


class ResearchDataAccessGuard:
    """Canonical research access guard enforcing dataset roles and locked holdout boundary."""

    FORBIDDEN_RESEARCH_OPS = {
        ResearchOperation.HYPOTHESIS_GENERATION,
        ResearchOperation.FEATURE_SELECTION,
        ResearchOperation.PARAMETER_TUNING,
        ResearchOperation.STRATEGY_SELECTION,
        ResearchOperation.THRESHOLD_TUNING,
        ResearchOperation.BACKTEST,
    }

    @classmethod
    def check_access(
        cls,
        operation: ResearchOperation | str,
        dataset_id: str,
        dataset_version: str = "v3.1.0",
        dataset_role: Optional[DatasetRole | str] = None,
        start_ts_ns: Optional[int] = None,
        end_ts_ns: Optional[int] = None,
        file_path: Optional[Path | str] = None,
        dataset_logical_sha: Optional[str] = None,
        research_generation: str = "ROUND3B",
    ) -> bool:
        op_enum = ResearchOperation(operation) if isinstance(operation, str) else operation

        # 1. Inspect file metadata if path is provided
        detected_role = DatasetRole(dataset_role) if dataset_role else None
        p_obj = Path(file_path) if file_path else None

        # Check if file has metadata or inspect timestamp bounds directly from Parquet
        if p_obj and p_obj.is_file() and p_obj.suffix == ".parquet":
            try:
                meta = pq.read_metadata(p_obj)
                # Check custom schema metadata
                if meta.schema:
                    custom = meta.schema.to_arrow_schema().metadata or {}
                    if b"dataset_role" in custom:
                        role_str = custom[b"dataset_role"].decode("utf-8")
                        detected_role = DatasetRole(role_str)
                    if b"start_ts_ns" in custom:
                        start_ts_ns = int(custom[b"start_ts_ns"].decode("utf-8"))
                    if b"end_ts_ns" in custom:
                        end_ts_ns = int(custom[b"end_ts_ns"].decode("utf-8"))
            except Exception:
                pass

        # 2. Check if timestamps overlap with the LOCKED HISTORICAL HOLDOUT (2024-01-01 to 2024-11-30)
        overlaps_holdout = False
        if start_ts_ns is not None and end_ts_ns is not None:
            # Overlaps if start <= HOLDOUT_END and end >= HOLDOUT_START
            overlaps_holdout = (start_ts_ns <= HOLDOUT_WINDOW_END_NS) and (end_ts_ns >= HOLDOUT_WINDOW_START_NS)
        elif start_ts_ns is not None:
            overlaps_holdout = (start_ts_ns >= HOLDOUT_WINDOW_START_NS) and (start_ts_ns <= HOLDOUT_WINDOW_END_NS)
        elif end_ts_ns is not None:
            overlaps_holdout = (end_ts_ns >= HOLDOUT_WINDOW_START_NS) and (end_ts_ns <= HOLDOUT_WINDOW_END_NS)

        # Path defensive check (supplementary, not sole mechanism)
        if p_obj:
            p_name = p_obj.name.lower()
            if "holdout" in p_name:
                detected_role = DatasetRole.LOCKED_HOLDOUT

        # Determine effective role
        if detected_role == DatasetRole.LOCKED_HOLDOUT or (overlaps_holdout and detected_role != DatasetRole.PROSPECTIVE_FORWARD):
            effective_role = DatasetRole.LOCKED_HOLDOUT
        elif detected_role:
            effective_role = detected_role
        elif start_ts_ns and start_ts_ns > HOLDOUT_WINDOW_END_NS:
            effective_role = DatasetRole.PROSPECTIVE_FORWARD
        elif end_ts_ns and end_ts_ns < HOLDOUT_WINDOW_START_NS:
            effective_role = DatasetRole.DEVELOPMENT
        else:
            effective_role = DatasetRole.DEVELOPMENT

        # 3. Policy Enforcement
        if effective_role == DatasetRole.LOCKED_HOLDOUT:
            if op_enum in cls.FORBIDDEN_RESEARCH_OPS:
                reason = f"Operation '{op_enum.value}' is strictly forbidden on LOCKED_HOLDOUT (2024-01-01 to 2024-11-30)"
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role=effective_role.value,
                    start_ns=start_ts_ns,
                    end_ns=end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(
                    f"HOLDOUT_FIREWALL_VIOLATION: Unauthorized attempt to access {effective_role.value}. {reason}"
                )

        # If prospective forward, allowed for forward validation or research
        if effective_role == DatasetRole.PROSPECTIVE_FORWARD:
            reason = "PROSPECTIVE_FORWARD dataset allowed for forward validation"
            log_guard_event(
                operation=op_enum.value,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                role=effective_role.value,
                start_ns=start_ts_ns,
                end_ns=end_ts_ns,
                decision="ALLOWED",
                reason=reason,
                research_generation=research_generation,
            )
            return True

        # Allowed development or validation access
        log_guard_event(
            operation=op_enum.value,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            role=effective_role.value,
            start_ns=start_ts_ns,
            end_ns=end_ts_ns,
            decision="ALLOWED",
            reason=f"Access permitted for role {effective_role.value}",
            research_generation=research_generation,
        )
        return True


def load_research_parquet(
    file_path: Path | str,
    operation: ResearchOperation | str = ResearchOperation.BACKTEST,
    dataset_id: str = "dataset_v3.1.0",
    dataset_role: Optional[DatasetRole | str] = None,
    start_ts_ns: Optional[int] = None,
    end_ts_ns: Optional[int] = None,
) -> Any:
    """Safe Parquet loader enforcing the ResearchDataAccessGuard before disk read."""
    p = Path(file_path)
    ResearchDataAccessGuard.check_access(
        operation=operation,
        dataset_id=dataset_id,
        dataset_role=dataset_role,
        start_ts_ns=start_ts_ns,
        end_ts_ns=end_ts_ns,
        file_path=p,
    )
    return pq.read_table(p)
