from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import aiohttp

from ..dashboard import read_dashboard_state
from .ledger import PaperLedger
from .modes import OperatingMode
from .orchestrator import MarketEvent, OrchestratorConfig, TradingOrchestrator


async def _run_loop(orchestrator: TradingOrchestrator, interval_seconds: float = 2.0) -> None:
    now_ns = time.time_ns()
    orchestrator.startup(now_ns)
    print(f"[Autopilot] Started in mode: {orchestrator.control.mode.value}")
    print("[Autopilot] Press Ctrl+C to stop.")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows or non-main thread

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        while not stop_event.is_set():
            step_now = time.time_ns()
            events: list[MarketEvent] = []

            # Fetch public Spot & USD-M tickers
            try:
                async with session.get("https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT") as r:
                    if r.status == 200:
                        data = await r.json()
                        mid = (Decimal(str(data["bidPrice"])) + Decimal(str(data["askPrice"]))) / Decimal("2")
                        events.append(MarketEvent("BINANCE:SPOT:BTCUSDT", mid, step_now, is_healthy=True))
            except Exception:
                pass

            try:
                async with session.get("https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=BTCUSDT") as r:
                    if r.status == 200:
                        data = await r.json()
                        mid = (Decimal(str(data["bidPrice"])) + Decimal(str(data["askPrice"]))) / Decimal("2")
                        events.append(MarketEvent("BINANCE:USD_M_PERP:BTCUSDT", mid, step_now, is_healthy=True))
            except Exception:
                pass

            # Step orchestrator
            res = orchestrator.step(events, step_now)

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                pass

    print("[Autopilot] Shutting down gracefully...")
    orchestrator.shutdown(time.time_ns())
    print("[Autopilot] Stopped.")


def print_status(config: OrchestratorConfig) -> int:
    state = read_dashboard_state(config.dashboard_state_path)
    ledger = PaperLedger(config.db_path)
    open_positions = ledger.get_open_positions()
    portfolio = ledger.load_or_init_portfolio(config.starting_equity, time.time_ns())
    decisions = ledger.get_recent_decisions(limit=1)
    latest_decision = decisions[0].reason_code if decisions else "NO_DECISIONS_RECORDED"

    report = {
        "mode": state.get("system_control", {}).get("mode", config.default_mode.value),
        "data_health": state.get("data_health", {}).get("status", "UNKNOWN"),
        "open_gaps": state.get("data_health", {}).get("open_gaps", 0),
        "cash": format(portfolio.cash, "f"),
        "equity": format(portfolio.equity, "f"),
        "daily_pnl": format(portfolio.equity - portfolio.day_start_equity, "f"),
        "open_positions": len(open_positions),
        "latest_decision": latest_decision,
        "dashboard_state_file": str(config.dashboard_state_path),
    }
    print(json.dumps(report, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BTCETH Trading OS Autonomous Autopilot Orchestrator")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "status", "pause", "resume"])
    parser.add_argument("--mode", default="PAPER_AUTO", choices=[m.value for m in OperatingMode])
    parser.add_argument("--db", type=Path, default=Path("artifacts/autopilot/ledger.sqlite"))
    parser.add_argument("--state", type=Path, default=Path("artifacts/dashboard/state.json"))
    parser.add_argument("--capital", type=Decimal, default=Decimal("1000"))
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    config = OrchestratorConfig(
        db_path=args.db,
        dashboard_state_path=args.state,
        starting_equity=args.capital,
        default_mode=OperatingMode(args.mode),
    )

    if args.command == "status":
        return print_status(config)

    orchestrator = TradingOrchestrator(config)

    if args.command == "pause":
        orchestrator.control.pause("CLI_PAUSE")
        print("Autopilot new entries paused.")
        return 0

    if args.command == "resume":
        orchestrator.control.resume()
        print("Autopilot resumed.")
        return 0

    try:
        asyncio.run(_run_loop(orchestrator, interval_seconds=args.interval))
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
