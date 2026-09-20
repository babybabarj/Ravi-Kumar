from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aiohttp import web


DEFAULT_STATE = {
    "data_health": {"status": "NOT_READY", "last_event_ns": None, "open_gaps": 0},
    "market": {"status": "NO_MARKET_DATA", "instrument": None, "price": None},
    "signal": {"status": "NO_SIGNAL", "target_position": "0", "reason": "Awaiting validated data"},
    "paper": {"status": "NOT_STARTED", "cash": None, "position": "0", "equity": None, "pnl": None},
}


def read_dashboard_state(path: Path | str) -> dict[str, Any]:
    """Return a safe empty state when the local snapshot is absent or malformed."""
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not all(key in state for key in DEFAULT_STATE):
            raise ValueError("missing dashboard sections")
        return state
    except (OSError, ValueError, json.JSONDecodeError):
        return DEFAULT_STATE | {"data_health": DEFAULT_STATE["data_health"] | {"status": "DEGRADED"}}


def write_dashboard_state(path: Path | str, state: dict[str, Any]) -> Path:
    """Atomically publish a local display snapshot; it has no exchange or account side effects."""
    destination = Path(path)
    if not all(key in state for key in DEFAULT_STATE):
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

    app.router.add_get("/", _index)
    app.router.add_get("/api/state", api_state)
    return app


async def _index(_: web.Request) -> web.Response:
    return web.Response(text=_HTML, content_type="text/html")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the read-only BTCETH Trading OS localhost dashboard.")
    parser.add_argument("--state", type=Path, default=Path("artifacts/dashboard/state.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    web.run_app(create_dashboard_app(args.state), host=args.host, port=args.port)
    return 0


_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BTCETH Trading OS</title><style>
:root{color-scheme:dark;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#08111c;color:#e7eff8}body{margin:0;max-width:1200px;padding:2rem;margin:auto}.top{display:flex;justify-content:space-between;gap:1rem;align-items:baseline}.eyebrow{color:#69d3a7;font-size:.8rem;letter-spacing:.12em}.muted{color:#94a6bb}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:1rem;margin-top:1.5rem}.card{background:#0e1c2c;border:1px solid #203952;border-radius:10px;padding:1.1rem}.label{color:#94a6bb;font-size:.8rem;text-transform:uppercase;letter-spacing:.08em}.value{font-size:1.35rem;margin:.65rem 0}.good{color:#69d3a7}.warn{color:#ffbd6e}.bad{color:#ff7b8b}.row{display:flex;justify-content:space-between;gap:.75rem;padding:.38rem 0;border-top:1px solid #1b3047}.row:first-of-type{border:0}footer{margin-top:1.5rem;font-size:.8rem;color:#94a6bb}@media(max-width:600px){body{padding:1rem}.top{display:block}}</style></head><body>
<div class="top"><div><div class="eyebrow">LOCAL • READ ONLY</div><h1>BTCETH Trading OS</h1></div><div id="updated" class="muted">Loading…</div></div><div class="grid" id="cards"></div><footer>Dashboard data is local. It cannot place orders or access an exchange account.</footer>
<script>const esc=v=>v===null||v===undefined?'—':String(v);const cls=s=>/READY|HEALTHY|ACCEPTED|FILLED/.test(s)?'good':/DEGRADED|GAP|FAILED|STALE|REJECTED/.test(s)?'bad':'warn';function card(title,status,rows){return `<section class="card"><div class="label">${title}</div><div class="value ${cls(status)}">${esc(status)}</div>${rows.map(([k,v])=>`<div class="row"><span>${k}</span><strong>${esc(v)}</strong></div>`).join('')}</section>`}async function refresh(){try{let s=await fetch('/api/state',{cache:'no-store'}).then(r=>r.json());cards.innerHTML=card('Data health',s.data_health.status,[['Last event',s.data_health.last_event_ns],['Open gaps',s.data_health.open_gaps]])+card('Market state',s.market.status,[['Instrument',s.market.instrument],['Price',s.market.price]])+card('Signal',s.signal.status,[['Target position',s.signal.target_position],['Reason',s.signal.reason]])+card('Simulated position',s.paper.status,[['Cash',s.paper.cash],['Position',s.paper.position],['Equity',s.paper.equity],['P&L',s.paper.pnl]]);updated.textContent='Updated '+new Date().toLocaleTimeString()}catch(e){updated.textContent='Dashboard state unavailable'}}refresh();setInterval(refresh,2000)</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
