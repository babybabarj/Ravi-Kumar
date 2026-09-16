#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p reports artifacts
rm -rf artifacts/phase1a

choose_python() {
  if command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    if python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3,12) else 1)
PY
    then
      echo "python3"
      return
    fi
  fi
  if command -v brew >/dev/null 2>&1; then
    echo "Python 3.12 not found. Installing python@3.12 with Homebrew..." >&2
    brew install python@3.12 >&2 || exit 10
    echo "$(brew --prefix python@3.12)/bin/python3.12"
    return
  fi
  echo "ERROR: Python 3.12+ is required. Install Homebrew/Python 3.12 and rerun." >&2
  exit 10
}

PYTHON_BIN="$(choose_python)"
echo "Using: $PYTHON_BIN"

if [ ! -d .venv-phase1a ]; then
  "$PYTHON_BIN" -m venv .venv-phase1a || exit 11
fi
# shellcheck disable=SC1091
source .venv-phase1a/bin/activate
python -m pip install -U pip >/dev/null || exit 12
pip install -e '.[test]' >/dev/null || exit 13

TEST_EXIT=0
SECURITY_EXIT=0
SMOKE_EXIT=0

echo ""
echo "[1/4] Running automated + failure simulation tests..."
pytest -q 2>&1 | tee reports/TEST_RESULTS.txt
TEST_EXIT=${PIPESTATUS[0]}

echo ""
echo "[2/4] Running zero-trading security scan..."
python -m btceth_os.security_scan 2>&1 | tee reports/SECURITY_SCAN_OUTPUT.txt
SECURITY_EXIT=${PIPESTATUS[0]}

echo ""
echo "[3/4] Running live India public-market capture..."
python -m btceth_os.live_smoke 2>&1 | tee reports/LIVE_SMOKE_CAPTURE.txt
SMOKE_EXIT=${PIPESTATUS[0]}

echo ""
echo "[4/4] Validating persisted evidence and building acceptance reports..."

TEST_EXIT="$TEST_EXIT" SECURITY_EXIT="$SECURITY_EXIT" SMOKE_EXIT="$SMOKE_EXIT" python - <<'PY'
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pyarrow.parquet as pq

root = Path.cwd()
reports = root / "reports"
artifacts = root / "artifacts" / "phase1a"
reports.mkdir(exist_ok=True)

checks: dict[str, object] = {}
checks["pytest_exit"] = int(os.environ["TEST_EXIT"])
checks["security_exit"] = int(os.environ["SECURITY_EXIT"])
checks["live_smoke_exit"] = int(os.environ["SMOKE_EXIT"])

smoke_path = artifacts / "LIVE_SMOKE.json"
if smoke_path.exists():
    smoke = json.loads(smoke_path.read_text())
else:
    smoke = {"errors": ["LIVE_SMOKE.json missing"]}

checks["smoke"] = smoke
checks["rest_required"] = 20
checks["rest_observed"] = int(smoke.get("rest", 0))
checks["ws_observed_events"] = int(smoke.get("ws", 0))

ws_results = list(smoke.get("ws_stream_results", []))
required_ws = [r for r in ws_results if not r.get("sparse", False)]
liquidation_ws = [r for r in ws_results if r.get("sparse", False)]
required_missing = [
    f"{r.get('market')}:{r.get('dataset')}:{r.get('instrument_id')}:{r.get('status')}"
    for r in required_ws
    if int(r.get("messages_received", 0)) < 1 or r.get("status") != "EVENT_RECEIVED"
]
checks["required_ws_streams_expected"] = 12
checks["required_ws_streams_reported"] = len(required_ws)
checks["required_ws_streams_missing"] = required_missing
checks["liquidation_streams_expected"] = 2
checks["liquidation_streams_reported"] = len(liquidation_ws)
checks["liquidation_streams_ok"] = (
    len(liquidation_ws) == 2
    and all(
        r.get("status") in {"EVENT_RECEIVED", "CONNECTED_NO_EVENT_ACCEPTABLE"}
        for r in liquidation_ws
    )
)

checks["orderbooks_required"] = 4
checks["orderbooks_synced"] = int(smoke.get("orderbooks_synced", 0))
checks["source_errors"] = list(smoke.get("errors", []))

raw_files = list((artifacts / "raw").rglob("*.jsonl.gz")) if (artifacts / "raw").exists() else []
checks["raw_files"] = len(raw_files)

parquet_path = artifacts / "silver" / "live_smoke.parquet"
if parquet_path.exists():
    table = pq.read_table(parquet_path)
    checks["silver_readback_rows"] = table.num_rows
    required_cols = {
        "source", "market", "dataset", "instrument_id",
        "ts_event_ns", "ts_recv_ns", "ts_ingest_ns",
        "source_ts_raw", "source_ts_unit", "source_precision",
        "record_key", "payload_hash", "values_json",
    }
    checks["silver_schema_ok"] = required_cols.issubset(set(table.column_names))
else:
    checks["silver_readback_rows"] = 0
    checks["silver_schema_ok"] = False

catalog_path = artifacts / "catalog.sqlite"
health_rows = []
gap_rows = []
if catalog_path.exists():
    db = sqlite3.connect(catalog_path)
    checks["journal_mode"] = db.execute("PRAGMA journal_mode").fetchone()[0]
    for table_name in (
        "collector_runs", "collector_heartbeats", "connection_runs",
        "raw_live_objects", "live_gaps", "subscription_state", "collector_errors",
    ):
        checks[f"catalog_{table_name}"] = int(db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
    health_rows = db.execute(
        """
        SELECT h.collector_id,h.status,h.messages_received,h.records_written,
               h.duplicates_seen,h.gaps_detected,h.reconnect_count,h.parse_errors,
               h.source_errors,h.heartbeat_ns
        FROM collector_heartbeats h
        JOIN (
          SELECT collector_id,MAX(heartbeat_ns) AS mx
          FROM collector_heartbeats GROUP BY collector_id
        ) x ON x.collector_id=h.collector_id AND x.mx=h.heartbeat_ns
        ORDER BY h.collector_id
        """
    ).fetchall()
    gap_rows = db.execute(
        "SELECT collector_id,instrument,gap_type,expected_value,observed_value,status FROM live_gaps ORDER BY id"
    ).fetchall()
    db.close()
else:
    checks["journal_mode"] = "missing"
    checks["catalog_collector_runs"] = 0
    checks["catalog_collector_heartbeats"] = 0
    checks["catalog_collector_errors"] = 0

security_md = reports / "SECURITY_SCAN.md"
security_text = security_md.read_text() if security_md.exists() else ""
checks["trading_capability_zero"] = "TRADING CAPABILITY = ZERO" in security_text

criteria = {
    "automated_tests_pass": checks["pytest_exit"] == 0,
    "security_scan_pass": checks["security_exit"] == 0 and checks["trading_capability_zero"],
    "live_smoke_process_pass": checks["live_smoke_exit"] == 0,
    "all_rest_collectors_observed": checks["rest_observed"] >= checks["rest_required"],
    "required_ws_streams_observed": (
        checks["required_ws_streams_reported"] == checks["required_ws_streams_expected"]
        and len(checks["required_ws_streams_missing"]) == 0
    ),
    "liquidation_streams_reachable": bool(checks["liquidation_streams_ok"]),
    "four_orderbooks_synchronized": checks["orderbooks_synced"] == 4,
    "no_source_errors": len(checks["source_errors"]) == 0,
    "raw_append_only_evidence_present": checks["raw_files"] > 0,
    "silver_parquet_readback": checks["silver_readback_rows"] > 0 and checks["silver_schema_ok"],
    "catalog_present": checks.get("catalog_collector_runs", 0) > 0 and checks.get("catalog_collector_heartbeats", 0) > 0,
    "sqlite_wal": str(checks.get("journal_mode", "")).lower() == "wal",
}
verified = all(criteria.values())
status = "VERIFIED" if verified else "REMEDIATION_REQUIRED"

acceptance = {
    "phase": "1A",
    "status": status,
    "canonical_live_capture": "VERIFIED" if verified else "NOT_VERIFIED",
    "trading_capability": "ZERO" if criteria["security_scan_pass"] else "NOT_PROVEN",
    "criteria": criteria,
    "checks": checks,
}
(reports / "PHASE_1A_ACCEPTANCE.json").write_text(json.dumps(acceptance, indent=2, default=str))

md = ["# Phase 1A Acceptance", "", f"PHASE_1A = {status}", ""]
for name, passed in criteria.items():
    md.append(f"- [{'x' if passed else ' '}] {name}")
md.extend([
    "",
    f"CANONICAL LIVE CAPTURE = {'VERIFIED' if verified else 'NOT VERIFIED'}",
    f"TRADING CAPABILITY = {'ZERO' if criteria['security_scan_pass'] else 'NOT PROVEN'}",
    f"NEXT = {'PHASE 1B' if verified else 'REMEDIATE FAILED ITEMS'}",
    "",
    "## Smoke summary",
    "",
    "```json",
    json.dumps(smoke, indent=2),
    "```",
])
(reports / "PHASE_1A_ACCEPTANCE.md").write_text("\n".join(md) + "\n")

health = ["# Collector Health", "", "| Collector | Status | Msg | Rows | Dup | Gaps | Reconnect | Parse | Source Err |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
for r in health_rows:
    health.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} | {r[8]} |")
(reports / "COLLECTOR_HEALTH.md").write_text("\n".join(health) + "\n")

retention = """# Source Retention Matrix

| Source | Dataset | Phase 1A policy |
|---|---|---|
| Binance USD-M | OI / positioning / taker statistics | Perishable; bootstrap available official history then capture forward continuously |
| Binance USD-M | aggTrades / bookTicker / diff depth | Forward WebSocket capture + official REST/archive recovery where available |
| Binance USD-M | liquidation sample | Forward only; PARTIAL / SAMPLED_LARGEST_ORDER, never total liquidation truth |
| Binance Spot | aggTrades / bookTicker / diff depth | Forward WebSocket capture + official archive/REST historical build in Phase 1B |
| Deribit | BTC/ETH option state | Forward capture immediately; preserve raw option state and source timestamps |
"""
(reports / "SOURCE_RETENTION_MATRIX.md").write_text(retention)

schema = """# Schema Matrix

RAW: append-only gzip JSONL retaining the complete source payload and unknown fields.

SILVER: PyArrow Parquet with int64 nanosecond canonical timestamps, preserved source timestamp/unit/precision, payload hash, record key, and exact numeric values serialized without binary-float truth semantics.

Required clocks: ts_event_ns, ts_recv_ns, ts_ingest_ns.
"""
(reports / "SCHEMA_MATRIX.md").write_text(schema)

gap = ["# Gap Report", ""]
if gap_rows:
    gap.append("| Collector | Instrument | Type | Expected | Observed | Status |")
    gap.append("|---|---|---|---|---|---|")
    for r in gap_rows:
        gap.append("| " + " | ".join(str(x) for x in r) + " |")
else:
    gap.append("No catalogued live gaps in this bounded acceptance run.")
(reports / "GAP_REPORT.md").write_text("\n".join(gap) + "\n")

(reports / "LIVE_SMOKE_CAPTURE.md").write_text("# Live Smoke Capture\n\n```json\n" + json.dumps(smoke, indent=2) + "\n```\n")

print("\n================ FINAL ================")
print(f"PHASE_1A = {status}")
print(f"CANONICAL LIVE CAPTURE = {'VERIFIED' if verified else 'NOT VERIFIED'}")
print(f"TRADING CAPABILITY = {'ZERO' if criteria['security_scan_pass'] else 'NOT PROVEN'}")
if not verified:
    failed = [name for name, passed in criteria.items() if not passed]
    print("FAILED CRITERIA =", ", ".join(failed))
    if checks["required_ws_streams_missing"]:
        print("MISSING REQUIRED WS =", ", ".join(checks["required_ws_streams_missing"]))
print(f"NEXT = {'PHASE 1B' if verified else 'REMEDIATE FAILED ITEMS'}")
print("Reports:", reports)
raise SystemExit(0 if verified else 20)
PY
FINAL_EXIT=$?

exit "$FINAL_EXIT"
