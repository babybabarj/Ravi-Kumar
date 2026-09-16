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
    Spot and USD-M use market-specific first-event bridge targets, then strict
    continuity rules are enforced for subsequent deltas.
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
                    first_event = await _next_event(queue, reader)
                    buffered: list[dict[str, Any]] = [first_event]

                    bridge_event: dict[str, Any] | None = None
                    bridge_target: int | None = None
                    snap: dict[str, Any] | None = None

                    for _snapshot_attempt in range(8):
                        snap = await _snapshot(session, market, symbol)
                        snapshot_id = int(snap["lastUpdateId"])

                        while not queue.empty():
                            buffered.append(queue.get_nowait())

                        # Spot docs discard u <= snapshot id. USD-M discards u < id.
                        if market == "spot":
                            buffered = [e for e in buffered if int(e["u"]) > snapshot_id]
                            # The next update expected by the snapshot can be snapshot+1.
                            bridge_target = snapshot_id + 1
                        else:
                            buffered = [e for e in buffered if int(e["u"]) >= snapshot_id]
                            bridge_target = snapshot_id

                        if not buffered:
                            await asyncio.sleep(0.02)
                            continue

                        # Find the first event that covers the market-specific bridge
                        # target. Do not assume buffered[0] must be the bridge event.
                        match_index: int | None = None
                        for idx, event in enumerate(buffered):
                            first_id = int(event["U"])
                            final_id = int(event["u"])
                            if first_id <= bridge_target <= final_id:
                                match_index = idx
                                break
                            if first_id > bridge_target:
                                # Snapshot is behind the buffered stream. Keep the WS
                                # reader alive and fetch a newer snapshot.
                                break

                        if match_index is not None:
                            # Events before the bridge are stale relative to snapshot.
                            buffered = buffered[match_index:]
                            bridge_event = buffered.pop(0)
                            break

                        await asyncio.sleep(0.02)

                    if snap is None or bridge_event is None or bridge_target is None:
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
                        bridge_id=bridge_target,
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
