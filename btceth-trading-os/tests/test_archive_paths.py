from __future__ import annotations

import pytest
from pathlib import Path

from btceth_os.sources.binance.archive_paths import (
    BinancePathError,
    build_archive_paths,
)
from btceth_os.sources.registry import load_historical_datasets_registry


def test_spot_trades_paths():
    btc_m = build_archive_paths("spot", "trades", "BTCUSDT", "monthly", "2024-11")
    assert btc_m.archive_url == "https://data.binance.vision/data/spot/monthly/trades/BTCUSDT/BTCUSDT-trades-2024-11.zip"
    assert btc_m.checksum_url == "https://data.binance.vision/data/spot/monthly/trades/BTCUSDT/BTCUSDT-trades-2024-11.zip.CHECKSUM"
    assert btc_m.archive_filename == "BTCUSDT-trades-2024-11.zip"

    eth_d = build_archive_paths("spot", "trades", "ETHUSDT", "daily", "2024-11-01")
    assert eth_d.archive_url == "https://data.binance.vision/data/spot/daily/trades/ETHUSDT/ETHUSDT-trades-2024-11-01.zip"
    assert eth_d.checksum_url == "https://data.binance.vision/data/spot/daily/trades/ETHUSDT/ETHUSDT-trades-2024-11-01.zip.CHECKSUM"


def test_spot_agg_trades_paths():
    btc_m = build_archive_paths("spot", "aggTrades", "BTCUSDT", "monthly", "2024-11")
    assert btc_m.archive_url == "https://data.binance.vision/data/spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-11.zip"

    eth_d = build_archive_paths("spot", "aggTrades", "ETHUSDT", "daily", "2024-11-01")
    assert eth_d.archive_url == "https://data.binance.vision/data/spot/daily/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2024-11-01.zip"


def test_spot_klines_1m_paths():
    btc_m = build_archive_paths("spot", "klines", "BTCUSDT", "monthly", "2024-11", interval="1m")
    assert btc_m.archive_url == "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip"

    eth_d = build_archive_paths("spot", "klines", "ETHUSDT", "daily", "2024-11-01", interval="1m")
    assert eth_d.archive_url == "https://data.binance.vision/data/spot/daily/klines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip"


def test_usdm_trades_and_aggtrades_paths():
    btc_tr = build_archive_paths("usdm", "trades", "BTCUSDT", "monthly", "2024-11")
    assert btc_tr.archive_url == "https://data.binance.vision/data/futures/um/monthly/trades/BTCUSDT/BTCUSDT-trades-2024-11.zip"

    eth_agg = build_archive_paths("usdm", "aggTrades", "ETHUSDT", "daily", "2024-11-01")
    assert eth_agg.archive_url == "https://data.binance.vision/data/futures/um/daily/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2024-11-01.zip"


def test_usdm_klines_1m_paths():
    btc_kl = build_archive_paths("usdm", "klines", "BTCUSDT", "monthly", "2024-11", interval="1m")
    assert btc_kl.archive_url == "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip"

    eth_kl = build_archive_paths("usdm", "klines", "ETHUSDT", "daily", "2024-11-01", interval="1m")
    assert eth_kl.archive_url == "https://data.binance.vision/data/futures/um/daily/klines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip"

    xau = build_archive_paths("usdm", "klines", "XAUUSDT", "monthly", "2026-01", interval="1m")
    assert xau.archive_url == "https://data.binance.vision/data/futures/um/monthly/klines/XAUUSDT/1m/XAUUSDT-1m-2026-01.zip"
    with pytest.raises(BinancePathError, match="only as a USD-M"):
        build_archive_paths("spot", "klines", "XAUUSDT", "monthly", "2026-01", interval="1m")


def test_usdm_mark_index_premium_paths():
    mark_m = build_archive_paths("usdm", "markPriceKlines", "BTCUSDT", "monthly", "2024-11", interval="1m")
    assert mark_m.archive_url == "https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip"

    index_d = build_archive_paths("usdm", "indexPriceKlines", "ETHUSDT", "daily", "2024-11-01", interval="1m")
    assert index_d.archive_url == "https://data.binance.vision/data/futures/um/daily/indexPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip"

    prem_m = build_archive_paths("usdm", "premiumIndexKlines", "BTCUSDT", "monthly", "2024-11", interval="1m")
    assert prem_m.archive_url == "https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip"

    prem_d = build_archive_paths("usdm", "premiumIndexKlines", "ETHUSDT", "daily", "2024-11-01", interval="1m")
    assert prem_d.archive_url == "https://data.binance.vision/data/futures/um/daily/premiumIndexKlines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip"


def test_funding_rate_monthly_and_daily_rejection():
    btc_f = build_archive_paths("usdm", "fundingRate", "BTCUSDT", "monthly", "2024-11")
    assert btc_f.archive_url == "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-11.zip"
    assert btc_f.archive_filename == "BTCUSDT-fundingRate-2024-11.zip"

    with pytest.raises(BinancePathError, match="fundingRate.*exclusively on monthly"):
        build_archive_paths("usdm", "fundingRate", "BTCUSDT", "daily", "2024-11-01")


def test_validation_errors():
    with pytest.raises(BinancePathError, match="Unsupported market"):
        build_archive_paths("options", "trades", "BTCUSDT", "monthly", "2024-11")

    with pytest.raises(BinancePathError, match="outside canonical universe"):
        build_archive_paths("spot", "trades", "DOGEUSDT", "monthly", "2024-11")

    with pytest.raises(BinancePathError, match="Monthly period.*YYYY-MM"):
        build_archive_paths("spot", "trades", "BTCUSDT", "monthly", "2024-13")

    with pytest.raises(BinancePathError, match="Daily period.*YYYY-MM-DD"):
        build_archive_paths("spot", "trades", "BTCUSDT", "daily", "2024-11")

    with pytest.raises(BinancePathError, match="Interval is required"):
        build_archive_paths("spot", "klines", "BTCUSDT", "monthly", "2024-11", interval=None)

    with pytest.raises(BinancePathError, match="Interval must be None"):
        build_archive_paths("spot", "trades", "BTCUSDT", "monthly", "2024-11", interval="1m")


def test_separate_xau_registry_does_not_expand_legacy_twenty_dataset_scope():
    assert len(load_historical_datasets_registry()) == 20
    root = Path(__file__).resolve().parents[1]
    xau = load_historical_datasets_registry(root / "config" / "xau_datasets.yaml")
    assert len(xau) == 7
    assert {item.instrument for item in xau} == {"BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"}
    assert xau[-1].source_dataset_name == "fundingRate" and xau[-1].daily_support == "VERIFIED_FALSE"
