"""Research Round 3B: Mechanical Holdout Firewall.

Enforces strict physical and logical isolation of the 2024 holdout dataset:
- Intercepts all file paths, timestamps, and queries.
- Any attempt to load, inspect, or query 2024 market data triggers immediate hard failure.
- Logs all access attempts to artifacts/research/holdout_firewall_audit.log.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
LOG_PATH = ROOT / "artifacts" / "research" / "holdout_firewall_audit.log"

HOLDOUT_START_TS_NS = 1704067200000000000  # 2024-01-01 00:00:00 UTC
FORBIDDEN_PATTERNS = [
    r"2024",
    r"2024-01", r"2024-02", r"2024-03", r"2024-04",
    r"2024-05", r"2024-06", r"2024-07", r"2024-08",
    r"2024-09", r"2024-10", r"2024-11", r"2024-12",
]


class HoldoutSecurityViolationError(RuntimeError):
    """Raised when an unauthorized attempt is made to access 2024 holdout market data."""
    pass


def log_firewall_event(event_type: str, target: str, reason: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    entry = f"[{ts}] [{event_type}] Target: {target} | Reason: {reason}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)


def enforce_path_firewall(path: str | Path) -> None:
    """Check file path against 2024 holdout access patterns."""
    p_str = str(path)
    for pat in FORBIDDEN_PATTERNS:
        # Match if path contains 2024 in a market data or parquet context
        if re.search(pat, p_str) and any(ext in p_str for ext in [".parquet", ".csv", ".zip", "klines", "funding"]):
            log_firewall_event("BLOCKED_PATH_ACCESS", p_str, f"Matched forbidden holdout pattern: {pat}")
            raise HoldoutSecurityViolationError(
                f"HOLDOUT FIREWALL VIOLATION: Access to 2024 market data artifact is strictly blocked: {p_str}"
            )


def enforce_timestamp_firewall(ts_event_ns: int) -> None:
    """Check timestamp against 2024 holdout boundary."""
    if ts_event_ns >= HOLDOUT_START_TS_NS:
        dt = datetime.fromtimestamp(ts_event_ns / 1_000_000_000, tz=timezone.utc)
        log_firewall_event("BLOCKED_TIMESTAMP_QUERY", str(ts_event_ns), f"Timestamp {dt} is inside locked 2024 holdout")
        raise HoldoutSecurityViolationError(
            f"HOLDOUT FIREWALL VIOLATION: Timestamp {ts_event_ns} ({dt}) enters locked 2024 holdout"
        )
