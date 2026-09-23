from pathlib import Path

import pyarrow.parquet as pq

from btceth_os.sources.binance.archive_parser import BronzeRecord
import pytest

from btceth_os.sources.binance.historical_silver import SilverBuildError, write_historical_silver


def funding(ts: int, rate: str = "0.00010000") -> BronzeRecord:
    return BronzeRecord("x", "BINANCE:USD_M_PERP:BTCUSDT", "fundingRate", "x.csv", 1, ts, ts // 1_000_000, "ms", "ms", {"funding_interval_hours": 8, "last_funding_rate": rate})


def test_funding_silver_uses_arrow_decimal_and_source_provenance(tmp_path: Path):
    path, findings = write_historical_silver([funding(1_730_419_200_000_000_000)], tmp_path / "funding.parquet", "a" * 64)
    table = pq.read_table(path)
    assert table.schema.field("funding_rate").type == __import__("pyarrow").decimal128(38, 18)
    assert table.column("funding_rate")[0].as_py().as_tuple().exponent == -18
    assert table.column("source_object_sha256")[0].as_py() == "a" * 64
    assert table.column("source_member")[0].as_py() == "x.csv"
    assert findings == []


def test_trade_and_aggregate_trade_remain_distinct_silver_schemas(tmp_path: Path):
    trade = BronzeRecord("x", "BINANCE:SPOT:BTCUSDT", "trades", "x.csv", 1, 1, 1, "ms", "ms", {"id": 7, "price": "10.01", "qty": "2.0", "quote_qty": "20.02", "is_buyer_maker": True, "is_best_match": False})
    agg = BronzeRecord("x", "BINANCE:SPOT:BTCUSDT", "aggTrades", "x.csv", 1, 1, 1, "ms", "ms", {"agg_trade_id": 8, "first_trade_id": 7, "last_trade_id": 9, "price": "10.01", "quantity": "2.0", "is_buyer_maker": False})
    trade_path, _ = write_historical_silver([trade], tmp_path / "trade.parquet", "b" * 64)
    agg_path, _ = write_historical_silver([agg], tmp_path / "agg.parquet", "b" * 64)
    assert "trade_id" in pq.read_table(trade_path).column_names
    assert "agg_trade_id" in pq.read_table(agg_path).column_names

    usdm_trade = BronzeRecord("x", "BINANCE:USD_M_PERP:BTCUSDT", "trades", "x.csv", 1, 2, 2, "ms", "ms", {"id": 9, "price": "10.01", "qty": "1.0", "quote_qty": "10.01", "is_buyer_maker": False})
    usdm_path, _ = write_historical_silver([usdm_trade], tmp_path / "usdm_trade.parquet", "b" * 64)
    assert pq.read_table(usdm_path).column("is_best_match")[0].as_py() is None


def test_silver_refuses_bad_provenance_or_overwrite(tmp_path: Path):
    destination = tmp_path / "funding.parquet"
    with pytest.raises(SilverBuildError, match="SHA-256"):
        write_historical_silver([funding(1)], destination, "not-a-hash")
    write_historical_silver([funding(1)], destination, "a" * 64)
    with pytest.raises(SilverBuildError, match="overwrite"):
        write_historical_silver([funding(1)], destination, "a" * 64)
