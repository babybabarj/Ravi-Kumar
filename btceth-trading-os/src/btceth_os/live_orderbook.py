from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import aiohttp
import websockets

from .collectors import (
    BINANCE_SPOT_REST,
    BINANCE_USDM_REST,
    BINANCE_SPOT_WS,
    BINANCE_USDM_PUBLIC_WS,
)
from .orderbook import OrderBookSync, BookState, SequenceGap


@dataclass(frozen=True)
class LiveBookResult:
    market: str
    symbol: str
    last_update_id: int
    best_bid: str
    best_ask: str
    deltas_applied: int


def _stream_url(market: str, symbol: str) -> str:
    s = symbol.lower()
    if market == "spot":
        return f"{BINANCE_SPOT_WS}/{s}@depth@100ms"
    if market == "usdm":
        return f"{BINANCE_USDM_PUBLIC_WS}/{s}@depth@100ms"
    raise ValueError(market)


def _snapshot_request(market: str, symbol: str) -> tuple[str, dict[str, Any]]:
    if market == "spot":
        # Binance's published Spot local-book procedure uses the maximum 5000
        # levels for the bootstrap snapshot.
        return f"{BINANCE_SPOT_REST}/api/v3/depth", {"symbol": symbol, "limit": 5000}
    if market == "usdm":
        return f"{BINANCE_USDM_REST}/fapi/v1/depth", {"symbol": symbol, "limit": 1000}
    raise ValueError(market)


async def _snapshot(session: aiohttp.ClientSession, market: str, symbol: str) -> dict[str, Any]:
    url, params = _snapshot_request(market, symbol)
    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as response:
        text = await response.text()
        if response.status != 200:
            raise RuntimeError(f"snapshot HTTP {response.status}: {text[:300]}")
        payload = json.loads(text)
        if not isinstance(payload, dict) or "lastUpdateId" not in payload:
            raise RuntimeError("invalid depth snapshot")
        return payload


async def _buffer_depth(ws, queue: asyncio.Queue[dict[str, Any]]) -> None:
    while True:
        raw = await ws.recv()
        event = json.loads(raw)
        if isinstance(event, dict) and "U" in event and "u" in event:
            await queue.put(event)


async def _next_event(
    queue: asyncio.Queue[dict[str, Any]],
    reader: asyncio.Task[None],
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        if reader.done():
            exc = reader.exception()
            if exc is not None:
                raise exc
        raise


def _drain(queue: asyncio.Queue[dict[str, Any]], buffered: list[dict[str, Any]]) -> None:
    while not queue.empty():
        buffered.append(queue.get_nowait())


def _drop_stale(market: str, buffered: list[dict[str, Any]], snapshot_id: int) -> None:
    if market == "spot":
        # Spot: discard u <= snapshot lastUpdateId.
        buffered[:] = [e for e in buffered if int(e["u"]) > snapshot_id]
    else:
        # USD-M: discard u < snapshot lastUpdateId.
        buffered[:] = [e for e in buffered if int(e["u"]) >= snapshot_id]


def _candidate_is_bridge(market: str, event: dict[str, Any], snapshot_id: int) -> bool:
    first_id = int(event["U"])
    final_id = int(event["u"])
    if market == "spot":
        # Once u <= snapshot is discarded, applying the update procedure means
        # U must not skip the next local update id.
        target = snapshot_id + 1
        return first_id <= target <= final_id
    # USD-M first processed event must contain snapshot lastUpdateId itself.
    return first_id <= snapshot_id <= final_id


async def _wait_for_spot_bridge(
    queue: asyncio.Queue[dict[str, Any]],
    reader: asyncio.Task[None],
    buffered: list[dict[str, Any]],
    snapshot_id: int,
) -> dict[str, Any]:
    """Wait on the frozen Spot snapshot until its first applicable diff exists."""
    deadline = asyncio.get_running_loop().time() + 12.0
    while asyncio.get_running_loop().time() < deadline:
        _drop_stale("spot", buffered, snapshot_id)
        if buffered:
            candidate = buffered[0]
            first_id = int(candidate["U"])
            if first_id > snapshot_id + 1:
                raise SequenceGap(
                    f"Spot gap after snapshot: U={first_id} expected<={snapshot_id + 1}"
                )
            if _candidate_is_bridge("spot", candidate, snapshot_id):
                return buffered.pop(0)
            # Defensive: a non-stale candidate which cannot bridge is not safe.
            raise SequenceGap(
                f"Spot unbridgeable candidate U={candidate['U']} u={candidate['u']} snapshot={snapshot_id}"
            )
        remaining = max(0.1, deadline - asyncio.get_running_loop().time())
        buffered.append(await _next_event(queue, reader, timeout=min(2.0, remaining)))
    raise SequenceGap(f"Spot timed out waiting for post-snapshot diff snapshot={snapshot_id}")


async def _bootstrap_spot(
    session: aiohttp.ClientSession,
    symbol: str,
    queue: asyncio.Queue[dict[str, Any]],
    reader: asyncio.Task[None],
    buffered: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Follow Binance Spot bootstrap literally without chasing the snapshot."""
    first_stream_u = int(buffered[0]["U"])
    snap: dict[str, Any] | None = None

    # Binance Spot step 4: only refetch while snapshot is strictly behind the U
    # of the first event received. Once it catches up, freeze this snapshot.
    for _ in range(10):
        snap = await _snapshot(session, "spot", symbol)
        snapshot_id = int(snap["lastUpdateId"])
        _drain(queue, buffered)
        if snapshot_id >= first_stream_u:
            bridge = await _wait_for_spot_bridge(queue, reader, buffered, snapshot_id)
            return snap, bridge, snapshot_id + 1
        await asyncio.sleep(0.03)

    raise SequenceGap(
        f"Spot snapshot remained behind first stream U={first_stream_u}; last snapshot={snap and snap.get('lastUpdateId')}"
    )


async def _bootstrap_usdm(
    session: aiohttp.ClientSession,
    symbol: str,
    queue: asyncio.Queue[dict[str, Any]],
    reader: asyncio.Task[None],
    buffered: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Bootstrap USD-M using U/u bridge and later pu continuity."""
    for _ in range(10):
        snap = await _snapshot(session, "usdm", symbol)
        snapshot_id = int(snap["lastUpdateId"])
        _drain(queue, buffered)
        _drop_stale("usdm", buffered, snapshot_id)

        # If all buffered events are older than the snapshot, do not chase the
        # snapshot forward. Wait for the next streamed event first.
        if not buffered:
            buffered.append(await _next_event(queue, reader, timeout=3.0))
            _drain(queue, buffered)
            _drop_stale("usdm", buffered, snapshot_id)

        if not buffered:
            continue

        candidate = buffered[0]
        if _candidate_is_bridge("usdm", candidate, snapshot_id):
            return snap, buffered.pop(0), snapshot_id

        # Earliest usable stream event begins after the snapshot: REST is behind;
        # keep the same live buffer and fetch a newer snapshot.
        if int(candidate["U"]) > snapshot_id:
            await asyncio.sleep(0.03)
            continue

        # Candidate should otherwise have bridged snapshot_id.
        raise SequenceGap(
            f"USD-M unbridgeable candidate U={candidate['U']} u={candidate['u']} snapshot={snapshot_id}"
        )

    raise SequenceGap("USD-M unable to bridge buffered depth to REST snapshot")


async def sync_one(
    session: aiohttp.ClientSession,
    market: str,
    symbol: str,
    *,
    max_attempts: int = 6,
    required_deltas: int = 3,
) -> LiveBookResult:
    url = _stream_url(market, symbol)
    last_error: Exception | None = None

    for _attempt in range(max_attempts):
        try:
            async with websockets.connect(
                url,
                open_timeout=15,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10,
                max_size=8 * 1024 * 1024,
            ) as ws:
                queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=20_000)
                reader = asyncio.create_task(_buffer_depth(ws, queue))
                try:
                    first_event = await _next_event(queue, reader, timeout=10.0)
                    buffered: list[dict[str, Any]] = [first_event]

                    if market == "spot":
                        snap, bridge_event, bridge_id = await _bootstrap_spot(
                            session, symbol, queue, reader, buffered
                        )
                    elif market == "usdm":
                        snap, bridge_event, bridge_id = await _bootstrap_usdm(
                            session, symbol, queue, reader, buffered
                        )
                    else:
                        raise ValueError(market)

                    snapshot_id = int(snap["lastUpdateId"])
                    book = OrderBookSync()
                    book.begin_buffering()
                    book.load_snapshot(snapshot_id, snap.get("bids", []), snap.get("asks", []))
                    book.bridge_first_delta(
                        int(bridge_event["U"]),
                        int(bridge_event["u"]),
                        bridge_event.get("b", []),
                        bridge_event.get("a", []),
                        bridge_id=bridge_id,
                    )
                    applied = 1

                    while applied < required_deltas:
                        event = buffered.pop(0) if buffered else await _next_event(queue, reader)
                        first_id = int(event["U"])
                        final_id = int(event["u"])

                        if final_id <= (book.last_update_id or -1):
                            continue

                        if market == "usdm":
                            if "pu" not in event:
                                raise SequenceGap("USD-M depth event missing pu")
                            book.apply_delta(
                                first_id,
                                final_id,
                                event.get("b", []),
                                event.get("a", []),
                                previous_final_id=int(event["pu"]),
                            )
                        else:
                            book.apply_delta(
                                first_id,
                                final_id,
                                event.get("b", []),
                                event.get("a", []),
                            )
                        applied += 1

                    bid, ask = book.best_bid_ask()
                    if book.state != BookState.VALID or bid is None or ask is None:
                        raise RuntimeError("book did not reach valid two-sided state")
                    if not (Decimal(bid) < Decimal(ask)):
                        raise RuntimeError(f"crossed/locked book bid={bid} ask={ask}")

                    return LiveBookResult(
                        market=market,
                        symbol=symbol,
                        last_update_id=int(book.last_update_id),
                        best_bid=str(bid),
                        best_ask=str(ask),
                        deltas_applied=applied,
                    )
                finally:
                    reader.cancel()
                    try:
                        await reader
                    except asyncio.CancelledError:
                        pass
        except Exception as exc:
            last_error = exc

        await asyncio.sleep(0.2)

    raise RuntimeError(f"orderbook sync failed {market}:{symbol}: {last_error}")


async def sync_all() -> list[LiveBookResult]:
    async with aiohttp.ClientSession(headers={"User-Agent": "btceth-phase1a/0.1"}) as session:
        results: list[LiveBookResult] = []
        for market in ("spot", "usdm"):
            for symbol in ("BTCUSDT", "ETHUSDT"):
                results.append(await sync_one(session, market, symbol))
        return results


if __name__ == "__main__":
    results = asyncio.run(sync_all())
    print(json.dumps([r.__dict__ for r in results], indent=2))
