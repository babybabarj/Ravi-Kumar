"""Canonical instrument identities and exchange-sourced specification values."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


SUPPORTED_INSTRUMENT_IDS = frozenset({
    "BINANCE:SPOT:BTCUSDT",
    "BINANCE:USD_M_PERP:BTCUSDT",
    "BINANCE:SPOT:ETHUSDT",
    "BINANCE:USD_M_PERP:ETHUSDT",
    "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
})

XAUT_INSTRUMENT_ID = "BINANCE:TOKENIZED_COMMODITY_PERP:XAUTUSDT"


def resolve_instrument(value: str) -> str:
    """Resolve an exact ID or an unambiguous symbol; never guess a market."""
    if value == "XAEUSDT":
        raise ValueError(
            "Unknown instrument XAEUSDT.\n\nDid you mean:\n\n"
            "XAUUSDT — Binance TradFi Gold perpetual\n\nor\n\n"
            "XAUTUSDT — Tether Gold perpetual?"
        )
    if value == XAUT_INSTRUMENT_ID or value == "XAUTUSDT":
        raise ValueError("XAUTUSDT is a distinct Tether Gold perpetual; support is not enabled")
    if value in SUPPORTED_INSTRUMENT_IDS:
        return value
    matches = sorted(i for i in SUPPORTED_INSTRUMENT_IDS if i.endswith(f":{value}"))
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError(f"Ambiguous instrument {value}; specify one of: {', '.join(matches)}")
    raise ValueError(f"Unknown instrument {value}")


@dataclass(frozen=True)
class InstrumentSpec:
    """One immutable exchange-rule snapshot. Times are UTC nanoseconds.

    Unknown exchange parameters are explicit ``None`` and cannot be used as
    order parameters. Monetary values must arrive as Decimal, never float.
    """

    instrument_id: str
    venue: str
    symbol: str
    base_asset: str
    quote_asset: str
    settlement_asset: str
    product_family: str
    market_type: str
    contract_type: str
    underlying_type: str
    tradfi_asset_class: str | None
    listing_ts: int | None
    status: str
    price_precision: int | None
    quantity_precision: int | None
    tick_size: Decimal | None
    step_size: Decimal | None
    min_qty: Decimal | None
    max_qty: Decimal | None
    min_notional: Decimal | None
    max_notional: Decimal | None
    contract_size: Decimal | None
    funding_enabled: bool
    current_funding_interval: int | None  # seconds
    leverage_supported: bool
    exchange_max_leverage: int | None
    session_calendar_id: str | None
    price_index_type: str | None
    mark_price_type: str | None
    api_segment: str
    exchange_info_snapshot_sha: str
    effective_from_ts: int
    retrieved_at_ts: int

    def __post_init__(self) -> None:
        if self.instrument_id not in SUPPORTED_INSTRUMENT_IDS:
            raise ValueError(f"Unsupported instrument ID: {self.instrument_id}")
        if self.instrument_id != f"{self.venue}:{self.product_family}:{self.symbol}":
            raise ValueError("Instrument ID disagrees with venue, product family, or symbol")
        if self.market_type != ("SPOT" if self.product_family == "SPOT" else "PERPETUAL"):
            raise ValueError("market_type disagrees with product family")
        if self.contract_type != ("NONE" if self.product_family == "SPOT" else "PERPETUAL"):
            raise ValueError("contract_type disagrees with product family")
        for name in ("tick_size", "step_size", "min_qty", "max_qty", "min_notional", "max_notional", "contract_size"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value < 0):
                raise ValueError(f"{name} must be a finite nonnegative Decimal or None")
        for name in ("tick_size", "step_size", "min_qty", "max_qty", "contract_size"):
            if getattr(self, name) == 0:
                raise ValueError(f"{name} must be positive when known")
        for name in ("price_precision", "quantity_precision", "current_funding_interval", "exchange_max_leverage"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer or None")
        for name in ("listing_ts", "effective_from_ts", "retrieved_at_ts"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0 or value >= 2**63):
                raise ValueError(f"{name} must be an int64 UTC nanosecond timestamp or None")
        for name in ("current_funding_interval", "exchange_max_leverage"):
            if getattr(self, name) == 0:
                raise ValueError(f"{name} must be positive when known")
        if self.min_qty is not None and self.max_qty is not None and self.min_qty > self.max_qty:
            raise ValueError("min_qty exceeds max_qty")
        if self.min_notional is not None and self.max_notional is not None and self.min_notional > self.max_notional:
            raise ValueError("min_notional exceeds max_notional")
        if len(self.exchange_info_snapshot_sha) != 64 or any(c not in "0123456789abcdef" for c in self.exchange_info_snapshot_sha):
            raise ValueError("exchange_info_snapshot_sha must be a lowercase SHA-256 digest")
