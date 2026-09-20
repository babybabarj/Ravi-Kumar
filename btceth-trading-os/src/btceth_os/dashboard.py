from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aiohttp import web


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
    "recent_decisions": [],
    "proposals": [],
}


def read_dashboard_state(path: Path | str) -> dict[str, Any]:
    """Return a safe empty state when the local snapshot is absent or malformed."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("state is not a dict")
        # Ensure all default top-level sections exist
        out = dict(DEFAULT_STATE)
        out.update(raw)
        return out
    except (OSError, ValueError, json.JSONDecodeError):
        fallback = dict(DEFAULT_STATE)
        fallback["data_health"] = dict(DEFAULT_STATE["data_health"])
        fallback["data_health"]["status"] = "DEGRADED"
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
        return web.json_response(read_dashboard_state(state_path))

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
    app.router.add_post("/api/control/pause", api_pause)
    app.router.add_post("/api/control/resume", api_resume)
    app.router.add_post("/api/control/mode", api_set_mode)
    app.router.add_post("/api/control/proposal/{id}/{action}", api_proposal_action)
    return app


async def _index(_: web.Request) -> web.Response:
    return web.Response(text=_HTML, content_type="text/html")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the BTCETH Trading OS Owner Control Center dashboard.")
    parser.add_argument("--state", type=Path, default=Path("artifacts/dashboard/state.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    web.run_app(create_dashboard_app(args.state), host=args.host, port=args.port)
    return 0


_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BTCETH Trading OS • Owner Control Center</title><style>
:root{color-scheme:dark;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#070e17;color:#e7eff8}
body{margin:0;max-width:1240px;padding:1.5rem;margin:auto}
.banner{background:#173426;border:1px solid #286847;color:#69d3a7;padding:.6rem 1rem;border-radius:8px;font-weight:600;letter-spacing:.08em;font-size:.85rem;text-align:center;margin-bottom:1.5rem}
.top{display:flex;justify-content:space-between;gap:1rem;align-items:center;border-bottom:1px solid #1b3047;padding-bottom:1rem}
.eyebrow{color:#69d3a7;font-size:.8rem;letter-spacing:.12em}
.controls{display:flex;gap:.5rem;align-items:center}
button{background:#15283c;color:#e7eff8;border:1px solid #2a4c6f;border-radius:6px;padding:.4rem .8rem;font-family:inherit;font-size:.8rem;cursor:pointer}
button:hover{background:#1f3b58}
button.btn-danger{background:#42171c;border-color:#78232c;color:#ff9fa9}
button.btn-success{background:#143d2b;border-color:#246648;color:#85e4ba}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem;margin-top:1.5rem}
.card{background:#0d1825;border:1px solid #1c324a;border-radius:10px;padding:1rem}
.card-wide{grid-column:1/-1}
.label{color:#8ea3b9;font-size:.78rem;text-transform:uppercase;letter-spacing:.08em}
.value{font-size:1.35rem;margin:.5rem 0}
.good{color:#69d3a7}.warn{color:#ffbd6e}.bad{color:#ff7b8b}
.row{display:flex;justify-content:space-between;gap:.75rem;padding:.35rem 0;border-top:1px solid #16293d;font-size:.85rem}
.row:first-of-type{border:0}
table{width:100%;border-collapse:collapse;margin-top:.6rem;font-size:.82rem}
th,td{padding:.4rem .6rem;text-align:left;border-bottom:1px solid #16293d}
th{color:#8ea3b9;font-weight:normal;text-transform:uppercase;font-size:.75rem}
.binance-panel{background:#121b29;border:1px solid #c79a32;border-radius:10px;padding:1.1rem;margin-top:1.5rem}
.binance-title{color:#f5cb5c;font-weight:bold;font-size:.9rem;letter-spacing:.08em;margin-bottom:.6rem}
footer{margin-top:2rem;font-size:.8rem;color:#7a8fa5;text-align:center;border-top:1px solid #1b3047;padding-top:1rem}
</style></head><body>
<div class="banner" id="banner">DEMO / PAPER • NO REAL MONEY • AUTOMATIC TRADING ENABLED</div>
<div class="top">
  <div>
    <div class="eyebrow" id="sys-mode-eyebrow">MODE: PAPER_AUTO • STATUS: HEALTHY</div>
    <h1 style="margin:0.2rem 0">BTCETH Trading OS</h1>
  </div>
  <div class="controls">
    <button onclick="controlPause()" id="pauseBtn" class="btn-danger">Pause New Trades</button>
    <button onclick="controlResume()" id="resumeBtn" class="btn-success">Resume</button>
    <div id="updated" style="font-size:0.8rem;color:#8ea3b9;margin-left:0.5rem">Loading…</div>
  </div>
</div>

<div class="grid" id="cards"></div>

<div class="binance-panel" id="realAccountPanel">
  <div class="binance-title">⚡ REAL BINANCE — READ ONLY (OBSERVATION ONLY • NEVER COMBINED WITH PAPER)</div>
  <div class="grid" style="margin-top:0.5rem" id="realCards"></div>
</div>

<div class="card card-wide" style="margin-top:1.5rem">
  <div class="label">Open Paper Positions</div>
  <div id="openPositionsTable" style="overflow-x:auto">No open positions</div>
</div>

<div class="card card-wide" style="margin-top:1.5rem">
  <div class="label">Recent Decisions & No-Trade Audit</div>
  <div id="decisionsTable" style="overflow-x:auto">No decisions recorded</div>
</div>

<div class="card card-wide" style="margin-top:1.5rem" id="proposalsCard">
  <div class="label">Pending Live Approval Proposals (Mock Testing)</div>
  <div id="proposalsList">No pending proposals</div>
</div>

<footer>Owner Control Center • Real Binance trading capability = ZERO • All order submissions in paper mode are simulated locally with exact Decimal accounting.</footer>

<script>
const esc=v=>v===null||v===undefined?'—':String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cls=s=>/READY|HEALTHY|ACCEPTED|FILLED|CONNECTED|LIVE|APPROVED/.test(s)?'good':/DEGRADED|GAP|FAILED|STALE|REJECTED|HALTED/.test(s)?'bad':'warn';

function card(title,status,rows){
  return `<section class="card"><div class="label">${title}</div><div class="value ${cls(status)}">${esc(status)}</div>${rows.map(([k,v])=>`<div class="row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</section>`;
}

async function controlPause(){
  await fetch('/api/control/pause',{method:'POST'});
  refresh();
}
async function controlResume(){
  await fetch('/api/control/resume',{method:'POST'});
  refresh();
}
async function approveProp(id){
  await fetch(`/api/control/proposal/${id}/approve`,{method:'POST'});
  refresh();
}
async function rejectProp(id){
  await fetch(`/api/control/proposal/${id}/reject`,{method:'POST'});
  refresh();
}

async function refresh(){
  try{
    let s=await fetch('/api/state',{cache:'no-store'}).then(r=>r.json());
    let a=s.account, c=s.system_control||{}, p=s.paper||{};

    let modeText = c.mode || 'PAPER_AUTO';
    let pausedText = c.paused ? ' [PAUSED]' : (c.halted ? ' [HALTED]' : '');
    document.getElementById('sys-mode-eyebrow').textContent = `SYSTEM MODE: ${modeText}${pausedText}`;

    let banner = document.getElementById('banner');
    if(modeText==='PAPER_AUTO'){
      banner.style.display='block';
      banner.textContent='DEMO / PAPER • NO REAL MONEY • AUTOMATIC TRADING ENABLED';
    } else if(modeText==='SHADOW_AUTO'){
      banner.style.display='block';
      banner.textContent='SHADOW MODE • RECORDING HYPOTHETICAL DECISIONS • ZERO ORDERS';
    } else if(modeText==='LIVE_APPROVAL'){
      banner.style.display='block';
      banner.style.background='#3d2c12';
      banner.style.borderColor='#73531e';
      banner.style.color='#f5cb5c';
      banner.textContent='LIVE APPROVAL MODE • PROPOSALS REQUIRE EXPLICIT OWNER CONFIRMATION';
    } else {
      banner.style.display='none';
    }

    // Main 4 cards
    let cardsHtml = '';
    cardsHtml += card('System Status', c.halted ? 'HALTED' : (c.paused ? 'PAUSED' : 'RUNNING'), [
      ['Mode', modeText],
      ['Kill Switch', c.paused ? 'PAUSED' : 'ACTIVE'],
      ['Pause Detail', c.pause_reason || c.halt_reason || 'NORMAL']
    ]);

    cardsHtml += card('Data health', s.data_health.status, [
      ['Last event', s.data_health.last_event_ns],
      ['Open gaps', s.data_health.open_gaps]
    ]);

    cardsHtml += card('Market state', s.market.status, [
      ['Instrument', s.market.instrument],
      ['Price', s.market.price]
    ]);

    cardsHtml += card('Signal & Risk', s.signal.status, [
      ['Target position', s.signal.target_position],
      ['Latest Reason', s.signal.reason]
    ]);

    cardsHtml += card('Simulated position', p.status, [
      ['Cash', p.cash],
      ['Position', p.position],
      ['Equity', p.equity],
      ['Total P&L', p.pnl],
      ['Daily P&L', p.daily_pnl || '0']
    ]);

    document.getElementById('cards').innerHTML = cardsHtml;

    // Real Binance Cards
    let realCardsHtml = card('Binance account', a.status, [
      ['Spot balances', a.spot.balances.length],
      ['Spot open orders', a.spot.open_orders],
      ['USD-M positions', a.usdm.positions.length],
      ['USD-M open orders', a.usdm.open_orders],
      ['Last sync', a.last_sync_ns],
      ['Status detail', a.error]
    ]);
    document.getElementById('realCards').innerHTML = realCardsHtml;

    // Open positions table
    let posList = p.open_positions || [];
    if(posList.length === 0){
      document.getElementById('openPositionsTable').innerHTML = '<div style="color:#8ea3b9;padding:0.5rem 0">No open positions.</div>';
    } else {
      let t = '<table><thead><tr><th>Instrument</th><th>Side</th><th>Quantity</th><th>Entry Price</th><th>Mark Price</th><th>Unrealized P&L</th><th>Stop Price</th></tr></thead><tbody>';
      for(let pos of posList){
        t += `<tr><td>${esc(pos.instrument)}</td><td class="${pos.side==='LONG'?'good':'bad'}">${esc(pos.side)}</td><td>${esc(pos.quantity)}</td><td>${esc(pos.average_entry)}</td><td>${esc(pos.mark_price)}</td><td class="${Number(pos.unrealized_pnl)>=0?'good':'bad'}">${esc(pos.unrealized_pnl)}</td><td>${esc(pos.stop_price)}</td></tr>`;
      }
      t += '</tbody></table>';
      document.getElementById('openPositionsTable').innerHTML = t;
    }

    // Decisions table
    let decList = s.recent_decisions || [];
    if(decList.length === 0){
      document.getElementById('decisionsTable').innerHTML = '<div style="color:#8ea3b9;padding:0.5rem 0">No decisions recorded yet.</div>';
    } else {
      let t = '<table><thead><tr><th>Strategy</th><th>Approved</th><th>Reason Code</th></tr></thead><tbody>';
      for(let dec of decList){
        t += `<tr><td>${esc(dec.strategy)}</td><td class="${dec.approved?'good':'bad'}">${dec.approved?'YES':'NO'}</td><td><strong>${esc(dec.reason)}</strong></td></tr>`;
      }
      t += '</tbody></table>';
      document.getElementById('decisionsTable').innerHTML = t;
    }

    // Pending Proposals
    let propList = s.proposals || [];
    if(propList.length === 0){
      document.getElementById('proposalsList').innerHTML = '<div style="color:#8ea3b9;padding:0.5rem 0">No pending trade proposals.</div>';
    } else {
      let pHtml = '';
      for(let prop of propList){
        pHtml += `<div class="card" style="margin-top:0.5rem"><div class="row"><strong>${esc(prop.instrument)} • ${esc(prop.side)}</strong><span>Status: <strong class="${cls(prop.status)}">${esc(prop.status)}</strong></span></div><div class="row"><span>Size: ${esc(prop.proposed_quantity)} • Price: ${esc(prop.current_price)}</span><span>Stop: ${esc(prop.stop_price)} • Max Loss: $${esc(prop.max_expected_loss)}</span></div>`;
        if(prop.status === 'AWAITING_OWNER_APPROVAL'){
          pHtml += `<div style="margin-top:0.5rem;display:flex;gap:0.5rem"><button class="btn-success" onclick="approveProp('${prop.proposal_id}')">APPROVE (MOCK)</button><button class="btn-danger" onclick="rejectProp('${prop.proposal_id}')">REJECT</button></div>`;
        }
        pHtml += `</div>`;
      }
      document.getElementById('proposalsList').innerHTML = pHtml;
    }

    document.getElementById('updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
  }catch(e){
    document.getElementById('updated').textContent = 'Dashboard state unavailable';
  }
}

refresh();
setInterval(refresh, 2000);
</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
