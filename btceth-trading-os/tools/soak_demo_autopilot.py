from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import sys
import time
from decimal import Decimal
from pathlib import Path

import aiohttp

from btceth_os.autopilot.modes import OperatingMode
from btceth_os.autopilot.orchestrator import (
    MarketEvent,
    OrchestratorConfig,
    TradingOrchestrator,
)
from btceth_os.dashboard import read_dashboard_state


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def _get_memory_mb() -> float:
    # ru_maxrss is in bytes on macOS, kilobytes on Linux
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return usage / (1024 * 1024)
    return usage / 1024


async def run_soak(seconds: int = 30) -> dict:
    REPORTS.mkdir(exist_ok=True)
    start_time = time.time()
    start_mem = _get_memory_mb()

    cfg = OrchestratorConfig(
        db_path=ROOT / "artifacts" / "soak" / "soak_ledger.sqlite",
        dashboard_state_path=ROOT / "artifacts" / "dashboard" / "state.json",
        default_mode=OperatingMode.PAPER_AUTO,
    )
    orch = TradingOrchestrator(cfg)
    now_ns = time.time_ns()
    orch.startup(now_ns)

    ticks = 0
    errors = 0
    reconnections = 0

    print(f"[Soak] Commencing demo autopilot soak test for {seconds} seconds...")

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
        while time.time() - start_time < seconds:
            step_now = time.time_ns()
            events: list[MarketEvent] = []

            # Poll public ticker
            try:
                async with session.get("https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT") as r:
                    if r.status == 200:
                        data = await r.json()
                        mid = (Decimal(str(data["bidPrice"])) + Decimal(str(data["askPrice"]))) / Decimal("2")
                        events.append(MarketEvent("BINANCE:SPOT:BTCUSDT", mid, step_now, is_healthy=True))
            except Exception as e:
                errors += 1

            try:
                async with session.get("https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=BTCUSDT") as r:
                    if r.status == 200:
                        data = await r.json()
                        mid = (Decimal(str(data["bidPrice"])) + Decimal(str(data["askPrice"]))) / Decimal("2")
                        events.append(MarketEvent("BINANCE:USD_M_PERP:BTCUSDT", mid, step_now, is_healthy=True))
            except Exception as e:
                errors += 1

            try:
                orch.step(events, step_now)
                ticks += 1
            except Exception as e:
                errors += 1

            await asyncio.sleep(1.0)

    end_mem = _get_memory_mb()
    uptime = time.time() - start_time
    orch.shutdown(time.time_ns())

    # Verify dashboard health
    dstate = read_dashboard_state(cfg.dashboard_state_path)
    dashboard_ok = dstate.get("paper", {}).get("status") in ("PAPER_AUTO_ACTIVE", "PAPER_PAUSED")

    report = {
        "status": "HEALTHY" if errors == 0 and dashboard_ok else "DEGRADED",
        "duration_seconds": round(uptime, 2),
        "ticks_processed": ticks,
        "unhandled_exceptions": errors,
        "reconnections": reconnections,
        "start_memory_mb": round(start_mem, 2),
        "end_memory_mb": round(end_mem, 2),
        "memory_growth_mb": round(max(0, end_mem - start_mem), 2),
        "dashboard_health": "HEALTHY" if dashboard_ok else "UNHEALTHY",
        "paper_equity": str(orch.portfolio.equity) if orch.portfolio else "0",
    }

    out_file = REPORTS / "DEMO_AUTOPILOT_SOAK.json"
    out_file.write_text(json.dumps(report, indent=2))
    print(f"[Soak] Complete. Status: {report['status']}, Ticks: {ticks}, Memory Growth: {report['memory_growth_mb']}MB")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(run_soak(args.seconds))
