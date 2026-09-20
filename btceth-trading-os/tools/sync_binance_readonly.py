from __future__ import annotations

import argparse
from pathlib import Path
from time import time_ns

from btceth_os.dashboard import read_dashboard_state, write_dashboard_state
from btceth_os.sources.binance.account_readonly import BinanceCredentials, BinanceReadOnlyError, read_spot_account, read_usdm_account


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Binance Spot and USD-M account summaries using read-only credentials.")
    parser.add_argument("--state", type=Path, default=Path("artifacts/dashboard/state.json"))
    parser.add_argument("--spot", action="store_true", help="sync only Spot when combined with --usdm")
    parser.add_argument("--usdm", action="store_true", help="sync only USD-M when combined with --spot")
    args = parser.parse_args()
    wanted = {"spot", "usdm"} if not (args.spot or args.usdm) else ({"spot"} if args.spot else set()) | ({"usdm"} if args.usdm else set())
    state, details, errors = read_dashboard_state(args.state), {}, []
    for product, prefix, reader in (
        ("spot", "BINANCE_SPOT_READONLY", read_spot_account),
        ("usdm", "BINANCE_USDM_READONLY", read_usdm_account),
    ):
        if product not in wanted:
            continue
        try:
            details[product] = reader(BinanceCredentials.from_environment(prefix)).dashboard_summary()
        except BinanceReadOnlyError as exc:
            errors.append(f"{product}: {exc}")
    existing = state["account"]
    spot = details.get("spot", existing["spot"])
    usdm = details.get("usdm", existing["usdm"])
    state["account"] = {"status": "READ_ONLY_CONNECTED" if details and not errors else "DEGRADED", "last_sync_ns": time_ns(), "spot": spot, "usdm": usdm, "error": "; ".join(errors) or None}
    state["data_health"] = {"status": "ACCOUNT_SYNC_HEALTHY" if details and not errors else "DEGRADED", "last_event_ns": state["account"]["last_sync_ns"], "open_gaps": 0}
    write_dashboard_state(args.state, state)
    print(f"dashboard_state={args.state}")
    return 0 if details and not errors else 20


if __name__ == "__main__":
    raise SystemExit(main())
