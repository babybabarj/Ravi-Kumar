from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from tools.verify_round3b_reliability import (
    ROOT,
    REPORTS_DIR,
    check_oracle_ast_isolation,
    check_gap_forensics_descriptive,
    evaluate_round3b_reliability,
)


def test_round3b_reliability_after_canonical_promotion() -> None:
    """The historical verifier detects the intentional canonical promotion."""
    all_passed, checks, status, details = evaluate_round3b_reliability(skip_sub_tests=True)
    assert all_passed is False
    assert {k for k, passed in checks.items() if not passed} == {"CANONICAL_REMOTE_UNTOUCHED"}
    assert status == "REMEDIATION_REQUIRED"
    assert subprocess.check_output(["git", "rev-parse", "origin/btceth-phase1b"], cwd=ROOT, text=True).strip() == (
        "fb2d2c1f25f199ea040212fe683e64776754b805"
    )


def test_oracle_ast_isolation_positive() -> None:
    """Positive test: independent accounting oracle imports zero btceth_os modules."""
    ok, msg = check_oracle_ast_isolation()
    assert ok is True, msg


def test_gap_forensics_descriptive_positive() -> None:
    """Positive test: gap forensics report is purely descriptive with dynamic counts."""
    ok, msg = check_gap_forensics_descriptive()
    assert ok is True, msg


def test_round3b_reliability_wip_tamper_negative(tmp_path: Path) -> None:
    """Negative test: if WIP audit has COPY_AS_IS > 0, verifier fails closed."""
    tmp_reports = tmp_path / "reports"
    shutil.copytree(REPORTS_DIR, tmp_reports)

    audit_file = tmp_reports / "ROUND3B_WIP_INDEPENDENT_AUDIT.json"
    data = json.loads(audit_file.read_text(encoding="utf-8"))
    data["classifications_summary"]["COPY_AS_IS"] = 1
    audit_file.write_text(json.dumps(data), encoding="utf-8")

    all_passed, checks, status, details = evaluate_round3b_reliability(
        skip_sub_tests=True,
        override_reports_dir=tmp_reports,
    )
    assert all_passed is False
    assert checks["WIP_AUDIT_COMPLETE"] is False
    assert status == "REMEDIATION_REQUIRED"


def test_round3b_reliability_oracle_tamper_negative(tmp_path: Path) -> None:
    """Negative test: if oracle report has discrepancies > 0, verifier fails closed."""
    tmp_reports = tmp_path / "reports"
    shutil.copytree(REPORTS_DIR, tmp_reports)

    oracle_file = tmp_reports / "ROUND3B_ACCOUNTING_ORACLE_V2.json"
    data = json.loads(oracle_file.read_text(encoding="utf-8"))
    data["discrepancies_count"] = 1
    oracle_file.write_text(json.dumps(data), encoding="utf-8")

    all_passed, checks, status, details = evaluate_round3b_reliability(
        skip_sub_tests=True,
        override_reports_dir=tmp_reports,
    )
    assert all_passed is False
    assert checks["ORACLE_RECONCILIATION_PASS"] is False
    assert status == "REMEDIATION_REQUIRED"


def test_round3b_reliability_capital_tamper_negative(tmp_path: Path) -> None:
    """Negative test: if scale down is enabled in capital report, verifier fails closed."""
    tmp_reports = tmp_path / "reports"
    shutil.copytree(REPORTS_DIR, tmp_reports)

    cap_file = tmp_reports / "ROUND3B_CAPITAL_AUDIT.json"
    data = json.loads(cap_file.read_text(encoding="utf-8"))
    data["scale_down_policy"] = "ENABLED"
    cap_file.write_text(json.dumps(data), encoding="utf-8")

    all_passed, checks, status, details = evaluate_round3b_reliability(
        skip_sub_tests=True,
        override_reports_dir=tmp_reports,
    )
    assert all_passed is False
    assert checks["CAPITAL_GOVERNOR_PASS"] is False
    assert status == "REMEDIATION_REQUIRED"
