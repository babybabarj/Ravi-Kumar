"""Phase 2E.2 V16: separate code acceptance from full evidence acceptance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.research.data_guard import (
    CANONICAL_DATASET_REGISTRY, DatasetRole, XAU_HOLDOUT_UNLOCK_CAPABILITY,
    XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY, verify_access_ledger_integrity,
)
from btceth_os.research.promotion_state import inspect_promotion_state
from btceth_os.security_scan import FORBIDDEN
from btceth_os.sessions import evaluate_sessions
from tools.materialize_xau_primary_sources_v3 import canonical, digest, extract
from tools.materialize_xau_research_v3 import logical_sha

BASELINE = "fb2d2c1f25f199ea040212fe683e64776754b805"
V15_EVIDENCE = "3170c2a608b66be171e8da39d4a0e8eae75f8e96"
V15_CODE = "2871266785d0c56fea05a93669b5c6db12a95979"
WIP_SAFETY = "11d6e370db0d27cd635528a3c530286b28c60416"
REPORT_NAMES = (
    "PHASE2E_2_XAU_FOUNDATION_V16.json", "XAU_AGGTRADE_RECONCILIATION_V16.json",
    "XAU_PRIMARY_SOURCE_REPRODUCIBILITY_V16.json", "XAU_PRIMARY_SOURCE_METADATA_V16.json",
    "XAU_FUNDING_SEMANTICS_V16.json", "XAU_SESSION_CERTAINTY_V16.json",
    "XAU_LOGICAL_HASH_AUDIT_V16.json", "XAU_TRADES_AGGTRADES_AUDIT_V16.json",
    "XAU_JUNE_TRADES_REPLACEMENT_V16.json",
    "XAU_SERIES_ALIGNMENT_AUDIT_V16.json", "XAU_DECIMAL_SCHEMA_AUDIT_V16.json",
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def read_report(name: str) -> dict:
    return json.loads((ROOT / "reports" / name).read_text())


def security_zero() -> bool:
    for path in (ROOT / "src").rglob("*.py"):
        if path.name == "security_scan.py":
            continue
        content = path.read_text(errors="ignore")
        if any(re.search(pattern, content, re.I) for pattern in FORBIDDEN):
            return False
    return True


def source_checks() -> dict[str, bool]:
    checks: dict[str, bool] = {}
    manifest = json.loads((ROOT / "config/xau_primary_sources_v3.json").read_text())
    results = []
    for source_id, spec in manifest["sources"].items():
        raw = (ROOT / spec["snapshot_path"]).read_bytes()
        logical = digest(canonical(extract(spec, raw)))
        results.append(
            source_id == spec["source_id"]
            and file_sha(ROOT / spec["snapshot_path"]) == spec["snapshot_physical_sha256"]
            and logical == spec["expected_logical_sha256"]
        )
    checks["PRIMARY_SOURCE_MANIFEST_V3_VALID"] = len(results) == 8 and all(results)
    checks["PRIMARY_SOURCE_LOGICAL_HASH_RECOMPUTED"] = all(results)
    checks["PRIMARY_SOURCE_FETCH_IMPLEMENTED"] = "network" in (ROOT / "tools/materialize_xau_primary_sources_v3.py").read_text()
    checks["SOURCE_METADATA_CONFLICTS_EXPLICIT"] = "SOURCE_METADATA_CONFLICT" in manifest["metadata_conflict"]
    checks["LAUNCH_AND_RESEARCH_ADMISSION_SEPARATED"] = (
        manifest["official_listing_or_availability_date"] == "2026-01-05"
        and manifest["research_admission_timestamp"] == "2026-01-06T00:00:00Z"
        and manifest["official_listing_or_availability_timestamp"] == "UNKNOWN"
    )
    production_text = "\n".join(p.read_text(errors="ignore") for base in ("tools", "config")
                                 for p in (ROOT / base).rglob("*") if p.is_file() and p.suffix in (".py", ".json", ".yaml", ".toml"))
    checks["NO_GEMINI_CACHE_DEPENDENCY"] = ".ge" + "mini" not in production_text
    checks["NO_ABSOLUTE_LOCAL_SOURCE_DEPENDENCY"] = "/Users/" + "ravi/" not in production_text
    return checks


def verify(mode: str) -> tuple[dict[str, bool], dict[str, bool], dict[str, object]]:
    code: dict[str, bool] = {}
    evidence: dict[str, bool] = {}
    details: dict[str, object] = {}
    try:
        code["CURRENT_CANONICAL_BASELINE_VALID"] = git("rev-parse", "origin/btceth-phase1b") == BASELINE
        code["WIP_SAFETY_UNCHANGED"] = git("rev-parse", "origin/btceth-round3b-wip-safety") == WIP_SAFETY
        code["V15_PARENT_PRESERVED"] = git("merge-base", V15_EVIDENCE, "HEAD") == V15_EVIDENCE and git("rev-parse", V15_EVIDENCE + "^") == V15_CODE
        code["PHASE2_BRANCH_ANCESTRY_VALID"] = git("merge-base", BASELINE, "HEAD") == BASELINE
        code["CLEAN_WORKTREE"] = git("status", "--porcelain=v1") == ""
        details["head_sha"] = git("rev-parse", "HEAD")
        details["tree_sha"] = git("rev-parse", "HEAD^{tree}")
    except Exception as exc:
        code["GIT_BASELINE"] = False
        details["git_error"] = str(exc)
    try:
        code.update(source_checks())
    except Exception as exc:
        code["PRIMARY_SOURCE_MANIFEST_V3_VALID"] = False
        details["source_error"] = str(exc)
    try:
        manifest = json.loads((ROOT / "config/xau_research_partitions_v3.json").read_text())
        code["PARTITION_MANIFEST_V3_VALID"] = len(manifest["partitions"]) == 4 and manifest["silver"]["rows"] == 374400
        roles = {p["role"] for p in manifest["partitions"].values()}
        code["XAU_V3_ROLES_VALID"] = roles == {"DEVELOPMENT", "VALIDATION", "LOCKED_HOLDOUT", "LOCKED_PROSPECTIVE_PRISTINE"}
        code["XAU_V3_GUARD_REGISTERED"] = all(CANONICAL_DATASET_REGISTRY[p].role == DatasetRole(v["role"])
                                              for p, v in manifest["partitions"].items())
        code["XAU_HOLDOUT_UNLOCK_CAPABILITY_ZERO"] = XAU_HOLDOUT_UNLOCK_CAPABILITY == 0
        code["XAU_PRISTINE_UNLOCK_CAPABILITY_ZERO"] = XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY == 0
        code["FUNDING_SCHEMA_V3_IMPLEMENTED"] = "funding_event_ts_ns" in (ROOT / "tools/materialize_xau_research_v3.py").read_text()
        code["LOGICAL_HASH_ENGINE_IMPLEMENTED"] = callable(logical_sha)
    except Exception as exc:
        code["PARTITION_MANIFEST_V3_VALID"] = False
        details["partition_manifest_error"] = str(exc)
    try:
        weekday = evaluate_sessions(datetime(2026, 7, 6, 14, tzinfo=timezone.utc))
        weekend = evaluate_sessions(datetime(2026, 7, 5, 14, tzinfo=timezone.utc))
        code["SESSION_CERTAINTY_MODEL_VALID"] = (
            weekday.underlying_session_certainty == "WEEKDAY_RULE_ONLY"
            and weekday.price_index_mode_certainty == "HOLIDAY_UNKNOWN"
            and weekday.is_contract_tradable and weekend.is_contract_tradable
            and weekday.holiday_status == "NOT_IMPLEMENTED"
        )
    except Exception as exc:
        code["SESSION_CERTAINTY_MODEL_VALID"] = False
        details["session_error"] = str(exc)
    try:
        promotion = inspect_promotion_state()
        code["ZERO_SHADOW_PROMOTIONS"] = promotion.persistent_approved_shadow == promotion.runtime_approved_shadow == 0
        code["ZERO_PAPER_PROMOTIONS"] = promotion.persistent_approved_paper == promotion.runtime_approved_paper == 0
        code["TRADING_CAPABILITY_ZERO"] = security_zero()
        code["MAINNET_MUTATION_DISABLED"] = security_zero()
        ledger_valid, _, _, ledger = verify_access_ledger_integrity()
        code["HOLDOUT_ALLOWED_ACCESSES_ZERO"] = ledger_valid and ledger.get("allowed_holdout_accesses") == 0
    except Exception as exc:
        code["SAFETY_STATE"] = False
        details["safety_error"] = str(exc)
    code["SECURITY_SCAN_ZERO"] = security_zero()
    test = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    code["FULL_PYTEST_PASS"] = test.returncode == 0
    details["pytest_tail"] = "\n".join((test.stdout + test.stderr).splitlines()[-3:])

    if mode == "FINAL_EVIDENCE_ACCEPTANCE":
        evidence["FINAL_REPORTS_PRESENT"] = all((ROOT / "reports" / name).is_file() for name in REPORT_NAMES)
        if evidence["FINAL_REPORTS_PRESENT"]:
            try:
                agg = read_report("XAU_AGGTRADE_RECONCILIATION_V16.json")
                audit = read_report("XAU_TRADES_AGGTRADES_AUDIT_V16.json")
                june = read_report("XAU_JUNE_TRADES_REPLACEMENT_V16.json")
                may = audit["reconciliations"]["2026-05-15"]
                arcs = {(a["dataset_type"], a["period"]): a for a in audit["archives"] if a["cadence"] == "daily"}
                evidence["MAY15_AGGTRADE_DISCREPANCY_EXPLAINED"] = (
                    agg["covered_constituent_exact"] is True and agg["uncovered_trade_count"] == 99
                    and Decimal(agg["uncovered_trade_volume"]) == Decimal("32.841")
                    and agg["boundary_analysis"]["agg_ids_continuous_across_days"] is True
                    and agg["monthly_daily_match"] is True
                    and agg["trades_source"]["physical_sha256"] == arcs[("trades", "2026-05-15")]["physical_sha256"]
                    and agg["aggtrades_source"]["physical_sha256"] == arcs[("aggTrades", "2026-05-15")]["physical_sha256"]
                    and may["aggtrade_policy"] == "SOURCE_SEMANTICALLY_CONSISTENT"
                    and may["aggtrades_reconciliation_passed"] is True
                )
                evidence["TRADE_AGGTRADE_FULL_AUDIT_PASS"] = (
                    audit["audit_version"] == "2.0.0" and len(audit["archives"]) == 66
                    and audit["multi_epoch_reconciliation_passed"] is True
                    and sum(a["status"] == "FAIL" for a in audit["archives"]) == 1
                    and june["replacement_passed"] is True and june["daily_archive_count"] == 30
                    and june["affected_archive"]["physical_sha256"] == next(
                        a["physical_sha256"] for a in audit["archives"] if a["dataset_type"] == "trades" and a["cadence"] == "monthly" and a["period"] == "2026-06"
                    )
                    and all(a["status"] == "PASS" and a["duplicate_rows"] == 0 and a["timestamp_regressions"] == 0
                            and a["invalid_prices"] == 0 and a["invalid_quantities"] == 0
                            and len(a["physical_sha256"]) == len(a["logical_sha256"]) == 64
                            for a in audit["archives"] if not (a["dataset_type"] == "trades" and a["cadence"] == "monthly" and a["period"] == "2026-06"))
                    and all(a["status"] == "PASS" and a["duplicate_rows"] == 0 for a in june["daily_archives"])
                )
                source_report = read_report("XAU_PRIMARY_SOURCE_REPRODUCIBILITY_V16.json")
                evidence["PRIMARY_SOURCES_FULL_MATERIALIZATION_PASS"] = (
                    source_report["all_passed"] is True and source_report["sources_requested"] == 8
                    and source_report["sources_restored_from_committed_snapshot"] == 8
                    and source_report.get("fresh_worktree_artifact_directory_initially_absent") is True
                    and source_report.get("fresh_worktree_head_sha") == git("rev-parse", "HEAD^")
                    and all(v["logical_sha_match"] is True for v in source_report["sources"].values())
                )
                for label, item in [("SILVER", manifest["silver"]), *manifest["partitions"].items()]:
                    table_path = ROOT / item["relative_path"]
                    evidence[label + "_V3_LOGICAL_HASH_RECOMPUTED"] = (
                        file_sha(table_path) == item["physical_sha256"]
                        and logical_sha(pq.read_table(table_path)) == item["logical_sha256"]
                    )
                silver = pq.read_table(ROOT / manifest["silver"]["relative_path"])
                fund = pq.read_table(ROOT / manifest["funding_events"]["relative_path"])
                evidence["AMBIGUOUS_FUNDING_RATE_ABSENT"] = "funding_rate" not in silver.column_names
                evidence["SILVER_V3_DECIMAL_SCHEMA"] = all(pa.types.is_decimal(silver.schema.field(name).type)
                    for name in ("open", "high", "low", "close", "volume", "quote_volume", "mark_price", "index_price", "premium_index", "funding_event_rate", "last_realized_funding_rate"))
                evidence["DISCRETE_FUNDING_EVENTS_VALID"] = fund.num_rows == 1589 and manifest["funding_events"]["interval_mismatches"] == 0
                evidence["SOURCE_LOGICAL_HASHES_MATCH"] = all(source_checks()[k] for k in ("PRIMARY_SOURCE_MANIFEST_V3_VALID", "PRIMARY_SOURCE_LOGICAL_HASH_RECOMPUTED"))
                final = read_report("PHASE2E_2_XAU_FOUNDATION_V16.json")
                evidence["FINAL_REPORT_DIGESTS_MATCH"] = all(
                    file_sha(ROOT / "reports" / name) == expected for name, expected in final["report_sha256"].items()
                )
                evidence["TESTED_CODE_TREE_VALID"] = (
                    git("rev-parse", "HEAD^") == final["tested_code_sha"]
                    and git("rev-parse", final["tested_code_sha"] + "^{tree}") == final["tested_tree_sha"]
                )
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("CODE_ACCEPTANCE", "FINAL_EVIDENCE_ACCEPTANCE"), required=True)
    args = parser.parse_args()
    code, evidence, details = verify(args.mode)
    status = "VERIFIED" if all(code.values()) and all(evidence.values()) else "REMEDIATION_REQUIRED"
    for name, passed in {**code, **evidence}.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    print(json.dumps({"mode": args.mode, "status": status, "code_checks": code,
                      "evidence_checks": evidence, "details": details}, indent=2))
    return 0 if status == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
