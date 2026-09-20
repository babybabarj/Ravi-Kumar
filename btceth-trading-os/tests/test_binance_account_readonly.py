from __future__ import annotations

import json
import urllib.parse

import pytest

from btceth_os.sources.binance.account_readonly import BinanceCredentials, BinanceReadOnlyClient, BinanceReadOnlyError, read_spot_account, read_usdm_account


class Response:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *_): return None
    def read(self): return json.dumps(self.payload).encode()


class FakeBinance:
    def __init__(self): self.requests = []
    def __call__(self, request, timeout):
        self.requests.append(request)
        path = urllib.parse.urlparse(request.full_url).path
        payloads = {
            "/api/v3/time": {"serverTime": 2_000},
            "/api/v3/account": {"balances": [{"asset": "BTC", "free": "0.1", "locked": "0"}, {"asset": "USDT", "free": "0", "locked": "0"}]},
            "/api/v3/openOrders": [{"symbol": "BTCUSDT"}],
            "/fapi/v1/time": {"serverTime": 2_000},
            "/fapi/v3/account": {"availableBalance": "20", "totalWalletBalance": "25", "assets": [{"asset": "USDT", "walletBalance": "25", "availableBalance": "20", "unrealizedProfit": "1"}], "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.01", "unrealizedProfit": "1", "entryPrice": "50000"}]},
            "/fapi/v1/openOrders": [],
        }
        return Response(payloads[path])


def client(base_url, fake):
    return BinanceReadOnlyClient(base_url, BinanceCredentials("key", "secret"), opener=fake, clock_ms=lambda: 1_000)


def test_spot_sync_uses_signed_gets_only_and_filters_zero_balances():
    fake = FakeBinance()
    snapshot = read_spot_account(BinanceCredentials("key", "secret"), client=client("https://spot.test", fake))
    assert snapshot.balances == ({"asset": "BTC", "free": "0.1", "locked": "0"},)
    assert snapshot.open_order_count == 1
    signed = urllib.parse.parse_qs(urllib.parse.urlparse(fake.requests[1].full_url).query)
    assert signed["timestamp"] == ["2000"] and "signature" in signed
    assert fake.requests[1].method == "GET"


def test_usdm_sync_exposes_positions_but_no_execution_surface():
    fake = FakeBinance()
    snapshot = read_usdm_account(BinanceCredentials("key", "secret"), client=client("https://futures.test", fake))
    assert snapshot.available_balance == "20"
    assert snapshot.positions[0]["symbol"] == "BTCUSDT"
    with pytest.raises(BinanceReadOnlyError, match="rejects endpoint"):
        client("https://futures.test", fake).signed_get("/fapi/v1/order")
