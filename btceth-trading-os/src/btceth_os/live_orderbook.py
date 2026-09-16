from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import aiohttp
import websockets

from .collectors import BINANCE_SPOT_REST, BINANCE_USDM_REST, BINANCE_SPOT_WS, BINANCE_USDM_PUBLIC_WS
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
        return f"{BINANCE_SPOT_REST}/api/v3/depth", {"symbol": symbol, "limit": 1000}
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
    """Continuously read diff-depth messages so REST snapshot latency cannot create a gap."""
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


async def sync_one(
    session: aiohttp.ClientSession,
    market: str,
    symbol: str,
    *,
    max_attempts: int = 4,
    required_deltas: int = 2,
) -> LiveBookResult:
    """Prove live snapshot + diff alignment for one Binance book.

    The WebSocket reader runs continuously before and during REST snapshot fetches.
    This follows Binance's documented bootstrap order and prevents a fast book from
    advancing past the snapshot while our client is blocked waiting for REST.
    """
    url = _stream_url(market, symbol)
    last_error: Exception | None = None

    for _ in range(max_attempts):
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
                    # Prove the stream is alive before asking REST for a snapshot.
                    first_event = await _next_event(queue, reader)
                    buffered: list[dict[str, Any]] = [first_event]

                    # While REST responds, _buffer_depth keeps receiving every delta.
                    # If the snapshot is still too old for our earliest usable event,
                    # refetch it while keeping the same live stream/buffer.
                    bridge_event: dict[str, Any] | None = None
                    snap: dict[str, Any] | None = None
                    for _snapshot_attempt in range(6):
                        snap = await _snapshot(session, market, symbol)
                        snapshot_id = int(snap["lastUpdateId"])

                        while not queue.empty():
                            buffered.append(queue.get_nowait())

                        # Binance Spot drops u <= snapshot id. USD-M docs say u < id.
                        def is_stale(event: dict[str, Any]) -> bool:
                            final_id = int(event["u"])
                            return final_id <= snapshot_id if market == "spot" else final_id < snapshot_id

                        buffered = [event for event in buffered if not is_stale(event)]

                        if not buffered:
                            buffered.append(await _next_event(queue, reader))
                            while not queue.empty():
                                buffered.append(queue.get_nowait())
                            buffered = [event for event in buffered if not is_stale(event)]

                        if not buffered:
                            continue

                        candidate = buffered[0]
                        first_id = int(candidate["U"])
                        final_id = int(candidate["u"])

                        # Binance's documented first-event bridge rule for both Spot
                        # and USD-M is that lastUpdateId lies inside [U, u].
                        if first_id <= snapshot_id <= final_id:
                            bridge_event = buffered.pop(0)
                            break

                        # If candidate starts after snapshot, REST was too old. Keep
                        # buffering and fetch a newer snapshot; do not discard WS.
                        if first_id > snapshot_id:
                            await asyncio.sleep(0.05)
                            continue

                        # Candidate overlaps oddly but cannot bridge; drop and continue.
                        buffered.pop(0)

                    if snap is None or bridge_event is None:
                        raise SequenceGap("unable to bridge buffered depth to REST snapshot")

                    book = OrderBookSync()
                    book.begin_buffering()
                    snapshot_id = int(snap["lastUpdateId"])
                    book.load_snapshot(snapshot_id, snap.get("bids", []), snap.get("asks", []))
                    book.bridge_first_delta(
                        int(bridge_event["U"]),
                        int(bridge_event["u"]),
                        bridge_event.get("b", []),
                        bridge_event.get("a", []),
                    )

                    applied = 1
                    previous_u = int(bridge_event["u"])

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

                        previous_u = final_id
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

        await asyncio.sleep(0.25)

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
