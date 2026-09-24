"""INTEL-1A Intelligence Architecture Verifier.

Modes:
- CODE_ACCEPTANCE: Validates code, architecture, causality contracts, security scans, holdout locks, and full tests.
- FINAL_EVIDENCE_ACCEPTANCE: Validates that all evidence reports exist, match SHA digests, ledger audits confirm zero holdout/pristine access, and evidence commit is pure reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

V16_REMEDIATION_HEAD = "8df25bc8e949219be77faba1a48c095852c0a1d5"
CANONICAL_BASELINE = "fb2d2c1f25f199ea040212fe683e64776754b805"
WIP_SAFETY = "11d6e370db0d27cd635528a3c530286b28c60416"

REPORT_NAMES = (
    "INTEL_1A_FOUNDATION.json",
    "INTEL_1A_FEATURE_REGISTRY.json",
    "INTEL_1A_CAUSALITY_AUDIT.json",
    "INTEL_1A_DATA_ACCESS_AUDIT.json",
    "INTEL_1A_DATA_QUALITY_AUDIT.json",
    "INTEL_1A_CROSS_ASSET_FOUNDATION.json",
    "INTEL_1A_REPRODUCIBILITY.json",
    "INTEL_1A_SECURITY_AUDIT.json",
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

    # 1. Git & Baseline Invariants
    code["CURRENT_CANONICAL_BASELINE_VALID"] = git("rev-parse", "origin/btceth-phase1b") == CANONICAL_BASELINE
    code["WIP_SAFETY_UNCHANGED"] = git("rev-parse", "origin/btceth-round3b-wip-safety") == WIP_SAFETY
    code["BASELINE_V16_PRESERVED"] = (
        subprocess.run(["git", "merge-base", "--is-ancestor", V16_REMEDIATION_HEAD, "HEAD"], cwd=ROOT).returncode == 0
    )
    code["PHASE2_BRANCH_ANCESTRY_VALID"] = git("merge-base", CANONICAL_BASELINE, "HEAD") == CANONICAL_BASELINE
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

    # 3. Feature Registry & Architecture
    from btceth_os.intel.cross_asset import CrossAssetContextEngine
    from btceth_os.intel.data_access import IntelAccessDeniedError, IntelDatasetAccessAPI, audit_intel_access_ledger
    from btceth_os.intel.data_quality import DataQualityGate, DataQualityStatus
    from btceth_os.intel.feature_contract import FeatureDefinition
    from btceth_os.intel.feature_engine import CausalFeatureEngine
    from btceth_os.intel.feature_registry import ALL_FEATURES, FEATURESET_V1_ID, FeatureRegistry
    from btceth_os.intel.market_state import MarketStateEngine
    from btceth_os.intel.normalization import TrailingRollingScaler
    from btceth_os.intel.reproducibility import compute_feature_table_logical_hash
    from btceth_os.intel.resampler import CausalResampler
    from btceth_os.intel.snapshot import ExecutionFieldForbiddenError, assert_no_execution_fields

    reg = FeatureRegistry()
    code["FEATURE_REGISTRY_VALID"] = len(reg.list_features()) == len(ALL_FEATURES) and len(ALL_FEATURES) >= 30
    code["FEATURE_SCHEMA_VALID"] = all(
        isinstance(f, FeatureDefinition) and f.feature_name and f.inputs and f.lookback >= 0
        for f in reg.list_features()
    )

    # 4. Causality Engine Verification
    # Resample causality
    agg = CausalResampler.resample(
        "5m", [0, 60_000_000_000, 120_000_000_000, 180_000_000_000, 240_000_000_000, 300_000_000_000],
        [1.0] * 6, [2.0] * 6, [0.5] * 6, [1.5] * 6, [10.0] * 6
    )
    code["RESAMPLE_CAUSALITY_PASS"] = len(agg) == 1 and agg[0].period_end_ns == 300_000_000_000

    # Normalization causality
    z1 = TrailingRollingScaler.rolling_zscore([1.0, 2.0, 3.0, 4.0, 5.0], window=3, min_periods=2)
    z2 = TrailingRollingScaler.rolling_zscore([1.0, 2.0, 3.0, 4.0, 5.0, 999.0], window=3, min_periods=2)
    code["NORMALIZATION_CAUSALITY_PASS"] = z1 == z2[:5]

    # Cross asset causality
    r_a = [0.01, 0.02, -0.01] * 20
    r_b = [0.02, 0.01, -0.02] * 20
    cm1 = CrossAssetContextEngine.compute_pair_metrics("A", "B", r_a, r_b, lookback=60)
    cm2 = CrossAssetContextEngine.compute_pair_metrics("A", "B", r_a, r_b[:60], lookback=60)
    code["CROSS_ASSET_CAUSALITY_PASS"] = cm1.return_correlation == cm2.return_correlation and cm1.return_correlation is not None

    # Execution fields forbidden check
    try:
        assert_no_execution_fields({"ORDER_TYPE": "LIMIT"})
        exec_forbidden = False
    except ExecutionFieldForbiddenError:
        exec_forbidden = True
    code["EXECUTION_FIELDS_FORBIDDEN"] = exec_forbidden

    # Data Quality Gate
    ass = DataQualityGate.assess_bar(
        ts_ns=1000, prev_ts_ns=2000, open_p=10.0, high_p=12.0, low_p=8.0, close_p=11.0, volume=5.0
    )
    code["DATA_QUALITY_GATE_VALID"] = ass.status == DataQualityStatus.UNRELIABLE.value

    # Session uncertainty preserved
    st = MarketStateEngine.evaluate_state(
        {"holiday_status": "NOT_IMPLEMENTED", "price_index_mode_certainty": "HOLIDAY_UNKNOWN"},
        data_quality_status="GOOD"
    )
    code["SESSION_UNCERTAINTY_PRESERVED"] = "SESSION_HOLIDAY_STATUS_UNPROVEN" in st.uncertainties

    # Security scan
    import re
    sec_hits = []
    forbidden_pats = [r"\bcreate_order\b", r"\bcancel_order\b", r"\bwithdraw\b", r"\bset_leverage\b", r"/fapi/v1/order"]
    for p in (ROOT / "src").rglob("*.py"):
        if p.name in ("security_scan.py", "verify_intel_1a.py"):
            continue
        txt = p.read_text(errors="ignore")
        for pat in forbidden_pats:
            if re.search(pat, txt, re.I):
                sec_hits.append({"file": str(p.relative_to(ROOT)), "pattern": pat})
    code["SECURITY_SCAN_ZERO"] = len(sec_hits) == 0

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
                foundation = read_report("INTEL_1A_FOUNDATION.json")
                feat_rep = read_report("INTEL_1A_FEATURE_REGISTRY.json")
                access_rep = read_report("INTEL_1A_DATA_ACCESS_AUDIT.json")
                caus_rep = read_report("INTEL_1A_CAUSALITY_AUDIT.json")
                cross_rep = read_report("INTEL_1A_CROSS_ASSET_FOUNDATION.json")
                repro_rep = read_report("INTEL_1A_REPRODUCIBILITY.json")
                sec_rep = read_report("INTEL_1A_SECURITY_AUDIT.json")

                evidence["HOLDOUT_SUCCESSFUL_ACCESSES_ZERO"] = access_rep.get("successful_holdout_accesses") == 0
                evidence["PRISTINE_SUCCESSFUL_ACCESSES_ZERO"] = access_rep.get("successful_pristine_accesses") == 0
                evidence["DATA_ACCESS_LEDGER_VALID"] = access_rep.get("audit_passed") is True
                evidence["FEATURE_REGISTRY_REPORT_VALID"] = feat_rep.get("total_features", 0) >= 30
                evidence["CAUSALITY_AUDIT_PASS"] = caus_rep.get("all_causality_checks_passed") is True
                evidence["CROSS_ASSET_FOUNDATION_PASS"] = cross_rep.get("cross_asset_engine_verified") is True
                evidence["REPRODUCIBILITY_PASS"] = repro_rep.get("reproducibility_verified") is True
                evidence["SECURITY_AUDIT_PASS"] = sec_rep.get("security_audit_passed") is True

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
    parser = argparse.ArgumentParser(description="INTEL-1A Verifier")
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
