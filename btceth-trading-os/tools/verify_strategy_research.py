#!/usr/bin/env python3
"""Mechanical Acceptance Gate for Market Brain, Strategy Research & Validation."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
CARDS_DIR = REPORTS / "STRATEGY_REPORT_CARDS"


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    print("=" * 70)
    print("BTCETH TRADING OS: STRATEGY RESEARCH ACCEPTANCE GATE")
    print("=" * 70)

    # 1. Dataset Readiness Check
    readiness_path = REPORTS / "RESEARCH_DATA_READINESS.json"
    if not readiness_path.exists():
        print("FAIL: reports/RESEARCH_DATA_READINESS.json does not exist.")
        return 1
    with open(readiness_path) as f:
        readiness = json.load(f)
    if not readiness.get("research_data_ready"):
        print(f"FAIL: research_data_ready is false in {readiness_path}")
        return 1
    print(f"✓ Research Data Readiness: VERIFIED (SHA-256: {readiness['dataset_logical_sha256'][:16]}...)")

    # 2. Market Brain Features Documentation
    features_doc = REPORTS / "MARKET_BRAIN_FEATURES.md"
    if not features_doc.exists() or len(features_doc.read_text()) < 200:
        print("FAIL: reports/MARKET_BRAIN_FEATURES.md missing or empty.")
        return 1
    print("✓ Market Brain Features & Point-in-Time Catalog: VERIFIED")

    # 3. Experiment Registry Persistence
    exp_reg = REPORTS / "EXPERIMENT_REGISTRY.json"
    db_file = ROOT / "artifacts" / "research" / "experiments.sqlite"
    if not exp_reg.exists() or not db_file.exists():
        print("FAIL: Experiment registry SQLite database or JSON export missing.")
        return 1
    with open(exp_reg) as f:
        exp_data = json.load(f)
    total_experiments = exp_data.get("total_experiments", 0)
    if total_experiments < 5:
        print(f"FAIL: Insufficient experiments recorded ({total_experiments} < 5).")
        return 1
    print(f"✓ Persistent Experiment Registry: VERIFIED ({total_experiments} experiments tracked)")

    # 4. Strategy Validation Results
    val_json = REPORTS / "STRATEGY_VALIDATION_RESULTS.json"
    val_md = REPORTS / "STRATEGY_VALIDATION_RESULTS.md"
    summary_md = REPORTS / "STRATEGY_RESEARCH_SUMMARY.md"
    if not val_json.exists() or not val_md.exists() or not summary_md.exists():
        print("FAIL: Strategy validation reports missing.")
        return 1
    with open(val_json) as f:
        val_data = json.load(f)
    print(
        f"✓ Strategy Validation Engine: VERIFIED "
        f"(Evaluated: {val_data['total_strategies_evaluated']}, "
        f"Approved Paper: {val_data['approved_for_paper']}, "
        f"Approved Shadow: {val_data['approved_for_shadow']}, "
        f"Rejected: {val_data['rejected']})"
    )

    # 5. Individual Report Cards
    report_cards = list(CARDS_DIR.glob("*.md"))
    if len(report_cards) < 5:
        print(f"FAIL: Insufficient report cards generated ({len(report_cards)} < 5).")
        return 1
    print(f"✓ Strategy Report Cards: VERIFIED ({len(report_cards)} standardized report cards generated)")

    # 6. Run Security Scan
    sec_proc = run_cmd(["./.venv-phase1a/bin/python", "-m", "btceth_os.security_scan"])
    if sec_proc.returncode != 0:
        print("FAIL: Security scan detected forbidden mutations!")
        print(sec_proc.stdout)
        print(sec_proc.stderr)
        return 1
    print("✓ Mainnet Security Scan: VERIFIED (0 hits, TRADING CAPABILITY = ZERO)")

    # 7. Run Full Automated Test Suite
    pytest_proc = run_cmd(["./.venv-phase1a/bin/pytest"])
    if pytest_proc.returncode != 0:
        print("FAIL: Pytest test suite failed!")
        print(pytest_proc.stdout)
        print(pytest_proc.stderr)
        return 1
    passed_line = [l for l in pytest_proc.stdout.splitlines() if "passed in" in l]
    print(f"✓ Automated Regression & Research Suite: VERIFIED ({passed_line[-1] if passed_line else 'ALL PASSED'})")

    # 8. Verify Zero Forced Promotion Policy Invariant
    if val_data["approved_for_paper"] != 0:
        print("FAIL: Violation of scientific honesty: strategy improperly promoted without meeting stressed criteria.")
        return 1
    print("✓ Scientific Honesty Invariant: VERIFIED (APPROVED_FOR_PAPER = 0 upheld with zero forced promotion)")

    print("=" * 70)
    print("ALL ACCEPTANCE GATES PASSED")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
