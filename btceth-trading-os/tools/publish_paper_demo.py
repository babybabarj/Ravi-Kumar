from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from time import time_ns

from btceth_os.dashboard import write_dashboard_state
from btceth_os.safety import PaperPortfolio, ProposedPosition, RiskLimits, SafetySnapshot, simulate_paper_fill


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a clearly labeled local paper-demo snapshot to the dashboard.")
    parser.add_argument("--state", type=Path, default=Path("artifacts/dashboard/state.json"))
    args = parser.parse_args()
    now = time_ns()
    entry, mark = Decimal("50000"), Decimal("50500")
    proposal = ProposedPosition("BINANCE:SPOT:BTCUSDT", Decimal("0.001"), now)
    result = simulate_paper_fill(
        proposal, PaperPortfolio(Decimal("1000")),
        SafetySnapshot(Decimal("1000"), Decimal("1000"), Decimal("1000"), now, True),
        RiskLimits(Decimal("0.01"), Decimal("0.10"), Decimal("0.05"), 60_000_000_000),
        now_ns=now, mark_price=entry, taker_fee_bps=Decimal("10"), slippage_bps=Decimal("5"),
    )
    equity = result.portfolio.equity_at(mark)
    write_dashboard_state(args.state, {
        "data_health": {"status": "SIMULATED_HEALTHY", "last_event_ns": now, "open_gaps": 0},
        "market": {"status": "PAPER_DEMO", "instrument": proposal.instrument_id, "price": str(mark)},
        "signal": {"status": result.decision.reason, "target_position": str(proposal.target_position), "reason": "Local simulated fill; not live data"},
        "paper": {"status": "PAPER_DEMO", "cash": str(result.portfolio.cash), "position": str(result.portfolio.position), "equity": str(equity), "pnl": str(equity - Decimal("1000"))},
        "account": {"status": "NOT_CONNECTED", "last_sync_ns": None, "spot": {"balances": [], "open_orders": 0}, "usdm": {"balances": [], "positions": [], "open_orders": 0}, "error": None},
    })
    print(f"dashboard_state={args.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
