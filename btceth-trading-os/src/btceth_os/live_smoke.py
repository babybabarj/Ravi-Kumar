from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import aiohttp

from .core import RawEnvelope, now_ns, ns_from_source_timestamp, DedupIndex, SourceConflict
from .storage import RawStore, SilverStore
from .catalog import Catalog
from .collectors import PublicRestClient, phase1a_rest_requests, phase1a_ws_urls, websocket_messages
from .live_orderbook import sync_one as sync_one_orderbook


def _source_ts(payload):
    if isinstance(payload, dict):
        for k in ("E", "T", "time", "timestamp", "creation_timestamp"):
            if k in payload and isinstance(payload[k], int):
                return payload[k], "ms"
    return None, None


def _is_sparse_ws_dataset(dataset: str) -> bool:
    # Binance forceOrder is event-driven. A quiet two-second acceptance window can
    # legitimately contain no liquidation event; successful connection without an
    # exception is therefore valid liveness evidence for this sparse stream.
    return dataset == "liquidation_sample"


async def run(root: str = "artifacts/phase1a") -> dict:
    rootp = Path(root)
    raw = RawStore(rootp / "raw")
    silver = SilverStore(rootp / "silver")
    cat = Catalog(rootp / "catalog.sqlite")
    run_id = str(uuid.uuid4())
    dedup = DedupIndex()
    rows = []
    stats = {
        "rest": 0,
        "ws": 0,
        "duplicates": 0,
        "conflicts": 0,
        "errors": [],
        "ws_stream_results": [],
        "ws_required_missing": [],
        "orderbooks_synced": 0,
        "orderbook_results": [],
        "orderbook_errors": [],
    }

    async with aiohttp.ClientSession(headers={"User-Agent": "btceth-phase1a/0.1"}) as session:
        client = PublicRestClient(session)
        for source, market, dataset, iid, req in phase1a_rest_requests():
            cid = f"{source}-{market}-{dataset}-{iid}"
            cat.start_run(cid, run_id, source, dataset, iid, now_ns())
            try:
                payload = await client.get_json(req["url"], req["params"])
                recv = now_ns()
                ts, unit = _source_ts(payload if isinstance(payload, dict) else (payload[-1] if payload else {}))
                ev = ns_from_source_timestamp(ts, unit) if ts else None
                env = RawEnvelope(
                    source,
                    market,
                    dataset,
                    iid,
                    payload if isinstance(payload, dict) else {"records": payload},
                    ts,
                    unit,
                    unit,
                    ev,
                    recv,
                    now_ns(),
                )
                key = f"{source}|{market}|{dataset}|{iid}|{ts}|{env.payload_hash}"
                dedup.observe(key, env.payload_hash)
                raw.append(env)
                rows.append(
                    {
                        "source": source,
                        "market": market,
                        "dataset": dataset,
                        "instrument_id": iid,
                        "ts_event_ns": ev,
                        "ts_recv_ns": recv,
                        "ts_ingest_ns": now_ns(),
                        "source_ts_raw": ts,
                        "source_ts_unit": unit,
                        "source_precision": unit,
                        "record_key": key,
                        "payload_hash": env.payload_hash,
                        "values": env.payload,
                    }
                )
                stats["rest"] += 1
                cat.heartbeat(cid, run_id, now_ns(), messages_received=1, records_written=1, status="HEALTHY")
            except Exception as e:
                stats["errors"].append(f"{cid}:{type(e).__name__}:{e}")
                cat.error(cid, now_ns(), type(e).__name__, str(e))
                cat.heartbeat(cid, run_id, now_ns(), source_errors=1, status="FAILED")

        for source, market, dataset, iid, url in phase1a_ws_urls():
            cid = f"{source}-{market}-{dataset}-{iid}"
            sparse = _is_sparse_ws_dataset(dataset)
            cat.start_run(cid, run_id, source, dataset, iid, now_ns())
            received = 0
            timeout_seconds = 2.0 if sparse else 6.0
            try:
                async for payload in websocket_messages(url, seconds=timeout_seconds, reconnects=1):
                    recv = now_ns()
                    ts, unit = _source_ts(payload)
                    ev = ns_from_source_timestamp(ts, unit) if ts else None
                    env = RawEnvelope(source, market, dataset, iid, payload, ts, unit, unit, ev, recv, now_ns(), connection_id=run_id)
                    key = f"{source}|{market}|{dataset}|{iid}|{payload.get('a', payload.get('u', ts))}"
                    try:
                        state = dedup.observe(key, env.payload_hash)
                        if state == "DUPLICATE":
                            stats["duplicates"] += 1
                            continue
                    except SourceConflict:
                        stats["conflicts"] += 1
                        continue
                    raw.append(env)
                    rows.append(
                        {
                            "source": source,
                            "market": market,
                            "dataset": dataset,
                            "instrument_id": iid,
                            "ts_event_ns": ev,
                            "ts_recv_ns": recv,
                            "ts_ingest_ns": now_ns(),
                            "source_ts_raw": ts,
                            "source_ts_unit": unit,
                            "source_precision": unit,
                            "record_key": key,
                            "payload_hash": env.payload_hash,
                            "values": env.payload,
                        }
                    )
                    stats["ws"] += 1
                    received += 1
                    break

                if received:
                    stream_status = "EVENT_RECEIVED"
                elif sparse:
                    stream_status = "CONNECTED_NO_EVENT_ACCEPTABLE"
                else:
                    stream_status = "NO_EVENT"
                    missing = f"{market}:{dataset}:{iid}"
                    stats["ws_required_missing"].append(missing)
                    stats["errors"].append(f"ws-required-no-event:{missing}")

                stats["ws_stream_results"].append(
                    {
                        "market": market,
                        "dataset": dataset,
                        "instrument_id": iid,
                        "sparse": sparse,
                        "messages_received": received,
                        "status": stream_status,
                    }
                )
                cat.heartbeat(
                    cid,
                    run_id,
                    now_ns(),
                    messages_received=received,
                    records_written=received,
                    status="HEALTHY" if (received or sparse) else "STALE",
                )
            except Exception as e:
                stats["ws_stream_results"].append(
                    {
                        "market": market,
                        "dataset": dataset,
                        "instrument_id": iid,
                        "sparse": sparse,
                        "messages_received": received,
                        "status": "FAILED",
                        "error": f"{type(e).__name__}:{e}",
                    }
                )
                stats["errors"].append(f"{cid}:{type(e).__name__}:{e}")
                if not sparse:
                    stats["ws_required_missing"].append(f"{market}:{dataset}:{iid}")
                cat.error(cid, now_ns(), type(e).__name__, str(e))
                cat.heartbeat(cid, run_id, now_ns(), source_errors=1, status="FAILED")

    # Prove every book independently so one failure does not hide successful books.
    async with aiohttp.ClientSession(headers={"User-Agent": "btceth-phase1a/0.1"}) as book_session:
        for market in ("spot", "usdm"):
            for symbol in ("BTCUSDT", "ETHUSDT"):
                try:
                    book = await sync_one_orderbook(book_session, market, symbol)
                    stats["orderbook_results"].append(book.__dict__)
                except Exception as e:
                    msg = f"{market}:{symbol}:{type(e).__name__}:{e}"
                    stats["orderbook_errors"].append(msg)
                    stats["errors"].append(f"orderbook-sync:{msg}")
    stats["orderbooks_synced"] = len(stats["orderbook_results"])

    if rows:
        p = silver.write(rows, "live_smoke.parquet")
        stats["silver_rows"] = SilverStore.read(p).num_rows
    else:
        stats["silver_rows"] = 0

    stats["catalog_heartbeats"] = cat.count("collector_heartbeats")
    cat.close()
    rootp.mkdir(parents=True, exist_ok=True)
    (rootp / "LIVE_SMOKE.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    result = asyncio.run(run())
    sparse_results = [r for r in result["ws_stream_results"] if r.get("sparse")]
    sparse_ok = len(sparse_results) == 2 and all(
        r.get("status") in {"EVENT_RECEIVED", "CONNECTED_NO_EVENT_ACCEPTABLE"}
        for r in sparse_results
    )
    if (
        result["rest"] < 20
        or result["ws_required_missing"]
        or not sparse_ok
        or result["silver_rows"] <= 0
        or result["orderbooks_synced"] != 4
        or result["errors"]
    ):
        raise SystemExit(2)
