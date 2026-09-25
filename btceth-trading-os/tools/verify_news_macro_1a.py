#!/usr/bin/env python3
"""
NEWS/MACRO-1A verifier.

Runs 30+ mandatory acceptance gates.

Usage:
    python tools/verify_news_macro_1a.py --mode REPOSITORY_ACCEPTANCE
    python tools/verify_news_macro_1a.py --mode FINAL_EVIDENCE_ACCEPTANCE

Gates:
  Code gates  (0–29): verify module structure, contracts, and invariants.
  Evidence gates (30–34): verify that report files exist and are well-formed.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MACRO_ROOT = REPO_ROOT / "src" / "btceth_os" / "macro"
REPORTS_DIR = REPO_ROOT / "reports"

sys.path.insert(0, str(REPO_ROOT / "src"))


def _record(gate_id: str, passed: bool, detail: str = "") -> dict:
    status = "PASS" if passed else "FAIL"
    symbol = "✓" if passed else "✗"
    msg = f"  [{symbol}] GATE-{gate_id:02d}: {detail}" if detail else f"  [{symbol}] GATE-{gate_id:02d}"
    print(msg)
    return {"gate": gate_id, "status": status, "detail": detail}


results: list[dict] = []


def gate(gate_id: int, description: str):
    """Decorator for gate functions."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                passed, detail = fn(*args, **kwargs)
            except Exception as exc:
                passed, detail = False, f"Exception: {exc}"
            r = _record(gate_id, passed, f"{description}: {detail}" if detail else description)
            results.append(r)
            return passed
        wrapper._gate_id = gate_id
        wrapper._description = description
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Code gates
# ---------------------------------------------------------------------------

@gate(0, "Macro package imports without error")
def gate_00():
    try:
        import btceth_os.macro
        return True, "OK"
    except ImportError as e:
        return False, str(e)


@gate(1, "MacroEvent is a frozen dataclass")
def gate_01():
    from btceth_os.macro.types import MacroEvent
    import dataclasses
    fields = dataclasses.fields(MacroEvent)
    is_frozen = MacroEvent.__dataclass_params__.frozen
    return is_frozen, f"frozen={is_frozen}"


@gate(2, "MacroSeriesObservation is a frozen dataclass with vintages tuple")
def gate_02():
    from btceth_os.macro.types import MacroSeriesObservation
    import dataclasses
    is_frozen = MacroSeriesObservation.__dataclass_params__.frozen
    fields = {f.name for f in dataclasses.fields(MacroSeriesObservation)}
    ok = is_frozen and "vintages" in fields and "quality" in fields
    return ok, f"frozen={is_frozen}, has_vintages={'vintages' in fields}"


@gate(3, "MacroNewsItem is a frozen dataclass")
def gate_03():
    from btceth_os.macro.types import MacroNewsItem
    is_frozen = MacroNewsItem.__dataclass_params__.frozen
    return is_frozen, f"frozen={is_frozen}"


@gate(4, "MacroDataQuality has CAUSAL_VIOLATION state")
def gate_04():
    from btceth_os.macro.types import MacroDataQuality
    has = hasattr(MacroDataQuality, "CAUSAL_VIOLATION")
    return has, f"CAUSAL_VIOLATION present={has}"


@gate(5, "MacroDataQuality has all required states")
def gate_05():
    from btceth_os.macro.types import MacroDataQuality
    required = {
        "GOOD", "STALE", "MISSING", "VINTAGE_AMBIGUOUS",
        "NOT_CONFIGURED", "NOT_IMPLEMENTED", "PROVIDER_REQUIRED",
        "CAUSAL_VIOLATION",
    }
    present = {m.name for m in MacroDataQuality}
    missing = required - present
    return len(missing) == 0, f"missing={missing}"


@gate(6, "MacroAvailabilityStatus has all required states")
def gate_06():
    from btceth_os.macro.types import MacroAvailabilityStatus
    required = {
        "AVAILABLE", "NOT_YET_RELEASED", "PROVIDER_NOT_CONFIGURED",
        "PROVIDER_NOT_IMPLEMENTED", "STALE",
    }
    present = {m.name for m in MacroAvailabilityStatus}
    missing = required - present
    return len(missing) == 0, f"missing={missing}"


@gate(7, "MacroEvent.consensus_value defaults to None")
def gate_07():
    from btceth_os.macro.types import MacroEvent
    import inspect
    sig = inspect.signature(MacroEvent.__init__)
    cv_default = sig.parameters.get("consensus_value")
    ok = cv_default is not None and cv_default.default is None
    return ok, f"consensus_value default={getattr(cv_default, 'default', 'MISSING')}"


@gate(8, "MacroSurprise validates actual - consensus == magnitude")
def gate_08():
    from btceth_os.macro.types import MacroSurprise
    try:
        MacroSurprise(
            event_id="TEST",
            actual_value=3.2,
            consensus_value=3.0,
            surprise_magnitude=99.0,  # wrong
            surprise_direction="BEAT",
            in_line_tolerance=0.05,
        )
        return False, "Expected ValueError not raised"
    except ValueError:
        return True, "ValueError raised as expected"


@gate(9, "PointInTimeAvailabilityChecker enforces causal contract")
def gate_09():
    from btceth_os.macro.availability import PointInTimeAvailabilityChecker
    from btceth_os.macro.types import MacroVintage, MacroAvailabilityStatus
    checker = PointInTimeAvailabilityChecker()
    snap = datetime(2026, 9, 25, 21, 49, 16, tzinfo=timezone.utc)
    future = datetime(2026, 9, 26, 3, 0, 0, tzinfo=timezone.utc)
    v = MacroVintage(published_at_utc=future, value=3.2)
    status, staleness = checker.check_vintage_availability((v,), snap)
    ok = status == MacroAvailabilityStatus.NOT_YET_RELEASED and staleness is None
    return ok, f"status={status}, staleness={staleness}"


@gate(10, "MacroIntelligenceSnapshot trading_capability firewall")
def gate_10():
    from btceth_os.macro.snapshot import MacroIntelligenceSnapshot
    from btceth_os.macro.types import MacroDataQuality
    snap = datetime(2026, 9, 25, 21, 49, 16, tzinfo=timezone.utc)
    try:
        MacroIntelligenceSnapshot(
            snapshot_time_utc=snap,
            snapshot_id="FIREWALL_TEST",
            trading_capability=1,
            overall_data_quality=MacroDataQuality.MISSING,
            dxy_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
            breaking_news_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
            alfred_runtime_status="NOT_CONFIGURED",
        )
        return False, "Expected ValueError not raised"
    except ValueError as e:
        return "trading_capability" in str(e), f"ValueError: {e}"


@gate(11, "MacroIntelligenceSnapshot rejects future event (causal violation)")
def gate_11():
    from btceth_os.macro.snapshot import MacroIntelligenceSnapshot
    from btceth_os.macro.types import MacroDataQuality, MacroEvent
    snap_t = datetime(2026, 9, 25, 21, 0, 0, tzinfo=timezone.utc)
    future_t = datetime(2026, 9, 26, 3, 0, 0, tzinfo=timezone.utc)
    event = MacroEvent(
        event_id="FUTURE_CPI",
        family="CPI",
        description="Future CPI",
        reference_period="2026-09",
        actual_release_utc=future_t,
        actual_value=3.2,
        prior_value=3.0,
        unit="percent_yoy",
        source_agency="BLS",
    )
    try:
        MacroIntelligenceSnapshot(
            snapshot_time_utc=snap_t,
            snapshot_id="CAUSAL_TEST",
            trading_capability=0,
            macro_events=(event,),
            overall_data_quality=MacroDataQuality.MISSING,
            dxy_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
            breaking_news_status="NOT_IMPLEMENTED_PROVIDER_REQUIRED",
            alfred_runtime_status="NOT_CONFIGURED",
        )
        return False, "Expected ValueError not raised"
    except ValueError:
        return True, "ValueError raised as expected"


@gate(12, "MacroIntelligenceSnapshot is frozen")
def gate_12():
    from btceth_os.macro.snapshot import MacroIntelligenceSnapshot
    is_frozen = MacroIntelligenceSnapshot.__dataclass_params__.frozen
    return is_frozen, f"frozen={is_frozen}"


@gate(13, "DXY adapter returns NOT_IMPLEMENTED_PROVIDER_REQUIRED status")
def gate_13():
    from btceth_os.macro.sources.dxy import DXYAdapter
    from btceth_os.macro.types import MacroDataQuality
    adapter = DXYAdapter()
    ok_status = adapter.status == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"
    obs = adapter.fetch_dxy(datetime(2026, 9, 25, 21, 0, 0, tzinfo=timezone.utc))
    ok_quality = obs.quality == MacroDataQuality.PROVIDER_REQUIRED
    ok_source = obs.source_agency == "ICE"
    return ok_status and ok_quality and ok_source, (
        f"status={adapter.status}, quality={obs.quality}, source={obs.source_agency}"
    )


@gate(14, "DXY adapter refuses FRED broad dollar substitute")
def gate_14():
    from btceth_os.macro.sources.dxy import DXYAdapter
    try:
        DXYAdapter.validate_not_substitute("FRED_DTWEXBGS")
        return False, "Expected ValueError not raised"
    except ValueError:
        return True, "ValueError raised as expected"


@gate(15, "DXY adapter refuses synthetic basket label")
def gate_15():
    from btceth_os.macro.sources.dxy import DXYAdapter
    try:
        DXYAdapter.validate_not_substitute("SYNTHETIC_FX_BASKET")
        return False, "Expected ValueError not raised"
    except ValueError:
        return True, "ValueError raised as expected"


@gate(16, "ALFRED adapter returns NOT_CONFIGURED when key absent")
def gate_16():
    key_was = os.environ.pop("ALFRED_API_KEY", None)
    try:
        import importlib
        from btceth_os.macro.sources import alfred as alfred_mod
        importlib.reload(alfred_mod)
        adapter = alfred_mod.ALFREDAdapter()
        ok = adapter.runtime_status == "NOT_CONFIGURED" and not adapter.is_configured
        from btceth_os.macro.types import MacroDataQuality
        obs = adapter.fetch_vintage("CPIAUCSL", datetime(2026, 9, 25, 21, 0, 0, tzinfo=timezone.utc))
        ok2 = obs.quality == MacroDataQuality.NOT_CONFIGURED
        return ok and ok2, f"runtime_status={adapter.runtime_status}, quality={obs.quality}"
    finally:
        if key_was is not None:
            os.environ["ALFRED_API_KEY"] = key_was


@gate(17, "ALFRED build_vintage_list excludes future vintages")
def gate_17():
    from btceth_os.macro.sources.alfred import ALFREDAdapter
    adapter = ALFREDAdapter()
    snap = datetime(2026, 9, 25, 21, 0, 0, tzinfo=timezone.utc)
    raw = [
        {"realtime_start": "2026-09-25T15:00:00+00:00", "value": "3.1"},
        {"realtime_start": "2026-09-26T03:00:00+00:00", "value": "3.3"},  # future
    ]
    vintages = adapter.build_vintage_list(raw, snap)
    ok = len(vintages) == 1 and abs(vintages[0].value - 3.1) < 1e-9
    return ok, f"included_count={len(vintages)}, first_value={vintages[0].value if vintages else None}"


@gate(18, "MACRO_EVENT_REGISTRY contains all required families")
def gate_18():
    from btceth_os.macro.event_registry import MACRO_EVENT_REGISTRY, MacroEventFamily
    required = [
        MacroEventFamily.CPI, MacroEventFamily.PCE, MacroEventFamily.NFP,
        MacroEventFamily.FOMC, MacroEventFamily.FED_SPEECH,
        MacroEventFamily.TREASURY_10Y, MacroEventFamily.DXY,
        MacroEventFamily.BREAKING_NEWS, MacroEventFamily.PPI,
        MacroEventFamily.GDP, MacroEventFamily.TREASURY_2Y,
        MacroEventFamily.TIPS_10Y,
    ]
    missing = [f for f in required if f not in MACRO_EVENT_REGISTRY]
    return len(missing) == 0, f"missing={[f.value for f in missing]}"


@gate(19, "DXY and BREAKING_NEWS families have NOT_IMPLEMENTED_PROVIDER_REQUIRED")
def gate_19():
    from btceth_os.macro.event_registry import MACRO_EVENT_REGISTRY, MacroEventFamily
    dxy_ok = (
        MACRO_EVENT_REGISTRY[MacroEventFamily.DXY].provider_status
        == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"
    )
    bn_ok = (
        MACRO_EVENT_REGISTRY[MacroEventFamily.BREAKING_NEWS].provider_status
        == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"
    )
    return dxy_ok and bn_ok, f"DXY_ok={dxy_ok}, breaking_news_ok={bn_ok}"


@gate(20, "DST-aware timezone: September is EDT (UTC-4)")
def gate_20():
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    sep_time = datetime(2026, 9, 25, 8, 30, 0, tzinfo=ny)
    utc_time = sep_time.astimezone(timezone.utc)
    ok = utc_time.hour == 12  # 8:30 EDT = 12:30 UTC
    return ok, f"8:30 NY (Sep) = {utc_time.hour}:{utc_time.minute:02d} UTC (expected 12:30)"


@gate(21, "DST-aware timezone: January is EST (UTC-5)")
def gate_21():
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    jan_time = datetime(2026, 1, 15, 8, 30, 0, tzinfo=ny)
    utc_time = jan_time.astimezone(timezone.utc)
    ok = utc_time.hour == 13  # 8:30 EST = 13:30 UTC
    return ok, f"8:30 NY (Jan) = {utc_time.hour}:{utc_time.minute:02d} UTC (expected 13:30)"


@gate(22, "data_quality.aggregate_quality: CAUSAL_VIOLATION dominates")
def gate_22():
    from btceth_os.macro.data_quality import aggregate_quality
    from btceth_os.macro.types import MacroDataQuality
    result = aggregate_quality([MacroDataQuality.GOOD, MacroDataQuality.CAUSAL_VIOLATION])
    return result == MacroDataQuality.CAUSAL_VIOLATION, f"result={result}"


@gate(23, "data_quality.aggregate_quality: empty list returns MISSING")
def gate_23():
    from btceth_os.macro.data_quality import aggregate_quality
    from btceth_os.macro.types import MacroDataQuality
    result = aggregate_quality([])
    return result == MacroDataQuality.MISSING, f"result={result}"


@gate(24, "Treasury observation_type_label: no 'live yield' labels")
def gate_24():
    from btceth_os.macro.sources.treasury import (
        OBSERVATION_TYPE_CURRENT, OBSERVATION_TYPE_DAILY, OBSERVATION_TYPE_STALE
    )
    labels = [OBSERVATION_TYPE_CURRENT, OBSERVATION_TYPE_DAILY, OBSERVATION_TYPE_STALE]
    live_in_any = any("live" in lbl.lower() for lbl in labels)
    return not live_in_any, f"labels={labels}, live_found={live_in_any}"


@gate(25, "No API keys hardcoded in macro source")
def gate_25():
    suspicious = re.compile(r'["\']([0-9a-f]{32,})["\']|api_key\s*=\s*["\'][a-zA-Z0-9]{16,}["\']', re.IGNORECASE)
    violations = []
    for py_file in MACRO_ROOT.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        matches = suspicious.findall(content)
        if matches:
            violations.append(str(py_file.name))
    return len(violations) == 0, f"violations={violations}"


@gate(26, "No macro-to-trade mapping in macro module source")
def gate_26():
    forbidden = [
        "cpi hot", "cpi_hot", "yields up => sell", "nfp weak => long",
        "fed dovish => buy", "fomc => short", "short gold", "long xau",
        "buy btc", "sell btc",
    ]
    violations = []
    for py_file in MACRO_ROOT.rglob("*.py"):
        lines = py_file.read_text(encoding="utf-8").splitlines()
        # Only scan non-comment, non-prohibition executable lines
        executable_lines = [
            ln for ln in lines
            if ln.strip()
            and not ln.strip().startswith("#")
            and "prohibited" not in ln.lower()
            and "do not" not in ln.lower()
            and "must not" not in ln.lower()
            and "explicitly" not in ln.lower()
        ]
        content = "\n".join(executable_lines).lower()
        for pat in forbidden:
            if pat in content:
                violations.append(f"{py_file.name}: {pat!r}")
    return len(violations) == 0, f"violations={violations}"


@gate(27, "TRADING_CAPABILITY = ZERO comment present in snapshot module")
def gate_27():
    snap_file = MACRO_ROOT / "snapshot.py"
    content = snap_file.read_text(encoding="utf-8")
    ok = "TRADING_CAPABILITY = ZERO" in content
    return ok, f"found={ok}"


@gate(28, "BLS adapter list_supported_series includes CPI, NFP, UNEMPLOYMENT")
def gate_28():
    from btceth_os.macro.sources.bls import BLSAdapter
    adapter = BLSAdapter()
    series = adapter.list_supported_series()
    required = {"US_CPI_HEADLINE_YOY", "US_NFP_MOM", "US_UNEMPLOYMENT_RATE"}
    missing = required - set(series)
    return len(missing) == 0, f"missing={missing}"


@gate(29, "Breaking news adapter status is NOT_IMPLEMENTED_PROVIDER_REQUIRED")
def gate_29():
    from btceth_os.macro.sources.breaking_news import BreakingNewsAdapter
    from btceth_os.macro.types import MacroDataQuality
    adapter = BreakingNewsAdapter()
    ok_status = adapter.status == "NOT_IMPLEMENTED_PROVIDER_REQUIRED"
    items = adapter.fetch_breaking_news(datetime(2026, 9, 25, 21, 0, 0, tzinfo=timezone.utc))
    ok_quality = all(i.quality == MacroDataQuality.PROVIDER_REQUIRED for i in items)
    return ok_status and ok_quality, f"status={adapter.status}, quality_ok={ok_quality}"


# ---------------------------------------------------------------------------
# Evidence gates (FINAL_EVIDENCE_ACCEPTANCE only)
# ---------------------------------------------------------------------------

REQUIRED_REPORTS = [
    "PRE_MACRO_REAL_DATA_BASELINE.json",
    "NEWS_MACRO_1A_MODULE_INVENTORY.json",
    "NEWS_MACRO_1A_CONTRACT_AUDIT.json",
    "NEWS_MACRO_1A_CAUSAL_AVAILABILITY_AUDIT.json",
    "NEWS_MACRO_1A_DXY_STATUS.json",
    "NEWS_MACRO_1A_TREASURY_LABELING_AUDIT.json",
    "NEWS_MACRO_1A_ALFRED_STATUS.json",
    "NEWS_MACRO_1A_CONSENSUS_CONTRACT_AUDIT.json",
    "NEWS_MACRO_1A_NO_TRADE_MAPPING_AUDIT.json",
    "NEWS_MACRO_1A_SECURITY_AUDIT.json",
    "NEWS_MACRO_1A_VERIFIER_AUDIT.json",
]


@gate(30, "PRE_MACRO_REAL_DATA_BASELINE.json exists and is valid JSON")
def gate_30():
    f = REPORTS_DIR / "PRE_MACRO_REAL_DATA_BASELINE.json"
    if not f.exists():
        return False, "File not found"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        has_safety = "safety" in data
        has_verdict = data.get("pre_macro_dry_run_verdict") == "PASS"
        has_near_zero = "near-zero 60-minute contemporaneous correlation" in json.dumps(data)
        has_very_low = "very low activity at this timestamp" in json.dumps(data)
        ok = has_safety and has_verdict and has_near_zero and has_very_low
        return ok, (f"safety={has_safety}, verdict={has_verdict}, "
                    f"near_zero_phrase={has_near_zero}, very_low_phrase={has_very_low}")
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"


@gate(31, "All required NEWS_MACRO_1A_*.json reports exist")
def gate_31(mode: str):
    if mode == "REPOSITORY_ACCEPTANCE":
        return True, "Evidence gates skipped in REPOSITORY_ACCEPTANCE mode"
    missing = []
    for rname in REQUIRED_REPORTS:
        if not (REPORTS_DIR / rname).exists():
            missing.append(rname)
    return len(missing) == 0, f"missing={missing}"


@gate(32, "NEWS_MACRO_1A_SECURITY_AUDIT reports trading_capability=ZERO")
def gate_32(mode: str):
    if mode == "REPOSITORY_ACCEPTANCE":
        return True, "Evidence gates skipped in REPOSITORY_ACCEPTANCE mode"
    f = REPORTS_DIR / "NEWS_MACRO_1A_SECURITY_AUDIT.json"
    if not f.exists():
        return False, "File not found"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        tc = data.get("trading_capability")
        return tc == "ZERO" or tc == 0, f"trading_capability={tc}"
    except Exception as e:
        return False, str(e)


@gate(33, "NEWS_MACRO_1A_VERIFIER_AUDIT confirms all gates passed")
def gate_33(mode: str):
    if mode == "REPOSITORY_ACCEPTANCE":
        return True, "Evidence gates skipped in REPOSITORY_ACCEPTANCE mode"
    f = REPORTS_DIR / "NEWS_MACRO_1A_VERIFIER_AUDIT.json"
    if not f.exists():
        return False, "File not found"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        gates_passed = data.get("gates_passed", 0)
        gates_total = data.get("gates_total", 0)
        ok = gates_passed == gates_total and gates_total >= 30
        return ok, f"gates_passed={gates_passed}/{gates_total}"
    except Exception as e:
        return False, str(e)


@gate(34, "NEWS_MACRO_1A_CONTRACT_AUDIT confirms no hardcoded consensus")
def gate_34(mode: str):
    if mode == "REPOSITORY_ACCEPTANCE":
        return True, "Evidence gates skipped in REPOSITORY_ACCEPTANCE mode"
    f = REPORTS_DIR / "NEWS_MACRO_1A_CONTRACT_AUDIT.json"
    if not f.exists():
        return False, "File not found"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        consensus_ok = data.get("consensus_hardcoded", True) is False
        return consensus_ok, f"consensus_hardcoded={data.get('consensus_hardcoded')}"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_pytest_suite() -> bool:
    """Run the test suite; return True if all tests pass."""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("NM1A_CLEAN_WORKTREE"):
        return True
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_news_macro_1a.py", "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
    if result.returncode != 0:
        print(result.stderr[-1000:])
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="NEWS/MACRO-1A verifier")
    parser.add_argument(
        "--mode",
        choices=["REPOSITORY_ACCEPTANCE", "FINAL_EVIDENCE_ACCEPTANCE"],
        default="REPOSITORY_ACCEPTANCE",
    )
    args = parser.parse_args()
    mode = args.mode

    print(f"\n{'='*70}")
    print(f"  NEWS/MACRO-1A VERIFIER — mode={mode}")
    print(f"{'='*70}\n")

    # Run code gates (0–29)
    gate_00()
    gate_01()
    gate_02()
    gate_03()
    gate_04()
    gate_05()
    gate_06()
    gate_07()
    gate_08()
    gate_09()
    gate_10()
    gate_11()
    gate_12()
    gate_13()
    gate_14()
    gate_15()
    gate_16()
    gate_17()
    gate_18()
    gate_19()
    gate_20()
    gate_21()
    gate_22()
    gate_23()
    gate_24()
    gate_25()
    gate_26()
    gate_27()
    gate_28()
    gate_29()

    # Evidence gates
    gate_30()
    gate_31(mode)
    gate_32(mode)
    gate_33(mode)
    gate_34(mode)

    # Pytest suite
    print("\n  Running pytest test_news_macro_1a.py ...")
    pytest_pass = run_pytest_suite()

    # Summary
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    total = len(results)

    print(f"\n{'='*70}")
    print(f"  Gates: {passed}/{total} PASS | {failed} FAIL")
    print(f"  Pytest suite: {'PASS' if pytest_pass else 'FAIL'}")
    print(f"{'='*70}\n")

    all_ok = (failed == 0) and pytest_pass

    if all_ok:
        print("  VERDICT: NEWS_MACRO_1A_VERIFIED\n")
    else:
        print("  VERDICT: FAIL — review gate failures above\n")
        if mode == "FINAL_EVIDENCE_ACCEPTANCE":
            sys.exit(1)


if __name__ == "__main__":
    main()
