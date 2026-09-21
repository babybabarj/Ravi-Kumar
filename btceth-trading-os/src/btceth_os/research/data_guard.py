from __future__ import annotations

import hashlib
import json
import re
import threading
import types
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "artifacts" / "research" / "holdout_access_ledger.jsonl"
_LEDGER_LOCK = threading.Lock()

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


class LedgerIntegrityFailureError(RuntimeError):
    """Raised when the research access ledger hash chain integrity is compromised."""
    pass


@dataclass(frozen=True)
class CanonicalPartitionEntry:
    dataset_id: str
    dataset_version: str
    partition_id: str
    canonical_relative_path: Optional[str]
    physical_sha256: Optional[str]
    dataset_logical_sha256: Optional[str]
    start_ts_ns: Optional[int]
    end_ts_ns: Optional[int]
    role: DatasetRole
    parent_dataset: Optional[str] = None
    status: str = "CANONICAL"

    @property
    def dataset_logical_sha(self) -> Optional[str]:
        return self.dataset_logical_sha256


CanonicalDatasetEntry = CanonicalPartitionEntry


# Authoritative Dataset Registry
_CANONICAL_DATASETS: dict[str, CanonicalPartitionEntry] = {
    "BTCUSDT-resampled-1h-v3.1.0": CanonicalPartitionEntry(
        dataset_id="BTCUSDT-resampled-1h-v3.1.0",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_2020_2023_1H",
        canonical_relative_path="artifacts/research/silver_v3/BTCUSDT-resampled-1h-v3.1.0.parquet",
        physical_sha256="f706dfa1fc637e46fa6604b19fd8dea15edfebaa3478cc859ed1d23111eff70e",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="dataset_v3.0.0",
        status="CANONICAL",
    ),
    "ETHUSDT-resampled-1h-v3.1.0": CanonicalPartitionEntry(
        dataset_id="ETHUSDT-resampled-1h-v3.1.0",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_2020_2023_1H",
        canonical_relative_path="artifacts/research/silver_v3/ETHUSDT-resampled-1h-v3.1.0.parquet",
        physical_sha256="64cd9f71654fe6e9791fb379b2fdf7891d3d27fd8f7456b97c0d31e892b8e510",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="dataset_v3.0.0",
        status="CANONICAL",
    ),
    "BTCUSDT-funding-2020-01-2023-12-v3.1": CanonicalPartitionEntry(
        dataset_id="BTCUSDT-funding-2020-01-2023-12-v3.1",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_FUNDING_2020_2023",
        canonical_relative_path="artifacts/research/silver_v3/BTCUSDT-funding-2020-01-2023-12-v3.1.parquet",
        physical_sha256="a966c54a24d6ab8558221b329c8ba2f024fa981738ca9b368bf6ae1d6668bdf6",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704038400_000_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="dataset_v3.0.0",
        status="CANONICAL",
    ),
    "ETHUSDT-funding-2020-01-2023-12-v3.1": CanonicalPartitionEntry(
        dataset_id="ETHUSDT-funding-2020-01-2023-12-v3.1",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_FUNDING_2020_2023",
        canonical_relative_path="artifacts/research/silver_v3/ETHUSDT-funding-2020-01-2023-12-v3.1.parquet",
        physical_sha256="89a22768444ebb06b618fd2e30699dc020c46ccb38ae804a8cf164874eb6462b",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704038400_000_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="dataset_v3.0.0",
        status="CANONICAL",
    ),
    "dataset_v3.1.0": CanonicalPartitionEntry(
        dataset_id="dataset_v3.1.0",
        dataset_version="v3.1.0",
        partition_id="FULL_DEV_2020_2023",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.DEVELOPMENT,
        start_ts_ns=1577836800_000_000_000,  # 2020-01-01T00:00:00Z
        end_ts_ns=1704067199_000_000_000,    # 2023-12-31T23:59:59Z
        parent_dataset="dataset_v3.0.0",
        status="CANONICAL",
    ),
    "BTCUSDT_DEV": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_DEV",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_DEV_2020_2022",
        canonical_relative_path="artifacts/research/silver_v3/BTCUSDT-resampled-1h-v3.1.0.parquet",
        physical_sha256="f706dfa1fc637e46fa6604b19fd8dea15edfebaa3478cc859ed1d23111eff70e",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.DEVELOPMENT,
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        parent_dataset="dataset_v3.1.0",
        status="CANONICAL",
    ),
    "BTCUSDT_VAL": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_VAL",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_VAL_2023",
        canonical_relative_path="artifacts/research/silver_v3/BTCUSDT-resampled-1h-v3.1.0.parquet",
        physical_sha256="f706dfa1fc637e46fa6604b19fd8dea15edfebaa3478cc859ed1d23111eff70e",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.VALIDATION,
        start_ts_ns=1672531200_000_000_000,  # 2023-01-01T00:00:00Z
        end_ts_ns=1704063600_000_000_000,    # 2023-12-31T23:59:59Z
        parent_dataset="dataset_v3.1.0",
        status="CANONICAL",
    ),
    "BTCUSDT_2024_HOLDOUT": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_2024_HOLDOUT",
        dataset_version="v3.1.0",
        partition_id="HOLDOUT_2024",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256=None,
        role=DatasetRole.LOCKED_HOLDOUT,
        start_ts_ns=HOLDOUT_WINDOW_START_NS,
        end_ts_ns=HOLDOUT_WINDOW_END_NS,
        parent_dataset="dataset_v3.1.0",
        status="LOCKED_UNREGISTERED_FOR_READ",
    ),
    "BTCUSDT_2025_PROSPECTIVE": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_2025_PROSPECTIVE",
        dataset_version="v3.2.0_prospective",
        partition_id="PROSPECTIVE_2025",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256=None,
        role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=1735689600_000_000_000,  # 2025-01-01T00:00:00Z
        end_ts_ns=1767225599_000_000_000,    # 2025-12-31T23:59:59Z
        parent_dataset=None,
        status="PROSPECTIVE_PRISTINE",
    ),
    "BTCUSDT_2026_LIVE_FORWARD": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_2026_LIVE_FORWARD",
        dataset_version="v3.3.0_prospective",
        partition_id="PROSPECTIVE_2026",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256=None,
        role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=1767225600_000_000_000,  # 2026-01-01T00:00:00Z
        end_ts_ns=1798761599_000_000_000,    # 2026-12-31T23:59:59Z
        parent_dataset=None,
        status="PROSPECTIVE_PRISTINE",
    ),
}

CANONICAL_DATASET_REGISTRY: Mapping[str, CanonicalPartitionEntry] = types.MappingProxyType(_CANONICAL_DATASETS)


def register_canonical_dataset(entry: CanonicalPartitionEntry) -> None:
    """Register a new canonical dataset entry in memory (immutable in production)."""
    raise TypeError(
        "CANONICAL_DATASET_REGISTRY is immutable in production. "
        "Use explicit dependency injection via the 'registry' parameter in tests."
    )


def corroborate_parquet_timestamps(p_obj: Path) -> tuple[int, int]:
    """Inspect Parquet row group statistics or ts_event_ns column values.

    Returns (min_ts_ns, max_ts_ns).
    Raises HoldoutAccessDeniedError if file cannot be parsed or if holdout window is violated.
    """
    try:
        meta = pq.read_metadata(p_obj)
    except Exception as e:
        raise HoldoutAccessDeniedError(f"DATASET_METADATA_INVALID: Failed to inspect Parquet metadata on {p_obj.name}: {e}")

    overall_min: Optional[int] = None
    overall_max: Optional[int] = None
    all_stats_set = True

    for i in range(meta.num_row_groups):
        rg = meta.row_group(i)
        ts_col_idx: Optional[int] = None
        for c in range(rg.num_columns):
            col = rg.column(c)
            if col.path_in_schema == "ts_event_ns" or col.path_in_schema.endswith(".ts_event_ns"):
                ts_col_idx = c
                if col.is_stats_set and col.statistics.has_min_max:
                    rg_min = col.statistics.min
                    rg_max = col.statistics.max
                    if overall_min is None or rg_min < overall_min:
                        overall_min = rg_min
                    if overall_max is None or rg_max > overall_max:
                        overall_max = rg_max
                else:
                    all_stats_set = False
                break
        if ts_col_idx is None:
            all_stats_set = False

    if not all_stats_set or overall_min is None or overall_max is None:
        try:
            tbl = pq.read_table(p_obj, columns=["ts_event_ns"])
            ts_series = tbl["ts_event_ns"].to_pylist()
            if not ts_series:
                raise ValueError("Parquet file has no rows in ts_event_ns")
            overall_min = min(ts_series)
            overall_max = max(ts_series)
        except Exception as e:
            raise HoldoutAccessDeniedError(f"DATASET_METADATA_INVALID: Failed to read ts_event_ns from {p_obj.name}: {e}")

    # Corroborate against 2024 holdout firewall
    # Invariant: If ANY row falls in [HOLDOUT_WINDOW_START_NS, HOLDOUT_WINDOW_END_NS], fail closed!
    if (overall_min <= HOLDOUT_WINDOW_END_NS) and (overall_max >= HOLDOUT_WINDOW_START_NS):
        raise HoldoutAccessDeniedError(
            f"HOLDOUT_FIREWALL_VIOLATION: Physical Parquet rows in {p_obj.name} intersect locked 2024 holdout window "
            f"([{overall_min}, {overall_max}] overlaps [{HOLDOUT_WINDOW_START_NS}, {HOLDOUT_WINDOW_END_NS}]). "
            f"HOLDOUT_UNLOCK_CAPABILITY is ZERO."
        )

    return overall_min, overall_max


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
    research_generation: str = "ROUND3B.0B",
) -> dict[str, Any]:
    """Record an append-only, tamper-evident cryptographic hash-chain entry in the access ledger."""
    with _LEDGER_LOCK:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Pre-append integrity check: fail closed if chain is corrupt
        is_valid, err_idx, err_msg, _ = verify_access_ledger_integrity()
        if not is_valid:
            raise LedgerIntegrityFailureError(
                f"LEDGER_INTEGRITY_FAILURE: Access ledger hash chain is corrupted at line {err_idx}: {err_msg}. Append refused."
            )
        
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
        ResearchOperation.FINAL_HOLDOUT_AUDIT,
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
        research_generation: str = "ROUND3B.0B",
        registry: Optional[Mapping[str, CanonicalPartitionEntry]] = None,
    ) -> bool:
        """Evaluate data access request under the strict adversarial trust hierarchy."""
        if not dataset_id:
            raise HoldoutAccessDeniedError("DATASET_IDENTITY_REQUIRED: An explicit dataset_id must be provided.")

        try:
            op_enum = ResearchOperation(operation) if isinstance(operation, str) else operation
        except ValueError:
            reason = f"UNKNOWN_RESEARCH_OPERATION: Operation '{operation}' is not recognized."
            log_guard_event(
                operation=str(operation),
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

        detected_role: Optional[DatasetRole] = None
        if dataset_role:
            try:
                detected_role = DatasetRole(dataset_role)
            except ValueError:
                detected_role = None

        p_obj = Path(file_path) if file_path else None
        active_registry = registry if registry is not None else CANONICAL_DATASET_REGISTRY

        # -------------------------------------------------------------
        # TRUST LEVEL 1: Canonical Registry Verification
        # -------------------------------------------------------------
        registry_entry = active_registry.get(dataset_id)
        if registry_entry:
            # Check for locked holdout entries in registry
            if registry_entry.status == "LOCKED_UNREGISTERED_FOR_READ" or registry_entry.role == DatasetRole.LOCKED_HOLDOUT:
                reason = (
                    f"HOLDOUT_FIREWALL_VIOLATION: Locked holdout dataset '{dataset_id}' is inaccessible. "
                    f"Operation '{op_enum.value}' denied. HOLDOUT_UNLOCK_CAPABILITY is ZERO."
                )
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role=registry_entry.role.value,
                    start_ns=start_ts_ns or registry_entry.start_ts_ns,
                    end_ns=end_ts_ns or registry_entry.end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(reason)

            # Enforce logical SHA match if caller provided one
            if dataset_logical_sha is not None and registry_entry.dataset_logical_sha256 is not None:
                if dataset_logical_sha != registry_entry.dataset_logical_sha256:
                    reason = (
                        f"DATASET_IDENTITY_MISMATCH: Caller provided logical SHA {dataset_logical_sha} "
                        f"does not match canonical registry SHA {registry_entry.dataset_logical_sha256} for {dataset_id}"
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
                # 1. Row-level timestamp corroboration (catches stripped/forged metadata and holdout rows)
                actual_min_ts, actual_max_ts = corroborate_parquet_timestamps(p_obj)

                # 2. Physical SHA-256 verification
                actual_physical_sha = hashlib.sha256(p_obj.read_bytes()).hexdigest()
                if registry_entry and registry_entry.physical_sha256:
                    if actual_physical_sha != registry_entry.physical_sha256:
                        reason = (
                            f"DATASET_PHYSICAL_IDENTITY_MISMATCH: File '{p_obj.name}' physical SHA {actual_physical_sha} "
                            f"does not match registered physical SHA {registry_entry.physical_sha256} for dataset '{dataset_id}'"
                        )
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

                if registry_entry and registry_entry.start_ts_ns is not None and registry_entry.end_ts_ns is not None:
                    if actual_min_ts < registry_entry.start_ts_ns or actual_max_ts > registry_entry.end_ts_ns:
                        reason = (
                            f"ACTUAL_TIMESTAMP_RANGE_MISMATCH: Physical timestamp range [{actual_min_ts}, {actual_max_ts}] "
                            f"outside registered partition range [{registry_entry.start_ts_ns}, {registry_entry.end_ts_ns}] for dataset '{dataset_id}'"
                        )
                        log_guard_event(
                            operation=op_enum.value,
                            dataset_id=dataset_id,
                            dataset_version=dataset_version,
                            role=detected_role.value if detected_role else "UNKNOWN",
                            start_ns=actual_min_ts,
                            end_ns=actual_max_ts,
                            decision="BLOCKED",
                            reason=reason,
                            research_generation=research_generation,
                        )
                        raise HoldoutAccessDeniedError(reason)

                # 3. Custom Parquet metadata verification (Authoritative registry precedence)
                try:
                    meta = pq.read_metadata(p_obj)
                    if meta.schema:
                        custom = meta.schema.to_arrow_schema().metadata or {}
                        if b"dataset_role" in custom:
                            role_str = custom[b"dataset_role"].decode("utf-8")
                            if registry_entry and role_str != registry_entry.role.value:
                                reason = f"METADATA_REGISTRY_MISMATCH: File metadata role '{role_str}' != registered role '{registry_entry.role.value}'"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=role_str,
                                    start_ns=start_ts_ns,
                                    end_ns=end_ts_ns,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                            if not registry_entry:
                                detected_role = DatasetRole(role_str)
                        if b"start_ts_ns" in custom:
                            meta_start = int(custom[b"start_ts_ns"].decode("utf-8"))
                            if registry_entry and registry_entry.start_ts_ns is not None and meta_start != registry_entry.start_ts_ns:
                                reason = f"METADATA_REGISTRY_MISMATCH: File metadata start_ts_ns {meta_start} != registered start_ts_ns {registry_entry.start_ts_ns}"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=detected_role.value if detected_role else "UNKNOWN",
                                    start_ns=meta_start,
                                    end_ns=end_ts_ns,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                            if not registry_entry and start_ts_ns is None:
                                start_ts_ns = meta_start
                        if b"end_ts_ns" in custom:
                            meta_end = int(custom[b"end_ts_ns"].decode("utf-8"))
                            if registry_entry and registry_entry.end_ts_ns is not None and meta_end != registry_entry.end_ts_ns:
                                reason = f"METADATA_REGISTRY_MISMATCH: File metadata end_ts_ns {meta_end} != registered end_ts_ns {registry_entry.end_ts_ns}"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=detected_role.value if detected_role else "UNKNOWN",
                                    start_ns=start_ts_ns,
                                    end_ns=meta_end,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                            if not registry_entry and end_ts_ns is None:
                                end_ts_ns = meta_end
                        if b"dataset_logical_sha" in custom:
                            file_logical_sha = custom[b"dataset_logical_sha"].decode("utf-8")
                            if registry_entry and registry_entry.dataset_logical_sha256 and file_logical_sha != registry_entry.dataset_logical_sha256:
                                reason = f"METADATA_REGISTRY_MISMATCH: File metadata logical SHA '{file_logical_sha}' != registered SHA '{registry_entry.dataset_logical_sha256}'"
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
        # -------------------------------------------------------------
        intersects_holdout = False
        if start_ts_ns is not None and end_ts_ns is not None:
            intersects_holdout = (start_ts_ns <= HOLDOUT_WINDOW_END_NS) and (end_ts_ns >= HOLDOUT_WINDOW_START_NS)
        elif start_ts_ns is not None:
            intersects_holdout = (start_ts_ns >= HOLDOUT_WINDOW_START_NS) and (start_ts_ns <= HOLDOUT_WINDOW_END_NS)
        elif end_ts_ns is not None:
            intersects_holdout = (end_ts_ns >= HOLDOUT_WINDOW_START_NS) and (end_ts_ns <= HOLDOUT_WINDOW_END_NS)

        path_indicates_holdout = bool(p_obj and ("holdout" in p_obj.name.lower() or "2024" in p_obj.name.lower()))

        if intersects_holdout or path_indicates_holdout:
            effective_role = DatasetRole.LOCKED_HOLDOUT
        elif detected_role:
            effective_role = detected_role
        elif start_ts_ns and start_ts_ns > HOLDOUT_WINDOW_END_NS:
            effective_role = DatasetRole.PROSPECTIVE_FORWARD
        elif end_ts_ns and end_ts_ns < HOLDOUT_WINDOW_START_NS:
            effective_role = DatasetRole.DEVELOPMENT
        else:
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

        # 2. PROSPECTIVE_FORWARD Policy (Whitelist only: PROSPECTIVE_VALIDATION, SHADOW_EVALUATION, PAPER_EVALUATION)
        if effective_role == DatasetRole.PROSPECTIVE_FORWARD:
            if op_enum not in cls.PROSPECTIVE_ALLOWED_OPERATIONS:
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
    dataset_id: str,
    operation: ResearchOperation | str = ResearchOperation.BACKTEST,
    dataset_role: Optional[DatasetRole | str] = None,
    start_ts_ns: Optional[int] = None,
    end_ts_ns: Optional[int] = None,
    dataset_logical_sha: Optional[str] = None,
    registry: Optional[Mapping[str, CanonicalPartitionEntry]] = None,
) -> Any:
    """Safe Parquet loader enforcing the ResearchDataAccessGuard before disk read."""
    if not dataset_id:
        raise HoldoutAccessDeniedError("DATASET_IDENTITY_REQUIRED: Explicit dataset_id must be provided to load research parquet.")
    p = Path(file_path)
    ResearchDataAccessGuard.check_access(
        operation=operation,
        dataset_id=dataset_id,
        dataset_role=dataset_role,
        start_ts_ns=start_ts_ns,
        end_ts_ns=end_ts_ns,
        file_path=p,
        dataset_logical_sha=dataset_logical_sha,
        registry=registry,
    )
    return pq.read_table(p)
