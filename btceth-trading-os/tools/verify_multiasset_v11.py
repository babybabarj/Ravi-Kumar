"""Phase 2C instrument-identity acceptance; no exchange or holdout data access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.instruments import InstrumentSpec, SUPPORTED_INSTRUMENT_IDS, resolve_instrument
from btceth_os.research.data_guard import verify_access_ledger_integrity
from btceth_os.research.promotion_state import inspect_promotion_state


EXPECTED_IDS = {
    "BINANCE:SPOT:BTCUSDT",
    "BINANCE:USD_M_PERP:BTCUSDT",
    "BINANCE:SPOT:ETHUSDT",
    "BINANCE:USD_M_PERP:ETHUSDT",
    "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
}
EXPECTED_FIELDS = {
    "instrument_id", "venue", "symbol", "base_asset", "quote_asset", "settlement_asset",
    "product_family", "market_type", "contract_type", "underlying_type", "tradfi_asset_class",
    "listing_ts", "status", "price_precision", "quantity_precision", "tick_size", "step_size",
    "min_qty", "max_qty", "min_notional", "max_notional", "contract_size", "funding_enabled",
    "current_funding_interval", "leverage_supported", "exchange_max_leverage",
    "session_calendar_id", "price_index_type", "mark_price_type", "api_segment",
    "exchange_info_snapshot_sha", "effective_from_ts", "retrieved_at_ts",
}
BASELINE_SHA = "fb2d2c1f25f199ea040212fe683e64776754b805"


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def run_python(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def rejected(value: str) -> str:
    try:
        resolve_instrument(value)
    except ValueError as exc:
        return str(exc)
    return ""


def verify(mode: str) -> tuple[dict[str, bool], dict[str, str]]:
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}
    checks["CANONICAL_BASELINE"] = git("rev-parse", "btceth-phase1b") == BASELINE_SHA
    checks["BASELINE_ANCESTRY"] = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE_SHA, "HEAD"], cwd=ROOT, check=False
    ).returncode == 0
    checks["DEVELOPMENT_BRANCH"] = (
        git("branch", "--show-current") in ("", "btceth-phase2-multiasset")
        and git("rev-parse", "HEAD") == git("rev-parse", "btceth-phase2-multiasset")
    )
    checks["CLEAN_WORKTREE"] = git("status", "--porcelain=v1") == ""
    baseline_report = json.loads((ROOT / "reports" / "ROUND3B_0I_RELIABILITY_ACCEPTANCE.json").read_text())
    baseline_payload = {k: v for k, v in baseline_report.items() if k != "acceptance_payload_sha256"}
    baseline_digest = hashlib.sha256(json.dumps(baseline_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    checks["BASELINE_EVIDENCE_HASH"] = (
        baseline_digest == baseline_report.get("acceptance_payload_sha256")
        and baseline_report.get("tested_code_commit_sha") == "4612bb0e6cdc64b9f28a352d213305e7ffb692a2"
    )
    checks["CANONICAL_IDS"] = SUPPORTED_INSTRUMENT_IDS == EXPECTED_IDS
    checks["IMMUTABLE_SPEC_FIELDS"] = (
        InstrumentSpec.__dataclass_params__.frozen
        and set(InstrumentSpec.__dataclass_fields__) == EXPECTED_FIELDS
    )
    xae_error = rejected("XAEUSDT")
    checks["XAE_FAILS_CLOSED"] = (
        xae_error.startswith("Unknown instrument XAEUSDT.")
        and "XAUUSDT — Binance TradFi Gold perpetual" in xae_error
        and "XAUTUSDT — Tether Gold perpetual" in xae_error
    )
    checks["GOLD_PRODUCTS_DISTINCT"] = (
        resolve_instrument("XAUUSDT") == "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"
        and "support is not enabled" in rejected("XAUTUSDT")
        and "Ambiguous" in rejected("BTCUSDT")
    )
    tests = run_python("-m", "pytest", "-q")
    checks["FULL_PYTEST"] = tests.returncode == 0
    details["pytest_tail"] = "\n".join((tests.stdout + tests.stderr).splitlines()[-4:])
    security = run_python("-m", "btceth_os.security_scan")
    try:
        scan = json.loads(security.stdout)
    except json.JSONDecodeError:
        scan = {}
    checks["SECURITY_ZERO"] = security.returncode == 0 and scan.get("trading_capability") == "ZERO" and scan.get("hits") == []
    promotion = inspect_promotion_state()
    checks["ZERO_PROMOTIONS"] = (
        promotion.status == "VERIFIED"
        and promotion.persistent_total_experiments >= 26
        and promotion.persistent_approved_shadow == 0
        and promotion.persistent_approved_paper == 0
        and promotion.runtime_approved_shadow == 0
        and promotion.runtime_approved_paper == 0
    )
    ledger_ok, count, _, ledger = verify_access_ledger_integrity()
    checks["HOLDOUT_LOCKED"] = ledger_ok and count > 0 and ledger.get("allowed_holdout_accesses") == 0
    details["ledger_entries"] = str(count)
    if mode == "FINAL_EVIDENCE_ACCEPTANCE":
        report_path = ROOT / "reports" / "PHASE2C_MULTI_ASSET_ACCEPTANCE.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text())
            payload = {k: v for k, v in report.items() if k != "payload_sha256"}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            changed = git("diff", "--name-only", "HEAD^", "HEAD").splitlines()
            checks["EVIDENCE_PAYLOAD"] = digest == report.get("payload_sha256")
            checks["TESTED_CODE_TREE"] = (
                git("rev-parse", "HEAD^") == report.get("tested_code_commit_sha")
                and git("rev-parse", f"{report.get('tested_code_commit_sha')}^{{tree}}") == report.get("tested_tree_sha")
            )
            checks["EVIDENCE_ONLY_COMMIT"] = bool(changed) and all(
                path.startswith("btceth-trading-os/reports/") for path in changed
            )
        else:
            checks["EVIDENCE_PAYLOAD"] = False
            checks["TESTED_CODE_TREE"] = False
            checks["EVIDENCE_ONLY_COMMIT"] = False
        checks["REMOTE_HEAD"] = git("rev-parse", "HEAD") == git("rev-parse", "origin/btceth-phase2-multiasset")
    return checks, details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("CODE_ACCEPTANCE", "FINAL_EVIDENCE_ACCEPTANCE"), required=True)
    args = parser.parse_args()
    checks, details = verify(args.mode)
    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    print(f"GATES = {sum(checks.values())}/{len(checks)}")
    print(json.dumps(details, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
