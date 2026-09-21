from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools.verify_round3b_reliability_v4 import (
    ROOT,
    REPORTS_DIR,
    check_oracle_ast_isolation,
    compute_canonical_payload_sha256,
    evaluate_round3b_0c_reliability,
    generate_partition_split_audit,
    generate_execution_causality_audit,
    generate_capital_config_audit,
    generate_promotion_continuity_audit,
    generate_ledger_concurrency_audit,
)


def test_oracle_ast_isolation_v4() -> None:
    """Proves oracle has strictly zero btceth_os imports."""
    ok, msg = check_oracle_ast_isolation()
    assert ok is True, msg


def test_diagnostic_mode_cannot_issue_acceptance() -> None:
    """Verifier in DIAGNOSTIC mode must fail closed and never issue acceptance."""
    all_passed, checks, status, details = evaluate_round3b_0c_reliability(mode="DIAGNOSTIC")
    assert all_passed is False
    assert status == "DIAGNOSTIC_NOT_ELIGIBLE_FOR_ACCEPTANCE"
    assert checks["SECURITY_SCAN_ZERO"] is False
    assert checks["FULL_PYTEST_PASS"] is False


def test_canonical_payload_hash_is_non_self_referential() -> None:
    """Proves canonical payload SHA-256 excludes the hash field itself and is deterministic."""
    sample = {
        "report_version": "ROUND3B.0C",
        "acceptance_status": "ROUND3B_0C_RELIABILITY = VERIFIED",
        "acceptance_payload_sha256": "placeholder_sha",
        "data": [1, 2, 3],
    }
    hash1 = compute_canonical_payload_sha256(sample)

    sample["acceptance_payload_sha256"] = "different_sha"
    hash2 = compute_canonical_payload_sha256(sample)
    assert hash1 == hash2, "Payload hash must be non-self-referential"

    sample["data"] = [1, 2, 4]
    hash3 = compute_canonical_payload_sha256(sample)
    assert hash1 != hash3


def test_supporting_audit_generators() -> None:
    """All 5 supporting audit generators run cleanly and return VERIFIED status."""
    audit_part = generate_partition_split_audit()
    assert audit_part["status"] == "VERIFIED"
    assert audit_part["total_physical_partitions"] == 8
    assert audit_part["all_physical_hashes_match"] is True

    audit_exec = generate_execution_causality_audit()
    assert audit_exec["status"] == "VERIFIED"
    assert audit_exec["causality_temporal_ordering_verified"] is True

    audit_cap = generate_capital_config_audit()
    assert audit_cap["status"] == "VERIFIED"
    assert audit_cap["fail_closed_on_missing_yaml_verified"] is True

    audit_promo = generate_promotion_continuity_audit()
    assert audit_promo["status"] == "VERIFIED"
    assert audit_promo["continuity_threshold_met"] is True

    audit_ledger = generate_ledger_concurrency_audit()
    assert audit_ledger["status"] == "VERIFIED"
    assert audit_ledger["multiprocess_test_verified"] is True


def test_core_reliability_gates_pass() -> None:
    """All core mechanical gates (1-28) pass in diagnostic evaluation."""
    all_passed, checks, status, details = evaluate_round3b_0c_reliability(mode="DIAGNOSTIC")
    
    core_gates = [
        "WIP_AUDIT_COMPLETE",
        "CANONICAL_BASELINE_ANCESTRY_VALID",
        "WIP_SAFETY_BRANCH_UNTOUCHED",
        "CANONICAL_REMOTE_UNTOUCHED",
        "INDEPENDENT_ORACLE_ISOLATED",
        "ORACLE_MULTI_FAMILY_CAMPAIGN_PASS",
        "PHYSICAL_DATASET_BINDING_VERIFIED",
        "DEV_VALIDATION_PHYSICAL_SEPARATION",
        "DEV_MAX_TIMESTAMP_PRE_2023",
        "VALIDATION_MIN_TIMESTAMP_2023",
        "VALIDATION_MAX_TIMESTAMP_PRE_2024",
        "NO_AGGREGATE_DIRECT_RESEARCH_READ",
        "ROLE_BOUNDARY_CONTAMINATION_GUARD",
        "REGISTRY_IMMUTABILITY_VERIFIED",
        "NO_PUBLIC_REGISTRY_TRUST_OVERRIDE",
        "NO_PLACEHOLDER_HASHES_VERIFIED",
        "HOLDOUT_UNREGISTERED_FOR_READ_VERIFIED",
        "DATASET_IDENTITY_REQUIRED_ENFORCED",
        "ROW_LEVEL_TIMESTAMP_CORROBORATION_VERIFIED",
        "TAMPER_EVIDENT_HASH_CHAIN_VERIFIED",
        "LEDGER_PROCESS_SAFE_CONCURRENCY",
        "EXECUTABLE_PRICE_CAUSALITY_ENFORCED",
        "NEXT_OBSERVATION_FILL_CLOCK",
        "STRICT_CAUSAL_WALK_FORWARD",
        "CAPITAL_POLICY_CANONICAL_YAML_DEFAULT",
        "CAPITAL_POLICY_CONFIG_HASH_VERIFIED",
        "PROMOTION_DB_REQUIRED_AND_CONTINUITY",
        "ZERO_PROMOTIONS_PERSISTENT_AND_RUNTIME",
    ]
    for gate in core_gates:
        assert checks[gate] is True, f"Gate {gate} failed!"
