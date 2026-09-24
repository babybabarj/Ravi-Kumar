"""INTEL-1A Dataset Access API and Append-Only Research Data Access Ledger.

Enforces strict firewall between exploratory/intelligence research and locked holdouts.
Every access request must specify asset, dataset_role, purpose, caller, and phase.
Locked holdout and pristine partition requests are unconditionally DENIED and logged
before opening any underlying artifact.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
INTEL_LEDGER_PATH = ROOT / "artifacts" / "research" / "intel_data_access_ledger.jsonl"
INTEL_LEDGER_LOCK_PATH = ROOT / "artifacts" / "research" / "intel_data_access_ledger.lock"
_LEDGER_LOCK = threading.Lock()

LOCKED_ROLES = {
    "LOCKED_HOLDOUT",
    "HOLDOUT",
    "LOCKED_PROSPECTIVE_PRISTINE",
    "PRISTINE",
    "PROSPECTIVE_PRISTINE",
}


class IntelDatasetRole(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    LOCKED_HOLDOUT = "LOCKED_HOLDOUT"
    LOCKED_PROSPECTIVE_PRISTINE = "LOCKED_PROSPECTIVE_PRISTINE"


class IntelAccessDeniedError(PermissionError):
    """Raised when an unauthorized access attempt is blocked by the holdout firewall."""
    pass


@dataclass(frozen=True)
class IntelDataAccessRequest:
    asset: str
    dataset_role: str
    purpose: str
    caller: str
    phase: str
    timestamp_utc: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp_utc:
            object.__setattr__(
                self, "timestamp_utc", datetime.now(timezone.utc).isoformat()
            )


@dataclass(frozen=True)
class IntelAccessLedgerEntry:
    timestamp_utc: str
    phase: str
    caller: str
    asset: str
    artifact: str
    dataset_role: str
    purpose: str
    access_result: str  # GRANTED or DENIED
    rows_requested: Optional[int]
    rows_returned: Optional[int]
    artifact_hash: str
    denial_reason: Optional[str] = None


def _compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def append_intel_access_ledger(
    entry: IntelAccessLedgerEntry, ledger_path: Path = INTEL_LEDGER_PATH
) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(entry), sort_keys=True) + "\n"
    with _LEDGER_LOCK:
        lock_fd = None
        try:
            INTEL_LEDGER_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            lock_fd = open(INTEL_LEDGER_LOCK_PATH, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            with ledger_path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        finally:
            if lock_fd is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()


class IntelDatasetAccessAPI:
    """Formal dataset-access API governing all research data accesses in INTEL-1A."""

    @staticmethod
    def resolve_partition_path(asset: str, role: str) -> Optional[Path]:
        role_upper = role.upper()
        # Canonical XAU V3 partitions
        if "XAU" in asset.upper():
            if role_upper == "DEVELOPMENT":
                return ROOT / "artifacts/research/partitions/XAUUSDT_DEV_2026_01_04_V3.parquet"
            if role_upper == "VALIDATION":
                return ROOT / "artifacts/research/partitions/XAUUSDT_VAL_2026_05_07_V3.parquet"
            if role_upper in ("LOCKED_HOLDOUT", "HOLDOUT"):
                return ROOT / "artifacts/research/partitions/XAUUSDT_HOLDOUT_2026_08_09_V3.parquet"
            if role_upper in ("LOCKED_PROSPECTIVE_PRISTINE", "PRISTINE"):
                return ROOT / "artifacts/research/partitions/XAUUSDT_PROSPECTIVE_PRISTINE_V3.parquet"

        # Canonical BTC partitions
        if "BTC" in asset.upper():
            if role_upper == "DEVELOPMENT":
                return ROOT / "artifacts/research/partitions/BTCUSDT_DEV_2020_2022.parquet"
            if role_upper == "VALIDATION":
                return ROOT / "artifacts/research/partitions/BTCUSDT_VAL_2023.parquet"
            if role_upper in ("LOCKED_HOLDOUT", "HOLDOUT"):
                return ROOT / "artifacts/research/partitions/BTCUSDT_HOLDOUT_2024.parquet"

        # Canonical ETH partitions
        if "ETH" in asset.upper():
            if role_upper == "DEVELOPMENT":
                return ROOT / "artifacts/research/partitions/ETHUSDT_DEV_2020_2022.parquet"
            if role_upper == "VALIDATION":
                return ROOT / "artifacts/research/partitions/ETHUSDT_VAL_2023.parquet"
            if role_upper in ("LOCKED_HOLDOUT", "HOLDOUT"):
                return ROOT / "artifacts/research/partitions/ETHUSDT_HOLDOUT_2024.parquet"

        return None

    @classmethod
    def request_dataset(
        cls,
        asset: str,
        dataset_role: str,
        purpose: str,
        caller: str,
        phase: str = "INTEL_1A",
        max_rows: Optional[int] = None,
        ledger_path: Path = INTEL_LEDGER_PATH,
    ) -> pa.Table:
        req = IntelDataAccessRequest(
            asset=asset,
            dataset_role=dataset_role,
            purpose=purpose,
            caller=caller,
            phase=phase,
        )

        role_normalized = dataset_role.upper()
        artifact_path = cls.resolve_partition_path(asset, role_normalized)
        artifact_str = str(artifact_path.relative_to(ROOT)) if artifact_path and artifact_path.is_relative_to(ROOT) else str(artifact_path)

        # FIREWALL: Deny holdout/pristine unconditionally before opening any artifact
        if role_normalized in LOCKED_ROLES or "HOLDOUT" in role_normalized or "PRISTINE" in role_normalized:
            denial_entry = IntelAccessLedgerEntry(
                timestamp_utc=req.timestamp_utc,
                phase=req.phase,
                caller=req.caller,
                asset=req.asset,
                artifact=artifact_str,
                dataset_role=role_normalized,
                purpose=req.purpose,
                access_result="DENIED",
                rows_requested=max_rows,
                rows_returned=0,
                artifact_hash="ACCESS_DENIED_BEFORE_READ",
                denial_reason=f"Firewall block: {role_normalized} is locked and inaccessible in {phase}",
            )
            append_intel_access_ledger(denial_entry, ledger_path)
            raise IntelAccessDeniedError(
                f"HOLDOUT FIREWALL: Access to {role_normalized} for {asset} is strictly forbidden. Attempt logged."
            )

        # Check authorized roles
        if role_normalized not in ("DEVELOPMENT", "VALIDATION"):
            denial_entry = IntelAccessLedgerEntry(
                timestamp_utc=req.timestamp_utc,
                phase=req.phase,
                caller=req.caller,
                asset=req.asset,
                artifact=artifact_str,
                dataset_role=role_normalized,
                purpose=req.purpose,
                access_result="DENIED",
                rows_requested=max_rows,
                rows_returned=0,
                artifact_hash="ACCESS_DENIED_INVALID_ROLE",
                denial_reason=f"Unauthorized role: {role_normalized} is not permitted for research in {phase}",
            )
            append_intel_access_ledger(denial_entry, ledger_path)
            raise IntelAccessDeniedError(f"Role {role_normalized} is not authorized for research access.")

        if artifact_path is None or not artifact_path.is_file():
            raise FileNotFoundError(f"Requested dataset artifact for {asset} ({role_normalized}) not found.")

        # Compute hash and read allowed partition
        file_hash = _compute_file_sha256(artifact_path)
        table = pq.read_table(artifact_path)
        total_rows = table.num_rows

        if max_rows is not None and max_rows < total_rows:
            returned_table = table.slice(0, max_rows)
            returned_rows = max_rows
        else:
            returned_table = table
            returned_rows = total_rows

        grant_entry = IntelAccessLedgerEntry(
            timestamp_utc=req.timestamp_utc,
            phase=req.phase,
            caller=req.caller,
            asset=req.asset,
            artifact=artifact_str,
            dataset_role=role_normalized,
            purpose=req.purpose,
            access_result="GRANTED",
            rows_requested=max_rows or total_rows,
            rows_returned=returned_rows,
            artifact_hash=file_hash,
            denial_reason=None,
        )
        append_intel_access_ledger(grant_entry, ledger_path)
        return returned_table


def audit_intel_access_ledger(ledger_path: Path = INTEL_LEDGER_PATH) -> dict[str, Any]:
    """Audits the INTEL data access ledger with full role-level accounting and reconciliation."""
    if not ledger_path.is_file():
        return {
            "ledger_exists": False,
            "total_access_attempts": 0,
            "total_granted": 0,
            "total_denied": 0,
            "dev_granted": 0,
            "val_granted": 0,
            "holdout_granted": 0,
            "pristine_granted": 0,
            "other_role_granted": 0,
            "dev_denied": 0,
            "val_denied": 0,
            "holdout_denied": 0,
            "pristine_denied": 0,
            "other_role_denied": 0,
            "granted_accesses": 0,
            "denied_accesses": 0,
            "successful_holdout_accesses": 0,
            "successful_pristine_accesses": 0,
            "accesses_by_asset": {},
            "accesses_by_role": {},
            "unrecognized_entries": 0,
            "reconciled": True,
            "audit_passed": True,
        }

    total_attempts = 0
    total_granted = 0
    total_denied = 0

    dev_granted = 0
    val_granted = 0
    holdout_granted = 0
    pristine_granted = 0
    other_granted = 0

    dev_denied = 0
    val_denied = 0
    holdout_denied = 0
    pristine_denied = 0
    other_denied = 0

    by_asset: dict[str, int] = {}
    by_role: dict[str, int] = {}
    unrecognized_entries = 0

    VALID_RESULTS = {"GRANTED", "DENIED"}
    RECOGNIZED_ROLES = {
        "DEV": {"DEVELOPMENT", "DEV"},
        "VAL": {"VALIDATION", "VAL"},
        "HOLDOUT": {"HOLDOUT", "LOCKED_HOLDOUT"},
        "PRISTINE": {"PRISTINE", "LOCKED_PROSPECTIVE_PRISTINE", "PROSPECTIVE_PRISTINE"},
        "OTHER": {"SHADOW", "PAPER", "PROSPECTIVE_FORWARD"},
    }
    ALL_VALID_ROLES = set().union(*RECOGNIZED_ROLES.values())

    with ledger_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_attempts += 1
            try:
                entry = json.loads(line)
            except Exception:
                unrecognized_entries += 1
                continue

            res = entry.get("access_result")
            role = (entry.get("dataset_role") or "").upper()
            asset = entry.get("asset", "")

            if res not in VALID_RESULTS or role not in ALL_VALID_ROLES:
                unrecognized_entries += 1
                continue

            by_asset[asset] = by_asset.get(asset, 0) + 1
            by_role[role] = by_role.get(role, 0) + 1

            if res == "GRANTED":
                total_granted += 1
                if role in RECOGNIZED_ROLES["DEV"]:
                    dev_granted += 1
                elif role in RECOGNIZED_ROLES["VAL"]:
                    val_granted += 1
                elif role in RECOGNIZED_ROLES["HOLDOUT"]:
                    holdout_granted += 1
                elif role in RECOGNIZED_ROLES["PRISTINE"]:
                    pristine_granted += 1
                elif role in RECOGNIZED_ROLES["OTHER"]:
                    other_granted += 1
            elif res == "DENIED":
                total_denied += 1
                if role in RECOGNIZED_ROLES["DEV"]:
                    dev_denied += 1
                elif role in RECOGNIZED_ROLES["VAL"]:
                    val_denied += 1
                elif role in RECOGNIZED_ROLES["HOLDOUT"]:
                    holdout_denied += 1
                elif role in RECOGNIZED_ROLES["PRISTINE"]:
                    pristine_denied += 1
                elif role in RECOGNIZED_ROLES["OTHER"]:
                    other_denied += 1

    reconciled = (
        (unrecognized_entries == 0)
        and (total_granted + total_denied == total_attempts)
        and (dev_granted + val_granted + holdout_granted + pristine_granted + other_granted == total_granted)
        and (dev_denied + val_denied + holdout_denied + pristine_denied + other_denied == total_denied)
    )
    audit_passed = reconciled and (holdout_granted == 0) and (pristine_granted == 0)

    return {
        "ledger_exists": True,
        "total_access_attempts": total_attempts,
        "total_granted": total_granted,
        "total_denied": total_denied,
        "dev_granted": dev_granted,
        "val_granted": val_granted,
        "holdout_granted": holdout_granted,
        "pristine_granted": pristine_granted,
        "other_role_granted": other_granted,
        "dev_denied": dev_denied,
        "val_denied": val_denied,
        "holdout_denied": holdout_denied,
        "pristine_denied": pristine_denied,
        "other_role_denied": other_denied,
        "granted_accesses": total_granted,
        "denied_accesses": total_denied,
        "successful_holdout_accesses": holdout_granted,
        "successful_pristine_accesses": pristine_granted,
        "accesses_by_asset": by_asset,
        "accesses_by_role": by_role,
        "unrecognized_entries": unrecognized_entries,
        "reconciled": reconciled,
        "audit_passed": audit_passed,
    }
