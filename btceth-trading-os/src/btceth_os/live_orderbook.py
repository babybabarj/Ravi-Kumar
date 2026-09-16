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


async def sync_one(
    session: aiohttp.ClientSession,
    market: str,
    symbol: str,
    *,
    max_attempts: int = 4,
    required_deltas: int = 2,
) -> LiveBookResult:
    """Prove live snapshot + diff alignment for one Binance book.

    The routine intentionally restarts from scratch on any unbridgeable sequence gap.
    It publishes no book until snapshot and streamed update IDs are aligned.
    """
    url = _stream_url(market, symbol)
    last_error: Exception | None = None

    for _ in range(max_attempts):
        book = OrderBookSync()
        book.begin_buffering()
        try:
            async with websockets.connect(
                url,
                open_timeout=15,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10,
                max_size=8 * 1024 * 1024,
            ) as ws:
                # Begin buffering before fetching the REST snapshot, per Binance's
                # documented local-order-book procedure.
                buffered: list[dict[str, Any]] = []
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                buffered.append(json.loads(raw))

                snap = await _snapshot(session, market, symbol)
                snapshot_id = int(snap["lastUpdateId"])
                book.load_snapshot(snapshot_id, snap.get("bids", []), snap.get("asks", []))

                applied = 0
                previous_u: int | None = None

                async def next_event() -> dict[str, Any]:
                    if buffered:
                        return buffered.pop(0)
                    raw_event = await asyncio.wait_for(ws.recv(), timeout=10)
                    return json.loads(raw_event)

                # Search for the first event that bridges the snapshot, then require
                # at least one additional contiguous delta. Bound the scan so a bad
                # stream can never hang acceptance indefinitely.
                for _scan in range(100):
                    event = await next_event()
                    if not isinstance(event, dict) or "U" not in event or "u" not in event:
                        continue
                    first_id = int(event["U"])
                    final_id = int(event["u"])
                    if final_id <= (book.last_update_id or -1):
                        continue

                    try:
                        if market == "usdm" and previous_u is not None:
                            book.apply_delta(
                                first_id,
                                final_id,
                                event.get("b", []),
                                event.get("a", []),
                                previous_final_id=int(event.get("pu", -1)),
                            )
                        else:
                            book.apply_delta(first_id, final_id, event.get("b", []), event.get("a", []))
                    except SequenceGap as exc:
                        last_error = exc
                        break

                    previous_u = final_id
                    applied += 1
                    if applied >= required_deltas:
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
                else:
                    last_error = RuntimeError("unable to find bridge event within bounded scan")
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
