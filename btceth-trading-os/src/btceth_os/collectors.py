from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import random
from typing import Any, AsyncIterator

import aiohttp
import websockets


class RetryableSourceError(RuntimeError): pass
class FatalSourceError(RuntimeError): pass


def classify_http(status: int) -> str:
    if status == 429 or 500 <= status <= 599:
        return "RETRY"
    if status in (401, 403, 451):
        return "FATAL"
    if 200 <= status <= 299:
        return "OK"
    return "ERROR"


@dataclass
class ReconnectPolicy:
    base: float = 0.25
    maximum: float = 10.0
    attempt: int = 0

    def next_delay(self) -> float:
        delay = min(self.maximum, self.base * (2 ** self.attempt))
        self.attempt += 1
        return delay * (0.8 + random.random() * 0.4)

    def reset(self) -> None:
        self.attempt = 0


class PublicRestClient:
    def __init__(self, session: aiohttp.ClientSession, *, max_attempts: int = 4):
        self.session = session
        self.max_attempts = max_attempts

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(self.max_attempts):
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as response:
                text = await response.text()
                cls = classify_http(response.status)
                if cls == "OK":
                    return json.loads(text)
                if cls == "RETRY" and attempt + 1 < self.max_attempts:
                    await asyncio.sleep(min(2.0, 0.2 * (2 ** attempt)))
                    continue
                if cls == "FATAL":
                    raise FatalSourceError(f"HTTP {response.status}: {text[:300]}")
                raise RetryableSourceError(f"HTTP {response.status}: {text[:300]}")
        raise RetryableSourceError("retry budget exhausted")


async def websocket_messages(url: str, *, seconds: float = 5.0, reconnects: int = 1) -> AsyncIterator[dict[str, Any]]:
    """Read public websocket JSON with bounded reconnect for smoke/collector use."""
    deadline = asyncio.get_running_loop().time() + seconds
    policy = ReconnectPolicy()
    failures = 0
    while asyncio.get_running_loop().time() < deadline:
        try:
            async with websockets.connect(
                url,
                open_timeout=15,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10,
                max_size=8 * 1024 * 1024,
            ) as ws:
                policy.reset()
                while asyncio.get_running_loop().time() < deadline:
                    timeout = max(0.1, deadline - asyncio.get_running_loop().time())
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    yield json.loads(raw)
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            if asyncio.get_running_loop().time() >= deadline:
                break
            failures += 1
            if failures > reconnects:
                raise
            await asyncio.sleep(policy.next_delay())


BINANCE_SPOT_REST = "https://api.binance.com"
BINANCE_USDM_REST = "https://fapi.binance.com"
BINANCE_SPOT_WS = "wss://stream.binance.com:9443/ws"
# Binance permanently retired the legacy USD-M market-stream URLs on 2026-04-23.
# Phase 1A only uses high-frequency public streams, so route them through /public/ws.
BINANCE_USDM_PUBLIC_WS = "wss://fstream.binance.com/public/ws"
# Reserved for regular public market streams such as markPrice when Phase 1A moves them to WS.
BINANCE_USDM_MARKET_WS = "wss://fstream.binance.com/market/ws"
DERIBIT_REST = "https://www.deribit.com/api/v2"


def phase1a_rest_requests() -> list[tuple[str, str, str, str, dict[str, Any]]]:
    out: list[tuple[str, str, str, str, dict[str, Any]]] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        iid = f"BINANCE:USD_M_PERP:{symbol}"
        out.extend([
            ("binance", "usdm", "open_interest", iid, {"url": f"{BINANCE_USDM_REST}/fapi/v1/openInterest", "params": {"symbol": symbol}}),
            ("binance", "usdm", "global_long_short", iid, {"url": f"{BINANCE_USDM_REST}/futures/data/globalLongShortAccountRatio", "params": {"symbol": symbol, "period": "5m", "limit": 2}}),
            ("binance", "usdm", "top_account_ratio", iid, {"url": f"{BINANCE_USDM_REST}/futures/data/topLongShortAccountRatio", "params": {"symbol": symbol, "period": "5m", "limit": 2}}),
            ("binance", "usdm", "top_position_ratio", iid, {"url": f"{BINANCE_USDM_REST}/futures/data/topLongShortPositionRatio", "params": {"symbol": symbol, "period": "5m", "limit": 2}}),
            ("binance", "usdm", "taker_buy_sell", iid, {"url": f"{BINANCE_USDM_REST}/futures/data/takerlongshortRatio", "params": {"symbol": symbol, "period": "5m", "limit": 2}}),
            ("binance", "usdm", "basis", iid, {"url": f"{BINANCE_USDM_REST}/futures/data/basis", "params": {"pair": symbol, "contractType": "PERPETUAL", "period": "5m", "limit": 2}}),
            ("binance", "usdm", "mark_funding", iid, {"url": f"{BINANCE_USDM_REST}/fapi/v1/premiumIndex", "params": {"symbol": symbol}}),
            ("binance", "usdm", "book_ticker", iid, {"url": f"{BINANCE_USDM_REST}/fapi/v1/ticker/bookTicker", "params": {"symbol": symbol}}),
        ])
        sid = f"BINANCE:SPOT:{symbol}"
        out.append(("binance", "spot", "book_ticker", sid, {"url": f"{BINANCE_SPOT_REST}/api/v3/ticker/bookTicker", "params": {"symbol": symbol}}))
    for currency in ("BTC", "ETH"):
        out.append(("deribit", "option", "option_summary", f"DERIBIT:OPTION:{currency}:SUMMARY", {"url": f"{DERIBIT_REST}/public/get_book_summary_by_currency", "params": {"currency": currency, "kind": "option"}}))
    return out


def phase1a_ws_urls() -> list[tuple[str, str, str, str, str]]:
    out: list[tuple[str, str, str, str, str]] = []
    for s in ("btcusdt", "ethusdt"):
        up = s.upper()
        out.extend([
            ("binance", "spot", "aggtrade", f"BINANCE:SPOT:{up}", f"{BINANCE_SPOT_WS}/{s}@aggTrade"),
            ("binance", "spot", "book_ticker", f"BINANCE:SPOT:{up}", f"{BINANCE_SPOT_WS}/{s}@bookTicker"),
            # Diff-depth streams are required for a reconstructable local order book.
            ("binance", "spot", "depth_delta", f"BINANCE:SPOT:{up}", f"{BINANCE_SPOT_WS}/{s}@depth@100ms"),
            ("binance", "usdm", "aggtrade", f"BINANCE:USD_M_PERP:{up}", f"{BINANCE_USDM_PUBLIC_WS}/{s}@aggTrade"),
            ("binance", "usdm", "book_ticker", f"BINANCE:USD_M_PERP:{up}", f"{BINANCE_USDM_PUBLIC_WS}/{s}@bookTicker"),
            ("binance", "usdm", "depth_delta", f"BINANCE:USD_M_PERP:{up}", f"{BINANCE_USDM_PUBLIC_WS}/{s}@depth@100ms"),
            ("binance", "usdm", "liquidation_sample", f"BINANCE:USD_M_PERP:{up}", f"{BINANCE_USDM_PUBLIC_WS}/{s}@forceOrder"),
        ])
    return out
