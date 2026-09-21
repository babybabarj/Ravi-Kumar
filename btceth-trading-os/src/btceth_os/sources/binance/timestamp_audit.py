from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema_inspector import SchemaInspector, normalize_timestamp


class TimestampPolicyError(ValueError):
    """Raised when timestamp digit count or policy does not match expectation."""
    pass


@dataclass(frozen=True)
class TimestampPolicyVerificationResult:
    dataset_id: str
    symbol: str
    market: str
    period_key: str
    declared_policy_unit: str
    first_raw_timestamp: int | None
    first_normalized_utc: str | None
    last_raw_timestamp: int | None
    last_normalized_utc: str | None
    digits_observed: int | None
    policy_compliant: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TimestampPolicyAuditor:
    """Verifies that archive timestamps comply with declared policy (Spot ms/us split, USD-M fixed ms)."""

    @staticmethod
    def expected_policy_unit(market: str, period_key: str) -> str:
        """Determines expected unit based on canonical rules:
        - Spot: 'ms' before 2025; 'us' from 2025-01-01 onward
        - USD-M: 'ms' across all dates
        """
        if market == "spot":
            # Extract year from period_key (e.g. '2024-12' or '2025-01-01')
            year_str = period_key.split("-")[0]
            try:
                year = int(year_str)
                return "us" if year >= 2025 else "ms"
            except ValueError:
                return "ms"
        elif market == "usdm":
            return "ms"
        else:
            raise ValueError(f"Unknown market kind: {market}")

    @staticmethod
    def audit_file(
        file_path: Path,
        dataset_id: str,
        symbol: str,
        market: str,
        period_key: str,
    ) -> TimestampPolicyVerificationResult:
        expected_unit = TimestampPolicyAuditor.expected_policy_unit(market, period_key)
        probe = SchemaInspector.run_quality_probe(file_path, dataset_id, expected_unit=expected_unit)

        first_raw = probe.first_timestamp_raw
        last_raw = probe.last_timestamp_raw
        if first_raw is None:
            return TimestampPolicyVerificationResult(
                dataset_id=dataset_id,
                symbol=symbol,
                market=market,
                period_key=period_key,
                declared_policy_unit=expected_unit,
                first_raw_timestamp=None,
                first_normalized_utc=None,
                last_raw_timestamp=None,
                last_normalized_utc=None,
                digits_observed=None,
                policy_compliant=True,
                notes="Empty file, no timestamps to verify",
            )

        digits = len(str(first_raw))
        compliant = False
        notes = ""

        if expected_unit == "ms":
            compliant = (digits == 13)
            notes = "Valid 13-digit millisecond timestamp" if compliant else f"Expected 13 digits for ms, observed {digits}"
        elif expected_unit == "us":
            compliant = (digits == 16)
            notes = "Valid 16-digit microsecond timestamp" if compliant else f"Expected 16 digits for us, observed {digits}"

        return TimestampPolicyVerificationResult(
            dataset_id=dataset_id,
            symbol=symbol,
            market=market,
            period_key=period_key,
            declared_policy_unit=expected_unit,
            first_raw_timestamp=first_raw,
            first_normalized_utc=probe.first_timestamp_utc,
            last_raw_timestamp=last_raw,
            last_normalized_utc=probe.last_timestamp_utc,
            digits_observed=digits,
            policy_compliant=compliant,
            notes=notes,
        )
