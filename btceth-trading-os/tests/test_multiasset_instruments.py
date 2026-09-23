from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from btceth_os.instruments import InstrumentSpec, resolve_instrument
from btceth_os.sources.registry import validate_canonical_instrument


def test_symbol_resolution_keeps_products_distinct() -> None:
    assert resolve_instrument("XAUUSDT") == "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"
    assert resolve_instrument("BINANCE:USD_M_PERP:BTCUSDT") == "BINANCE:USD_M_PERP:BTCUSDT"
    assert validate_canonical_instrument("BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT")
    assert not validate_canonical_instrument("BINANCE:TOKENIZED_COMMODITY_PERP:XAUTUSDT")
    with pytest.raises(ValueError, match="Unknown instrument XAEUSDT") as error:
        resolve_instrument("XAEUSDT")
    assert "XAUUSDT — Binance TradFi Gold perpetual" in str(error.value)
    assert "XAUTUSDT — Tether Gold perpetual" in str(error.value)
    with pytest.raises(ValueError, match="Ambiguous instrument BTCUSDT"):
        resolve_instrument("BTCUSDT")
    with pytest.raises(ValueError, match="support is not enabled"):
        resolve_instrument("XAUTUSDT")


def test_spec_is_immutable_and_rejects_float_or_cross_product_identity() -> None:
    spec = InstrumentSpec(
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        venue="BINANCE",
        symbol="XAUUSDT",
        base_asset="XAU",
        quote_asset="USDT",
        settlement_asset="USDT",
        product_family="TRADFI_COMMODITY_PERP",
        market_type="PERPETUAL",
        contract_type="PERPETUAL",
        underlying_type="GOLD_PRICE",
        tradfi_asset_class="COMMODITY",
        listing_ts=None,
        status="UNKNOWN",
        price_precision=None,
        quantity_precision=None,
        tick_size=Decimal("0.01"),
        step_size=None,
        min_qty=None,
        max_qty=None,
        min_notional=None,
        max_notional=None,
        contract_size=None,
        funding_enabled=True,
        current_funding_interval=None,
        leverage_supported=True,
        exchange_max_leverage=None,
        session_calendar_id=None,
        price_index_type=None,
        mark_price_type=None,
        api_segment="usdm",
        exchange_info_snapshot_sha="a" * 64,
        effective_from_ts=1,
        retrieved_at_ts=2,
    )
    with pytest.raises(FrozenInstanceError):
        spec.symbol = "XAUTUSDT"
    with pytest.raises(ValueError, match="tick_size"):
        replace(spec, tick_size=0.01)
    with pytest.raises(ValueError, match="disagrees"):
        replace(spec, symbol="XAUTUSDT")
    with pytest.raises(ValueError, match="market_type disagrees"):
        replace(spec, market_type="SPOT")
