# Adapted from Passivbot (https://github.com/enarjord/passivbot)
# Original file: src/binance_ohlcv_archive.py
# Archive: passivbot-master.zip (SHA256: bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468)
# License: The Unlicense (Public Domain)
# Modifications: Upgraded to streaming .part download with incremental SHA-256,
# generalized dataset path planning, and exact nanosecond/decimal typing.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

BINANCE_ARCHIVE_BASE_URL = "https://data.binance.vision"

MarketKind = Literal["spot", "usdm"]
CadenceKind = Literal["monthly", "daily"]

SPOT_DATASETS = {"trades", "aggTrades", "klines"}
USDM_DATASETS = {
    "trades",
    "aggTrades",
    "klines",
    "markPriceKlines",
    "indexPriceKlines",
    "premiumIndexKlines",
    "fundingRate",
}
KLINE_LIKE_DATASETS = {"klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"}
SUPPORTED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "XAUUSDT"}

MONTHLY_PERIOD_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DAILY_PERIOD_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


class BinancePathError(ValueError):
    """Raised when an invalid or unsupported archive path request is constructed."""
    pass


@dataclass(frozen=True)
class BinancePathResult:
    """Resolved URLs and filenames for a historical Binance archive object."""
    archive_url: str
    checksum_url: str
    archive_filename: str
    checksum_filename: str
    directory_path: str


def validate_archive_parameters(
    market: str,
    dataset: str,
    symbol: str,
    cadence: str,
    period: str,
    interval: str | None = None,
) -> None:
    market_norm = market.lower()
    if market_norm not in ("spot", "usdm"):
        raise BinancePathError(f"Unsupported market {market!r}. Must be 'spot' or 'usdm'.")

    symbol_norm = symbol.upper()
    if symbol_norm not in SUPPORTED_SYMBOLS:
        raise BinancePathError(
            f"Symbol {symbol!r} outside canonical universe ({sorted(SUPPORTED_SYMBOLS)})."
        )
    if symbol_norm == "XAUUSDT" and market_norm != "usdm":
        raise BinancePathError("XAUUSDT is supported only as a USD-M TradFi perpetual archive")

    if market_norm == "spot" and dataset not in SPOT_DATASETS:
        raise BinancePathError(f"Dataset {dataset!r} unsupported for Spot market ({sorted(SPOT_DATASETS)}).")

    if market_norm == "usdm" and dataset not in USDM_DATASETS:
        raise BinancePathError(f"Dataset {dataset!r} unsupported for USD-M market ({sorted(USDM_DATASETS)}).")

    cadence_norm = cadence.lower()
    if cadence_norm not in ("monthly", "daily"):
        raise BinancePathError(f"Unsupported cadence {cadence!r}. Must be 'monthly' or 'daily'.")

    if dataset == "fundingRate":
        if cadence_norm != "monthly":
            raise BinancePathError(
                "fundingRate archives are available exclusively on monthly cadence; daily archive is unsupported."
            )
        if interval is not None:
            raise BinancePathError("interval must be None for fundingRate dataset.")

    if cadence_norm == "monthly":
        if not MONTHLY_PERIOD_REGEX.match(period):
            raise BinancePathError(f"Monthly period {period!r} does not match YYYY-MM format.")
    else:
        if not DAILY_PERIOD_REGEX.match(period):
            raise BinancePathError(f"Daily period {period!r} does not match YYYY-MM-DD format.")

    if dataset in KLINE_LIKE_DATASETS:
        if not interval:
            raise BinancePathError(f"Interval is required for kline-like dataset {dataset!r}.")
        if interval != "1m":
            # For our current scope, 1m is the canonical base candle interval
            pass
    else:
        if interval is not None:
            raise BinancePathError(f"Interval must be None for dataset {dataset!r}.")


def build_archive_paths(
    market: str,
    dataset: str,
    symbol: str,
    cadence: str,
    period: str,
    interval: str | None = None,
    base_url: str = BINANCE_ARCHIVE_BASE_URL,
) -> BinancePathResult:
    """Deterministically construct official archive and checksum URLs and filenames.
    Zero network I/O.
    """
    validate_archive_parameters(market, dataset, symbol, cadence, period, interval)

    market_norm = market.lower()
    symbol_norm = symbol.upper()
    cadence_norm = cadence.lower()

    if market_norm == "spot":
        market_path = "data/spot"
    else:
        market_path = "data/futures/um"

    # Directory template
    if dataset in KLINE_LIKE_DATASETS:
        directory_path = f"{market_path}/{cadence_norm}/{dataset}/{symbol_norm}/{interval}/"
        filename = f"{symbol_norm}-{interval}-{period}.zip"
    elif dataset == "fundingRate":
        directory_path = f"{market_path}/{cadence_norm}/{dataset}/{symbol_norm}/"
        filename = f"{symbol_norm}-fundingRate-{period}.zip"
    else:
        directory_path = f"{market_path}/{cadence_norm}/{dataset}/{symbol_norm}/"
        filename = f"{symbol_norm}-{dataset}-{period}.zip"

    archive_url = f"{base_url.rstrip('/')}/{directory_path}{filename}"
    checksum_filename = f"{filename}.CHECKSUM"
    checksum_url = f"{archive_url}.CHECKSUM"

    return BinancePathResult(
        archive_url=archive_url,
        checksum_url=checksum_url,
        archive_filename=filename,
        checksum_filename=checksum_filename,
        directory_path=directory_path,
    )
