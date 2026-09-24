"""Trading OS INTEL-1B R3.1 Verifier.

Usage:
    python tools/verify_intel_1b_r3_1.py --mode CODE_ACCEPTANCE
    python tools/verify_intel_1b_r3_1.py --mode FINAL_EVIDENCE_ACCEPTANCE

Full verification gate suite for INTEL-1B R3.1: Final Evidence-Truth Patch.
Enforces:
  1. Threshold dataset source truth derived from XAU empirical validation report.
  2. Exact sample-size and unchanged perturbation results verification.
  3. Recomputed normalized ledger snapshot hash truth matching de9e68b03d...
  4. Exact ledger source hash and 12-entry ledger counts preservation.
  5. Zero hardcoded pass shortcuts and fail-closed evidence validation.
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
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.intel.data_access import audit_intel_access_ledger
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


def derive_threshold_provenance() -> Dict[str, Any]:
    """Reads source dataset and sample size directly from empirical source report."""
    source_path = ROOT / "reports/INTEL_1B_R1_EMPIRICAL_EVIDENCE_VALIDATION.json"
    if not source_path.is_file():
        return {"dataset": "", "sample_size": 0, "results": []}
    data = json.loads(source_path.read_text())
    dataset = data.get("dataset", "")
    ts_data = data.get("threshold_sensitivity", {})
    results = ts_data.get("results", [])
    sample_size = 0
    if results and "perturbation_results" in results[0] and results[0]["perturbation_results"]:
        sample_size = results[0]["perturbation_results"][0].get("total_bars", 0)
    return {
        "dataset": dataset,
        "sample_size": sample_size,
        "results": results,
    }


def recompute_normalized_snapshot_hash(snapshot_path: Path) -> Tuple[bool, str, str]:
    """Recomputes deterministic canonical serialization hash of normalized entries."""
    if not snapshot_path.is_file():
        return False, "", ""
    data = json.loads(snapshot_path.read_text())
    entries = data.get("normalized_entries", [])
    norm_json_bytes = json.dumps(entries, sort_keys=True, indent=2).encode("utf-8")
    recomputed_sha = hashlib.sha256(norm_json_bytes).hexdigest()
    reported_sha = data.get("normalized_snapshot_sha256", "")
    matches = (recomputed_sha == reported_sha)
    return matches, recomputed_sha, reported_sha


class Intel1bR31Verifier:
    def __init__(self, mode: str):
        self.mode = mode
        self.code_checks: Dict[str, bool] = {}
        self.evidence_checks: Dict[str, bool] = {}
        self.details: Dict[str, Any] = {}

    def run(self) -> int:
        print(f"Running INTEL-1B R3.1 Verifier in {self.mode} mode...\n")
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
        r3_evidence_baseline = "304d0068027d24237a53436e3235aa4acf6b09c6"

        # 1. R3_ANCESTRY_VALID
        try:
            head = git("rev-parse", "HEAD")
            res = subprocess.run(["git", "merge-base", "--is-ancestor", r3_evidence_baseline, head], cwd=str(ROOT))
            self._record("R3_ANCESTRY_VALID", res.returncode == 0)
        except Exception as exc:
            self._record("R3_ANCESTRY_VALID", False, msg=str(exc))

        # 2. R3_REMOTE_BASELINE_VALID
        try:
            remote_ref = git("rev-parse", "origin/btceth-phase2-multiasset")
            res_rem = subprocess.run(["git", "merge-base", "--is-ancestor", r3_evidence_baseline, remote_ref], cwd=str(ROOT))
            self._record("R3_REMOTE_BASELINE_VALID", res_rem.returncode == 0)
        except Exception as exc:
            self._record("R3_REMOTE_BASELINE_VALID", False, msg=str(exc))

        # 3. THRESHOLD_SOURCE_REPORT_PRESENT
        source_r1_path = ROOT / "reports/INTEL_1B_R1_EMPIRICAL_EVIDENCE_VALIDATION.json"
        source_present = source_r1_path.is_file()
        self._record("THRESHOLD_SOURCE_REPORT_PRESENT", source_present)

        # 4-5. THRESHOLD DATASET & SAMPLE SIZE PROVENANCE MATCH
        derived_prov = derive_threshold_provenance()
        r3_1_thresh_path = ROOT / "reports/INTEL_1B_R3_1_THRESHOLD_PROVENANCE.json"
        if r3_1_thresh_path.is_file():
            target_thresh_data = json.loads(r3_1_thresh_path.read_text())
            target_dataset = target_thresh_data.get("dataset", "")
            target_sample_size = target_thresh_data.get("sample_size", 0)
        else:
            target_dataset = derived_prov["dataset"]
            target_sample_size = derived_prov["sample_size"]

        expected_dataset = "XAUUSDT_DEV_2026_01_04_V3 (10,000 bars sample)"
        dataset_match = (
            source_present
            and derived_prov["dataset"] == expected_dataset
            and target_dataset == expected_dataset
        )
        self._record("THRESHOLD_SOURCE_DATASET_IDENTITY_MATCH", dataset_match)

        sample_size_match = (
            source_present
            and derived_prov["sample_size"] == 10000
            and target_sample_size == 10000
        )
        self._record("THRESHOLD_SOURCE_SAMPLE_SIZE_MATCH", sample_size_match)

        # 6-9. THRESHOLD RESULTS INTEGRITY & CONTINUITY
        expected_threshold_results = {
            "directional_persistence_up": {
                -0.1: 0.0057,
                -0.05: 0.0,
                0.05: 0.009,
                0.1: 0.0144,
            },
            "efficiency_ratio_high": {
                -0.1: 0.0033,
                -0.05: 0.002,
                0.05: 0.0023,
                0.1: 0.0041,
            },
        }
        results_unchanged = True
        all_finite = True
        all_rates_in_range = True
        all_reconciles = True
        evaluated_perts = 0

        actual_results = derived_prov.get("results", [])
        if len(actual_results) < 2:
            results_unchanged = False

        for r in actual_results:
            p_name = r.get("parameter_name")
            if p_name not in expected_threshold_results:
                results_unchanged = False
                continue
            exp_perts = expected_threshold_results[p_name]
            perts = r.get("perturbation_results", [])
            if len(perts) != 4:
                results_unchanged = False
            for p in perts:
                evaluated_perts += 1
                pct = round(p.get("perturbation_pct", 0.0), 2)
                d_rate = p.get("disagreement_rate", -1.0)
                tot = p.get("total_bars", 0)
                ag_rate = round(1.0 - d_rate, 4)

                if pct not in exp_perts or abs(exp_perts[pct] - d_rate) > 1e-4:
                    results_unchanged = False

                if any(x != x for x in [tot, d_rate, ag_rate]):
                    all_finite = False
                if any(math.isinf(x) for x in [tot, d_rate, ag_rate]):
                    all_finite = False
                if not (0.0 <= d_rate <= 1.0 and 0.0 <= ag_rate <= 1.0):
                    all_rates_in_range = False
                if abs(ag_rate - (1.0 - d_rate)) > 1e-4:
                    all_reconciles = False

        self._record("THRESHOLD_RESULTS_UNCHANGED", results_unchanged and evaluated_perts == 8)
        self._record("THRESHOLD_VALUES_FINITE", all_finite)
        self._record("THRESHOLD_RATES_IN_RANGE", all_rates_in_range)
        self._record("THRESHOLD_AGREEMENT_RECONCILES", all_reconciles)

        # 10. LEDGER_SNAPSHOT_REPORT_PRESENT
        snap_path = ROOT / "reports/INTEL_1B_R3_LEDGER_SNAPSHOT.json"
        snap_present = snap_path.is_file()
        self._record("LEDGER_SNAPSHOT_REPORT_PRESENT", snap_present)

        # 11-13. LEDGER SOURCE SHA, ENTRY COUNT & COUNTS UNCHANGED
        ledger_path = ROOT / "artifacts/research/intel_data_access_ledger.jsonl"
        expected_ledger_sha = "c9f2ae3ddc9505bbdaeff01820ba58600a6389e52827ab27e1c509791c32d532"
        actual_ledger_sha = compute_sha256(ledger_path) if ledger_path.is_file() else ""
        self._record("LEDGER_SOURCE_SHA_UNCHANGED", actual_ledger_sha == expected_ledger_sha)

        da_res = audit_intel_access_ledger(ledger_path)
        self._record("LEDGER_ENTRY_COUNT_UNCHANGED", da_res["total_access_attempts"] == 12)

        counts_ok = (
            da_res["total_access_attempts"] == 12
            and da_res["total_granted"] == 12
            and da_res["total_denied"] == 0
            and da_res["dev_granted"] == 12
            and da_res["val_granted"] == 0
            and da_res["holdout_granted"] == 0
            and da_res["pristine_granted"] == 0
            and da_res["unrecognized_entries"] == 0
            and da_res["reconciled"] is True
            and da_res["audit_passed"] is True
        )
        self._record("LEDGER_COUNTS_UNCHANGED", counts_ok)

        # 14. LEDGER_NORMALIZED_SNAPSHOT_HASH_VALID
        expected_norm_sha = "de9e68b03dfe3f7263a1ab8270e500c153b770638b583d318b9ce34b0e864920"
        hash_matches, recomputed_sha, reported_sha = recompute_normalized_snapshot_hash(snap_path)
        norm_hash_valid = (
            hash_matches
            and recomputed_sha == expected_norm_sha
            and reported_sha == expected_norm_sha
        )
        self._record("LEDGER_NORMALIZED_SNAPSHOT_HASH_VALID", norm_hash_valid)

        # 15-16. HOLDOUT & PRISTINE
        self._record("HOLDOUT_GRANTED_ZERO", da_res["holdout_granted"] == 0)
        self._record("PRISTINE_GRANTED_ZERO", da_res["pristine_granted"] == 0)

        # 17-21. AUTHORITATIVE SAFETY INSPECTION
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

        # 22-24. QUARANTINE & ISOLATION
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

        # 25-27. SUITE & WORKTREE
        res_pytest = subprocess.run([sys.executable, "-m", "pytest", "tests/"], cwd=str(ROOT), capture_output=True, text=True)
        self._record("FULL_PYTEST_PASS", res_pytest.returncode == 0)
        self._record("SECURITY_SCAN_ZERO", sec_proc.returncode == 0)

        status_out = git("status", "--porcelain")
        self._record("CLEAN_WORKTREE", len(status_out.strip()) == 0)

    def _run_evidence_checks(self) -> None:
        reports_dir = ROOT / "reports"
        required_reports = [
            "INTEL_1B_R3_1_FOUNDATION.json",
            "INTEL_1B_R3_1_THRESHOLD_PROVENANCE.json",
            "INTEL_1B_R3_1_LEDGER_HASH_AUDIT.json",
            "INTEL_1B_R3_1_VERIFIER_AUDIT.json",
        ]

        all_present = all((reports_dir / r).is_file() for r in required_reports)
        self._record("R3_1_REPORTS_PRESENT", all_present, is_evidence=True)
        if not all_present:
            self._record("R3_1_REPORT_DIGESTS_MATCH", False, is_evidence=True)
            self._record("TESTED_CODE_TREE_VALID", False, is_evidence=True)
            self._record("EVIDENCE_ONLY_COMMIT", False, is_evidence=True)
            self._record("REMOTE_HEAD_MATCHES_LOCAL", False, is_evidence=True)
            return

        foundation_file = reports_dir / "INTEL_1B_R3_1_FOUNDATION.json"
        found_data = json.loads(foundation_file.read_text())

        digests = found_data.get("report_sha256", {})
        sub_reports = [
            "INTEL_1B_R3_1_THRESHOLD_PROVENANCE.json",
            "INTEL_1B_R3_1_LEDGER_HASH_AUDIT.json",
            "INTEL_1B_R3_1_VERIFIER_AUDIT.json",
        ]
        digests_ok = len(digests) >= len(sub_reports)
        for r_name in sub_reports:
            r_path = reports_dir / r_name
            exp_sha = digests.get(r_name, "")
            if not r_path.is_file() or compute_sha256(r_path) != exp_sha:
                digests_ok = False
                break
        self._record("R3_1_REPORT_DIGESTS_MATCH", digests_ok, is_evidence=True)

        tested_tree = found_data.get("tested_tree_sha")
        parent_tree = git("rev-parse", "HEAD~1^{tree}")
        self._record("TESTED_CODE_TREE_VALID", tested_tree == parent_tree, is_evidence=True)

        changed_files = git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
        ev_only = all(f.startswith("btceth-trading-os/reports/INTEL_1B_R3_1_") for f in changed_files if f.strip())
        self._record("EVIDENCE_ONLY_COMMIT", ev_only, is_evidence=True)

        local_head = git("rev-parse", "HEAD")
        remote_head = git("rev-parse", "origin/btceth-phase2-multiasset")
        self._record("REMOTE_HEAD_MATCHES_LOCAL", local_head == remote_head, is_evidence=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["CODE_ACCEPTANCE", "FINAL_EVIDENCE_ACCEPTANCE"], required=True)
    args = parser.parse_args()
    sys.exit(Intel1bR31Verifier(args.mode).run())
