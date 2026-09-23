"""Phase 2E.1 authoritative multi-asset data foundation verifier (Verifier V15).

Verifies all 15 audit remediation blockers (Blockers A through O):
1.  CURRENT_CANONICAL_BASELINE_VALID (origin/btceth-phase1b == fb2d2c1f25f199ea040212fe683e64776754b805)
2.  PHASE2_BRANCH_ANCESTRY_VALID (canonical baseline is ancestor of HEAD)
3.  PHASE2E_V14_PARENT_PRESERVED (commit d7bf609b8d61cd549be9c11943854bc66f0b3459 preserved, V14 evidence untouched)
4.  CLEAN_WORKTREE
5.  PHASE2C_REGRESSION
6.  PHASE2D_REGRESSION
7.  GATE_01_PRIMARY_SOURCES_MANIFEST_V2 (Blocker A)
8.  GATE_02_CONTRACT_RULE_EPOCHS_V2 (Blockers I, J, N)
9.  GATE_03_EXACT_1815_UTC_EPOCH_TRANSITION (Blocker I)
10. GATE_04_SILVER_V2_DECIMAL_SCHEMA (Blocker C)
11. GATE_05_PARTITIONS_V2_DECIMAL_SCHEMA (Blockers C, K)
12. GATE_06_SERIES_ALIGNMENT_AUDIT_V15 (Blocker D)
13. GATE_07_DISCRETE_FUNDING_EVENTS_V2 (Blocker E)
14. GATE_08_SESSION_ENGINE_FAIL_CLOSED (Blocker F)
15. GATE_09_HOLIDAY_STATUS_NOT_IMPLEMENTED (Blocker G)
16. GATE_10_EPOCH_AWARE_MAINTENANCE_WINDOWS (Blocker H)
17. GATE_11_TRADES_AGGTRADES_FULL_AUDIT_V15 (Blocker B)
18. GATE_12_XAU_HOLDOUT_LOCKED (Blocker L)
19. GATE_13_XAU_PROSPECTIVE_PRISTINE_LOCKED (Blocker L)
20. GATE_14_BTC_ETH_HOLDOUT_UNTOUCHED (Blocker L, M)
21. GATE_15_LEDGER_INTEGRITY_FAIL_CLOSED (Blocker M)
22. GATE_16_ZERO_SHADOW_PROMOTIONS
23. GATE_17_ZERO_PAPER_PROMOTIONS
24. GATE_18_TRADING_CAPABILITY_ZERO
25. GATE_19_FULL_PYTEST_PASS
26. GATE_20_SECURITY_SCAN_ZERO

Modes:
- CODE_ACCEPTANCE: Run on Commit C before committing reports.
- FINAL_EVIDENCE_ACCEPTANCE: Run on Commit D after pushing to origin.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from unittest.mock import patch
import zoneinfo

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.contract_rule_epochs import ContractRuleEpochRegistry
from btceth_os.research.data_guard import (
    CANONICAL_DATASET_REGISTRY,
    DatasetRole,
    HoldoutAccessDeniedError,
    ResearchDataAccessGuard,
    ResearchOperation,
    XAU_HOLDOUT_UNLOCK_CAPABILITY,
    XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY,
    load_research_parquet,
    verify_access_ledger_integrity,
)
from btceth_os.research.promotion_state import inspect_promotion_state
from btceth_os.sessions import (
    GoldSessionState,
    HolidayStatus,
    PerpetualContractSession,
    SessionTimezoneUnavailableError,
    UnderlyingReferenceSession,
    evaluate_sessions,
)
from tools.verify_multiasset_v11 import git, run_python
from tools.verify_multiasset_v12 import verify as verify_v12

EXPECTED_CANONICAL_SHA = "fb2d2c1f25f199ea040212fe683e64776754b805"
EXPECTED_CANONICAL_TAG = "btceth-reliability-3b0i-canonical-2026-09-23"
EXPECTED_V14_COMMIT_SHA = "d7bf609b8d61cd549be9c11943854bc66f0b3459"


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
        checks["CURRENT_CANONICAL_BASELINE_VALID"] = (
            remote_canonical == EXPECTED_CANONICAL_SHA
            and tag_commit == EXPECTED_CANONICAL_SHA
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

    # 3. PHASE2E_V14_PARENT_PRESERVED
    try:
        v14_ancestor_ok = subprocess.run(
            ["git", "merge-base", "--is-ancestor", EXPECTED_V14_COMMIT_SHA, "HEAD"],
            cwd=ROOT,
            check=False,
        ).returncode == 0
        v14_report_path = ROOT / "reports" / "PHASE2E_XAU_DATA_GATE_V14.json"
        checks["PHASE2E_V14_PARENT_PRESERVED"] = v14_ancestor_ok and v14_report_path.is_file()
    except Exception as exc:
        checks["PHASE2E_V14_PARENT_PRESERVED"] = False
        details["v14_preservation_error"] = str(exc)

    # 4. CLEAN_WORKTREE
    try:
        clean_status = git("status", "--porcelain=v1")
        checks["CLEAN_WORKTREE"] = clean_status == ""
        if clean_status:
            details["dirty_files"] = clean_status.splitlines()[:15]
    except Exception as exc:
        checks["CLEAN_WORKTREE"] = False
        details["worktree_error"] = str(exc)

    # 5. PHASE2C_REGRESSION & 6. PHASE2D_REGRESSION
    try:
        v12_checks, v12_details = verify_v12("CODE_ACCEPTANCE")
        checks["PHASE2C_REGRESSION"] = all(
            v12_checks[k]
            for k in (
                "CANONICAL_BASELINE",
                "BASELINE_ANCESTRY",
                "DEVELOPMENT_BRANCH",
                "CANONICAL_IDS",
                "IMMUTABLE_SPEC_FIELDS",
                "XAE_FAILS_CLOSED",
                "GOLD_PRODUCTS_DISTINCT",
            )
            if k in v12_checks
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
            if k in v12_checks
        )
        from tools.verify_multiasset_v14 import verify as verify_v14
        v14_checks, _ = verify_v14("CODE_ACCEPTANCE")
        v14_subset = {k: v for k, v in v14_checks.items() if k != "CLEAN_WORKTREE"}
        checks["PHASE2E_V14_REGRESSION"] = all(v14_subset.values())
    except Exception as exc:
        checks["PHASE2C_REGRESSION"] = False
        checks["PHASE2D_REGRESSION"] = False
        checks["PHASE2E_V14_REGRESSION"] = False
        details["regression_error"] = str(exc)

    # 7. GATE_01_PRIMARY_SOURCES_MANIFEST_V2 (Blocker A)
    try:
        manifest_path = ROOT / "config" / "xau_primary_sources_v2.json"
        if manifest_path.is_file():
            data = json.loads(manifest_path.read_text())
            sources = data.get("sources", {})
            sources_ok = len(sources) == 8
            for src_id, src in sources.items():
                f_path = ROOT / src["file_path"]
                if not f_path.is_file() or compute_file_sha256(f_path) != src["physical_sha256"]:
                    sources_ok = False
                    break
            checks["GATE_01_PRIMARY_SOURCES_MANIFEST_V2"] = sources_ok
        else:
            checks["GATE_01_PRIMARY_SOURCES_MANIFEST_V2"] = False
    except Exception as exc:
        checks["GATE_01_PRIMARY_SOURCES_MANIFEST_V2"] = False
        details["sources_manifest_error"] = str(exc)

    # 8. GATE_02_CONTRACT_RULE_EPOCHS_V2 (Blockers I, J, N)
    try:
        epochs_path = ROOT / "config" / "xau_contract_rule_epochs_v2.yaml"
        if epochs_path.is_file():
            reg = ContractRuleEpochRegistry.from_yaml(epochs_path)
            chrono_ok = reg.validate_chronology()
            ep0 = reg.epochs[0]
            terminology_ok = "PRE_ADMISSION" in ep0.epoch_id and ep0.confidence == "QUARANTINED"
            provenance_ok = all(
                (isinstance(e.field_provenance, dict) and (len(e.field_provenance) > 0 or e.epoch_id == ep0.epoch_id))
                for e in reg.epochs
            )
            checks["GATE_02_CONTRACT_RULE_EPOCHS_V2"] = (len(reg.epochs) == 8 and chrono_ok and terminology_ok and provenance_ok)
        else:
            checks["GATE_02_CONTRACT_RULE_EPOCHS_V2"] = False
    except Exception as exc:
        checks["GATE_02_CONTRACT_RULE_EPOCHS_V2"] = False
        details["contract_epochs_error"] = str(exc)

    # 9. GATE_03_EXACT_1815_UTC_EPOCH_TRANSITION (Blocker I)
    try:
        epochs_path = ROOT / "config" / "xau_contract_rule_epochs_v2.yaml"
        reg = ContractRuleEpochRegistry.from_yaml(epochs_path)
        ep_before = reg.get_epoch_for_timestamp("2026-01-30T18:14:59Z")
        ep_at = reg.get_epoch_for_timestamp("2026-01-30T18:15:00Z")
        checks["GATE_03_EXACT_1815_UTC_EPOCH_TRANSITION"] = (
            ep_before.epoch_id == "XAU_EPOCH_4A_8H_TEMPORARY_FUNDING"
            and ep_before.funding_interval_seconds == 28800
            and ep_at.epoch_id == "XAU_EPOCH_4B_4H_FUNDING_AND_CAP_EXPANSION"
            and ep_at.funding_interval_seconds == 14400
            and ep_at.funding_cap == Decimal("0.0050")
            and ep_at.funding_floor == Decimal("-0.0050")
        )
    except Exception as exc:
        checks["GATE_03_EXACT_1815_UTC_EPOCH_TRANSITION"] = False
        details["epoch_transition_error"] = str(exc)

    # 10. GATE_04_SILVER_V2_DECIMAL_SCHEMA (Blocker C)
    try:
        silver_v2_path = ROOT / "artifacts" / "research" / "silver_xau" / "XAUUSDT-resampled-1m-silver-v2.parquet"
        if silver_v2_path.is_file():
            tbl = pq.read_table(silver_v2_path)
            float_cols = [f.name for f in tbl.schema if pa.types.is_floating(f.type)]
            open_type = tbl.schema.field("open").type
            funding_type = tbl.schema.field("funding_rate").type
            vol_type = tbl.schema.field("volume").type
            schema_ok = (
                len(float_cols) == 0
                and pa.types.is_decimal(open_type) and open_type.scale == 4
                and pa.types.is_decimal(funding_type) and funding_type.scale == 8
                and pa.types.is_decimal(vol_type) and vol_type.scale == 8
                and tbl.num_rows == 374_400
            )
            checks["GATE_04_SILVER_V2_DECIMAL_SCHEMA"] = schema_ok
        else:
            checks["GATE_04_SILVER_V2_DECIMAL_SCHEMA"] = False
    except Exception as exc:
        checks["GATE_04_SILVER_V2_DECIMAL_SCHEMA"] = False
        details["silver_v2_schema_error"] = str(exc)

    # 11. GATE_05_PARTITIONS_V2_DECIMAL_SCHEMA (Blockers C, K)
    try:
        part_manifest_path = ROOT / "config" / "xau_research_partitions_v2.json"
        if part_manifest_path.is_file():
            data = json.loads(part_manifest_path.read_text())
            partitions = data.get("partitions", {})
            parts_ok = len(partitions) == 4
            total_rows = 0
            for name, meta in partitions.items():
                p_file = ROOT / meta["relative_path"]
                if not p_file.is_file() or compute_file_sha256(p_file) != meta["expected_physical_sha256"]:
                    parts_ok = False
                    break
                t = pq.read_table(p_file)
                if t.num_rows != meta["expected_rows"]:
                    parts_ok = False
                    break
                float_cols = [f.name for f in t.schema if pa.types.is_floating(f.type)]
                if len(float_cols) > 0:
                    parts_ok = False
                    break
                total_rows += t.num_rows
            checks["GATE_05_PARTITIONS_V2_DECIMAL_SCHEMA"] = parts_ok and total_rows == 374_400
        else:
            checks["GATE_05_PARTITIONS_V2_DECIMAL_SCHEMA"] = False
    except Exception as exc:
        checks["GATE_05_PARTITIONS_V2_DECIMAL_SCHEMA"] = False
        details["partitions_v2_error"] = str(exc)

    # 12. GATE_06_SERIES_ALIGNMENT_AUDIT_V15 (Blocker D)
    try:
        align_path = ROOT / "reports" / "XAU_SERIES_ALIGNMENT_AUDIT_V15.json"
        if align_path.is_file():
            data = json.loads(align_path.read_text())
            stats = data.get("alignment_statistics", {})
            checks["GATE_06_SERIES_ALIGNMENT_AUDIT_V15"] = (
                stats.get("alignment_status") == "PERFECT_100_PERCENT_NO_FALLBACK"
                and stats.get("total_admitted_bars") == 374_400
                and stats.get("fallback_substitutions") == 0
                and stats.get("missing_mark_bars") == 0
                and stats.get("missing_index_bars") == 0
                and stats.get("missing_premium_bars") == 0
            )
        elif mode == "CODE_ACCEPTANCE":
            checks["GATE_06_SERIES_ALIGNMENT_AUDIT_V15"] = True
            details["series_alignment_evidence"] = "DEFERRED_TO_COMMIT_D"
        else:
            checks["GATE_06_SERIES_ALIGNMENT_AUDIT_V15"] = False
    except Exception as exc:
        checks["GATE_06_SERIES_ALIGNMENT_AUDIT_V15"] = False
        details["series_alignment_error"] = str(exc)

    # 13. GATE_07_DISCRETE_FUNDING_EVENTS_V2 (Blocker E)
    try:
        events_path = ROOT / "artifacts" / "research" / "silver_xau" / "XAUUSDT-funding-events-silver-v2.parquet"
        if events_path.is_file():
            tbl = pq.read_table(events_path)
            rate_type = tbl.schema.field("funding_rate").type
            checks["GATE_07_DISCRETE_FUNDING_EVENTS_V2"] = (
                tbl.num_rows == 1589
                and pa.types.is_decimal(rate_type)
                and "funding_time_utc" in tbl.column_names
            )
        else:
            checks["GATE_07_DISCRETE_FUNDING_EVENTS_V2"] = False
    except Exception as exc:
        checks["GATE_07_DISCRETE_FUNDING_EVENTS_V2"] = False
        details["funding_events_error"] = str(exc)

    # 14. GATE_08_SESSION_ENGINE_FAIL_CLOSED (Blocker F)
    try:
        underlying = UnderlyingReferenceSession()
        dt = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)
        raised = False
        with patch("zoneinfo.ZoneInfo", side_effect=zoneinfo.ZoneInfoNotFoundError("Mock unavailable")):
            try:
                underlying.get_state(dt)
            except SessionTimezoneUnavailableError:
                raised = True
        checks["GATE_08_SESSION_ENGINE_FAIL_CLOSED"] = raised
    except Exception as exc:
        checks["GATE_08_SESSION_ENGINE_FAIL_CLOSED"] = False
        details["session_fail_closed_error"] = str(exc)

    # 15. GATE_09_HOLIDAY_STATUS_NOT_IMPLEMENTED (Blocker G)
    try:
        underlying = UnderlyingReferenceSession()
        st = underlying.get_holiday_status("2026-07-04")
        checks["GATE_09_HOLIDAY_STATUS_NOT_IMPLEMENTED"] = (st == HolidayStatus.NOT_IMPLEMENTED)
    except Exception as exc:
        checks["GATE_09_HOLIDAY_STATUS_NOT_IMPLEMENTED"] = False
        details["holiday_status_error"] = str(exc)

    # 16. GATE_10_EPOCH_AWARE_MAINTENANCE_WINDOWS (Blocker H)
    try:
        session_break = UnderlyingReferenceSession(has_daily_break=True)
        session_no_break = UnderlyingReferenceSession(has_daily_break=False)
        st_break = session_break.get_state(datetime(2026, 8, 19, 21, 30, tzinfo=timezone.utc))
        st_no_break = session_no_break.get_state(datetime(2026, 9, 16, 21, 30, tzinfo=timezone.utc))
        checks["GATE_10_EPOCH_AWARE_MAINTENANCE_WINDOWS"] = (
            st_break == GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE
            and st_no_break == GoldSessionState.UNDERLYING_OPEN
        )
    except Exception as exc:
        checks["GATE_10_EPOCH_AWARE_MAINTENANCE_WINDOWS"] = False
        details["maintenance_window_error"] = str(exc)

    # 17. GATE_11_TRADES_AGGTRADES_FULL_AUDIT_V15 (Blocker B)
    try:
        audit_file_v15 = ROOT / "reports" / "XAU_TRADES_AGGTRADES_AUDIT_V15.json"
        audit_script = ROOT / "tools" / "audit_xau_trades_and_aggtrades.py"
        if audit_file_v15.is_file():
            data = json.loads(audit_file_v15.read_text())
            all_passed = data.get("all_archives_passed") is True
            multi_rec_passed = data.get("multi_epoch_reconciliation_passed") is True
            recs = data.get("reconciliations", {})
            has_3_recs = len(recs) == 3 and all(r["trades_exact_reconciliation"] for r in recs.values())
            checks["GATE_11_TRADES_AGGTRADES_FULL_AUDIT_V15"] = (all_passed and multi_rec_passed and has_3_recs)
        elif mode == "CODE_ACCEPTANCE" and audit_script.is_file():
            checks["GATE_11_TRADES_AGGTRADES_FULL_AUDIT_V15"] = True
            details["trade_audit_v15_evidence"] = "DEFERRED_TO_COMMIT_D"
        else:
            checks["GATE_11_TRADES_AGGTRADES_FULL_AUDIT_V15"] = False
    except Exception as exc:
        checks["GATE_11_TRADES_AGGTRADES_FULL_AUDIT_V15"] = False
        details["trade_audit_v15_error"] = str(exc)

    # 18. GATE_12_XAU_HOLDOUT_LOCKED (Blocker L)
    try:
        holdout_v2 = "XAUUSDT_HOLDOUT_2026_08_09_V2"
        h_blocked = False
        try:
            ResearchDataAccessGuard.check_access(ResearchOperation.BACKTEST, dataset_id=holdout_v2)
        except HoldoutAccessDeniedError:
            h_blocked = True

        holdout_path = ROOT / "artifacts" / "research" / "partitions" / f"{holdout_v2}.parquet"
        h_loader_blocked = False
        try:
            load_research_parquet(holdout_path, dataset_id=holdout_v2)
        except HoldoutAccessDeniedError:
            h_loader_blocked = True

        checks["GATE_12_XAU_HOLDOUT_LOCKED"] = (
            XAU_HOLDOUT_UNLOCK_CAPABILITY == 0
            and h_blocked
            and h_loader_blocked
            and CANONICAL_DATASET_REGISTRY[holdout_v2].role == DatasetRole.LOCKED_HOLDOUT
        )
    except Exception as exc:
        checks["GATE_12_XAU_HOLDOUT_LOCKED"] = False
        details["xau_holdout_locked_error"] = str(exc)

    # 19. GATE_13_XAU_PROSPECTIVE_PRISTINE_LOCKED (Blocker L)
    try:
        pristine_v2 = "XAUUSDT_PROSPECTIVE_PRISTINE_V2"
        p_blocked = False
        try:
            ResearchDataAccessGuard.check_access(ResearchOperation.BACKTEST, dataset_id=pristine_v2)
        except HoldoutAccessDeniedError:
            p_blocked = True

        pristine_path = ROOT / "artifacts" / "research" / "partitions" / f"{pristine_v2}.parquet"
        p_loader_blocked = False
        try:
            load_research_parquet(pristine_path, dataset_id=pristine_v2)
        except HoldoutAccessDeniedError:
            p_loader_blocked = True

        checks["GATE_13_XAU_PROSPECTIVE_PRISTINE_LOCKED"] = (
            XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY == 0
            and p_blocked
            and p_loader_blocked
            and CANONICAL_DATASET_REGISTRY[pristine_v2].role == DatasetRole.LOCKED_PROSPECTIVE_PRISTINE
        )
    except Exception as exc:
        checks["GATE_13_XAU_PROSPECTIVE_PRISTINE_LOCKED"] = False
        details["pristine_locked_error"] = str(exc)

    # 20. GATE_14_BTC_ETH_HOLDOUT_UNTOUCHED (Blocker L, M)
    try:
        ledger_ok, count, _, ledger = verify_access_ledger_integrity()
        checks["GATE_14_BTC_ETH_HOLDOUT_UNTOUCHED"] = (
            ledger_ok and count > 0 and ledger.get("allowed_holdout_accesses") == 0
        )
    except Exception as exc:
        checks["GATE_14_BTC_ETH_HOLDOUT_UNTOUCHED"] = False
        details["btc_eth_holdout_error"] = str(exc)

    # 21. GATE_15_LEDGER_INTEGRITY_FAIL_CLOSED (Blocker M)
    try:
        is_valid, _, msg, _ = verify_access_ledger_integrity(
            ledger_path=ROOT / "reports" / "nonexistent_ledger.jsonl",
            require_exists=True,
        )
        checks["GATE_15_LEDGER_INTEGRITY_FAIL_CLOSED"] = (is_valid is False and msg == "LEDGER_MISSING")
    except Exception as exc:
        checks["GATE_15_LEDGER_INTEGRITY_FAIL_CLOSED"] = False
        details["ledger_fail_closed_error"] = str(exc)

    # 22. GATE_16_ZERO_SHADOW_PROMOTIONS & 23. GATE_17_ZERO_PAPER_PROMOTIONS
    try:
        prom = inspect_promotion_state()
        checks["GATE_16_ZERO_SHADOW_PROMOTIONS"] = (
            prom.status == "VERIFIED"
            and prom.persistent_approved_shadow == 0
            and prom.runtime_approved_shadow == 0
        )
        checks["GATE_17_ZERO_PAPER_PROMOTIONS"] = (
            prom.status == "VERIFIED"
            and prom.persistent_approved_paper == 0
            and prom.runtime_approved_paper == 0
        )
    except Exception as exc:
        checks["GATE_16_ZERO_SHADOW_PROMOTIONS"] = False
        checks["GATE_17_ZERO_PAPER_PROMOTIONS"] = False
        details["promotion_error"] = str(exc)

    # 24. GATE_18_TRADING_CAPABILITY_ZERO & 26. GATE_20_SECURITY_SCAN_ZERO
    try:
        sec = run_python("-m", "btceth_os.security_scan")
        scan = json.loads(sec.stdout)
        checks["GATE_18_TRADING_CAPABILITY_ZERO"] = sec.returncode == 0 and scan.get("trading_capability") == "ZERO"
        checks["GATE_20_SECURITY_SCAN_ZERO"] = sec.returncode == 0 and scan.get("hits") == []
    except Exception as exc:
        checks["GATE_18_TRADING_CAPABILITY_ZERO"] = False
        checks["GATE_20_SECURITY_SCAN_ZERO"] = False
        details["security_error"] = str(exc)

    # 25. GATE_19_FULL_PYTEST_PASS
    try:
        tests = run_python("-m", "pytest", "-q")
        checks["GATE_19_FULL_PYTEST_PASS"] = tests.returncode == 0
        details["pytest_tail"] = "\n".join((tests.stdout + tests.stderr).splitlines()[-4:])
    except Exception as exc:
        checks["GATE_19_FULL_PYTEST_PASS"] = False
        details["pytest_error"] = str(exc)

    # Mode-specific gates for FINAL_EVIDENCE_ACCEPTANCE
    if mode == "FINAL_EVIDENCE_ACCEPTANCE":
        v15_report_path = ROOT / "reports" / "PHASE2E_1_XAU_FOUNDATION_V15.json"
        if v15_report_path.is_file():
            report_data = json.loads(v15_report_path.read_text())
            payload = {k: v for k, v in report_data.items() if k != "payload_sha256"}
            checks["EVIDENCE_PAYLOAD_V15"] = compute_canonical_digest(payload) == report_data.get("payload_sha256")

            audit_file = ROOT / "reports" / "XAU_TRADES_AGGTRADES_AUDIT_V15.json"
            if audit_file.is_file():
                checks["AUDIT_SOURCE_DIGEST_V15"] = compute_file_sha256(audit_file) == report_data.get("audit_report_physical_sha256")
            else:
                checks["AUDIT_SOURCE_DIGEST_V15"] = False

            align_file = ROOT / "reports" / "XAU_SERIES_ALIGNMENT_AUDIT_V15.json"
            if align_file.is_file():
                checks["ALIGNMENT_AUDIT_DIGEST_V15"] = compute_file_sha256(align_file) == report_data.get("series_alignment_physical_sha256")
            else:
                checks["ALIGNMENT_AUDIT_DIGEST_V15"] = False

            manifest_file = ROOT / "config" / "xau_research_partitions_v2.json"
            if manifest_file.is_file():
                checks["PARTITIONS_MANIFEST_DIGEST_V2"] = compute_file_sha256(manifest_file) == report_data.get("partitions_manifest_physical_sha256")
            else:
                checks["PARTITIONS_MANIFEST_DIGEST_V2"] = False

            try:
                changed = git("diff", "--name-only", "HEAD^", "HEAD").splitlines()
                checks["TESTED_CODE_TREE_V15"] = (
                    git("rev-parse", "HEAD^") == report_data.get("tested_code_commit_sha")
                    and git("rev-parse", f"{report_data.get('tested_code_commit_sha')}^{{tree}}")
                    == report_data.get("tested_tree_sha")
                )
                checks["EVIDENCE_ONLY_COMMIT_V15"] = bool(changed) and all(
                    (p.startswith("btceth-trading-os/reports/") or p.startswith("reports/")) for p in changed
                )
            except Exception as exc:
                checks["TESTED_CODE_TREE_V15"] = False
                checks["EVIDENCE_ONLY_COMMIT_V15"] = False
                details["tree_evidence_error"] = str(exc)
        else:
            checks["EVIDENCE_PAYLOAD_V15"] = False
            checks["AUDIT_SOURCE_DIGEST_V15"] = False
            checks["ALIGNMENT_AUDIT_DIGEST_V15"] = False
            checks["PARTITIONS_MANIFEST_DIGEST_V2"] = False
            checks["TESTED_CODE_TREE_V15"] = False
            checks["EVIDENCE_ONLY_COMMIT_V15"] = False

        try:
            checks["REMOTE_HEAD_V15"] = git("rev-parse", "HEAD") == git("rev-parse", "origin/btceth-phase2-multiasset")
        except Exception as exc:
            checks["REMOTE_HEAD_V15"] = False
            details["remote_head_error"] = str(exc)

    return checks, details


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2E.1 Multi-Asset Data Foundation Verifier V15")
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
    print(f"PHASE2E_1_V15_STATUS = {status}")

    if args.json:
        print(json.dumps({"status": status, "checks": checks, "details": details}, indent=2, sort_keys=True))

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
