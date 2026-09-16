from pathlib import Path
import asyncio
import json

import pytest

from btceth_os.core import RawEnvelope, DedupIndex, SourceConflict, ns_from_source_timestamp, now_ns
from btceth_os.storage import RawStore, SilverStore
from btceth_os.catalog import Catalog
from btceth_os.orderbook import OrderBookSync, BookState, SequenceGap
from btceth_os.collectors import (
    classify_http,
    ReconnectPolicy,
    PublicRestClient,
    websocket_messages,
    FatalSourceError,
)


def test_timestamp_precision():
    assert ns_from_source_timestamp(1, "ms") == 1_000_000
    assert ns_from_source_timestamp(1, "us") == 1_000


def test_duplicate_and_conflict():
    d = DedupIndex()
    assert d.observe("k", "a") == "NEW"
    assert d.observe("k", "a") == "DUPLICATE"
    with pytest.raises(SourceConflict):
        d.observe("k", "b")


def test_duplicate_after_reconnect_is_not_double_counted():
    d = DedupIndex()
    payload_hash = "same-event-hash"
    assert d.observe("binance|spot|BTCUSDT|123", payload_hash) == "NEW"
    assert d.observe("binance|spot|BTCUSDT|123", payload_hash) == "DUPLICATE"


def test_raw_and_silver_roundtrip(tmp_path: Path):
    n = now_ns()
    env = RawEnvelope(
        "binance", "spot", "book_ticker", "BINANCE:SPOT:BTCUSDT",
        {"bidPrice": "1.10", "askPrice": "1.20"},
        1, "ms", "ms", 1_000_000, n, n,
    )
    rp = RawStore(tmp_path / "raw").append(env)
    data = RawStore.read(rp)
    assert data[0]["payload"]["bidPrice"] == "1.10"
    row = {
        "source": "binance", "market": "spot", "dataset": "book_ticker",
        "instrument_id": "BINANCE:SPOT:BTCUSDT", "ts_event_ns": 1_000_000,
        "ts_recv_ns": n, "ts_ingest_ns": n, "source_ts_raw": 1,
        "source_ts_unit": "ms", "source_precision": "ms", "record_key": "k",
        "payload_hash": env.payload_hash, "values": {"price": "1.10", "float_guard": 1.1},
    }
    sp = SilverStore(tmp_path / "silver").write([row], "x.parquet")
    table = SilverStore.read(sp)
    assert table.num_rows == 1
    vals = json.loads(table.column("values_json")[0].as_py())
    assert vals["price"] == "1.10"
    assert vals["float_guard"] == "1.1"


def test_unknown_source_fields_are_preserved_in_raw(tmp_path: Path):
    n = now_ns()
    payload = {"known": "1", "brandNew2026Field": {"nested": [1, 2, 3]}}
    env = RawEnvelope("binance", "usdm", "future_schema", "BINANCE:USD_M_PERP:BTCUSDT", payload, 1, "ms", "ms", 1_000_000, n, n)
    path = RawStore(tmp_path / "raw").append(env)
    restored = RawStore.read(path)[0]["payload"]
    assert restored["brandNew2026Field"] == {"nested": [1, 2, 3]}


def test_catalog_restart(tmp_path: Path):
    p = tmp_path / "cat.sqlite"
    c = Catalog(p)
    c.start_run("c", "r", "binance", "x", "BTC", 1)
    c.heartbeat("c", "r", 2, messages_received=1, records_written=1)
    c.close()
    c2 = Catalog(p)
    assert c2.count("collector_runs") == 1
    assert c2.count("collector_heartbeats") == 1
    c2.close()


def test_collector_crash_is_recordable_and_catalog_survives(tmp_path: Path):
    p = tmp_path / "cat.sqlite"
    c = Catalog(p)
    c.start_run("collector", "run", "binance", "depth", "BTC", 1)
    c.error("collector", 2, "SimulatedCrash", "boom")
    c.heartbeat("collector", "run", 3, source_errors=1, status="FAILED")
    c.close()
    reopened = Catalog(p)
    assert reopened.count("collector_errors") == 1
    assert reopened.count("collector_runs") == 1
    reopened.close()


def test_snapshot_is_not_valid_until_first_stream_bridge():
    b = OrderBookSync()
    b.begin_buffering()
    b.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    assert b.state == BookState.BUFFERING
    b.bridge_first_delta(95, 105, [["10", "1"]], [])
    assert b.state == BookState.VALID
    assert b.last_update_id == 105


def test_orderbook_gap_forces_invalid():
    b = OrderBookSync()
    b.begin_buffering()
    b.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    b.bridge_first_delta(99, 100, [], [])
    b.apply_delta(101, 101, [["10", "1"]], [])
    assert b.state == BookState.VALID and b.last_update_id == 101
    with pytest.raises(SequenceGap):
        b.apply_delta(103, 103, [], [])
    assert b.state == BookState.INVALID and b.resync_count == 1


def test_previous_sequence_mismatch_invalidates():
    b = OrderBookSync()
    b.begin_buffering()
    b.load_snapshot(50, [["1", "1"]], [["2", "1"]])
    b.bridge_first_delta(49, 50, [], [])
    with pytest.raises(SequenceGap):
        b.apply_delta(51, 51, [], [], previous_final_id=49)
    assert b.state == BookState.INVALID


def test_out_of_order_stale_delta_is_ignored_without_corruption():
    b = OrderBookSync()
    b.begin_buffering()
    b.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    b.bridge_first_delta(99, 100, [], [])
    b.apply_delta(90, 99, [["10", "999"]], [])
    assert b.state == BookState.VALID
    assert b.last_update_id == 100
    assert str(b.bids[next(iter(b.bids))]) == "2"


def test_snapshot_older_than_first_buffered_delta_forces_resync():
    b = OrderBookSync()
    b.begin_buffering()
    b.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    with pytest.raises(SequenceGap):
        b.bridge_first_delta(150, 160, [], [])
    assert b.state == BookState.INVALID


def test_http_failure_classification():
    assert classify_http(200) == "OK"
    assert classify_http(429) == "RETRY"
    assert classify_http(503) == "RETRY"
    assert classify_http(451) == "FATAL"


def test_reconnect_backoff_is_bounded():
    p = ReconnectPolicy(base=.1, maximum=.3)
    vals = [p.next_delay() for _ in range(10)]
    assert max(vals) <= .36
    p.reset()
    assert p.attempt == 0


class _FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body

    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc, tb): return False
    async def text(self): return self._body


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_http_429_retries_then_succeeds():
    s = _FakeSession([_FakeResponse(429, '{"code":-1003}'), _FakeResponse(200, '{"ok":true}')])
    result = await PublicRestClient(s, max_attempts=2).get_json("https://example.invalid")
    assert result == {"ok": True}
    assert s.calls == 2


@pytest.mark.asyncio
async def test_http_5xx_retries_then_succeeds():
    s = _FakeSession([_FakeResponse(503, "temporary"), _FakeResponse(200, '[1,2]')])
    result = await PublicRestClient(s, max_attempts=2).get_json("https://example.invalid")
    assert result == [1, 2]
    assert s.calls == 2


@pytest.mark.asyncio
async def test_http_451_is_fatal_and_not_retried():
    s = _FakeSession([_FakeResponse(451, "restricted")])
    with pytest.raises(FatalSourceError):
        await PublicRestClient(s, max_attempts=4).get_json("https://example.invalid")
    assert s.calls == 1


@pytest.mark.asyncio
async def test_empty_valid_response_is_preserved():
    s = _FakeSession([_FakeResponse(200, "[]")])
    result = await PublicRestClient(s).get_json("https://example.invalid")
    assert result == []


@pytest.mark.asyncio
async def test_malformed_success_payload_is_rejected():
    s = _FakeSession([_FakeResponse(200, "{not-json")])
    with pytest.raises(json.JSONDecodeError):
        await PublicRestClient(s).get_json("https://example.invalid")


class _FakeWS:
    def __init__(self, behavior): self.behavior = list(behavior)
    async def recv(self):
        item = self.behavior.pop(0)
        if isinstance(item, BaseException): raise item
        return item


class _FakeConnection:
    def __init__(self, ws): self.ws = ws
    async def __aenter__(self): return self.ws
    async def __aexit__(self, exc_type, exc, tb): return False


@pytest.mark.asyncio
async def test_websocket_disconnect_reconnect_restores_stream(monkeypatch):
    connections = [
        _FakeConnection(_FakeWS([asyncio.TimeoutError()])),
        _FakeConnection(_FakeWS(['{"e":"aggTrade","a":123}'])),
    ]

    def fake_connect(*args, **kwargs):
        return connections.pop(0)

    monkeypatch.setattr("btceth_os.collectors.websockets.connect", fake_connect)
    stream = websocket_messages("wss://example.invalid", seconds=1.0, reconnects=2)
    event = await anext(stream)
    assert event["a"] == 123
