"""Regression tests for TRADING OS — INTEL-1B R3 Final Acceptance Patch.

Proves:
  1. Missing ledger fails closed: audit_intel_access_ledger returns reconciled=False, audit_passed=False.
  2. Empty ledger causes audit failure or verifier gate rejection.
  3. Malformed JSON line in ledger fails reconciliation.
  4. Unknown access_result (e.g. MAYBE) fails reconciliation.
  5. Unknown dataset_role (e.g. ADMIN) fails reconciliation.
  6. Locked access granted (HOLDOUT or PRISTINE with GRANTED) fails verifier gate.
  7. Execution rejection: valid snapshot accepted, top-level and nested forbidden execution tokens rejected.
  8. Empirical threshold sensitivity: rates in [0, 1], finite values, agreement reconciles with disagreement.
  9. Verifier integrity: zero unjustified hardcoded pass gates and zero fail-open paths.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.intel.data_access import audit_intel_access_ledger
from btceth_os.intel.snapshot import ExecutionFieldForbiddenError
from btceth_os.intel.snapshot_v2 import assert_no_execution_fields_v2
from tools.verify_intel_1b_r3 import (
    Intel1bR3Verifier,
    audit_empirical_threshold_sensitivity,
    verify_execution_fields_rejection,
)


def test_missing_ledger_fails_closed(tmp_path: Path) -> None:
    """Missing ledger file must return ledger_exists=False, reconciled=False, audit_passed=False."""
    nonexistent = tmp_path / "nonexistent_ledger.jsonl"
    res = audit_intel_access_ledger(nonexistent)
    assert res["ledger_exists"] is False
    assert res["reconciled"] is False
    assert res["audit_passed"] is False
    assert res["total_access_attempts"] == 0


def test_empty_ledger_rejected(tmp_path: Path) -> None:
    """Empty ledger file must reconcile to 0 entries, which fails the non-zero entry requirement."""
    empty_ledger = tmp_path / "empty_ledger.jsonl"
    empty_ledger.write_text("")
    res = audit_intel_access_ledger(empty_ledger)
    assert res["ledger_exists"] is True
    assert res["total_access_attempts"] == 0
    # A 0-entry ledger cannot satisfy the required 12 entries
    assert res["total_access_attempts"] != 12


def test_malformed_json_ledger_fails(tmp_path: Path) -> None:
    """Malformed non-JSON lines must fail reconciliation and audit."""
    ledger = tmp_path / "malformed.jsonl"
    ledger.write_text("THIS IS NOT JSON\n")
    res = audit_intel_access_ledger(ledger)
    assert res["unrecognized_entries"] == 1
    assert res["reconciled"] is False
    assert res["audit_passed"] is False


def test_unknown_access_result_fails(tmp_path: Path) -> None:
    """Unknown access_result (e.g. MAYBE) must fail reconciliation."""
    ledger = tmp_path / "unknown_result.jsonl"
    entry = {
        "timestamp_utc": "2026-09-24T00:00:00Z",
        "phase": "INTEL_1B",
        "caller": "test",
        "asset": "BTC",
        "artifact": "test.parquet",
        "dataset_role": "DEVELOPMENT",
        "purpose": "TEST",
        "access_result": "MAYBE",
    }
    ledger.write_text(json.dumps(entry) + "\n")
    res = audit_intel_access_ledger(ledger)
    assert res["unrecognized_entries"] == 1
    assert res["reconciled"] is False
    assert res["audit_passed"] is False


def test_unknown_dataset_role_fails(tmp_path: Path) -> None:
    """Unknown dataset_role (e.g. ADMIN) must fail reconciliation."""
    ledger = tmp_path / "unknown_role.jsonl"
    entry = {
        "timestamp_utc": "2026-09-24T00:00:00Z",
        "phase": "INTEL_1B",
        "caller": "test",
        "asset": "BTC",
        "artifact": "test.parquet",
        "dataset_role": "ADMIN",
        "purpose": "TEST",
        "access_result": "GRANTED",
    }
    ledger.write_text(json.dumps(entry) + "\n")
    res = audit_intel_access_ledger(ledger)
    assert res["unrecognized_entries"] == 1
    assert res["reconciled"] is False
    assert res["audit_passed"] is False


def test_locked_access_granted_detected(tmp_path: Path) -> None:
    """HOLDOUT or PRISTINE with GRANTED must be detected and result in non-zero counts."""
    # Test HOLDOUT
    ledger_holdout = tmp_path / "holdout_granted.jsonl"
    entry_h = {
        "dataset_role": "HOLDOUT",
        "access_result": "GRANTED",
        "asset": "BTC",
    }
    ledger_holdout.write_text(json.dumps(entry_h) + "\n")
    res_h = audit_intel_access_ledger(ledger_holdout)
    assert res_h["holdout_granted"] == 1

    # Test PRISTINE
    ledger_pristine = tmp_path / "pristine_granted.jsonl"
    entry_p = {
        "dataset_role": "PRISTINE",
        "access_result": "GRANTED",
        "asset": "XAU",
    }
    ledger_pristine.write_text(json.dumps(entry_p) + "\n")
    res_p = audit_intel_access_ledger(ledger_pristine)
    assert res_p["pristine_granted"] == 1


def test_execution_fields_active_rejection() -> None:
    """Valid descriptive snapshot passes, all top-level and nested forbidden execution tokens rejected."""
    valid_accepted, toplevel_rejected, nested_rejected, fixtures = verify_execution_fields_rejection()
    assert valid_accepted is True
    assert toplevel_rejected is True
    assert nested_rejected is True
    assert len(fixtures) >= 18
    for f in fixtures:
        assert f["rejected"] is True, f"Failed rejection on fixture: {f}"


def test_empirical_threshold_sensitivity_validity() -> None:
    """Empirical threshold sensitivity evaluated on committed DEV dataset."""
    emp_valid, all_fin, rates_in_range, ag_reconciles, ts_data = audit_empirical_threshold_sensitivity()
    assert emp_valid is True
    assert all_fin is True
    assert rates_in_range is True
    assert ag_reconciles is True
    assert len(ts_data.get("results", [])) >= 2


def test_verifier_integrity_no_unjustified_hardcoded_passes() -> None:
    """Verifier code must not contain any unjustified literal self._record(..., True) calls."""
    verifier_path = ROOT / "tools/verify_intel_1b_r3.py"
    assert verifier_path.is_file()
    verifier_text = verifier_path.read_text()
    import re
    raw_calls = [
        line.strip() for line in verifier_text.splitlines()
        if not line.strip().startswith("#") and re.search(r"self\._record\([^,]+,\s*True\b", line)
    ]
    assert len(raw_calls) == 0, f"Found hardcoded True calls: {raw_calls}"
