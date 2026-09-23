from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from btceth_os.sources.binance.archive_parser import ArchiveSchemaError, iter_bronze_records
from btceth_os.sources.binance.models import ArchiveObjectSpec


def spec(dataset: str, market: str = "usdm") -> ArchiveObjectSpec:
    return ArchiveObjectSpec(
        source="binance", market=market, dataset_id=f"TEST:{dataset}", source_dataset_name=dataset,
        instrument="BINANCE:SPOT:BTCUSDT" if market == "spot" else "BINANCE:USD_M_PERP:BTCUSDT",
        symbol="BTCUSDT", cadence="daily", interval="1m" if dataset != "fundingRate" else None,
        period_key="2025-01-01", period_start_utc="", period_end_utc="", archive_url="https://example.test/x.zip",
        checksum_url="https://example.test/x.zip.CHECKSUM", archive_filename="x.zip", checksum_filename="x.zip.CHECKSUM",
        expected_timestamp_policy={}, support_status="VERIFIED_TRUE", discovery_evidence_id="test",
    )


def archive(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("source.csv", body)
    return path


def test_funding_parser_preserves_exact_rate_and_ms_precision(tmp_path: Path):
    path = archive(tmp_path, "calc_time,funding_interval_hours,last_funding_rate\n1730419200000,8,0.00010000\n")
    record = list(iter_bronze_records(path, spec("fundingRate")))[0]
    assert record.ts_event_ns == 1_730_419_200_000_000_000
    assert record.source_ts_unit == "ms"
    assert record.values["last_funding_rate"] == "0.00010000"
    assert record.values["funding_interval_hours"] == 8


def test_spot_kline_parser_handles_microsecond_epoch_without_float(tmp_path: Path):
    body = "1735689600000000,1.00,2.00,0.50,1.50,3.000,1735689659999999,4.500,7,1.000,1.500,0\n"
    record = list(iter_bronze_records(archive(tmp_path, body), spec("klines", "spot")))[0]
    assert record.ts_event_ns == 1_735_689_600_000_000_000
    assert record.source_ts_unit == "us"
    assert record.values["open"] == "1.00"
    assert record.values["count"] == 7


def test_trade_and_aggtrade_headers_are_normalized_but_strict(tmp_path: Path):
    trade = archive(tmp_path, "trade Id,price,qty,quoteQty,time,isBuyerMaker,isBestMatch\n1,1.20,0.30,0.36,1730000000000,true,false\n")
    trade_record = list(iter_bronze_records(trade, spec("trades", "spot")))[0]
    assert trade_record.values["id"] == 1
    assert trade_record.values["is_buyer_maker"] is True

    agg = archive(tmp_path, "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n2,1.20,0.30,1,2,1730000000000,false\n")
    agg_record = list(iter_bronze_records(agg, spec("aggTrades")))[0]
    assert agg_record.values["first_trade_id"] == 1


def test_usdm_trade_schema_has_no_spot_best_match_field(tmp_path: Path):
    path = archive(tmp_path, "id,price,qty,quote_qty,time,is_buyer_maker\n1,4217.00,0.017,71.689,1765440320838,true\n")
    record = list(iter_bronze_records(path, spec("trades")))[0]
    assert record.values["price"] == "4217.00"
    assert record.values["is_buyer_maker"] is True
    assert "is_best_match" not in record.values
    with pytest.raises(ArchiveSchemaError, match="unexpected"):
        list(iter_bronze_records(path, spec("trades", "spot")))


def test_unknown_headers_and_malformed_rows_fail_closed(tmp_path: Path):
    with pytest.raises(ArchiveSchemaError, match="unexpected"):
        list(iter_bronze_records(archive(tmp_path, "time,rate\n1,2\n"), spec("fundingRate")))
    with pytest.raises(ArchiveSchemaError, match="expected 3"):
        list(iter_bronze_records(archive(tmp_path, "calc_time,funding_interval_hours,last_funding_rate\n1,8\n"), spec("fundingRate")))
    with pytest.raises(ValueError, match="Invalid financial decimal"):
        list(iter_bronze_records(archive(tmp_path, "id,price,qty,quote_qty,time,is_buyer_maker,is_best_match\n1,1,2,not-a-number,1730000000000,true,false\n"), spec("trades", "spot")))
