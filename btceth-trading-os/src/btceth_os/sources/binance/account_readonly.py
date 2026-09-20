from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable


SPOT_BASE_URL = "https://api.binance.com"
USDM_BASE_URL = "https://fapi.binance.com"
_ALLOWED_SIGNED_PATHS = frozenset({"/api/v3/account", "/api/v3/openOrders", "/fapi/v3/account", "/fapi/v1/openOrders"})


class BinanceReadOnlyError(RuntimeError):
    pass


@dataclass(frozen=True)
class BinanceCredentials:
    api_key: str
    api_secret: str = field(repr=False)

    @classmethod
    def from_environment(cls, prefix: str) -> BinanceCredentials:
        key, secret = os.environ.get(f"{prefix}_API_KEY"), os.environ.get(f"{prefix}_API_SECRET")
        if not key or not secret:
            raise BinanceReadOnlyError(f"missing {prefix}_API_KEY or {prefix}_API_SECRET")
        return cls(key, secret)


@dataclass(frozen=True)
class BinanceAccountSnapshot:
    product: str
    synced_at_ns: int
    server_time_ms: int
    balances: tuple[dict[str, str], ...]
    positions: tuple[dict[str, str], ...]
    open_order_count: int
    available_balance: str | None = None
    total_wallet_balance: str | None = None

    def dashboard_summary(self) -> dict[str, object]:
        return {
            "balances": list(self.balances), "positions": list(self.positions), "open_orders": self.open_order_count,
            "available_balance": self.available_balance, "total_wallet_balance": self.total_wallet_balance,
        }


Opener = Callable[..., Any]


class BinanceReadOnlyClient:
    """Narrow Binance private-data client: signed GETs only, with no trading routes in its allowlist."""

    def __init__(self, base_url: str, credentials: BinanceCredentials, *, opener: Opener = urllib.request.urlopen, clock_ms: Callable[[], int] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.credentials = credentials
        self._opener = opener
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._clock_offset_ms = 0

    def sync_time(self, path: str) -> int:
        payload = self._get(path, {})
        try:
            server_time = int(payload["serverTime"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BinanceReadOnlyError("Binance time response is malformed") from exc
        self._clock_offset_ms = server_time - self._clock_ms()
        return server_time

    def signed_get(self, path: str, params: dict[str, str] | None = None) -> Any:
        if path not in _ALLOWED_SIGNED_PATHS:
            raise BinanceReadOnlyError(f"read-only client rejects endpoint {path!r}")
        values = dict(params or {})
        values["recvWindow"] = "5000"
        values["timestamp"] = str(self._clock_ms() + self._clock_offset_ms)
        query = urllib.parse.urlencode(values)
        signature = hmac.new(self.credentials.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return self._get(path, values | {"signature": signature}, {"X-MBX-APIKEY": self.credentials.api_key})

    def _get(self, path: str, params: dict[str, str], headers: dict[str, str] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers=headers or {}, method="GET")
        try:
            with self._opener(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BinanceReadOnlyError(f"Binance read-only request failed for {path}") from exc


def read_spot_account(credentials: BinanceCredentials, *, client: BinanceReadOnlyClient | None = None) -> BinanceAccountSnapshot:
    api = client or BinanceReadOnlyClient(SPOT_BASE_URL, credentials)
    server_time = api.sync_time("/api/v3/time")
    account, open_orders = api.signed_get("/api/v3/account"), api.signed_get("/api/v3/openOrders")
    balances = tuple({"asset": str(row["asset"]), "free": str(row["free"]), "locked": str(row["locked"])} for row in account.get("balances", []) if _nonzero(row.get("free")) or _nonzero(row.get("locked")))
    return BinanceAccountSnapshot("spot", time.time_ns(), server_time, balances, (), len(open_orders))


def read_usdm_account(credentials: BinanceCredentials, *, client: BinanceReadOnlyClient | None = None) -> BinanceAccountSnapshot:
    api = client or BinanceReadOnlyClient(USDM_BASE_URL, credentials)
    server_time = api.sync_time("/fapi/v1/time")
    account, open_orders = api.signed_get("/fapi/v3/account"), api.signed_get("/fapi/v1/openOrders")
    balances = tuple({"asset": str(row["asset"]), "wallet_balance": str(row["walletBalance"]), "available_balance": str(row.get("availableBalance", "0")), "unrealized_pnl": str(row.get("unrealizedProfit", "0"))} for row in account.get("assets", []) if _nonzero(row.get("walletBalance")) or _nonzero(row.get("unrealizedProfit")))
    positions = tuple({"symbol": str(row["symbol"]), "position_amount": str(row["positionAmt"]), "unrealized_pnl": str(row.get("unrealizedProfit", "0")), "entry_price": str(row.get("entryPrice", "0"))} for row in account.get("positions", []) if _nonzero(row.get("positionAmt")))
    return BinanceAccountSnapshot("usdm", time.time_ns(), server_time, balances, positions, len(open_orders), str(account.get("availableBalance")) if account.get("availableBalance") is not None else None, str(account.get("totalWalletBalance")) if account.get("totalWalletBalance") is not None else None)


def _nonzero(value: object) -> bool:
    try:
        return Decimal(str(value)) != 0
    except (InvalidOperation, ValueError) as exc:
        raise BinanceReadOnlyError("Binance account response has an invalid decimal") from exc
