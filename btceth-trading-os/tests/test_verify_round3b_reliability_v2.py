from __future__ import annotations

import json
import pytest
from pathlib import Path

from tools.verify_round3b_reliability_v2 import (
    ROOT,
    REPORTS_DIR,
    check_oracle_ast_isolation,
    check_gap_forensics_descriptive,
    evaluate_round3b_0a_reliability,
    compute_canonical_payload_sha256,
)


def test_oracle_ast_isolation_v2() -> None:
    """Proves oracle has strictly zero btceth_os imports."""
    ok, msg = check_oracle_ast_isolation()
    assert ok is True, msg


def test_gap_forensics_descriptive_v2() -> None:
    """Proves gap forensics report contains no unsupported causal assertions."""
    ok, msg = check_gap_forensics_descriptive()
    assert ok is True, msg


def test_diagnostic_mode_cannot_issue_acceptance() -> None:
    """Verifier in DIAGNOSTIC mode must fail closed and never issue acceptance."""
    all_passed, checks, status, details = evaluate_round3b_0a_reliability(mode="DIAGNOSTIC")
    assert all_passed is False
    assert status == "DIAGNOSTIC_NOT_ELIGIBLE_FOR_ACCEPTANCE"
    assert checks["SECURITY_SCAN_ZERO"] is False
    assert checks["FULL_PYTEST_PASS"] is False


def test_canonical_payload_hash_is_non_self_referential() -> None:
    """Proves canonical payload SHA-256 excludes the hash field itself and is deterministic."""
    sample = {
        "report_version": "ROUND3B.0A",
        "acceptance_status": "ROUND3B_0A_RELIABILITY = VERIFIED",
        "acceptance_payload_sha256": "placeholder_sha",
        "arbitrary_data": [1, 2, 3],
    }
    hash1 = compute_canonical_payload_sha256(sample)
    
    # Mutating acceptance_payload_sha256 in sample does NOT alter the computed hash
    sample["acceptance_payload_sha256"] = "different_sha"
    hash2 = compute_canonical_payload_sha256(sample)
    assert hash1 == hash2, "Payload hash must be non-self-referential"

    # Mutating other fields DOES alter the computed hash
    sample["arbitrary_data"] = [1, 2, 4]
    hash3 = compute_canonical_payload_sha256(sample)
    assert hash1 != hash3


def test_zero_forced_promotion_derived_mechanically() -> None:
    """Verify ZERO_FORCED_PROMOTION_DERIVED is mechanically queried from StrategyRegistry."""
    from btceth_os.autopilot.strategy_registry import StrategyRegistry
    reg = StrategyRegistry()
    assert len(reg.get_approved_for_paper()) == 0
    assert len(reg.get_approved_for_shadow()) == 0
