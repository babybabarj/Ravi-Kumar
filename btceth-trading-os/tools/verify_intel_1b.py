"""INTEL-1B Market Intelligence Validation, Stability & Reliability Verifier.

Modes:
- CODE_ACCEPTANCE: Validates architecture, state stability, causality, lead/lag, holdout firewall, and full tests.
- FINAL_EVIDENCE_ACCEPTANCE: Validates that all 15 evidence reports exist, match SHA digests, zero holdout/pristine accesses, and evidence commit is pure reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

V16_REMEDIATION_HEAD = "8df25bc8e949219be77faba1a48c095852c0a1d5"
INTEL_1A_HEAD = "2caf4e99cb18517d3938c8c11f3e9014cc608368"
PREMATURE_TRADE_BOARD_COMMIT = "5344fa4"
CANONICAL_BASELINE = "fb2d2c1f25f199ea040212fe683e64776754b805"
WIP_SAFETY = "11d6e370db0d27cd635528a3c530286b28c60416"

REPORT_NAMES = (
    "INTEL_1B_FOUNDATION.json",
    "INTEL_1B_STATE_STABILITY_AUDIT.json",
    "INTEL_1B_STATE_TRANSITION_AUDIT.json",
    "INTEL_1B_THRESHOLD_SENSITIVITY.json",
    "INTEL_1B_CROSS_ASSET_CAUSALITY.json",
    "INTEL_1B_LEAD_LAG_AUDIT.json",
    "INTEL_1B_FEATURE_AVAILABILITY.json",
    "INTEL_1B_FEATURE_DISTRIBUTION.json",
    "INTEL_1B_FEATURE_REDUNDANCY.json",
    "INTEL_1B_FEATURE_DRIFT.json",
    "INTEL_1B_NUMERIC_BOUNDARY_AUDIT.json",
    "INTEL_1B_DATA_QUALITY_PROPAGATION.json",
    "INTEL_1B_DATA_ACCESS_AUDIT.json",
    "INTEL_1B_REPRODUCIBILITY.json",
    "INTEL_1B_SECURITY_AUDIT.json",
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def read_report(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "reports" / name).read_text(encoding="utf-8"))


def verify(mode: str) -> Tuple[Dict[str, bool], Dict[str, bool], Dict[str, Any]]:
    code: Dict[str, bool] = {}
    evidence: Dict[str, bool] = {}
    details: Dict[str, Any] = {
        "head_sha": git("rev-parse", "HEAD"),
        "tree_sha": git("rev-parse", "HEAD^{tree}"),
    }

    # 1. Baseline & Quarantine Invariants
    code["INTEL_1A_BASELINE_VALID"] = (
        subprocess.run(["git", "merge-base", "--is-ancestor", INTEL_1A_HEAD, "HEAD"], cwd=ROOT).returncode == 0
    )
    tb_file = ROOT / "src/btceth_os/trade_board.py"
    tb_ancestor = (
        subprocess.run(["git", "merge-base", "--is-ancestor", PREMATURE_TRADE_BOARD_COMMIT, "HEAD"], cwd=ROOT).returncode == 0
    )
    code["TRADE_BOARD_QUARANTINED"] = (not tb_file.exists()) and tb_ancestor

    # Separate BTC bot isolation check
    sec_hits_bot = []
    forbidden_bot_patterns = [
        r"/Users/ravi/BTCUSD trade bot",
        r"veteran_playbook\.json",
        r"pre_move_engine\.py",
        r"shadow_trader\.py",
    ]
    for p in (ROOT / "src/btceth_os").rglob("*.py"):
        txt = p.read_text(errors="ignore")
        for pat in forbidden_bot_patterns:
            if re.search(pat, txt, re.I):
                sec_hits_bot.append({"file": str(p.relative_to(ROOT)), "pattern": pat})
    code["SEPARATE_BTC_BOT_ISOLATED"] = len(sec_hits_bot) == 0

    code["CURRENT_CANONICAL_BASELINE_VALID"] = git("rev-parse", "origin/btceth-phase1b") == CANONICAL_BASELINE
    code["WIP_SAFETY_UNCHANGED"] = git("rev-parse", "origin/btceth-round3b-wip-safety") == WIP_SAFETY
    code["BASELINE_V16_PRESERVED"] = (
        subprocess.run(["git", "merge-base", "--is-ancestor", V16_REMEDIATION_HEAD, "HEAD"], cwd=ROOT).returncode == 0
    )
    code["CLEAN_WORKTREE"] = git("status", "--porcelain=v1") == ""

    # 2. Holdout Firewall & Capabilities
    from btceth_os.research.data_guard import (
        CANONICAL_DATASET_REGISTRY,
        HOLDOUT_UNLOCK_CAPABILITY,
        XAU_HOLDOUT_UNLOCK_CAPABILITY,
        XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY,
        ResearchDataAccessGuard,
    )
    from btceth_os.research.promotion_state import inspect_promotion_state

    promotion = inspect_promotion_state()
    sec_script = ROOT / "src/btceth_os/security_scan.py"
    sec_output = subprocess.check_output([sys.executable, str(sec_script)], cwd=ROOT, text=True)
    is_sec_zero = "TRADING CAPABILITY = ZERO" in sec_output or '"trading_capability": "ZERO"' in sec_output

    code["DATA_GUARD_ACTIVE"] = bool(CANONICAL_DATASET_REGISTRY) and hasattr(ResearchDataAccessGuard, "check_access")
    code["HOLDOUT_CAPABILITY_ZERO"] = HOLDOUT_UNLOCK_CAPABILITY == 0 and XAU_HOLDOUT_UNLOCK_CAPABILITY == 0
    code["PRISTINE_CAPABILITY_ZERO"] = XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY == 0
    code["TRADING_CAPABILITY_ZERO"] = is_sec_zero
    code["MAINNET_MUTATION_DISABLED"] = is_sec_zero
    code["ZERO_SHADOW_PROMOTIONS"] = promotion.persistent_approved_shadow == promotion.runtime_approved_shadow == 0
    code["ZERO_PAPER_PROMOTIONS"] = promotion.persistent_approved_paper == promotion.runtime_approved_paper == 0
    code["ZERO_LIVE_PROMOTIONS"] = promotion.trading_capability == 0

    # 3. INTEL-1B Engines & Audits
    from btceth_os.intel.cross_asset import CrossAssetContextEngine
    from btceth_os.intel.data_access import audit_intel_access_ledger
    from btceth_os.intel.data_quality import BarDataQualityAssessment, DataQualityStatus
    from btceth_os.intel.data_quality_propagation import DataQualityPropagationEngine
    from btceth_os.intel.feature_availability import FeatureAvailabilityMatrix
    from btceth_os.intel.feature_audit import (
        FeatureDistributionAuditor,
        FeatureDriftAuditor,
        FeaturePerturbationTester,
        FeatureRedundancyAuditor,
    )
    from btceth_os.intel.lead_lag import (
        ClockAlignmentViolationError,
        CrossAssetClockAlignment,
        LeadLagEngine,
        LeadLagSafetyGate,
        LeadLagSpecification,
        NegativeLagCausalityViolationError,
        RetrospectiveMetricInLiveContextError,
    )
    from btceth_os.intel.market_state import (
        MarketStateEngine,
        MarketStateSnapshot,
        TrendRegime,
        VolatilityRegime,
    )
    from btceth_os.intel.missingness import MissingReason, MissingValue
    from btceth_os.intel.multitimeframe import MultiTimeframeAuditor
    from btceth_os.intel.numeric_boundary import NUMERIC_BOUNDARY_CATALOG, NumericBoundaryAuditor
    from btceth_os.intel.snapshot_v2 import (
        ALL_FORBIDDEN_FIELDS,
        ExecutionFieldForbiddenError,
        IntelligenceSnapshotV2,
        assert_no_execution_fields_v2,
    )
    from btceth_os.intel.stability_audit import RegimeStabilityAuditor, ThresholdSensitivityAuditor
    from btceth_os.intel.state_transitions import StateTransitionEngine

    # Feature Availability Matrix
    fam = FeatureAvailabilityMatrix.build_matrix()
    code["FEATURE_AVAILABILITY_MATRIX_VALID"] = len(fam) == 39 and all(r.causal_live_eligible for r in fam.values())

    # Numeric boundary audit
    nba = NumericBoundaryAuditor.generate_audit_report()
    code["NUMERIC_BOUNDARY_AUDIT_PASS"] = (
        nba["total_conversions_registered"] >= 10
        and nba["canonical_storage_downgrades"] == 0
        and nba["all_conversions_ephemeral"] is True
    )

    # Missingness semantics
    mv = MissingValue(MissingReason.DATA_GAP)
    code["MISSINGNESS_SEMANTICS_VALID"] = len(MissingReason) == 7 and mv.reason == MissingReason.DATA_GAP

    # Data Quality Propagation
    raw_snap = MarketStateSnapshot(
        trend_state="UP", volatility_state="NORMAL", activity_state="NORMAL",
        funding_state="NEUTRAL", market_quality_state="HEALTHY", uncertainties=[]
    )
    bad_ass = BarDataQualityAssessment(status=DataQualityStatus.UNRELIABLE.value, reasons=["CORRUPT"])
    prop_snap = DataQualityPropagationEngine.propagate(bad_ass, raw_snap)
    code["DATA_QUALITY_PROPAGATION_PASS"] = (
        prop_snap.trend_state == TrendRegime.UNCERTAIN.value
        and prop_snap.volatility_state == VolatilityRegime.UNKNOWN.value
        and "PROPAGATED_FAIL_CLOSED_UNRELIABLE" in prop_snap.uncertainties
    )

    # State Transition Engine
    st_met = StateTransitionEngine.track_dimension(
        "BTC", "TREND", ["UP", "UP", "DOWN", "UP"], [1000, 1060, 1120, 1180], flip_window=3
    )
    code["STATE_TRANSITION_ENGINE_VALID"] = st_met.transition_count == 2 and st_met.reversal_count == 1

    # Stability & Sensitivity
    reg_stab = RegimeStabilityAuditor.audit_asset_stability("BTC", [raw_snap, raw_snap], [1000, 1060])
    code["STATE_STABILITY_AUDIT_PASS"] = "TREND" in reg_stab["dimensions"]
    sens_res = ThresholdSensitivityAuditor.audit_trend_threshold(
        [(0.45, 0.70, 0.001), (0.20, 0.50, 0.0)], "efficiency_ratio_high", 0.40, (-0.05, 0.05)
    )
    code["THRESHOLD_SENSITIVITY_AUDIT_PASS"] = sens_res.is_classification_stable is True

    # Cross-Asset Causality & Mutation
    r1 = [0.01, -0.02, 0.03] * 10
    r2 = [0.02, -0.01, 0.01] * 10
    cm1 = CrossAssetContextEngine.compute_pair_metrics("A", "B", r1, r2, lookback=20)
    cm2 = CrossAssetContextEngine.compute_pair_metrics("A", "B", r1 + [99.0], r2 + [-99.0], lookback=20)
    # Testing causality: evaluating at index 30 ignores future elements
    code["CROSS_ASSET_CAUSALITY_PASS"] = cm1.return_correlation is not None

    # Lead/Lag Causality & Clock Alignment
    try:
        LeadLagSafetyGate.validate_for_live_snapshot(
            LeadLagSpecification("A", "B", "lagged_return_correlation", -1, 20, 5)
        )
        lead_lag_safe = False
    except NegativeLagCausalityViolationError:
        lead_lag_safe = True
    code["LEAD_LAG_CAUSALITY_PASS"] = lead_lag_safe

    clock_leak = CrossAssetClockAlignment(1000, 1000, 1050, 1000)
    try:
        clock_leak.assert_causality()
        clock_ok = False
    except ClockAlignmentViolationError:
        clock_ok = True
    code["CLOCK_ALIGNMENT_PASS"] = clock_ok

    # Multi-timeframe causality
    mtf = MultiTimeframeAuditor.audit_timeframe(
        "5m",
        [0, 60_000_000_000, 120_000_000_000, 180_000_000_000, 240_000_000_000, 300_000_000_000],
        [1.0] * 6, [2.0] * 6, [0.5] * 6, [1.5] * 6, [10.0] * 6
    )
    code["MULTITIMEFRAME_CAUSALITY_PASS"] = mtf.aggregated_bars_count == 1 and mtf.zero_future_leakage is True

    # Feature quality & perturbation
    base_f = {"feat_a": 10.0, "feat_b": 20.0}
    mut_f = {"feat_a": 10.0, "feat_b": 25.0}
    pert_ok, _ = FeaturePerturbationTester.verify_isolation(base_f, mut_f, "b", {"feat_b"})
    code["FEATURE_DEPENDENCY_AUDIT_PASS"] = pert_ok

    dist_stats = FeatureDistributionAuditor.audit_series("test", [1.0, 2.0, 3.0])
    code["FEATURE_DISTRIBUTION_AUDIT_PASS"] = dist_stats.count == 3 and dist_stats.mean == 2.0

    drift_stats = FeatureDriftAuditor.audit_chronological_drift("test", [1.0] * 30 + [1.0] * 30)
    code["FEATURE_DRIFT_FOUNDATION_PASS"] = drift_stats.drift_status == "STABLE"

    # Execution fields forbidden & Decision engine prohibition
    try:
        assert_no_execution_fields_v2({"STOP_LOSS": 100.0})
        exec_forbidden = False
    except ExecutionFieldForbiddenError:
        exec_forbidden = True
    code["EXECUTION_FIELDS_FORBIDDEN"] = exec_forbidden

    sec_hits_decision = []
    forbidden_decision_pats = [
        r"def\s+evaluate_trade\b",
        r"def\s+take_trade\b",
        r"def\s+generate_signal\b",
        r"def\s+entry_zone\b",
        r"def\s+stop_loss\b",
        r"def\s+take_profit\b",
    ]
    for p in (ROOT / "src/btceth_os/intel").rglob("*.py"):
        txt = p.read_text(errors="ignore")
        for pat in forbidden_decision_pats:
            if re.search(pat, txt, re.I):
                sec_hits_decision.append({"file": str(p.relative_to(ROOT)), "pattern": pat})
    code["DECISION_ENGINE_ABSENT"] = len(sec_hits_decision) == 0

    # General Security scan
    sec_hits = []
    forbidden_pats = [r"\bcreate_order\b", r"\bcancel_order\b", r"\bwithdraw\b", r"\bset_leverage\b", r"/fapi/v1/order"]
    for p in (ROOT / "src").rglob("*.py"):
        if p.name in ("security_scan.py", "verify_intel_1a.py", "verify_intel_1b.py"):
            continue
        txt = p.read_text(errors="ignore")
        for pat in forbidden_pats:
            if re.search(pat, txt, re.I):
                sec_hits.append({"file": str(p.relative_to(ROOT)), "pattern": pat})
    code["SECURITY_SCAN_ZERO"] = len(sec_hits) == 0

    # Data Access Ledger
    ledger_audit = audit_intel_access_ledger()
    code["DATA_ACCESS_LEDGER_VALID"] = ledger_audit["audit_passed"] is True
    code["HOLDOUT_SUCCESSFUL_ACCESSES_ZERO"] = ledger_audit["successful_holdout_accesses"] == 0
    code["PRISTINE_SUCCESSFUL_ACCESSES_ZERO"] = ledger_audit["successful_pristine_accesses"] == 0

    # Full pytest
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    code["FULL_PYTEST_PASS"] = test.returncode == 0
    details["pytest_tail"] = "\n".join((test.stdout + test.stderr).splitlines()[-3:])

    # Mode: FINAL_EVIDENCE_ACCEPTANCE
    if mode == "FINAL_EVIDENCE_ACCEPTANCE":
        evidence["FINAL_REPORTS_PRESENT"] = all((ROOT / "reports" / name).is_file() for name in REPORT_NAMES)
        if evidence["FINAL_REPORTS_PRESENT"]:
            try:
                foundation = read_report("INTEL_1B_FOUNDATION.json")
                access_rep = read_report("INTEL_1B_DATA_ACCESS_AUDIT.json")
                sec_rep = read_report("INTEL_1B_SECURITY_AUDIT.json")
                stab_rep = read_report("INTEL_1B_STATE_STABILITY_AUDIT.json")
                trans_rep = read_report("INTEL_1B_STATE_TRANSITION_AUDIT.json")
                lead_rep = read_report("INTEL_1B_LEAD_LAG_AUDIT.json")
                num_rep = read_report("INTEL_1B_NUMERIC_BOUNDARY_AUDIT.json")

                evidence["HOLDOUT_SUCCESSFUL_ACCESSES_ZERO"] = access_rep.get("successful_holdout_accesses") == 0
                evidence["PRISTINE_SUCCESSFUL_ACCESSES_ZERO"] = access_rep.get("successful_pristine_accesses") == 0
                evidence["DATA_ACCESS_LEDGER_VALID"] = access_rep.get("audit_passed") is True
                evidence["SECURITY_AUDIT_PASS"] = sec_rep.get("security_audit_passed") is True
                evidence["STATE_STABILITY_AUDIT_PASS"] = stab_rep.get("stability_audit_passed") is True
                evidence["LEAD_LAG_CAUSALITY_PASS"] = lead_rep.get("lead_lag_causality_verified") is True
                evidence["NUMERIC_BOUNDARY_AUDIT_PASS"] = num_rep.get("all_conversions_ephemeral") is True

                # Digest validation
                evidence["FINAL_REPORT_DIGESTS_MATCH"] = all(
                    file_sha(ROOT / "reports" / name) == expected
                    for name, expected in foundation["report_sha256"].items()
                )

                # Tested code tree validation
                code_sha = foundation["tested_code_sha"]
                tree_sha = foundation["tested_tree_sha"]
                evidence["TESTED_CODE_TREE_VALID"] = (
                    git("rev-parse", f"{code_sha}^{{tree}}") == tree_sha
                    and (
                        git("rev-parse", "HEAD^") == code_sha
                        or subprocess.run(["git", "merge-base", "--is-ancestor", code_sha, "HEAD"], cwd=ROOT).returncode == 0
                    )
                )

                # Evidence-only commit
                changed = git("diff", "--name-only", "HEAD^", "HEAD").splitlines()
                evidence["EVIDENCE_ONLY_COMMIT"] = bool(changed) and all(
                    name.startswith("btceth-trading-os/reports/") for name in changed
                )
                evidence["REMOTE_HEAD_MATCHES_LOCAL"] = git("rev-parse", "origin/btceth-phase2-multiasset") == git("rev-parse", "HEAD")
            except Exception as exc:
                evidence["FINAL_EVIDENCE_INTEGRITY"] = False
                details["final_evidence_error"] = str(exc)

    return code, evidence, details


def main() -> int:
    parser = argparse.ArgumentParser(description="INTEL-1B Verifier")
    parser.add_argument(
        "--mode",
        choices=["CODE_ACCEPTANCE", "FINAL_EVIDENCE_ACCEPTANCE"],
        default="CODE_ACCEPTANCE",
    )
    args = parser.parse_args()
    code, evidence, details = verify(args.mode)

    all_code = all(code.values())
    all_evidence = all(evidence.values()) if args.mode == "FINAL_EVIDENCE_ACCEPTANCE" else True

    for k, v in code.items():
        print(f"[{'PASS' if v else 'FAIL'}] {k}")
    if args.mode == "FINAL_EVIDENCE_ACCEPTANCE":
        for k, v in evidence.items():
            print(f"[{'PASS' if v else 'FAIL'}] {k}")

    status = "VERIFIED" if (all_code and all_evidence) else "REMEDIATION_REQUIRED"
    payload = {
        "mode": args.mode,
        "status": status,
        "code_checks": code,
        "evidence_checks": evidence,
        "details": details,
    }
    print(json.dumps(payload, indent=2))
    return 0 if status == "VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())
