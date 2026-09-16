from pathlib import Path
from decimal import Decimal
import json
import pytest

from btceth_os.core import RawEnvelope, DedupIndex, SourceConflict, ns_from_source_timestamp, now_ns
from btceth_os.storage import RawStore, SilverStore
from btceth_os.catalog import Catalog
from btceth_os.orderbook import OrderBookSync, BookState, SequenceGap
from btceth_os.collectors import classify_http, ReconnectPolicy


def test_timestamp_precision():
    assert ns_from_source_timestamp(1,"ms") == 1_000_000
    assert ns_from_source_timestamp(1,"us") == 1_000


def test_duplicate_and_conflict():
    d=DedupIndex(); assert d.observe("k","a")=="NEW"; assert d.observe("k","a")=="DUPLICATE"
    with pytest.raises(SourceConflict): d.observe("k","b")


def test_raw_and_silver_roundtrip(tmp_path: Path):
    n=now_ns(); env=RawEnvelope("binance","spot","book_ticker","BINANCE:SPOT:BTCUSDT",{"bidPrice":"1.10","askPrice":"1.20"},1,"ms","ms",1_000_000,n,n)
    rp=RawStore(tmp_path/"raw").append(env); data=RawStore.read(rp); assert data[0]["payload"]["bidPrice"]=="1.10"
    row={"source":"binance","market":"spot","dataset":"book_ticker","instrument_id":"BINANCE:SPOT:BTCUSDT","ts_event_ns":1_000_000,"ts_recv_ns":n,"ts_ingest_ns":n,"source_ts_raw":1,"source_ts_unit":"ms","source_precision":"ms","record_key":"k","payload_hash":env.payload_hash,"values":{"price":"1.10","float_guard":1.1}}
    sp=SilverStore(tmp_path/"silver").write([row],"x.parquet"); table=SilverStore.read(sp); assert table.num_rows==1; vals=json.loads(table.column("values_json")[0].as_py()); assert vals["price"]=="1.10" and vals["float_guard"]=="1.1"


def test_catalog_restart(tmp_path: Path):
    p=tmp_path/"cat.sqlite"; c=Catalog(p); c.start_run("c","r","binance","x","BTC",1); c.heartbeat("c","r",2,messages_received=1,records_written=1); c.close(); c2=Catalog(p); assert c2.count("collector_runs")==1 and c2.count("collector_heartbeats")==1; c2.close()


def test_orderbook_gap_forces_invalid():
    b=OrderBookSync(); b.begin_buffering(); b.load_snapshot(100,[["10","2"]],[["11","3"]]); b.apply_delta(101,101,[["10","1"]],[]); assert b.state==BookState.VALID and b.last_update_id==101
    with pytest.raises(SequenceGap): b.apply_delta(103,103,[],[])
    assert b.state==BookState.INVALID and b.resync_count==1


def test_previous_sequence_mismatch_invalidates():
    b=OrderBookSync(); b.load_snapshot(50,[["1","1"]],[["2","1"]])
    with pytest.raises(SequenceGap): b.apply_delta(51,51,[],[],previous_final_id=49)
    assert b.state==BookState.INVALID


def test_http_failure_classification():
    assert classify_http(200)=="OK"; assert classify_http(429)=="RETRY"; assert classify_http(503)=="RETRY"; assert classify_http(451)=="FATAL"


def test_reconnect_backoff_is_bounded():
    p=ReconnectPolicy(base=.1,maximum=.3); vals=[p.next_delay() for _ in range(10)]; assert max(vals)<=.36; p.reset(); assert p.attempt==0
