"""Phase 2D public exchange-spec acceptance from captured Binance bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_multiasset_v11 import git, verify as verify_v11


IDS = (
    "BINANCE:SPOT:BTCUSDT",
    "BINANCE:USD_M_PERP:BTCUSDT",
    "BINANCE:SPOT:ETHUSDT",
    "BINANCE:USD_M_PERP:ETHUSDT",
    "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
)
SNAPSHOT_DIR = ROOT / "artifacts" / "instrument_specs"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load_snapshot(instrument_id: str) -> tuple[dict, dict[str, object]]:
    files = sorted((SNAPSHOT_DIR / "specs").glob(instrument_id.replace(":", "_") + "-*.json"))
    if not files:
        raise FileNotFoundError(f"Missing instrument snapshot: {instrument_id}")
    snapshot = json.loads(files[-1].read_text())
    if snapshot.get("instrument_id") != instrument_id:
        raise ValueError("Snapshot instrument identity mismatch")
    responses: dict[str, object] = {}
    for receipt in snapshot["source_snapshots"]:
        raw = (SNAPSHOT_DIR / receipt["raw_file"]).read_bytes()
        if sha(raw) != receipt["physical_sha256"]:
            raise ValueError("Raw response physical SHA mismatch")
        parsed = json.loads(raw, parse_float=str)
        if sha(canonical(parsed)) != receipt["logical_sha256"]:
            raise ValueError("Raw response logical SHA mismatch")
        responses[receipt["source_endpoint"]] = parsed
    return snapshot, responses


def verify(mode: str) -> tuple[dict[str, bool], dict[str, str]]:
    checks, details = verify_v11("CODE_ACCEPTANCE")
    try:
        snapshots = {instrument_id: load_snapshot(instrument_id) for instrument_id in IDS}
        checks["FIVE_SPEC_SNAPSHOTS_VERIFIED"] = len(snapshots) == 5
        xau, sources = snapshots[IDS[-1]]
        spec = xau["parsed_instrument_spec"]
        base = "https://fapi.binance.com"
        exchange = sources[base + "/fapi/v1/exchangeInfo"]
        row = [item for item in exchange["symbols"] if item["symbol"] == "XAUUSDT"]
        funding = sources[base + "/fapi/v1/fundingInfo"]
        funding_row = [item for item in funding if item["symbol"] == "XAUUSDT"]
        schedule = sources[base + "/fapi/v1/tradingSchedule"]
        premium = sources[base + "/fapi/v1/premiumIndex?symbol=XAUUSDT"]
        checks["XAU_PRODUCT_IDENTITY"] = (
            len(row) == 1
            and spec["instrument_id"] == IDS[-1]
            and row[0]["contractType"] == spec["contract_type"] == "TRADIFI_PERPETUAL"
            and row[0]["underlyingType"] == spec["underlying_type"] == "COMMODITY"
            and row[0]["marginAsset"] == spec["settlement_asset"] == "USDT"
        )
        filters = {item["filterType"]: item for item in row[0]["filters"]}
        checks["XAU_RULES_MATCH_SOURCE"] = (
            len(funding_row) == 1
            and spec["tick_size"] == filters["PRICE_FILTER"]["tickSize"]
            and spec["step_size"] == filters["LOT_SIZE"]["stepSize"]
            and spec["min_qty"] == filters["LOT_SIZE"]["minQty"]
            and spec["max_qty"] == filters["LOT_SIZE"]["maxQty"]
            and spec["min_notional"] == filters["MIN_NOTIONAL"]["notional"]
            and spec["current_funding_interval"] == funding_row[0]["fundingIntervalHours"] * 3600
        )
        checks["XAU_SESSION_AND_MARK_AVAILABLE"] = (
            bool(schedule.get("marketSchedules", {}).get("COMMODITY", {}).get("sessions"))
            and premium.get("symbol") == "XAUUSDT"
            and bool(premium.get("markPrice"))
            and bool(premium.get("indexPrice"))
        )
        checks["XAU_NOT_APPROVED_FOR_EXECUTION"] = (
            xau["execution_approval"] == "NOT_ACCEPTED"
            and spec["listing_ts"] is None
            and spec["exchange_max_leverage"] is None
        )
        details["xau_rules_logical_sha256"] = xau["rules_logical_sha256"]
        details["xau_exchange_info_physical_sha256"] = spec["exchange_info_snapshot_sha"]
    except (FileNotFoundError, KeyError, ValueError, TypeError) as exc:
        details["snapshot_error"] = f"{type(exc).__name__}: {exc}"
        for name in ("FIVE_SPEC_SNAPSHOTS_VERIFIED", "XAU_PRODUCT_IDENTITY", "XAU_RULES_MATCH_SOURCE", "XAU_SESSION_AND_MARK_AVAILABLE", "XAU_NOT_APPROVED_FOR_EXECUTION"):
            checks[name] = False
    try:
        probe_dir = SNAPSHOT_DIR / "probes"
        probe = json.loads((probe_dir / "probe_summary.json").read_text())
        required = ("exchangeInfo", "premiumIndex", "fundingInfo", "fundingRate", "bookTicker", "tradingSchedule")
        checks["XAU_PUBLIC_REST_PROBES"] = all(
            probe[name]["http_status"] == 200
            and sha((probe_dir / f"{name}.raw.json").read_bytes()) == probe[name]["physical_sha256"]
            for name in required
        ) and probe["exchangeInfo"]["xau_count"] == 1
        ws = json.loads((probe_dir / "markPriceMarketStream.probe.json").read_text())
        raw_ws = (probe_dir / "markPriceMarketStream.raw.json").read_bytes()
        event = json.loads(raw_ws)
        checks["XAU_ROUTED_WEBSOCKET"] = (
            ws["status"] == "RECEIVED"
            and ws["url"] == "wss://fstream.binance.com/market/ws/xauusdt@markPrice"
            and sha(raw_ws) == ws["physical_sha256"]
            and event.get("s") == "XAUUSDT"
            and event.get("e") == "markPriceUpdate"
        )
    except (FileNotFoundError, KeyError, ValueError, TypeError) as exc:
        details["probe_error"] = f"{type(exc).__name__}: {exc}"
        checks["XAU_PUBLIC_REST_PROBES"] = False
        checks["XAU_ROUTED_WEBSOCKET"] = False
    if mode == "FINAL_EVIDENCE_ACCEPTANCE":
        path = ROOT / "reports" / "PHASE2D_XAU_SPEC_ACCEPTANCE.json"
        if path.is_file():
            report = json.loads(path.read_text())
            payload = {key: value for key, value in report.items() if key != "payload_sha256"}
            changed = git("diff", "--name-only", "HEAD^", "HEAD").splitlines()
            checks["EVIDENCE_PAYLOAD"] = sha(canonical(payload)) == report.get("payload_sha256")
            checks["TESTED_CODE_TREE"] = (
                git("rev-parse", "HEAD^") == report.get("tested_code_commit_sha")
                and git("rev-parse", f"{report.get('tested_code_commit_sha')}^{{tree}}") == report.get("tested_tree_sha")
            )
            checks["EVIDENCE_ONLY_COMMIT"] = bool(changed) and all(
                item.startswith("btceth-trading-os/reports/") for item in changed
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
