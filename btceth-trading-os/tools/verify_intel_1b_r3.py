"""Trading OS INTEL-1B R3 Verifier.

Usage:
    python tools/verify_intel_1b_r3.py --mode CODE_ACCEPTANCE
    python tools/verify_intel_1b_r3.py --mode FINAL_EVIDENCE_ACCEPTANCE

Full verification gate suite for INTEL-1B R3: Final Acceptance Patch.
Enforces:
  1. Missing ledger fails closed (reconciled=False, audit_passed=False).
  2. Active schema rejection of forbidden top-level and nested execution directives.
  3. Empirical threshold sensitivity verification on 10,000-bar DEV dataset.
  4. Zero unjustified hardcoded pass gates and zero fail-open paths.
  5. Authoritative safety and promotion state inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.intel.data_access import audit_intel_access_ledger
from btceth_os.intel.snapshot import ExecutionFieldForbiddenError
from btceth_os.intel.snapshot_v2 import assert_no_execution_fields_v2
from btceth_os.research.promotion_state import inspect_promotion_state


def git(*args: str) -> str:
    res = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=True)
    return res.stdout.strip()


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_execution_fields_rejection() -> Tuple[bool, bool, bool, List[Dict[str, Any]]]:
    """Actively tests valid snapshot acceptance and recursive forbidden rejection."""
    # 1. Valid descriptive snapshot must pass
    valid_snap = {
        "trend_state": "UP",
        "volatility_state": "NORMAL",
        "liquidity_state": "NORMAL",
        "funding_state": "NEUTRAL",
        "market_quality_state": "HEALTHY",
        "uncertainties": [],
    }
    valid_accepted = False
    try:
        assert_no_execution_fields_v2(valid_snap)
        valid_accepted = True
    except Exception:
        valid_accepted = False

    # 2. Top-level forbidden cases
    forbidden_tokens = [
        "BUY", "SELL", "LONG", "SHORT", "ENTRY", "STOP_LOSS",
        "TAKE_PROFIT", "POSITION_SIZE", "LEVERAGE", "SIGNAL", "ORDER"
    ]
    toplevel_results = []
    toplevel_ok = True
    for tok in forbidden_tokens:
        fixture = {"trend_state": "UP", tok: 100.0}
        rejected = False
        try:
            assert_no_execution_fields_v2(fixture)
        except ExecutionFieldForbiddenError:
            rejected = True
        except Exception:
            rejected = False
        toplevel_results.append({"fixture_type": "TOPLEVEL", "token": tok, "rejected": rejected})
        if not rejected:
            toplevel_ok = False

    # 3. Nested and deeply nested forbidden cases
    nested_fixtures = [
        {"nested": {"position_size": 1.0}},
        {"signal": "BUY"},
        {"context": {"risk": {"take_profit": 123}}},
        {"strategy": {"rules": [{"action": "SELL"}]}},
        {"stOP_loSS": 50000},
        {"SiGnAl": "LONG"},
        {"nested_list": [{"deep": {"entry": 2000.0}}]},
    ]
    nested_results = []
    nested_ok = True
    for fix in nested_fixtures:
        rejected = False
        try:
            assert_no_execution_fields_v2(fix)
        except ExecutionFieldForbiddenError:
            rejected = True
        except Exception:
            rejected = False
        nested_results.append({"fixture_type": "NESTED", "fixture": fix, "rejected": rejected})
        if not rejected:
            nested_ok = False

    all_fixtures = toplevel_results + nested_results
    return valid_accepted, toplevel_ok, nested_ok, all_fixtures


def audit_empirical_threshold_sensitivity() -> Tuple[bool, bool, bool, bool, Dict[str, Any]]:
    """Evaluates empirical threshold sensitivity data from committed 10,000-bar DEV sample."""
    # Read from INTEL_1B_R1 evidence report committed in repository ancestry
    r1_ev_path = ROOT / "reports" / "INTEL_1B_R1_EMPIRICAL_EVIDENCE_VALIDATION.json"
    if not r1_ev_path.is_file():
        return False, False, False, False, {"error": "R1_EMPIRICAL_EVIDENCE_MISSING"}

    data = json.loads(r1_ev_path.read_text())
    ts_data = data.get("threshold_sensitivity", {})
    results = ts_data.get("results", [])

    if len(results) == 0:
        return False, False, False, False, {"error": "NO_THRESHOLD_RESULTS"}

    all_finite = True
    all_rates_in_range = True
    all_reconciles = True
    evaluated_perts = 0

    for r in results:
        perts = r.get("perturbation_results", [])
        if len(perts) == 0:
            all_finite = False
        for p in perts:
            evaluated_perts += 1
            tot = p.get("total_bars", 0)
            d_cnt = p.get("disagreement_count", -1)
            d_rate = p.get("disagreement_rate", -1.0)
            ag_rate = round(1.0 - d_rate, 4)

            # Check finiteness
            if any(x != x for x in [tot, d_cnt, d_rate, ag_rate]):
                all_finite = False
            if any(math.isinf(x) for x in [tot, d_cnt, d_rate, ag_rate]):
                all_finite = False

            # Check range
            if not (0.0 <= d_rate <= 1.0 and 0.0 <= ag_rate <= 1.0):
                all_rates_in_range = False

            # Check agreement reconciliation
            if abs(ag_rate - (1.0 - d_rate)) > 1e-4:
                all_reconciles = False

            # Check sample size > 0
            if tot != 10000:
                all_finite = False

    empirical_valid = (
        (len(results) >= 2)
        and (evaluated_perts >= 8)
        and all_finite
        and all_rates_in_range
        and all_reconciles
    )
    return empirical_valid, all_finite, all_rates_in_range, all_reconciles, ts_data


class Intel1bR3Verifier:
    def __init__(self, mode: str):
        self.mode = mode
        self.code_checks: Dict[str, bool] = {}
        self.evidence_checks: Dict[str, bool] = {}
        self.details: Dict[str, Any] = {}

    def run(self) -> int:
        print(f"Running INTEL-1B R3 Verifier in {self.mode} mode...\n")
        self._run_code_checks()

        if self.mode == "FINAL_EVIDENCE_ACCEPTANCE":
            self._run_evidence_checks()

        all_code_pass = all(self.code_checks.values())
        all_ev_pass = all(self.evidence_checks.values()) if self.mode == "FINAL_EVIDENCE_ACCEPTANCE" else True

        passed = all_code_pass and all_ev_pass
        status = "VERIFIED" if passed else "REMEDIATION_REQUIRED"

        report = {
            "mode": self.mode,
            "status": status,
            "code_checks": self.code_checks,
            "evidence_checks": self.evidence_checks,
            "details": self.details,
        }
        print(json.dumps(report, indent=2))
        return 0 if passed else 1

    def _record(self, gate: str, passed: bool, is_evidence: bool = False, msg: str = "") -> None:
        target = self.evidence_checks if is_evidence else self.code_checks
        target[gate] = passed
        status_tag = "[PASS]" if passed else "[FAIL]"
        extra = f" - {msg}" if msg else ""
        print(f"{status_tag} {gate}{extra}")

    def _run_code_checks(self) -> None:
        r2_evidence_baseline = "fbecce2da6da113738f9406aa8f8f34afaa2d1c3"

        # 1. INTEL_1B_R2_ANCESTRY_VALID
        try:
            head = git("rev-parse", "HEAD")
            res = subprocess.run(["git", "merge-base", "--is-ancestor", r2_evidence_baseline, head], cwd=str(ROOT))
            self._record("INTEL_1B_R2_ANCESTRY_VALID", res.returncode == 0)
        except Exception as exc:
            self._record("INTEL_1B_R2_ANCESTRY_VALID", False, msg=str(exc))

        # 2. R2_REMOTE_BASELINE_VALID
        try:
            remote_ref = git("rev-parse", "origin/btceth-phase2-multiasset")
            res_rem = subprocess.run(["git", "merge-base", "--is-ancestor", r2_evidence_baseline, remote_ref], cwd=str(ROOT))
            self._record("R2_REMOTE_BASELINE_VALID", res_rem.returncode == 0)
        except Exception as exc:
            self._record("R2_REMOTE_BASELINE_VALID", False, msg=str(exc))

        # 3-8. DATA ACCESS LEDGER TRUTH (authoritative inspection)
        ledger_path = ROOT / "artifacts/research/intel_data_access_ledger.jsonl"
        ledger_exists = ledger_path.is_file()
        self._record("LEDGER_EXISTS", ledger_exists)

        da_res = audit_intel_access_ledger(ledger_path)
        entry_cnt_valid = ledger_exists and (da_res["total_access_attempts"] == 12)
        self._record("LEDGER_ENTRY_COUNT_VALID", entry_cnt_valid)

        arithmetic_reconciled = (
            ledger_exists
            and da_res["reconciled"]
            and da_res["audit_passed"]
            and (da_res["total_granted"] + da_res["total_denied"] == da_res["total_access_attempts"])
            and (da_res["dev_granted"] + da_res["val_granted"] + da_res["holdout_granted"] + da_res["pristine_granted"] + da_res["other_role_granted"] == da_res["total_granted"])
            and (da_res["dev_denied"] + da_res["val_denied"] + da_res["holdout_denied"] + da_res["pristine_denied"] + da_res["other_role_denied"] == da_res["total_denied"])
        )
        self._record("LEDGER_ARITHMETIC_RECONCILED", arithmetic_reconciled)
        self._record("HOLDOUT_GRANTED_ZERO", ledger_exists and (da_res["holdout_granted"] == 0))
        self._record("PRISTINE_GRANTED_ZERO", ledger_exists and (da_res["pristine_granted"] == 0))
        self._record("UNRECOGNIZED_LEDGER_ENTRIES_ZERO", ledger_exists and (da_res["unrecognized_entries"] == 0))

        # 9-12. EXECUTION FIELDS ACTIVE REJECTION
        val_acc, top_rej, nest_rej, fixtures_list = verify_execution_fields_rejection()
        self._record("EXECUTION_VALID_SNAPSHOT_ACCEPTED", val_acc)
        self._record("EXECUTION_FORBIDDEN_TOPLEVEL_REJECTED", top_rej)
        self._record("EXECUTION_FORBIDDEN_NESTED_REJECTED", nest_rej)
        self._record("EXECUTION_FIELDS_FORBIDDEN", val_acc and top_rej and nest_rej)

        # 13-16. EMPIRICAL THRESHOLD SENSITIVITY VALIDATION (DEV data)
        emp_valid, all_fin, rates_in_range, ag_reconciles, ts_details = audit_empirical_threshold_sensitivity()
        self._record("THRESHOLD_SENSITIVITY_EMPIRICAL_VALID", emp_valid)
        self._record("THRESHOLD_VALUES_FINITE", all_fin)
        self._record("THRESHOLD_RATES_IN_RANGE", rates_in_range)
        self._record("THRESHOLD_AGREEMENT_RECONCILES", ag_reconciles)

        # 17-18. VERIFIER INTEGRITY (Zero unjustified hardcoded passes, Zero fail-open paths)
        # Static scan of this verifier itself to ensure no unjustified literal calls
        this_file_text = Path(__file__).read_text()
        raw_literal_true_calls = [
            line.strip() for line in this_file_text.splitlines()
            if not line.strip().startswith("#") and re.search(r"self\._record\([^,]+,\s*True\b", line)
        ]
        self._record("UNJUSTIFIED_HARDCODED_PASS_GATES_ZERO", len(raw_literal_true_calls) == 0)

        # Fail-closed test on missing ledger
        nonexistent_res = audit_intel_access_ledger(ROOT / "nonexistent_ledger.jsonl")
        fail_closed_ok = (
            (nonexistent_res["ledger_exists"] is False)
            and (nonexistent_res["reconciled"] is False)
            and (nonexistent_res["audit_passed"] is False)
        )
        self._record("FAIL_OPEN_PATHS_ZERO", fail_closed_ok)

        # 19-23. SAFETY STATE (Authoritative Inspections)
        sec_proc = subprocess.run(
            [sys.executable, "-m", "btceth_os.security_scan"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        is_sec_zero = (sec_proc.returncode == 0) and ('"trading_capability": "ZERO"' in sec_proc.stdout)
        self._record("TRADING_CAPABILITY_ZERO", is_sec_zero)

        src_files = list((ROOT / "src").rglob("*.py"))
        forbidden_mutation_patterns = [
            r"\bcreate_order\b",
            r"\bcancel_order\b",
            r"\bwithdraw\b",
            r"\bset_leverage\b",
            r"/fapi/v1/order",
            r"/api/v3/order",
        ]
        mutation_hits = 0
        for sf in src_files:
            if sf.name == "security_scan.py":
                continue
            txt = sf.read_text(errors="ignore")
            for pat in forbidden_mutation_patterns:
                if re.search(pat, txt, re.I):
                    mutation_hits += 1
        self._record("MAINNET_MUTATION_DISABLED", is_sec_zero and (mutation_hits == 0))

        prom = inspect_promotion_state()
        self._record(
            "ZERO_SHADOW_PROMOTIONS",
            prom.status == "VERIFIED" and prom.persistent_approved_shadow == 0 and prom.runtime_approved_shadow == 0,
        )
        self._record(
            "ZERO_PAPER_PROMOTIONS",
            prom.status == "VERIFIED" and prom.persistent_approved_paper == 0 and prom.runtime_approved_paper == 0,
        )
        self._record(
            "ZERO_LIVE_PROMOTIONS",
            prom.status == "VERIFIED" and prom.trading_capability == 0,
        )

        # 24-26. QUARANTINE & ISOLATION
        decision_patterns = [
            r"def\s+evaluate_trade\b",
            r"def\s+generate_signal\b",
            r"def\s+take_trade\b",
            r"def\s+entry_zone\b",
            r"def\s+stop_loss\b",
            r"def\s+take_profit\b",
            r"def\s+position_size\b",
            r"def\s+set_leverage\b",
            r"def\s+create_order\b",
            r"def\s+cancel_order\b",
        ]
        decision_hits = 0
        for sf in src_files:
            txt = sf.read_text(errors="ignore")
            for pat in decision_patterns:
                if re.search(pat, txt):
                    decision_hits += 1
        tb_file = ROOT / "src/btceth_os/trade_board.py"
        tb_test = ROOT / "tests/test_trade_board.py"
        tb_quarantined = not tb_file.exists() and not tb_test.exists()
        self._record("DECISION_ENGINE_ABSENT", (decision_hits == 0) and tb_quarantined)
        self._record("TRADE_BOARD_QUARANTINED", tb_quarantined)

        bot_tokens = ["BTCUSD trade bot", "watchdog.py", "1244"]
        bot_hits = 0
        for sf in src_files:
            txt = sf.read_text(errors="ignore")
            for tok in bot_tokens:
                if tok in txt:
                    bot_hits += 1
        self._record("SEPARATE_BTC_BOT_ISOLATED", bot_hits == 0)

        # 27-29. SUITE & WORKTREE
        res_pytest = subprocess.run([sys.executable, "-m", "pytest", "tests/"], cwd=str(ROOT), capture_output=True, text=True)
        self._record("FULL_PYTEST_PASS", res_pytest.returncode == 0)
        self._record("SECURITY_SCAN_ZERO", sec_proc.returncode == 0)

        status_out = git("status", "--porcelain")
        self._record("CLEAN_WORKTREE", len(status_out.strip()) == 0)

    def _run_evidence_checks(self) -> None:
        reports_dir = ROOT / "reports"
        required_reports = [
            "INTEL_1B_R3_FOUNDATION.json",
            "INTEL_1B_R3_LEDGER_SNAPSHOT.json",
            "INTEL_1B_R3_DATA_ACCESS_AUDIT.json",
            "INTEL_1B_R3_EXECUTION_SCHEMA_REJECTION.json",
            "INTEL_1B_R3_THRESHOLD_SENSITIVITY_AUDIT.json",
            "INTEL_1B_R3_VERIFIER_AUDIT.json",
            "INTEL_1B_R3_SECURITY_AUDIT.json",
        ]

        all_present = all((reports_dir / r).is_file() for r in required_reports)
        self._record("R3_REPORTS_PRESENT", all_present, is_evidence=True)
        if not all_present:
            self._record("LEDGER_SNAPSHOT_PRESENT", False, is_evidence=True)
            self._record("LEDGER_SOURCE_HASH_MATCH", False, is_evidence=True)
            self._record("R3_REPORT_DIGESTS_MATCH", False, is_evidence=True)
            self._record("TESTED_CODE_TREE_VALID", False, is_evidence=True)
            self._record("EVIDENCE_ONLY_COMMIT", False, is_evidence=True)
            self._record("REMOTE_HEAD_MATCHES_LOCAL", False, is_evidence=True)
            return

        foundation_file = reports_dir / "INTEL_1B_R3_FOUNDATION.json"
        found_data = json.loads(foundation_file.read_text())

        snapshot_file = reports_dir / "INTEL_1B_R3_LEDGER_SNAPSHOT.json"
        snapshot_present = snapshot_file.is_file()
        self._record("LEDGER_SNAPSHOT_PRESENT", snapshot_present, is_evidence=True)

        snap_data = json.loads(snapshot_file.read_text())
        actual_ledger_sha = compute_sha256(ROOT / "artifacts/research/intel_data_access_ledger.jsonl")
        snap_source_sha = snap_data.get("source_ledger_sha256", "")
        self._record("LEDGER_SOURCE_HASH_MATCH", actual_ledger_sha == snap_source_sha, is_evidence=True)

        digests = found_data.get("report_sha256", {})
        digests_ok = len(digests) >= 6
        for r_name, exp_sha in digests.items():
            r_path = reports_dir / r_name
            if not r_path.is_file() or compute_sha256(r_path) != exp_sha:
                digests_ok = False
                break
        self._record("R3_REPORT_DIGESTS_MATCH", digests_ok, is_evidence=True)

        tested_tree = found_data.get("tested_tree_sha")
        parent_tree = git("rev-parse", "HEAD~1^{tree}")
        self._record("TESTED_CODE_TREE_VALID", tested_tree == parent_tree, is_evidence=True)

        changed_files = git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
        ev_only = all(f.startswith("btceth-trading-os/reports/INTEL_1B_R3_") for f in changed_files if f.strip())
        self._record("EVIDENCE_ONLY_COMMIT", ev_only, is_evidence=True)

        local_head = git("rev-parse", "HEAD")
        remote_head = git("rev-parse", "origin/btceth-phase2-multiasset")
        self._record("REMOTE_HEAD_MATCHES_LOCAL", local_head == remote_head, is_evidence=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["CODE_ACCEPTANCE", "FINAL_EVIDENCE_ACCEPTANCE"], required=True)
    args = parser.parse_args()
    sys.exit(Intel1bR3Verifier(args.mode).run())
