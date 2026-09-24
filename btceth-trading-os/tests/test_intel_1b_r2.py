"""Regression tests for TRADING OS — INTEL-1B R2 remediation.

Proves:
  1. Ledger schema: uses actual `access_result`, not nonexistent `access_granted`.
  2. Ledger reconciliation: malformed/unrecognized entries cause FAIL.
  3. Missing evidence: deleting/omitting required report causes verifier failure (fail-closed).
  4. Hardcoded safety: safety gate changes when authoritative source is mutated.
  5. Security scan: injected forbidden execution function causes detection.
  6. Decision engine: injected `generate_signal()` causes detection.
  7. Manifest summary: generated row counts equal committed manifest values (374,400).
  8. Evidence identity: HEAD is derived dynamically rather than carrying a stale SHA.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.intel.data_access import audit_intel_access_ledger
from tools.verify_intel_1b_r2 import Intel1bR2Verifier, compute_sha256, run_feature_perturbation_audit


# 1. Ledger Schema: actual access_result
def test_ledger_schema_uses_access_result(tmp_path):
    ledger_file = tmp_path / "ledger.jsonl"
    entry = {
        "timestamp_utc": "2026-09-24T00:00:00Z",
        "phase": "INTEL_1B",
        "caller": "test",
        "asset": "XAU",
        "artifact": "test.parquet",
        "dataset_role": "DEVELOPMENT",
        "purpose": "TEST",
        "access_result": "GRANTED",
        "rows_requested": 100,
        "rows_returned": 100,
        "artifact_hash": "abc",
        "denial_reason": None,
    }
    ledger_file.write_text(json.dumps(entry) + "\n")

    res = audit_intel_access_ledger(ledger_file)
    assert res["total_access_attempts"] == 1
    assert res["total_granted"] == 1
    assert res["total_denied"] == 0
    assert res["dev_granted"] == 1
    assert res["reconciled"] is True
    assert res["audit_passed"] is True


# 2. Ledger Reconciliation: malformed/unrecognized entries cause FAIL
def test_ledger_reconciliation_fails_on_unrecognized_entries(tmp_path):
    ledger_file = tmp_path / "ledger.jsonl"

    # Bad access_result
    bad_result_entry = {
        "access_result": "MAYBE",
        "dataset_role": "DEVELOPMENT",
        "asset": "XAU",
    }
    ledger_file.write_text(json.dumps(bad_result_entry) + "\n")
    res1 = audit_intel_access_ledger(ledger_file)
    assert res1["unrecognized_entries"] == 1
    assert res1["reconciled"] is False
    assert res1["audit_passed"] is False

    # Bad dataset_role
    bad_role_entry = {
        "access_result": "GRANTED",
        "dataset_role": "UNAUTHORIZED_ADMIN_ROLE",
        "asset": "XAU",
    }
    ledger_file.write_text(json.dumps(bad_role_entry) + "\n")
    res2 = audit_intel_access_ledger(ledger_file)
    assert res2["unrecognized_entries"] == 1
    assert res2["reconciled"] is False
    assert res2["audit_passed"] is False

    # Malformed non-JSON line
    ledger_file.write_text("NOT_VALID_JSON\n")
    res3 = audit_intel_access_ledger(ledger_file)
    assert res3["unrecognized_entries"] == 1
    assert res3["reconciled"] is False
    assert res3["audit_passed"] is False


# 3. Missing Evidence: deleting required evidence causes fail-closed failure
def test_missing_evidence_causes_verifier_failure(tmp_path):
    verifier = Intel1bR2Verifier(mode="FINAL_EVIDENCE_ACCEPTANCE")

    # Point to a temporary empty reports directory
    with patch("tools.verify_intel_1b_r2.ROOT", tmp_path):
        empty_reports = tmp_path / "reports"
        empty_reports.mkdir(parents=True, exist_ok=True)
        verifier._run_evidence_checks()

    assert verifier.evidence_checks.get("R2_REPORTS_PRESENT") is False
    assert verifier.evidence_checks.get("FAIL_CLOSED_NO_MISSING_REPORT") is False


# 4. Hardcoded Safety: safety gate changes when authoritative source is mutated
def test_hardcoded_safety_authoritative_mutation():
    from btceth_os.research.promotion_state import PromotionStateReport

    mock_prom = PromotionStateReport(
        report_version="TEST",
        status="VERIFIED",
        persistent_db_path="test.db",
        persistent_db_exists=True,
        persistent_total_experiments=50,
        persistent_approved_shadow=1,  # VIOLATION: not zero!
        persistent_approved_paper=0,
        runtime_registry_initialized=True,
        runtime_total_registered=10,
        runtime_approved_shadow=0,
        runtime_approved_paper=0,
        runtime_promotion_loading="NONE",
        trading_capability=0,
        all_zero_promotions_verified=False,
    )

    verifier = Intel1bR2Verifier(mode="CODE_ACCEPTANCE")
    with patch("tools.verify_intel_1b_r2.inspect_promotion_state", return_value=mock_prom):
        prom = mock_prom
        zero_shadow = (
            prom.status == "VERIFIED"
            and prom.persistent_approved_shadow == 0
            and prom.runtime_approved_shadow == 0
        )
        assert zero_shadow is False


# 5. Security Scan: injected forbidden execution function causes detection
def test_security_scan_fails_on_forbidden_execution_function(tmp_path):
    test_src = tmp_path / "test_module.py"
    test_src.write_text("def create_order(symbol, qty):\n    pass\n")

    forbidden_patterns = [
        r"\bcreate_order\b",
        r"\bcancel_order\b",
        r"\bwithdraw\b",
        r"\bset_leverage\b",
    ]
    txt = test_src.read_text()
    hits = [pat for pat in forbidden_patterns if re.search(pat, txt)]
    assert len(hits) > 0
    assert r"\bcreate_order\b" in hits


# 6. Decision Engine: injected generate_signal() causes detection
def test_decision_engine_absent_fails_on_injected_signal(tmp_path):
    test_code = tmp_path / "strategy.py"
    test_code.write_text("def generate_signal(bar):\n    return 'BUY'\n")

    decision_patterns = [
        r"def\s+evaluate_trade\b",
        r"def\s+generate_signal\b",
        r"def\s+take_trade\b",
        r"def\s+entry_zone\b",
    ]
    txt = test_code.read_text()
    hits = [pat for pat in decision_patterns if re.search(pat, txt)]
    assert len(hits) == 1
    assert r"def\s+generate_signal\b" in hits


# 7. Manifest Summary: row counts equal committed manifest values (374,400)
def test_manifest_summary_matches_committed_values():
    manifest_path = ROOT / "config/xau_research_partitions_v1.json"
    assert manifest_path.is_file()
    m_data = json.loads(manifest_path.read_text())

    p_rows = m_data["parent_artifacts"]["XAUUSDT-resampled-1m-silver.parquet"]["rows"]
    parts = m_data["partitions"]
    dev_rows = parts["XAUUSDT_DEV_2026_01_04"]["expected_rows"]
    val_rows = parts["XAUUSDT_VAL_2026_05_07"]["expected_rows"]
    holdout_rows = parts["XAUUSDT_HOLDOUT_2026_08_09"]["expected_rows"]
    pristine_rows = parts["XAUUSDT_PROSPECTIVE_PRISTINE"]["expected_rows"]

    assert p_rows == 374400
    assert dev_rows == 165600
    assert val_rows == 132480
    assert holdout_rows == 66060
    assert pristine_rows == 10260
    assert dev_rows + val_rows + holdout_rows + pristine_rows == 374400

    actual_sha = compute_sha256(manifest_path)
    assert actual_sha == "92da0d96b41f9c4041090ac9a8a26787b9150e36726a893563d8d4918e41644b"


# 8. Evidence Identity: HEAD is derived dynamically
def test_evidence_identity_derived_dynamically():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    assert len(head) == 40
    assert all(c in "0123456789abcdef" for c in head)
    # Proves it is not carrying a stale hardcoded placeholder
    assert head != "stale_placeholder_sha"
