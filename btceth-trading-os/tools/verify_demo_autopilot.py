from __future__ import annotations

import json
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

from btceth_os.autopilot.ledger import PaperLedger
from btceth_os.autopilot.live_approval import LiveApprovalGate, ProposalStatus
from btceth_os.autopilot.modes import OperatingMode
from btceth_os.autopilot.orchestrator import (
    MarketEvent,
    OrchestratorConfig,
    TradingOrchestrator,
)
from btceth_os.autopilot.strategy_registry import (
    StrategyIntent,
    StrategyState,
    SyntheticTestStrategy,
    TargetSpec,
)
from btceth_os.sources.binance.account_readonly import BinanceCredentials


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
ARTIFACTS = ROOT / "artifacts" / "demo_acceptance"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print("Running automated pytest test suite...")
    tests = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    (REPORTS / "DEMO_AUTOPILOT_TEST_RESULTS.txt").write_text(tests.stdout + tests.stderr)

    print("Running security scan...")
    security = _run([sys.executable, "-m", "btceth_os.security_scan"])
    (REPORTS / "DEMO_AUTOPILOT_SECURITY_SCAN.txt").write_text(security.stdout + security.stderr)

    checks: dict[str, bool] = {
        "automated_tests_pass": tests.returncode == 0,
        "security_scan_pass": security.returncode == 0 and '"trading_capability": "ZERO"' in security.stdout,
    }

    evidence: dict[str, object] = {}
    error: str | None = None

    try:
        now = time.time_ns()
        db_path = ARTIFACTS / "test_ledger.sqlite"
        if db_path.exists():
            db_path.unlink()
        state_path = ARTIFACTS / "test_state.json"

        cfg = OrchestratorConfig(
            db_path=db_path,
            dashboard_state_path=state_path,
            default_mode=OperatingMode.PAPER_AUTO,
            taker_fee_bps=Decimal("10"),
            slippage_bps=Decimal("5"),
        )
        orch = TradingOrchestrator(cfg)
        strat = SyntheticTestStrategy(strategy_id="ACCEPTANCE_STRATEGY")
        orch.registry.register(strat)
        orch.startup(now)

        # 1. Automatic entry & fee/slippage calculation
        intent = StrategyIntent.create(
            strategy_id="ACCEPTANCE_STRATEGY",
            strategy_version="1.0.0",
            instrument_candidate="BTCUSDT",
            direction="LONG",
            signal_ts_ns=now,
            signal_expiry_ns=now + 60_000_000_000,
            expected_holding_horizon="1h",
            invalidation_price=Decimal("49000"),
            stop_price=Decimal("49000"),
            targets=(
                TargetSpec(target_price=Decimal("51000"), exit_fraction=Decimal("0.5")),
                TargetSpec(target_price=Decimal("52000"), exit_fraction=Decimal("0.5")),
            ),
        )
        strat.queue_intent(intent)
        entry_ev = [MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)]
        res1 = orch.step(entry_ev, now)

        open_pos = orch.ledger.get_open_positions()
        checks["automatic_entry_pass"] = len(open_pos) == 1
        pos = open_pos[0]
        checks["fees_and_slippage_applied_pass"] = pos.fees > 0 and pos.average_entry > Decimal("50000")

        # 2. Target TP1 & TP2 automatic exits
        now_tp1 = now + 1_000_000_000
        tp1_ev = [MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("51200"), now_tp1, is_healthy=True)]
        orch.step(tp1_ev, now_tp1)
        checks["automatic_partial_target_pass"] = len(orch.ledger.get_open_positions()) == 1

        now_tp2 = now + 2_000_000_000
        tp2_ev = [MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("52200"), now_tp2, is_healthy=True)]
        orch.step(tp2_ev, now_tp2)
        checks["automatic_full_target_exit_pass"] = len(orch.ledger.get_open_positions()) == 0

        trades = orch.ledger.get_completed_trades()
        checks["pnl_persists_pass"] = len(trades) == 2 and all(t.net_pnl > 0 for t in trades)

        # 3. Stop Loss Test
        now_stop = now + 3_000_000_000
        intent_stop = StrategyIntent.create(
            strategy_id="ACCEPTANCE_STRATEGY",
            strategy_version="1.0.0",
            instrument_candidate="BTCUSDT",
            direction="LONG",
            signal_ts_ns=now_stop,
            signal_expiry_ns=now_stop + 60_000_000_000,
            expected_holding_horizon="1h",
            invalidation_price=Decimal("49000"),
            stop_price=Decimal("49000"),
            targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
        )
        strat.queue_intent(intent_stop)
        orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now_stop, is_healthy=True)], now_stop)
        now_breach = now_stop + 1_000_000_000
        orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("48800"), now_breach, is_healthy=True)], now_breach)
        recent_trades = orch.ledger.get_completed_trades()
        checks["automatic_stop_pass"] = recent_trades[0].exit_reason == "STOP_LOSS"

        # 4. Restart recovery test
        now_rec = now + 10_000_000_000
        intent_rec = StrategyIntent.create(
            strategy_id="ACCEPTANCE_STRATEGY",
            strategy_version="1.0.0",
            instrument_candidate="BTCUSDT",
            direction="LONG",
            signal_ts_ns=now_rec,
            signal_expiry_ns=now_rec + 60_000_000_000,
            expected_holding_horizon="1h",
            invalidation_price=Decimal("49000"),
            stop_price=Decimal("49000"),
            targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
        )
        strat.queue_intent(intent_rec)
        orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now_rec, is_healthy=True)], now_rec)
        pos_id_before = orch.ledger.get_open_positions()[0].position_id
        orch.ledger.close()

        # Reopen with fresh instance
        orch_reopened = TradingOrchestrator(cfg)
        orch_reopened.startup(now_rec + 5_000_000_000)
        open_recovered = orch_reopened.ledger.get_open_positions()
        checks["restart_recovery_pass"] = len(open_recovered) == 1 and open_recovered[0].position_id == pos_id_before

        # 5. Idempotency test
        strat_reopened = SyntheticTestStrategy(strategy_id="ACCEPTANCE_STRATEGY")
        orch_reopened.registry.register(strat_reopened)
        strat_reopened.queue_intent(intent_rec)
        orch_reopened.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50100"), now_rec + 6_000_000_000, is_healthy=True)], now_rec + 6_000_000_000)
        checks["duplicate_intent_protection_pass"] = len(orch_reopened.ledger.get_open_positions()) == 1

        # Clean close for remaining open position
        orch_reopened.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("48500"), now_rec + 7_000_000_000, is_healthy=True)], now_rec + 7_000_000_000)

        # 6. Kill switch test
        orch_reopened.control.pause("TEST_PAUSE")
        strat_reopened.queue_intent(intent_rec)
        orch_reopened.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now_rec + 8_000_000_000, is_healthy=True)], now_rec + 8_000_000_000)
        checks["kill_switch_pass"] = len(orch_reopened.ledger.get_open_positions()) == 0
        orch_reopened.control.resume()

        # 7. Credential safety test
        creds = BinanceCredentials("API_KEY_PUBLIC", "API_SECRET_CONFIDENTIAL")
        checks["credential_safety_pass"] = "API_SECRET_CONFIDENTIAL" not in repr(creds)

        # 8. Live approval mock gate test
        gate = LiveApprovalGate(default_ttl_seconds=5)
        prop = gate.generate_proposal(
            instrument="BINANCE:USD_M_PERP:BTCUSDT", market="usdm", side="BUY", entry_type="MARKET",
            proposed_quantity=Decimal("0.01"), current_price=Decimal("50000"), stop_price=Decimal("49000"),
            targets_str="[]", max_expected_loss=Decimal("10"), estimated_fees=Decimal("0.5"),
            estimated_funding=Decimal("0"), estimated_slippage=Decimal("0.25"),
            strategy_id="TEST", strategy_version="1.0.0", market_regime="NORMAL", reason="test",
            signal_ts_ns=now, now_ns=now,
        )
        ok_app, _ = gate.approve(prop.proposal_id, now + 1_000_000_000)
        checks["live_approval_mock_gate_pass"] = ok_app and len(gate.mock_adapter.dispatched_proposals) == 1

        # 9. Dashboard state verification
        dstate = json.loads(state_path.read_text(encoding="utf-8"))
        checks["dashboard_state_pass"] = (
            "system_control" in dstate
            and "data_health" in dstate
            and "market" in dstate
            and "paper" in dstate
            and "account" in dstate
        )

        evidence = {
            "completed_trades_count": len(orch_reopened.ledger.get_completed_trades()),
            "total_decisions_count": len(orch_reopened.ledger.get_recent_decisions(limit=100)),
            "audit_logs_count": len(orch_reopened.ledger.get_recent_audit_logs(limit=100)),
            "starting_equity": str(cfg.starting_equity),
            "final_equity": str(orch_reopened.portfolio.equity),
            "dashboard_state_path": str(state_path),
            "ledger_db_path": str(db_path),
        }
        orch_reopened.shutdown(now_rec + 9_000_000_000)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    verified = all(checks.values()) and error is None
    payload = {
        "phase": "DEMO_AUTOPILOT",
        "status": "VERIFIED" if verified else "REMEDIATION_REQUIRED",
        "trading_capability": "ZERO" if checks.get("security_scan_pass") else "FAIL",
        "checks": checks,
        "evidence": evidence,
        "error": error,
    }

    (REPORTS / "DEMO_AUTOPILOT_ACCEPTANCE.json").write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Demo Autopilot Orchestrator Acceptance",
        "",
        f"DEMO_AUTOPILOT = {payload['status']}",
        f"TRADING_CAPABILITY = {payload['trading_capability']}",
        "",
        "## Mechanical Acceptance Checks",
        "",
    ]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in checks.items())
    if evidence:
        lines.extend([
            "",
            "## Evidence Summary",
            "",
            f"- Completed trades in verification: `{evidence.get('completed_trades_count')}`",
            f"- Total decisions in ledger: `{evidence.get('total_decisions_count')}`",
            f"- Audit events logged: `{evidence.get('audit_logs_count')}`",
            f"- Starting Equity: `${evidence.get('starting_equity')}`",
            f"- Final Equity: `${evidence.get('final_equity')}`",
        ])
    if error:
        lines.extend(["", f"Error: `{error}`"])

    (REPORTS / "DEMO_AUTOPILOT_ACCEPTANCE.md").write_text("\n".join(lines) + "\n")
    print(f"DEMO_AUTOPILOT = {payload['status']}")
    return 0 if verified else 20


if __name__ == "__main__":
    raise SystemExit(main())
