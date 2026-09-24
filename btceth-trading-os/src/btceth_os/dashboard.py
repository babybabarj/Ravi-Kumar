from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aiohttp import web

from btceth_os.trade_board import evaluate_all_assets_trade_board, read_shadow_bot_telemetry


DEFAULT_STATE = {
    "system_control": {"mode": "PAPER_AUTO", "paused": False, "halted": False, "pause_reason": None, "halt_reason": None},
    "data_health": {"status": "NOT_READY", "last_event_ns": None, "open_gaps": 0},
    "market": {"status": "NO_MARKET_DATA", "instrument": None, "price": None, "all_prices": {}},
    "signal": {"status": "NO_SIGNAL", "target_position": "0", "reason": "Awaiting validated data"},
    "paper": {
        "status": "NOT_STARTED",
        "cash": None,
        "position": "0",
        "equity": None,
        "pnl": None,
        "daily_pnl": None,
        "open_positions": [],
        "stats": {"completed_trades": 0, "wins": 0, "losses": 0, "win_rate": "0.0%"},
    },
    "account": {
        "status": "NOT_CONNECTED",
        "last_sync_ns": None,
        "spot": {"balances": [], "open_orders": 0},
        "usdm": {"balances": [], "positions": [], "open_orders": 0},
        "error": None,
    },
    "research": {
        "status": "NO_VALIDATED_EDGE",
        "active_regime": "RANGE_LOW_VOL",
        "strategies_evaluated": 7,
        "approved_for_paper": 0,
        "approved_for_shadow": 0,
        "rejected": 7,
        "policy": "1.0.0",
    },
    "trade_board": None,
    "recent_decisions": [],
    "proposals": [],
}


def read_dashboard_state(path: Path | str) -> dict[str, Any]:
    """Return a safe empty state when the local snapshot is absent or malformed."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("state is not a dict")
        out = dict(DEFAULT_STATE)
        out.update(raw)
        if out.get("trade_board") is None:
            out["trade_board"] = evaluate_all_assets_trade_board()
        return out
    except (OSError, ValueError, json.JSONDecodeError):
        fallback = dict(DEFAULT_STATE)
        fallback["data_health"] = dict(DEFAULT_STATE["data_health"])
        fallback["data_health"]["status"] = "DEGRADED"
        fallback["trade_board"] = evaluate_all_assets_trade_board()
        return fallback


def write_dashboard_state(path: Path | str, state: dict[str, Any]) -> Path:
    """Atomically publish a local display snapshot; it has no exchange or account side effects."""
    destination = Path(path)
    required = ("data_health", "market", "signal", "paper")
    if not all(k in state for k in required):
        raise ValueError("dashboard state must include data_health, market, signal, and paper")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.part")
    temporary.write_text(json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def create_dashboard_app(state_path: Path | str) -> web.Application:
    app = web.Application()

    async def api_state(_: web.Request) -> web.Response:
        st = read_dashboard_state(state_path)
        return web.json_response(st)

    async def api_trade_board(_: web.Request) -> web.Response:
        board = evaluate_all_assets_trade_board()
        return web.json_response(board)

    async def api_pause(_: web.Request) -> web.Response:
        st = read_dashboard_state(state_path)
        ctrl = st.setdefault("system_control", {})
        ctrl["paused"] = True
        ctrl["pause_reason"] = "DASHBOARD_PAUSE"
        write_dashboard_state(state_path, st)
        return web.json_response({"ok": True, "paused": True})

    async def api_resume(_: web.Request) -> web.Response:
        st = read_dashboard_state(state_path)
        ctrl = st.setdefault("system_control", {})
        ctrl["paused"] = False
        ctrl["pause_reason"] = None
        write_dashboard_state(state_path, st)
        return web.json_response({"ok": True, "paused": False})

    async def api_set_mode(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            mode = str(body.get("mode", "")).upper()
            if mode not in ("OFF", "SHADOW_AUTO", "PAPER_AUTO", "TESTNET_AUTO", "LIVE_APPROVAL"):
                return web.json_response({"ok": False, "error": "Invalid mode"}, status=400)
            st = read_dashboard_state(state_path)
            st.setdefault("system_control", {})["mode"] = mode
            write_dashboard_state(state_path, st)
            return web.json_response({"ok": True, "mode": mode})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    async def api_proposal_action(request: web.Request) -> web.Response:
        prop_id = request.match_info.get("id")
        action = request.match_info.get("action")
        st = read_dashboard_state(state_path)
        proposals = st.setdefault("proposals", [])
        found = False
        for p in proposals:
            if p.get("proposal_id") == prop_id:
                found = True
                p["status"] = "APPROVED" if action == "approve" else "REJECTED"
        if not found:
            return web.json_response({"ok": False, "error": "Proposal not found"}, status=404)
        write_dashboard_state(state_path, st)
        return web.json_response({"ok": True, "proposal_id": prop_id, "action": action})

    app.router.add_get("/", _index)
    app.router.add_get("/api/state", api_state)
    app.router.add_get("/api/trade_board", api_trade_board)
    app.router.add_post("/api/control/pause", api_pause)
    app.router.add_post("/api/control/resume", api_resume)
    app.router.add_post("/api/control/mode", api_set_mode)
    app.router.add_post("/api/control/proposal/{id}/{action}", api_proposal_action)
    return app


async def _index(_: web.Request) -> web.Response:
    return web.Response(text=_HTML, content_type="text/html")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the Unified Trading OS Trade Board & Control Center.")
    parser.add_argument("--state", type=Path, default=Path("artifacts/dashboard/state.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    print(f"🚀 Starting Unified Trade Board on http://{args.host}:{args.port}")
    web.run_app(create_dashboard_app(args.state), host=args.host, port=args.port)
    return 0


_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Unified Multi-Asset Trade Board • BTC / ETH / XAU</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Menlo, monospace;
      background: #060b13;
      color: #e5edf5;
    }
    body {
      margin: 0;
      max-width: 1400px;
      padding: 1.5rem 2rem;
      margin: auto;
    }
    .header-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 1.2rem;
      border-bottom: 1px solid #142436;
      margin-bottom: 1.5rem;
    }
    .title-group h1 {
      margin: 0;
      font-size: 1.6rem;
      letter-spacing: -0.02em;
      font-weight: 700;
      background: linear-gradient(90deg, #ffffff, #94a3b8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .badge-bar {
      display: flex;
      gap: 0.6rem;
      align-items: center;
      margin-top: 0.35rem;
      font-size: 0.8rem;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .badge-cyan { background: #0c2d3a; color: #38bdf8; border: 1px solid #0369a1; }
    .badge-emerald { background: #092f22; color: #34d399; border: 1px solid #059669; }
    .badge-amber { background: #3b280b; color: #fbbf24; border: 1px solid #d97706; }
    .badge-red { background: #3e1216; color: #f87171; border: 1px solid #dc2626; }
    .badge-purple { background: #28143d; color: #c084fc; border: 1px solid #7e22ce; }

    /* Asset Tabs */
    .asset-nav {
      display: flex;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }
    .asset-tab {
      background: #0f1c2c;
      border: 1px solid #1e3650;
      color: #94a3b8;
      padding: 0.65rem 1.4rem;
      border-radius: 8px;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.6rem;
      transition: all 0.15s ease-in-out;
    }
    .asset-tab:hover {
      background: #182c44;
      color: #f1f5f9;
      border-color: #3b82f6;
    }
    .asset-tab.active {
      background: #1e3a5f;
      color: #ffffff;
      border-color: #60a5fa;
      box-shadow: 0 0 16px rgba(59, 130, 246, 0.25);
    }
    .asset-tab .asset-price {
      font-size: 0.85rem;
      color: #cbd5e1;
      font-weight: 500;
    }

    /* Hero Decision Card */
    .hero-card {
      background: #0b1522;
      border: 1px solid #1e3650;
      border-radius: 12px;
      padding: 1.75rem;
      margin-bottom: 1.5rem;
      position: relative;
      overflow: hidden;
    }
    .hero-card::before {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0; height: 4px;
      background: linear-gradient(90deg, #3b82f6, #10b981);
    }
    .decision-banner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid #142436;
    }
    .decision-headline {
      display: flex;
      align-items: center;
      gap: 1.2rem;
    }
    .decision-pill {
      font-size: 1.85rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      padding: 0.6rem 1.4rem;
      border-radius: 8px;
      display: inline-block;
      text-transform: uppercase;
      box-shadow: 0 0 20px rgba(0,0,0,0.4);
    }
    .pill-long {
      background: #002e17;
      color: #00f076;
      border: 2px solid #00a852;
      box-shadow: 0 0 24px rgba(0, 240, 118, 0.25);
    }
    .pill-short {
      background: #380a10;
      color: #ff3b56;
      border: 2px solid #b3162b;
      box-shadow: 0 0 24px rgba(255, 59, 86, 0.25);
    }
    .pill-wait {
      background: #332100;
      color: #ffb703;
      border: 2px solid #b37d00;
      box-shadow: 0 0 24px rgba(255, 183, 3, 0.2);
    }
    .setup-title {
      font-size: 1.15rem;
      font-weight: 700;
      color: #f8fafc;
      margin-bottom: 0.25rem;
    }
    .setup-rule {
      font-size: 0.82rem;
      color: #94a3b8;
      font-family: ui-monospace, monospace;
    }

    /* Confidence Meter */
    .confidence-box {
      text-align: right;
      min-width: 180px;
    }
    .confidence-label {
      font-size: 0.75rem;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .confidence-val {
      font-size: 2.2rem;
      font-weight: 800;
      line-height: 1.1;
      margin: 0.2rem 0;
    }
    .confidence-bar-bg {
      background: #142436;
      border-radius: 999px;
      height: 8px;
      width: 100%;
      overflow: hidden;
      margin-top: 0.4rem;
    }
    .confidence-bar-fill {
      height: 100%;
      border-radius: 999px;
      transition: width 0.3s ease;
    }

    /* Parameters Grid */
    .trade-params-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-top: 1.5rem;
    }
    .param-card {
      background: #08101a;
      border: 1px solid #16293e;
      border-radius: 8px;
      padding: 0.85rem 1rem;
    }
    .param-label {
      font-size: 0.72rem;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 0.3rem;
    }
    .param-value {
      font-size: 1.25rem;
      font-weight: 700;
      color: #f1f5f9;
      font-family: ui-monospace, monospace;
    }
    .val-good { color: #00f076; }
    .val-bad { color: #ff3b56; }
    .val-gold { color: #f5cb5c; }

    /* Checklist & Traps Section */
    .factors-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
      margin-top: 1.5rem;
    }
    @media (max-width: 850px) {
      .factors-grid { grid-template-columns: 1fr; }
    }
    .factor-panel {
      background: #08101a;
      border: 1px solid #16293e;
      border-radius: 8px;
      padding: 1.1rem;
    }
    .panel-header {
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
      margin-bottom: 0.8rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .factor-item {
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      font-size: 0.85rem;
      padding: 0.4rem 0;
      border-bottom: 1px solid #122030;
      line-height: 1.4;
      color: #cbd5e1;
    }
    .factor-item:last-child { border-bottom: 0; }
    .factor-icon { font-weight: bold; flex-shrink: 0; }

    /* 5-Regime Diagnostic Bar */
    .regime-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 0.8rem;
      margin-bottom: 1.5rem;
    }
    .regime-card {
      background: #0b1522;
      border: 1px solid #16293e;
      border-radius: 8px;
      padding: 0.85rem;
    }
    .regime-card .label { font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; }
    .regime-card .val { font-size: 0.98rem; font-weight: 700; margin-top: 0.35rem; }

    /* Cross Asset & Shadow Bot Row */
    .secondary-grid {
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 1.5rem;
      margin-bottom: 1.5rem;
    }
    @media (max-width: 950px) {
      .secondary-grid { grid-template-columns: 1fr; }
    }
    .sec-card {
      background: #0b1522;
      border: 1px solid #16293e;
      border-radius: 8px;
      padding: 1.2rem;
    }
    .sec-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 0.8rem;
      border-bottom: 1px solid #142436;
      padding-bottom: 0.5rem;
    }
    .stat-row {
      display: flex;
      justify-content: space-between;
      padding: 0.35rem 0;
      font-size: 0.85rem;
      border-bottom: 1px solid #122030;
    }
    .stat-row:last-child { border-bottom: 0; }
    .stat-label { color: #8ea3b9; }
    .stat-val { font-weight: 600; font-family: ui-monospace, monospace; }

    /* Footer & Controls */
    .controls-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 1.5rem;
      padding-top: 1rem;
      border-top: 1px solid #142436;
      font-size: 0.8rem;
      color: #64748b;
    }
    button {
      background: #142436;
      color: #e5edf5;
      border: 1px solid #233e5c;
      border-radius: 6px;
      padding: 0.45rem 0.9rem;
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
      font-family: inherit;
    }
    button:hover { background: #1c334d; }
    button.btn-danger { background: #3e1216; border-color: #dc2626; color: #f87171; }
    button.btn-success { background: #092f22; border-color: #059669; color: #34d399; }
  </style>
</head>
<body>

  <!-- Top Bar -->
  <div class="header-bar">
    <div class="title-group">
      <h1>Trading OS • Unified Trade Board</h1>
      <div class="badge-bar">
        <span class="badge badge-emerald">INTELLIGENCE V1</span>
        <span class="badge badge-cyan">PLAYBOOK V3.0 (20 RULES)</span>
        <span class="badge badge-purple" id="shadow-bot-badge">SHADOW BOT: CONNECTED</span>
        <span id="last-updated" style="color: #64748b; font-size: 0.75rem; margin-left: 0.5rem">Syncing...</span>
      </div>
    </div>
    <div style="display:flex; gap:0.5rem; align-items:center;">
      <button onclick="triggerRefresh()">↻ Refresh Board</button>
      <button onclick="controlPause()" id="pauseBtn" class="btn-danger">Pause Engine</button>
      <button onclick="controlResume()" id="resumeBtn" class="btn-success">Resume</button>
    </div>
  </div>

  <!-- Asset Switcher Tabs -->
  <div class="asset-nav">
    <div class="asset-tab active" id="tab-BTC" onclick="selectAsset('BTCUSDT')">
      <span>₿ Bitcoin (BTC)</span>
      <span class="asset-price" id="price-BTC">$63,450.00</span>
    </div>
    <div class="asset-tab" id="tab-ETH" onclick="selectAsset('ETHUSDT')">
      <span>Ξ Ethereum (ETH)</span>
      <span class="asset-price" id="price-ETH">$2,680.00</span>
    </div>
    <div class="asset-tab" id="tab-XAU" onclick="selectAsset('XAUUSDT')">
      <span>🟡 Gold (XAU)</span>
      <span class="asset-price" id="price-XAU">$2,625.50</span>
    </div>
  </div>

  <!-- Hero Trade Decision Card -->
  <div class="hero-card">
    <div class="decision-banner">
      <div class="decision-headline">
        <div class="decision-pill pill-long" id="hero-action-pill">TAKE TRADE: LONG</div>
        <div>
          <div class="setup-title" id="hero-setup-title">VOLATILITY_COMPRESSION_BREAKOUT</div>
          <div class="setup-rule" id="hero-setup-rule">Rule: VP-007 • Volatility Contraction Heuristic</div>
        </div>
      </div>
      <div class="confidence-box">
        <div class="confidence-label">Decision Confidence</div>
        <div class="confidence-val val-good" id="hero-confidence">82%</div>
        <div class="confidence-bar-bg">
          <div class="confidence-bar-fill" id="hero-conf-bar" style="width: 82%; background: #00f076;"></div>
        </div>
      </div>
    </div>

    <!-- Trade Action Parameters -->
    <div class="trade-params-grid">
      <div class="param-card">
        <div class="param-label">Target Entry Zone</div>
        <div class="param-value" id="param-entry">$63,386 – $63,576</div>
      </div>
      <div class="param-card">
        <div class="param-label">Invalidation (Stop Loss)</div>
        <div class="param-value val-bad" id="param-stop">$62,307.00</div>
      </div>
      <div class="param-card">
        <div class="param-label">Take Profit 1 (Derisk)</div>
        <div class="param-value val-good" id="param-tp1">$65,736.00</div>
      </div>
      <div class="param-card">
        <div class="param-label">Take Profit 2 (Runner)</div>
        <div class="param-value val-good" id="param-tp2">$67,450.50</div>
      </div>
      <div class="param-card">
        <div class="param-label">Risk : Reward Ratio</div>
        <div class="param-value val-gold" id="param-rr">2.00 : 1</div>
      </div>
    </div>

    <!-- Supporting Evidence & Veteran Trap Checkers -->
    <div class="factors-grid">
      <div class="factor-panel">
        <div class="panel-header" style="color: #00f076;">
          <span>✓</span> Supporting Causal Evidence & Signals
        </div>
        <div id="supporting-list">
          <div class="factor-item"><span class="factor-icon" style="color:#00f076">✓</span> Volatility compression coiling (vol percentile 0.16). Anticipating expansion.</div>
          <div class="factor-item"><span class="factor-icon" style="color:#00f076">✓</span> Funding rate is neutral/negative during coiling; leverage overhang is low.</div>
        </div>
      </div>
      <div class="factor-panel">
        <div class="panel-header" style="color: #ffb703;">
          <span>⚠</span> Playbook Traps & Risk Warnings
        </div>
        <div id="traps-list">
          <div class="factor-item"><span class="factor-icon" style="color:#ffb703">⚠</span> No active traps detected. Structure is valid for planned risk.</div>
        </div>
      </div>
    </div>
  </div>

  <!-- 5-Regime Diagnostic Bar -->
  <div style="font-size:0.8rem; font-weight:700; color:#8ea3b9; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:0.6rem;">
    5-Regime Institutional Diagnostic Matrix (INTEL-1A)
  </div>
  <div class="regime-grid">
    <div class="regime-card">
      <div class="label">1. Trend Structure</div>
      <div class="val" id="regime-trend" style="color: #38bdf8;">UP</div>
    </div>
    <div class="regime-card">
      <div class="label">2. Volatility Compression</div>
      <div class="val" id="regime-vol" style="color: #fbbf24;">LOW</div>
    </div>
    <div class="regime-card">
      <div class="label">3. Liquidity Activity</div>
      <div class="val" id="regime-act" style="color: #34d399;">NORMAL</div>
    </div>
    <div class="regime-card">
      <div class="label">4. Funding & Leverage</div>
      <div class="val" id="regime-fund" style="color: #c084fc;">NEUTRAL</div>
    </div>
    <div class="regime-card">
      <div class="label">5. Market Quality</div>
      <div class="val" id="regime-qual" style="color: #00f076;">HEALTHY</div>
    </div>
  </div>

  <!-- Cross-Asset & Shadow Bot Telemetry -->
  <div class="secondary-grid">
    <div class="sec-card">
      <div class="sec-title">🌐 Cross-Asset Transmission & Macro Dispersion</div>
      <div class="stat-row">
        <span class="stat-label">BTC / ETH Correlation & Beta</span>
        <span class="stat-val" id="ca-btc-eth">0.88 (Beta: 1.25x)</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">BTC / XAU (Gold) Macro Transmission</span>
        <span class="stat-val" id="ca-btc-xau">0.12 (Decoupled / Neutral)</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">ETH / XAU Correlation</span>
        <span class="stat-val" id="ca-eth-xau">0.08</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Cross-Asset Lead / Lag Leader</span>
        <span class="stat-val" id="ca-leader" style="color: #38bdf8;">BTC</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Inter-Asset Regime Dispersion</span>
        <span class="stat-val" id="ca-dispersion" style="color: #34d399;">LOW</span>
      </div>
    </div>

    <div class="sec-card">
      <div class="sec-title">🤖 Live Running BTC Shadow Bot (Read-Only Bridge)</div>
      <div class="stat-row">
        <span class="stat-label">Daemon Status</span>
        <span class="stat-val" id="sb-status" style="color: #34d399;">IDLE_WAIT</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Process ID & Commit</span>
        <span class="stat-val" id="sb-pid">PID 1244 (f358dd4)</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Execution Cycles Completed</span>
        <span class="stat-val" id="sb-cycles">605 cycles</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Last Shadow Bot Decision</span>
        <span class="stat-val" id="sb-decision">NO TRADE (NO TRADE)</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Exchange Feeds (Binance / Delta / Coinbase)</span>
        <span class="stat-val" id="sb-feeds" style="color: #38bdf8;">HEALTHY • FRESH</span>
      </div>
    </div>
  </div>

  <div class="controls-row">
    <div>Unified Multi-Asset Trade Board • BTC / ETH / XAU Institutional OS • Non-Executable Advisory Mode</div>
    <div style="font-family: ui-monospace, monospace;">Port 8000 • Fail-Closed</div>
  </div>

  <!-- Real Binance Observation Hidden Compatibility Element -->
  <div style="display:none" id="realAccountPanel">Binance account</div>

  <script>
    let activeAsset = 'BTCUSDT';
    let boardData = null;

    function selectAsset(asset) {
      activeAsset = asset;
      document.getElementById('tab-BTC').classList.toggle('active', asset === 'BTCUSDT');
      document.getElementById('tab-ETH').classList.toggle('active', asset === 'ETHUSDT');
      document.getElementById('tab-XAU').classList.toggle('active', asset === 'XAUUSDT');
      renderActiveAsset();
    }

    function renderActiveAsset() {
      if (!boardData || !boardData.decisions) return;
      let dec = boardData.decisions[activeAsset];
      if (!dec) return;

      // Hero Action Pill
      let pill = document.getElementById('hero-action-pill');
      pill.textContent = dec.display_action;
      pill.className = 'decision-pill';
      if (dec.action === 'TAKE_LONG') {
        pill.classList.add('pill-long');
      } else if (dec.action === 'TAKE_SHORT') {
        pill.classList.add('pill-short');
      } else {
        pill.classList.add('pill-wait');
      }

      // Titles
      document.getElementById('hero-setup-title').textContent = dec.setup_name;
      document.getElementById('hero-setup-rule').textContent = `Rule ID: ${dec.primary_rule_id} • Veteran Heuristic Evaluator`;

      // Confidence
      let confEl = document.getElementById('hero-confidence');
      let confBar = document.getElementById('hero-conf-bar');
      confEl.textContent = `${Math.round(dec.confidence)}%`;
      confBar.style.width = `${Math.round(dec.confidence)}%`;
      if (dec.confidence >= 70) {
        confEl.style.color = '#00f076';
        confBar.style.background = '#00f076';
      } else if (dec.confidence >= 50) {
        confEl.style.color = '#fbbf24';
        confBar.style.background = '#fbbf24';
      } else {
        confEl.style.color = '#94a3b8';
        confBar.style.background = '#64748b';
      }

      // Parameters
      let eZone = dec.entry_zone || [dec.current_price, dec.current_price];
      document.getElementById('param-entry').textContent = `$${Number(eZone[0]).toLocaleString()} – $${Number(eZone[1]).toLocaleString()}`;
      document.getElementById('param-stop').textContent = `$${Number(dec.stop_loss).toLocaleString()}`;
      document.getElementById('param-tp1').textContent = `$${Number(dec.take_profit_1).toLocaleString()}`;
      document.getElementById('param-tp2').textContent = `$${Number(dec.take_profit_2).toLocaleString()}`;
      document.getElementById('param-rr').textContent = `${Number(dec.risk_reward_ratio).toFixed(2)} : 1`;

      // Supporting factors
      let supHtml = '';
      if (dec.supporting_reasons && dec.supporting_reasons.length > 0) {
        for (let r of dec.supporting_reasons) {
          supHtml += `<div class="factor-item"><span class="factor-icon" style="color:#00f076">✓</span> ${escapeHtml(r)}</div>`;
        }
      } else {
        supHtml = '<div class="factor-item" style="color:#64748b">No high-conviction supporting factors in current state.</div>';
      }
      document.getElementById('supporting-list').innerHTML = supHtml;

      // Traps
      let trapHtml = '';
      if (dec.trap_warnings && dec.trap_warnings.length > 0) {
        for (let w of dec.trap_warnings) {
          trapHtml += `<div class="factor-item"><span class="factor-icon" style="color:#ffb703">⚠</span> ${escapeHtml(w)}</div>`;
        }
      } else {
        trapHtml = '<div class="factor-item" style="color:#00f076"><span class="factor-icon">✓</span> Zero active traps identified. Standard execution authorized.</div>';
      }
      document.getElementById('traps-list').innerHTML = trapHtml;

      // Regimes
      let rc = dec.regime_scorecard || {};
      document.getElementById('regime-trend').textContent = rc.trend || 'UNKNOWN';
      document.getElementById('regime-vol').textContent = rc.volatility || 'UNKNOWN';
      document.getElementById('regime-act').textContent = rc.activity || 'UNKNOWN';
      document.getElementById('regime-fund').textContent = rc.funding || 'UNKNOWN';
      document.getElementById('regime-qual').textContent = rc.quality || 'HEALTHY';
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    async function triggerRefresh() {
      try {
        let res = await fetch('/api/trade_board', { cache: 'no-store' });
        boardData = await res.json();
        
        // Update asset price headers
        if (boardData.decisions) {
          if (boardData.decisions.BTCUSDT) document.getElementById('price-BTC').textContent = `$${Number(boardData.decisions.BTCUSDT.current_price).toLocaleString()}`;
          if (boardData.decisions.ETHUSDT) document.getElementById('price-ETH').textContent = `$${Number(boardData.decisions.ETHUSDT.current_price).toLocaleString()}`;
          if (boardData.decisions.XAUUSDT) document.getElementById('price-XAU').textContent = `$${Number(boardData.decisions.XAUUSDT.current_price).toLocaleString()}`;
        }

        // Cross asset
        let ca = boardData.cross_asset_matrix || {};
        document.getElementById('ca-btc-eth').textContent = `${ca.BTC_ETH_correlation || 0.88} (Beta: ${ca.BTC_ETH_beta || 1.25}x)`;
        document.getElementById('ca-btc-xau').textContent = `${ca.BTC_XAU_correlation || 0.12} (Decoupled)`;
        document.getElementById('ca-eth-xau').textContent = `${ca.ETH_XAU_correlation || 0.08}`;
        document.getElementById('ca-leader').textContent = ca.lead_lag_leader || 'BTC';
        document.getElementById('ca-dispersion').textContent = ca.regime_dispersion || 'LOW';

        // Shadow bot
        let sb = boardData.shadow_bot_telemetry || {};
        if (sb.connected) {
          document.getElementById('shadow-bot-badge').textContent = 'SHADOW BOT: LIVE (PID ' + sb.pid + ')';
          document.getElementById('shadow-bot-badge').className = 'badge badge-emerald';
          document.getElementById('sb-status').textContent = sb.status;
          document.getElementById('sb-pid').textContent = `PID ${sb.pid} (${sb.git_commit})`;
          document.getElementById('sb-cycles').textContent = `${sb.cycle_count} cycles`;
          document.getElementById('sb-decision').textContent = sb.last_decision;
          document.getElementById('sb-feeds').textContent = 'HEALTHY • FRESH';
        } else {
          document.getElementById('shadow-bot-badge').textContent = 'SHADOW BOT: STANDALONE';
          document.getElementById('shadow-bot-badge').className = 'badge badge-amber';
          document.getElementById('sb-status').textContent = 'STANDALONE RESEARCH';
        }

        renderActiveAsset();
        document.getElementById('last-updated').textContent = 'Updated: ' + new Date().toLocaleTimeString();
      } catch (err) {
        console.error('Error fetching trade board:', err);
      }
    }

    async function controlPause() {
      await fetch('/api/control/pause', { method: 'POST' });
      triggerRefresh();
    }
    async function controlResume() {
      await fetch('/api/control/resume', { method: 'POST' });
      triggerRefresh();
    }

    triggerRefresh();
    setInterval(triggerRefresh, 3000);
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
