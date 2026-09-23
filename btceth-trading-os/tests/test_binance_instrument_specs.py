import hashlib
import json
from decimal import Decimal

import pytest

from btceth_os.sources.binance.instrument_specs import InstrumentSpecProvider


def test_xau_spec_uses_source_rules_and_preserves_raw_snapshots(tmp_path, monkeypatch) -> None:
    base = "https://fapi.binance.com"
    bodies = {
        base + "/fapi/v1/exchangeInfo": {
            "symbols": [{
                "symbol": "XAUUSDT", "baseAsset": "XAU", "quoteAsset": "USDT", "marginAsset": "USDT",
                "contractType": "TRADIFI_PERPETUAL", "underlyingType": "COMMODITY", "status": "TRADING",
                "pricePrecision": 2, "quantityPrecision": 3, "onboardDate": 123,
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.25"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.005", "minQty": "0.005", "maxQty": "20"},
                    {"filterType": "MIN_NOTIONAL", "notional": "7"},
                ],
            }],
        },
        base + "/fapi/v1/fundingInfo": [
            {"symbol": "XAUUSDT", "fundingIntervalHours": 6, "adjustedFundingRateCap": "0.01"}
        ],
        base + "/fapi/v1/tradingSchedule": {
            "marketSchedules": {"COMMODITY": {"sessions": [{"startTime": 1, "endTime": 2, "type": "REGULAR"}]}}
        },
        base + "/fapi/v1/premiumIndex?symbol=XAUUSDT": {
            "symbol": "XAUUSDT", "markPrice": "2500.1", "indexPrice": "2500.0"
        },
    }
    raw = {url: json.dumps(body).encode() for url, body in bodies.items()}
    provider = InstrumentSpecProvider(tmp_path)
    monkeypatch.setattr(provider, "_fetch", lambda url: raw[url])

    spec = provider.refresh("XAUUSDT")
    assert spec.contract_type == "TRADIFI_PERPETUAL"
    assert spec.tick_size == Decimal("0.25")
    assert spec.step_size == Decimal("0.005")
    assert spec.min_notional == Decimal("7")
    assert spec.current_funding_interval == 6 * 3600
    assert spec.listing_ts is None  # onboardDate is not accepted as first trading time.
    assert spec.exchange_max_leverage is None

    snapshots = list((tmp_path / "specs").glob("*.json"))
    assert len(snapshots) == 1
    saved = json.loads(snapshots[0].read_text())
    assert saved["execution_approval"] == "NOT_ACCEPTED"
    assert len(saved["source_snapshots"]) == 4
    exchange_receipt = saved["source_snapshots"][0]
    assert exchange_receipt["physical_sha256"] == hashlib.sha256(raw[base + "/fapi/v1/exchangeInfo"]).hexdigest()
    assert (tmp_path / exchange_receipt["raw_file"]).read_bytes() == raw[base + "/fapi/v1/exchangeInfo"]

    bodies[base + "/fapi/v1/fundingInfo"] = []
    raw[base + "/fapi/v1/fundingInfo"] = b"[]"
    with pytest.raises(RuntimeError, match="XAU_FUNDING_RULE_UNKNOWN"):
        provider.refresh("XAUUSDT")
    assert len(list((tmp_path / "specs").glob("*.json"))) == 1
