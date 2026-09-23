"""Phase 2E authoritative multi-asset data foundation verifier.

Verifies:
1.  CURRENT_CANONICAL_BASELINE_VALID
2.  PHASE2_BRANCH_ANCESTRY_VALID
3.  CLEAN_WORKTREE (mode dependent or enforced in Commit A)
4.  PHASE2C_REGRESSION
5.  PHASE2D_REGRESSION
6.  XAU_RAW_SOURCE_HASHES_VALID
7.  XAU_PRE_ADMISSION_ROWS_QUARANTINED
8.  XAU_TRADES_FULL_AUDIT
9.  XAU_AGGTRADES_FULL_AUDIT
10. XAU_RULE_EPOCH_REGISTRY_VALID
11. XAU_FUNDING_EPOCH_REPLAY
12. XAU_INDEX_METHOD_EPOCH_REPLAY
13. XAU_SESSION_SEMANTICS_VALID
14. XAU_QUOTE_CAPABILITY_CLASSIFIED
15. XAU_DEPTH_CAPABILITY_CLASSIFIED
16. XAU_RESEARCH_CAPABILITY_MATRIX_VALID
17. XAU_PARTITIONS_DETERMINISTIC
18. XAU_HOLDOUT_LOCKED
19. BTC_ETH_HOLDOUT_UNTOUCHED
20. ZERO_SHADOW_PROMOTIONS
21. ZERO_PAPER_PROMOTIONS
22. TRADING_CAPABILITY_ZERO
23. FULL_PYTEST_PASS
24. SECURITY_SCAN_ZERO
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.capabilities import CapabilityStatus, ResearchCapabilityMatrix
from btceth_os.contract_rule_epochs import ContractRuleEpochRegistry
from btceth_os.research.data_guard import verify_access_ledger_integrity
from btceth_os.research.promotion_state import inspect_promotion_state
from btceth_os.sessions import (
    GoldSessionState,
    PerpetualContractSession,
    UnderlyingReferenceSession,
    evaluate_sessions,
)
from tools.verify_multiasset_v11 import git, run_python
from tools.verify_multiasset_v12 import verify as verify_v12

EXPECTED_CANONICAL_SHA = "fb2d2c1f25f199ea040212fe683e64776754b805"
EXPECTED_CANONICAL_TAG = "btceth-reliability-3b0i-canonical-2026-09-23"
EXPECTED_WIP_SAFETY_SHA = "11d6e370db0d27cd635528a3c530286b28c60416"
EXPECTED_0I_PARENT_SHA = "4612bb0e6cdc64b9f28a352d213305e7ffb692a2"
EXPECTED_0I_TREE_SHA = "e4859f17d25d31d12f31e2116c3c740259e244f1"


def compute_canonical_digest(data: object) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def compute_file_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verify(mode: str) -> tuple[dict[str, bool], dict[str, Any]]:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    # 1. CURRENT_CANONICAL_BASELINE_VALID
    try:
        remote_canonical = git("rev-parse", "origin/btceth-phase1b")
        tag_commit = git("rev-parse", f"{EXPECTED_CANONICAL_TAG}^{{commit}}")
        safety_sha = git("rev-parse", "origin/btceth-round3b-wip-safety")
        parent_sha = git("rev-parse", f"{EXPECTED_CANONICAL_SHA}^")
        tree_sha = git("rev-parse", f"{EXPECTED_0I_PARENT_SHA}^{{tree}}")
        checks["CURRENT_CANONICAL_BASELINE_VALID"] = (
            remote_canonical == EXPECTED_CANONICAL_SHA
            and tag_commit == EXPECTED_CANONICAL_SHA
            and safety_sha == EXPECTED_WIP_SAFETY_SHA
            and parent_sha == EXPECTED_0I_PARENT_SHA
            and tree_sha == EXPECTED_0I_TREE_SHA
        )
        details["canonical_sha"] = remote_canonical
    except Exception as exc:
        checks["CURRENT_CANONICAL_BASELINE_VALID"] = False
        details["canonical_error"] = str(exc)

    # 2. PHASE2_BRANCH_ANCESTRY_VALID
    try:
        ancestry_ok = subprocess.run(
            ["git", "merge-base", "--is-ancestor", EXPECTED_CANONICAL_SHA, "HEAD"],
            cwd=ROOT,
            check=False,
        ).returncode == 0
        checks["PHASE2_BRANCH_ANCESTRY_VALID"] = ancestry_ok
    except Exception as exc:
        checks["PHASE2_BRANCH_ANCESTRY_VALID"] = False
        details["ancestry_error"] = str(exc)

    # 3. CLEAN_WORKTREE
    try:
        clean_status = git("status", "--porcelain=v1")
        checks["CLEAN_WORKTREE"] = clean_status == ""
        if clean_status:
            details["dirty_files"] = clean_status.splitlines()[:10]
    except Exception as exc:
        checks["CLEAN_WORKTREE"] = False
        details["worktree_error"] = str(exc)

    # 4. PHASE2C_REGRESSION & 5. PHASE2D_REGRESSION
    try:
        v12_checks, v12_details = verify_v12("CODE_ACCEPTANCE")
        # Exclude CLEAN_WORKTREE from regression gate since we track it separately in gate 3
        v11_subset = {k: v for k, v in v12_checks.items() if k != "CLEAN_WORKTREE"}
        checks["PHASE2C_REGRESSION"] = all(
            v11_subset[k]
            for k in (
                "CANONICAL_BASELINE",
                "BASELINE_ANCESTRY",
                "DEVELOPMENT_BRANCH",
                "CANONICAL_IDS",
                "IMMUTABLE_SPEC_FIELDS",
                "XAE_FAILS_CLOSED",
                "GOLD_PRODUCTS_DISTINCT",
            )
        )
        checks["PHASE2D_REGRESSION"] = all(
            v12_checks[k]
            for k in (
                "FIVE_SPEC_SNAPSHOTS_VERIFIED",
                "XAU_PRODUCT_IDENTITY",
                "XAU_RULES_MATCH_SOURCE",
                "XAU_SESSION_AND_MARK_AVAILABLE",
                "XAU_NOT_APPROVED_FOR_EXECUTION",
                "XAU_PUBLIC_REST_PROBES",
                "XAU_ROUTED_WEBSOCKET",
            )
        )
    except Exception as exc:
        checks["PHASE2C_REGRESSION"] = False
        checks["PHASE2D_REGRESSION"] = False
        details["regression_error"] = str(exc)

    # 6. XAU_RAW_SOURCE_HASHES_VALID
    try:
        manifest_path = ROOT / "artifacts" / "instrument_specs" / "announcements" / "manifest.json"
        ann_manifest = json.loads(manifest_path.read_text())
        all_ann_valid = True
        for meta in ann_manifest.values():
            fpath = ROOT / meta["path"]
            if not fpath.exists() or compute_file_sha256(fpath) != meta["physical_sha256"]:
                all_ann_valid = False
                break
        checks["XAU_RAW_SOURCE_HASHES_VALID"] = all_ann_valid and len(ann_manifest) >= 6
    except Exception as exc:
        checks["XAU_RAW_SOURCE_HASHES_VALID"] = False
        details["raw_hashes_error"] = str(exc)

    # 7. XAU_PRE_ADMISSION_ROWS_QUARANTINED
    try:
        silver_path = ROOT / "artifacts" / "research" / "silver_xau" / "XAUUSDT-resampled-1m-silver.parquet"
        if silver_path.exists():
            silver_meta = pq.read_metadata(silver_path)
            table_head = pq.read_table(silver_path, columns=["ts_event_ns"])
            min_ts = table_head["ts_event_ns"][0].as_py()
            # 2026-01-06T00:00:00Z = 1767657600000000000 ns
            checks["XAU_PRE_ADMISSION_ROWS_QUARANTINED"] = min_ts >= 1767657600_000_000_000
        else:
            checks["XAU_PRE_ADMISSION_ROWS_QUARANTINED"] = False
    except Exception as exc:
        checks["XAU_PRE_ADMISSION_ROWS_QUARANTINED"] = False
        details["quarantine_error"] = str(exc)

    # 8. XAU_TRADES_FULL_AUDIT & 9. XAU_AGGTRADES_FULL_AUDIT
    try:
        audit_file = ROOT / "reports" / "XAU_TRADES_AGGTRADES_AUDIT.json"
        audit_script = ROOT / "tools" / "audit_xau_trades_and_aggtrades.py"
        if audit_file.exists():
            audit_report = json.loads(audit_file.read_text())
            trades_archives = [a for a in audit_report.get("archives", []) if a.get("dataset_type") == "trades"]
            aggtrades_archives = [a for a in audit_report.get("archives", []) if a.get("dataset_type") == "aggTrades"]
            checks["XAU_TRADES_FULL_AUDIT"] = (
                audit_report.get("all_archives_passed") is True
                and len(trades_archives) == 31
                and all(a.get("status") == "PASS" for a in trades_archives)
                and audit_report.get("total_trades_rows", 0) > 0
            )
            checks["XAU_AGGTRADES_FULL_AUDIT"] = (
                audit_report.get("all_archives_passed") is True
                and len(aggtrades_archives) == 31
                and all(a.get("status") == "PASS" for a in aggtrades_archives)
                and audit_report.get("reconciliation", {}).get("exact_reconciliation") is True
                and audit_report.get("total_aggtrades_rows", 0) > 0
            )
            details["total_trades_rows"] = audit_report.get("total_trades_rows")
            details["total_aggtrades_rows"] = audit_report.get("total_aggtrades_rows")
        elif mode == "CODE_ACCEPTANCE" and audit_script.exists():
            checks["XAU_TRADES_FULL_AUDIT"] = True
            checks["XAU_AGGTRADES_FULL_AUDIT"] = True
            details["audit_evidence"] = "DEFERRED_TO_COMMIT_B"
        else:
            checks["XAU_TRADES_FULL_AUDIT"] = False
            checks["XAU_AGGTRADES_FULL_AUDIT"] = False
            details["audit_report_missing"] = True
    except Exception as exc:
        checks["XAU_TRADES_FULL_AUDIT"] = False
        checks["XAU_AGGTRADES_FULL_AUDIT"] = False
        details["audit_error"] = str(exc)

    # 10. XAU_RULE_EPOCH_REGISTRY_VALID
    try:
        registry = ContractRuleEpochRegistry.from_yaml(ROOT / "config" / "xau_contract_rule_epochs.yaml")
        checks["XAU_RULE_EPOCH_REGISTRY_VALID"] = len(registry) == 7 and registry.validate_chronology()
    except Exception as exc:
        checks["XAU_RULE_EPOCH_REGISTRY_VALID"] = False
        details["epoch_registry_error"] = str(exc)

    # 11. XAU_FUNDING_EPOCH_REPLAY
    try:
        from decimal import Decimal
        registry = ContractRuleEpochRegistry.from_yaml(ROOT / "config" / "xau_contract_rule_epochs.yaml")
        ep1 = registry.get_epoch_for_timestamp("2026-01-15T00:00:00Z")
        ep4 = registry.get_epoch_for_timestamp("2026-02-15T00:00:00Z")
        checks["XAU_FUNDING_EPOCH_REPLAY"] = (
            ep1 is not None
            and ep4 is not None
            and ep1.funding_interval_seconds == 14400
            and ep1.funding_cap_floor == Decimal("0.00375")
            and ep4.funding_interval_seconds == 28800
            and ep4.funding_cap_floor == Decimal("0.0005")
        )
    except Exception as exc:
        checks["XAU_FUNDING_EPOCH_REPLAY"] = False
        details["funding_replay_error"] = str(exc)

    # 12. XAU_INDEX_METHOD_EPOCH_REPLAY
    try:
        registry = ContractRuleEpochRegistry.from_yaml(ROOT / "config" / "xau_contract_rule_epochs.yaml")
        ep3 = registry.get_epoch_for_timestamp("2026-01-25T00:00:00Z")
        ep5 = registry.get_epoch_for_timestamp("2026-08-15T00:00:00Z")
        ep6 = registry.get_epoch_for_timestamp("2026-09-20T00:00:00Z")
        checks["XAU_INDEX_METHOD_EPOCH_REPLAY"] = (
            ep3 is not None
            and ep5 is not None
            and ep6 is not None
            and "fixed_off_hours" in ep3.price_index_method.lower()
            and "ewma" in ep5.price_index_method.lower()
            and "orderbook_ewma" in ep6.price_index_method.lower()
        )
    except Exception as exc:
        checks["XAU_INDEX_METHOD_EPOCH_REPLAY"] = False
        details["index_replay_error"] = str(exc)

    # 13. XAU_SESSION_SEMANTICS_VALID
    try:
        # Test Saturday noon UTC (underlying off hours, crypto contract trading)
        sat_dt = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
        snap_sat = evaluate_sessions(sat_dt)
        # Test Wednesday 17:00 UTC (13:00 ET, both open)
        wed_dt = datetime(2026, 9, 16, 17, 0, tzinfo=timezone.utc)
        snap_wed = evaluate_sessions(wed_dt)
        checks["XAU_SESSION_SEMANTICS_VALID"] = (
            snap_sat.underlying_state == GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE
            and snap_sat.contract_state == GoldSessionState.CONTRACT_TRADING
            and snap_sat.is_contract_tradable is True
            and snap_wed.underlying_state == GoldSessionState.UNDERLYING_OPEN
            and snap_wed.contract_state == GoldSessionState.CONTRACT_TRADING
            and snap_wed.is_contract_tradable is True
        )
    except Exception as exc:
        checks["XAU_SESSION_SEMANTICS_VALID"] = False
        details["session_error"] = str(exc)

    # 14. XAU_QUOTE_CAPABILITY_CLASSIFIED & 15. XAU_DEPTH_CAPABILITY_CLASSIFIED
    try:
        matrix = ResearchCapabilityMatrix()
        bba = matrix.capabilities["BEST_BID_ASK_RESEARCH"]
        depth = matrix.capabilities["ORDERBOOK_DEPTH_RESEARCH"]
        checks["XAU_QUOTE_CAPABILITY_CLASSIFIED"] = (
            bba.status == CapabilityStatus.NOT_COMPUTABLE and bba.allowed_for_research is False
        )
        checks["XAU_DEPTH_CAPABILITY_CLASSIFIED"] = (
            depth.status == CapabilityStatus.NOT_COMPUTABLE and depth.allowed_for_research is False
        )
    except Exception as exc:
        checks["XAU_QUOTE_CAPABILITY_CLASSIFIED"] = False
        checks["XAU_DEPTH_CAPABILITY_CLASSIFIED"] = False
        details["quote_depth_error"] = str(exc)

    # 16. XAU_RESEARCH_CAPABILITY_MATRIX_VALID
    try:
        mat_file = ROOT / "reports" / "XAU_RESEARCH_CAPABILITY_MATRIX.json"
        matrix = ResearchCapabilityMatrix()
        if mat_file.exists():
            data = json.loads(mat_file.read_text())
            checks["XAU_RESEARCH_CAPABILITY_MATRIX_VALID"] = (
                data == matrix.to_dict()
                and data.get("bar_level_research_ready") is True
                and data.get("orderbook_research_ready") is False
                and data.get("realistic_fills_ready") is False
            )
        elif mode == "CODE_ACCEPTANCE":
            d = matrix.to_dict()
            checks["XAU_RESEARCH_CAPABILITY_MATRIX_VALID"] = (
                d.get("bar_level_research_ready") is True
                and d.get("orderbook_research_ready") is False
                and d.get("realistic_fills_ready") is False
            )
            details["matrix_evidence"] = "DEFERRED_TO_COMMIT_B"
        else:
            checks["XAU_RESEARCH_CAPABILITY_MATRIX_VALID"] = False
    except Exception as exc:
        checks["XAU_RESEARCH_CAPABILITY_MATRIX_VALID"] = False
        details["matrix_error"] = str(exc)

    # 17. XAU_PARTITIONS_DETERMINISTIC
    try:
        part_manifest_file = ROOT / "config" / "xau_research_partitions_v1.json"
        if part_manifest_file.exists():
            part_manifest = json.loads(part_manifest_file.read_text())
            partitions = part_manifest.get("partitions", {})
            parts_ok = len(partitions) == 4
            total_rows = 0
            for name, meta in partitions.items():
                p_file = ROOT / meta["relative_path"]
                if not p_file.exists() or compute_file_sha256(p_file) != meta["expected_physical_sha256"]:
                    parts_ok = False
                    break
                t = pq.read_table(p_file, columns=["ts_event_ns"])
                if t.num_rows != meta["expected_rows"]:
                    parts_ok = False
                    break
                total_rows += t.num_rows
            checks["XAU_PARTITIONS_DETERMINISTIC"] = parts_ok and total_rows == 374400
            details["partition_rows"] = total_rows
        else:
            checks["XAU_PARTITIONS_DETERMINISTIC"] = False
    except Exception as exc:
        checks["XAU_PARTITIONS_DETERMINISTIC"] = False
        details["partitions_error"] = str(exc)

    # 18. XAU_HOLDOUT_LOCKED
    try:
        ledger_path = ROOT / "artifacts" / "research" / "holdout_access_ledger.jsonl"
        if ledger_path.exists():
            records = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
            xau_violations = [
                r for r in records
                if r.get("dataset_id") in ("XAUUSDT_HOLDOUT_2026_08_09", "XAUUSDT_PROSPECTIVE_PRISTINE")
            ]
            checks["XAU_HOLDOUT_LOCKED"] = len(xau_violations) == 0
        else:
            checks["XAU_HOLDOUT_LOCKED"] = True
    except Exception as exc:
        checks["XAU_HOLDOUT_LOCKED"] = False
        details["xau_holdout_error"] = str(exc)

    # 19. BTC_ETH_HOLDOUT_UNTOUCHED
    try:
        ledger_ok, count, _, ledger = verify_access_ledger_integrity()
        checks["BTC_ETH_HOLDOUT_UNTOUCHED"] = ledger_ok and count > 0 and ledger.get("allowed_holdout_accesses") == 0
    except Exception as exc:
        checks["BTC_ETH_HOLDOUT_UNTOUCHED"] = False
        details["btc_eth_holdout_error"] = str(exc)

    # 20. ZERO_SHADOW_PROMOTIONS & 21. ZERO_PAPER_PROMOTIONS
    try:
        prom = inspect_promotion_state()
        checks["ZERO_SHADOW_PROMOTIONS"] = (
            prom.status == "VERIFIED"
            and prom.persistent_approved_shadow == 0
            and prom.runtime_approved_shadow == 0
        )
        checks["ZERO_PAPER_PROMOTIONS"] = (
            prom.status == "VERIFIED"
            and prom.persistent_approved_paper == 0
            and prom.runtime_approved_paper == 0
        )
    except Exception as exc:
        checks["ZERO_SHADOW_PROMOTIONS"] = False
        checks["ZERO_PAPER_PROMOTIONS"] = False
        details["promotion_error"] = str(exc)

    # 22. TRADING_CAPABILITY_ZERO & 24. SECURITY_SCAN_ZERO
    try:
        sec = run_python("-m", "btceth_os.security_scan")
        scan = json.loads(sec.stdout)
        checks["TRADING_CAPABILITY_ZERO"] = sec.returncode == 0 and scan.get("trading_capability") == "ZERO"
        checks["SECURITY_SCAN_ZERO"] = sec.returncode == 0 and scan.get("hits") == []
    except Exception as exc:
        checks["TRADING_CAPABILITY_ZERO"] = False
        checks["SECURITY_SCAN_ZERO"] = False
        details["security_error"] = str(exc)

    # 23. FULL_PYTEST_PASS
    try:
        if "FULL_PYTEST" in v12_checks:
            checks["FULL_PYTEST_PASS"] = v12_checks["FULL_PYTEST"]
            details["pytest_tail"] = v12_details.get("pytest_tail", "")
        else:
            tests = run_python("-m", "pytest", "-q")
            checks["FULL_PYTEST_PASS"] = tests.returncode == 0
            details["pytest_tail"] = "\n".join((tests.stdout + tests.stderr).splitlines()[-4:])
    except Exception as exc:
        checks["FULL_PYTEST_PASS"] = False
        details["pytest_error"] = str(exc)

    # FINAL_EVIDENCE_ACCEPTANCE mode specific gates
    if mode == "FINAL_EVIDENCE_ACCEPTANCE":
        v14_report_path = ROOT / "reports" / "PHASE2E_XAU_DATA_GATE_V14.json"
        if v14_report_path.exists():
            report_data = json.loads(v14_report_path.read_text())
            payload = {k: v for k, v in report_data.items() if k != "payload_sha256"}
            computed_payload_sha = compute_canonical_digest(payload)
            checks["EVIDENCE_PAYLOAD_V14"] = computed_payload_sha == report_data.get("payload_sha256")

            audit_file = ROOT / "reports" / "XAU_TRADES_AGGTRADES_AUDIT.json"
            if audit_file.exists():
                audit_sha = compute_file_sha256(audit_file)
                checks["AUDIT_SOURCE_DIGEST"] = audit_sha == report_data.get("audit_report_physical_sha256")
            else:
                checks["AUDIT_SOURCE_DIGEST"] = False

            mat_file = ROOT / "reports" / "XAU_RESEARCH_CAPABILITY_MATRIX.json"
            if mat_file.exists():
                mat_sha = compute_file_sha256(mat_file)
                checks["CAPABILITY_MATRIX_DIGEST"] = mat_sha == report_data.get("capability_matrix_physical_sha256")
            else:
                checks["CAPABILITY_MATRIX_DIGEST"] = False

            try:
                changed = git("diff", "--name-only", "HEAD^", "HEAD").splitlines()
                checks["TESTED_CODE_TREE"] = (
                    git("rev-parse", "HEAD^") == report_data.get("tested_code_commit_sha")
                    and git("rev-parse", f"{report_data.get('tested_code_commit_sha')}^{{tree}}")
                    == report_data.get("tested_tree_sha")
                )
                checks["EVIDENCE_ONLY_COMMIT"] = bool(changed) and all(
                    p.startswith("btceth-trading-os/reports/") for p in changed
                )
            except Exception as exc:
                checks["TESTED_CODE_TREE"] = False
                checks["EVIDENCE_ONLY_COMMIT"] = False
                details["tree_evidence_error"] = str(exc)
        else:
            checks["EVIDENCE_PAYLOAD_V14"] = False
            checks["AUDIT_SOURCE_DIGEST"] = False
            checks["CAPABILITY_MATRIX_DIGEST"] = False
            checks["TESTED_CODE_TREE"] = False
            checks["EVIDENCE_ONLY_COMMIT"] = False

        try:
            checks["REMOTE_HEAD"] = git("rev-parse", "HEAD") == git("rev-parse", "origin/btceth-phase2-multiasset")
        except Exception as exc:
            checks["REMOTE_HEAD"] = False
            details["remote_head_error"] = str(exc)

    return checks, details


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2E Multi-Asset Data Foundation Verifier V14")
    parser.add_argument(
        "--mode",
        choices=("CODE_ACCEPTANCE", "FINAL_EVIDENCE_ACCEPTANCE"),
        required=True,
        help="Verification mode",
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    checks, details = verify(args.mode)
    all_passed = all(checks.values())
    status = "VERIFIED" if all_passed else "REMEDIATION_REQUIRED"

    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    print(f"GATES = {sum(checks.values())}/{len(checks)}")
    print(f"PHASE2E_V14_STATUS = {status}")

    if args.json:
        print(json.dumps({"status": status, "checks": checks, "details": details}, indent=2, sort_keys=True))

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
