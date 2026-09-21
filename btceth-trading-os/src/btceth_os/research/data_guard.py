from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "artifacts" / "research" / "holdout_access_ledger.jsonl"

# The Locked Historical Holdout is strictly:
# 2024-01-01 00:00:00 UTC to 2024-11-30 23:59:59.999999999 UTC
HOLDOUT_WINDOW_START_NS = 1704067200_000_000_000  # 2024-01-01T00:00:00Z
HOLDOUT_WINDOW_END_NS   = 1733011199_999_999_999  # 2024-11-30T23:59:59.999999999Z

HOLDOUT_UNLOCK_CAPABILITY = 0  # Invariant: Zero unlock capability in this phase


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
    SHADOW_EVALUATION = "shadow_evaluation"
    PAPER_EVALUATION = "paper_evaluation"
    FINAL_HOLDOUT_AUDIT = "final_holdout_audit"  # Inaccessible: HOLDOUT_UNLOCK_CAPABILITY is ZERO


class HoldoutAccessDeniedError(PermissionError):
    """Raised when an unauthorized or unverified research operation attempts data access."""
    pass


@dataclass(frozen=True)
class CanonicalDatasetEntry:
    dataset_id: str
    dataset_version: str
    dataset_logical_sha: str
    role: DatasetRole
    start_ts_ns: int
    end_ts_ns: int
    parent_dataset: Optional[str] = None
    status: str = "CANONICAL"


# Authoritative Dataset Registry
CANONICAL_DATASET_REGISTRY: dict[str, CanonicalDatasetEntry] = {
    "dataset_v3.1.0": CanonicalDatasetEntry(
        dataset_id="dataset_v3.1.0",
        dataset_version="v3.1.0",
        dataset_logical_sha="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.DEVELOPMENT,
        start_ts_ns=1577836800_000_000_000,  # 2020-01-01T00:00:00Z
        end_ts_ns=1704067199_000_000_000,    # 2023-12-31T23:59:59Z
        parent_dataset="dataset_v3.0.0",
        status="CANONICAL",
    ),
    "BTCUSDT_DEV": CanonicalDatasetEntry(
        dataset_id="BTCUSDT_DEV",
        dataset_version="v3.1.0",
        dataset_logical_sha="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.DEVELOPMENT,
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1672531199_000_000_000,    # 2022-12-31T23:59:59Z
        parent_dataset="dataset_v3.1.0",
        status="CANONICAL",
    ),
    "BTCUSDT_VAL": CanonicalDatasetEntry(
        dataset_id="BTCUSDT_VAL",
        dataset_version="v3.1.0",
        dataset_logical_sha="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.VALIDATION,
        start_ts_ns=1672531200_000_000_000,  # 2023-01-01T00:00:00Z
        end_ts_ns=1704067199_000_000_000,    # 2023-12-31T23:59:59Z
        parent_dataset="dataset_v3.1.0",
        status="CANONICAL",
    ),
    "BTCUSDT_2024_HOLDOUT": CanonicalDatasetEntry(
        dataset_id="BTCUSDT_2024_HOLDOUT",
        dataset_version="v3.1.0",
        dataset_logical_sha="holdout_2024_locked_sha256",
        role=DatasetRole.LOCKED_HOLDOUT,
        start_ts_ns=HOLDOUT_WINDOW_START_NS,
        end_ts_ns=HOLDOUT_WINDOW_END_NS,
        parent_dataset="dataset_v3.1.0",
        status="LOCKED_HOLDOUT",
    ),
    "BTCUSDT_2025_PROSPECTIVE": CanonicalDatasetEntry(
        dataset_id="BTCUSDT_2025_PROSPECTIVE",
        dataset_version="v3.2.0_prospective",
        dataset_logical_sha="prospective_2025_sha256",
        role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=1735689600_000_000_000,  # 2025-01-01T00:00:00Z
        end_ts_ns=1767225599_000_000_000,    # 2025-12-31T23:59:59Z
        parent_dataset=None,
        status="PROSPECTIVE_PRISTINE",
    ),
    "BTCUSDT_2026_LIVE_FORWARD": CanonicalDatasetEntry(
        dataset_id="BTCUSDT_2026_LIVE_FORWARD",
        dataset_version="v3.3.0_prospective",
        dataset_logical_sha="prospective_2026_sha256",
        role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=1767225600_000_000_000,  # 2026-01-01T00:00:00Z
        end_ts_ns=1798761599_000_000_000,    # 2026-12-31T23:59:59Z
        parent_dataset=None,
        status="PROSPECTIVE_PRISTINE",
    ),
}


def register_canonical_dataset(entry: CanonicalDatasetEntry) -> None:
    """Register a new canonical dataset entry in memory."""
    CANONICAL_DATASET_REGISTRY[entry.dataset_id] = entry


def sanitize_payload_for_logging(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure no API keys, secrets, tokens, or credential-bearing URLs are logged."""
    sanitized = {}
    secret_patterns = re.compile(r"(key|secret|token|password|auth|credential)", re.IGNORECASE)
    url_creds = re.compile(r"://([^:@]+):([^@]+)@")
    
    for k, v in data.items():
        if secret_patterns.search(str(k)):
            sanitized[k] = "[REDACTED_SECRET]"
        elif isinstance(v, str):
            sanitized[k] = url_creds.sub("://[REDACTED_USER]:[REDACTED_PASS]@", v)
        else:
            sanitized[k] = v
    return sanitized


def compute_canonical_json_sha256(payload: dict[str, Any]) -> str:
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _get_last_ledger_chain_state() -> tuple[int, str]:
    """Read the last sequence number and entry_sha256 from the ledger file."""
    if not LEDGER_PATH.is_file():
        return 0, "0" * 64
    
    lines = [line.strip() for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return 0, "0" * 64
    
    try:
        last_entry = json.loads(lines[-1])
        seq = int(last_entry.get("sequence", 0))
        last_sha = str(last_entry.get("entry_sha256", "0" * 64))
        return seq, last_sha
    except Exception:
        return 0, "0" * 64


def log_guard_event(
    operation: str,
    dataset_id: str,
    dataset_version: str,
    role: str,
    start_ns: Optional[int],
    end_ns: Optional[int],
    decision: str,  # "ALLOWED" or "BLOCKED"
    reason: str,
    research_generation: str = "ROUND3B.0A",
) -> dict[str, Any]:
    """Record an append-only, tamper-evident cryptographic hash-chain entry in the access ledger."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    last_seq, prev_sha = _get_last_ledger_chain_state()
    current_seq = last_seq + 1
    
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "operation": str(operation),
        "dataset_id": str(dataset_id),
        "dataset_version": str(dataset_version),
        "dataset_role": str(role),
        "requested_start_ns": start_ns,
        "requested_end_ns": end_ns,
        "requested_start_utc": datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc).isoformat() if start_ns else None,
        "requested_end_utc": datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc).isoformat() if end_ns else None,
        "decision": str(decision),
        "reason": str(reason),
        "research_generation": str(research_generation),
    }
    sanitized_payload = sanitize_payload_for_logging(payload)
    payload_sha = compute_canonical_json_sha256(sanitized_payload)
    
    entry_commit_str = f"{current_seq}:{prev_sha}:{payload_sha}".encode("utf-8")
    entry_sha = hashlib.sha256(entry_commit_str).hexdigest()
    
    full_entry = {
        "sequence": current_seq,
        "previous_entry_sha256": prev_sha,
        "entry_payload_sha256": payload_sha,
        "entry_sha256": entry_sha,
        **sanitized_payload,
    }
    
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(full_entry) + "\n")
        
    return full_entry


def verify_access_ledger_integrity() -> tuple[bool, int, str, dict[str, Any]]:
    """Cryptographically verify the research access ledger hash chain.
    
    Returns (is_valid, total_entries, status_message, audit_summary).
    """
    if not LEDGER_PATH.is_file():
        return True, 0, "LEDGER_EMPTY", {"total_entries": 0, "allowed_holdout_accesses": 0}
    
    lines = [line.strip() for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return True, 0, "LEDGER_EMPTY", {"total_entries": 0, "allowed_holdout_accesses": 0}
    
    expected_prev = "0" * 64
    allowed_holdout_accesses = 0
    blocked_holdout_accesses = 0
    
    for idx, raw in enumerate(lines, 1):
        try:
            entry = json.loads(raw)
        except Exception as e:
            return False, idx - 1, f"JSON_CORRUPTION_LINE_{idx}: {e}", {}
            
        seq = entry.get("sequence")
        prev_sha = entry.get("previous_entry_sha256")
        payload_sha = entry.get("entry_payload_sha256")
        entry_sha = entry.get("entry_sha256")
        
        # Sequence check
        if seq != idx:
            return False, idx - 1, f"SEQUENCE_GAP_AT_LINE_{idx}: expected {idx}, got {seq}", {}
            
        # Hash chain continuity
        if prev_sha != expected_prev:
            return False, idx - 1, f"HASH_CHAIN_BROKEN_LINE_{idx}: expected {expected_prev}, got {prev_sha}", {}
            
        # Payload verification
        clean_payload = {
            k: v for k, v in entry.items()
            if k not in ("sequence", "previous_entry_sha256", "entry_payload_sha256", "entry_sha256")
        }
        recomputed_payload_sha = compute_canonical_json_sha256(clean_payload)
        if recomputed_payload_sha != payload_sha:
            return False, idx - 1, f"PAYLOAD_TAMPER_DETECTED_LINE_{idx}", {}
            
        # Entry hash verification
        expected_entry_sha = hashlib.sha256(f"{seq}:{prev_sha}:{payload_sha}".encode("utf-8")).hexdigest()
        if expected_entry_sha != entry_sha:
            return False, idx - 1, f"ENTRY_SHA_TAMPER_DETECTED_LINE_{idx}", {}
            
        # Check holdout access records
        role = entry.get("dataset_role")
        decision = entry.get("decision")
        if role == DatasetRole.LOCKED_HOLDOUT.value:
            if decision == "ALLOWED":
                allowed_holdout_accesses += 1
            else:
                blocked_holdout_accesses += 1
                
        expected_prev = entry_sha
        
    summary = {
        "total_entries": len(lines),
        "allowed_holdout_accesses": allowed_holdout_accesses,
        "blocked_holdout_accesses": blocked_holdout_accesses,
        "last_entry_sha": expected_prev,
    }
    return True, len(lines), "HASH_CHAIN_VERIFIED", summary


class ResearchDataAccessGuard:
    """Hardened research data access guard enforcing trust hierarchy, dataset identity,
    authoritative holdout boundary precedence, and restricted prospective forward operations."""

    PROSPECTIVE_ALLOWED_OPERATIONS = {
        ResearchOperation.PROSPECTIVE_VALIDATION,
        ResearchOperation.SHADOW_EVALUATION,
        ResearchOperation.PAPER_EVALUATION,
    }

    FORBIDDEN_PROSPECTIVE_OPERATIONS = {
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
        research_generation: str = "ROUND3B.0A",
    ) -> bool:
        """Evaluate data access request under the strict adversarial trust hierarchy."""
        try:
            op_enum = ResearchOperation(operation) if isinstance(operation, str) else operation
        except ValueError:
            op_enum = ResearchOperation.BACKTEST

        detected_role: Optional[DatasetRole] = None
        if dataset_role:
            try:
                detected_role = DatasetRole(dataset_role)
            except ValueError:
                detected_role = None

        p_obj = Path(file_path) if file_path else None
        
        # -------------------------------------------------------------
        # TRUST LEVEL 1: Canonical Registry Verification
        # -------------------------------------------------------------
        registry_entry = CANONICAL_DATASET_REGISTRY.get(dataset_id)
        if registry_entry:
            # Enforce logical SHA match if caller provided one
            if dataset_logical_sha is not None and dataset_logical_sha != registry_entry.dataset_logical_sha:
                reason = (
                    f"DATASET_IDENTITY_MISMATCH: Caller provided logical SHA {dataset_logical_sha} "
                    f"does not match canonical registry SHA {registry_entry.dataset_logical_sha} for {dataset_id}"
                )
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role=registry_entry.role.value,
                    start_ns=start_ts_ns,
                    end_ns=end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(reason)
            
            # Adopt registry timestamps and role
            if start_ts_ns is None:
                start_ts_ns = registry_entry.start_ts_ns
            if end_ts_ns is None:
                end_ts_ns = registry_entry.end_ts_ns
            detected_role = registry_entry.role

        # -------------------------------------------------------------
        # TRUST LEVEL 2: Physical / Metadata Verification (Parquet)
        # -------------------------------------------------------------
        if p_obj and p_obj.is_file():
            if p_obj.suffix == ".parquet":
                try:
                    meta = pq.read_metadata(p_obj)
                    if meta.schema:
                        custom = meta.schema.to_arrow_schema().metadata or {}
                        if b"dataset_role" in custom:
                            role_str = custom[b"dataset_role"].decode("utf-8")
                            detected_role = DatasetRole(role_str)
                        if b"start_ts_ns" in custom:
                            start_ts_ns = int(custom[b"start_ts_ns"].decode("utf-8"))
                        if b"end_ts_ns" in custom:
                            end_ts_ns = int(custom[b"end_ts_ns"].decode("utf-8"))
                        if b"dataset_logical_sha" in custom:
                            file_logical_sha = custom[b"dataset_logical_sha"].decode("utf-8")
                            if dataset_logical_sha and dataset_logical_sha != file_logical_sha:
                                reason = f"DATASET_IDENTITY_MISMATCH: Metadata SHA {file_logical_sha} != {dataset_logical_sha}"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=detected_role.value if detected_role else "UNKNOWN",
                                    start_ns=start_ts_ns,
                                    end_ns=end_ts_ns,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                except HoldoutAccessDeniedError:
                    raise
                except Exception as e:
                    # FAIL CLOSED ON METADATA PARSE FAILURE
                    reason = f"DATASET_METADATA_INVALID: Failed to inspect Parquet metadata on {p_obj.name}: {e}"
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role="UNKNOWN",
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise HoldoutAccessDeniedError(reason)

        # -------------------------------------------------------------
        # TRUST LEVEL 3: Authoritative Holdout Boundary Precedence
        # Invariant: IF dataset intersects locked holdout (2024-01-01 to 2024-11-30)
        # THEN role = LOCKED_HOLDOUT REGARDLESS OF CALLER-SUPPLIED ROLE.
        # -------------------------------------------------------------
        intersects_holdout = False
        if start_ts_ns is not None and end_ts_ns is not None:
            intersects_holdout = (start_ts_ns <= HOLDOUT_WINDOW_END_NS) and (end_ts_ns >= HOLDOUT_WINDOW_START_NS)
        elif start_ts_ns is not None:
            intersects_holdout = (start_ts_ns >= HOLDOUT_WINDOW_START_NS) and (start_ts_ns <= HOLDOUT_WINDOW_END_NS)
        elif end_ts_ns is not None:
            intersects_holdout = (end_ts_ns >= HOLDOUT_WINDOW_START_NS) and (end_ts_ns <= HOLDOUT_WINDOW_END_NS)

        # Defensive path heuristic
        path_indicates_holdout = bool(p_obj and ("holdout" in p_obj.name.lower() or "2024" in p_obj.name.lower()))

        # CRITICAL INVARIANT: Physical or temporal intersection with holdout OVERRIDES caller role!
        if intersects_holdout or path_indicates_holdout:
            effective_role = DatasetRole.LOCKED_HOLDOUT
        elif detected_role:
            effective_role = detected_role
        elif start_ts_ns and start_ts_ns > HOLDOUT_WINDOW_END_NS:
            effective_role = DatasetRole.PROSPECTIVE_FORWARD
        elif end_ts_ns and end_ts_ns < HOLDOUT_WINDOW_START_NS:
            effective_role = DatasetRole.DEVELOPMENT
        else:
            # FAIL CLOSED ON UNKNOWN PROVENANCE
            reason = f"DATASET_PROVENANCE_UNKNOWN: Dataset '{dataset_id}' cannot be proven. Access denied."
            log_guard_event(
                operation=op_enum.value,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                role="UNKNOWN",
                start_ns=start_ts_ns,
                end_ns=end_ts_ns,
                decision="BLOCKED",
                reason=reason,
                research_generation=research_generation,
            )
            raise HoldoutAccessDeniedError(reason)

        # -------------------------------------------------------------
        # TRUST LEVEL 4: Policy Enforcement
        # -------------------------------------------------------------
        # 1. LOCKED_HOLDOUT Policy (HOLDOUT_UNLOCK_CAPABILITY = 0)
        if effective_role == DatasetRole.LOCKED_HOLDOUT:
            reason = (
                f"HOLDOUT_FIREWALL_VIOLATION: Locked holdout (2024-01-01 to 2024-11-30) is inaccessible. "
                f"Operation '{op_enum.value}' denied. HOLDOUT_UNLOCK_CAPABILITY is ZERO."
            )
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
            raise HoldoutAccessDeniedError(reason)

        # 2. PROSPECTIVE_FORWARD Policy (Validation allowed; tuning/optimization blocked)
        if effective_role == DatasetRole.PROSPECTIVE_FORWARD:
            if op_enum in cls.FORBIDDEN_PROSPECTIVE_OPERATIONS:
                reason = (
                    f"PROSPECTIVE_TUNING_BLOCKED: Operation '{op_enum.value}' cannot access PROSPECTIVE_FORWARD data. "
                    f"Prospective forward data must remain PRISTINE and cannot be contaminated by tuning or optimization."
                )
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
                raise HoldoutAccessDeniedError(reason)

            # Allowed prospective operations: prospective_validation, shadow, paper
            reason = f"PROSPECTIVE_FORWARD permitted for forward evaluation operation '{op_enum.value}'"
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

        # 3. DEVELOPMENT & VALIDATION Policy
        if effective_role in (DatasetRole.DEVELOPMENT, DatasetRole.VALIDATION):
            log_guard_event(
                operation=op_enum.value,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                role=effective_role.value,
                start_ns=start_ts_ns,
                end_ns=end_ts_ns,
                decision="ALLOWED",
                reason=f"Access permitted for verified role {effective_role.value}",
                research_generation=research_generation,
            )
            return True

        # Fallback fail closed
        reason = f"DATASET_ACCESS_DENIED: Unhandled role {effective_role}"
        log_guard_event(
            operation=op_enum.value,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            role=str(effective_role),
            start_ns=start_ts_ns,
            end_ns=end_ts_ns,
            decision="BLOCKED",
            reason=reason,
            research_generation=research_generation,
        )
        raise HoldoutAccessDeniedError(reason)


def load_research_parquet(
    file_path: Path | str,
    operation: ResearchOperation | str = ResearchOperation.BACKTEST,
    dataset_id: str = "dataset_v3.1.0",
    dataset_role: Optional[DatasetRole | str] = None,
    start_ts_ns: Optional[int] = None,
    end_ts_ns: Optional[int] = None,
    dataset_logical_sha: Optional[str] = None,
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
        dataset_logical_sha=dataset_logical_sha,
    )
    return pq.read_table(p)
