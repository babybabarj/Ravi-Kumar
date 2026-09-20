import asyncio

from aiohttp.test_utils import TestClient, TestServer

from btceth_os.dashboard import create_dashboard_app, read_dashboard_state, write_dashboard_state


def state():
    return {
        "data_health": {"status": "HEALTHY", "last_event_ns": 1, "open_gaps": 0},
        "market": {"status": "READY", "instrument": "BINANCE:SPOT:BTCUSDT", "price": "100"},
        "signal": {"status": "SHADOW_ACCEPTED", "target_position": "1", "reason": "test"},
        "paper": {"status": "PAPER_FILLED", "cash": "900", "position": "1", "equity": "1000", "pnl": "0"},
    }


def test_dashboard_state_fails_safe_when_missing(tmp_path):
    assert read_dashboard_state(tmp_path / "missing.json")["data_health"]["status"] == "DEGRADED"


def test_dashboard_serves_local_snapshot(tmp_path):
    path = write_dashboard_state(tmp_path / "state.json", state())

    async def check():
        client = TestClient(TestServer(create_dashboard_app(path)))
        await client.start_server()
        try:
            assert (await (await client.get("/api/state")).json())["signal"]["status"] == "SHADOW_ACCEPTED"
            assert "BTCETH Trading OS" in await (await client.get("/")).text()
        finally:
            await client.close()
    asyncio.run(check())
