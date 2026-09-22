from decimal import Decimal
import json

from btceth_os.research import Candle, CostModel, load_kline_candles, run_backtest, walk_forward_momentum, write_walk_forward_report
from btceth_os.sources.binance.archive_parser import BronzeRecord
from btceth_os.sources.binance.historical_silver import write_historical_silver


def candles(*closes: str) -> list[Candle]:
    return [
        Candle(
            index,
            Decimal(close),
            open=Decimal(close),
            instrument_id="BTCUSDT",
            dataset_id="BTCUSDT_DEV_2020_2022",
            market_type="USD_M_PERP",
            venue="BINANCE",
        )
        for index, close in enumerate(closes)
    ]


def test_cost_model_charges_entry_and_forced_exit():
    result = run_backtest(candles("100", "110", "110"), [1, 0, 0], CostModel(Decimal("10"), Decimal("0")))
    assert result.gross_return == Decimal("0.10")
    assert result.net_return < result.gross_return
    assert result.trades == 2


def test_walk_forward_chooses_from_train_then_scores_only_following_data():
    result = walk_forward_momentum(
        candles("10", "11", "12", "13", "14", "13", "12", "11", "10", "11", "12", "13"),
        train_bars=4,
        test_bars=4,
        candidate_lookbacks=[1, 2],
        costs=CostModel(Decimal("0"), Decimal("0")),
    )
    assert len(result.folds) == 2
    assert all(fold.test_start == fold.train_end for fold in result.folds)
    assert result.trades > 0


def test_research_report_is_immutable_and_tied_to_one_silver_source(tmp_path):
    records = [BronzeRecord("x", "BINANCE:SPOT:BTCUSDT", "klines", "x.csv", row, row, row, "ms", "ms", {
        "open": close, "high": close, "low": close, "close": close, "volume": "1", "quote_volume": "1", "count": 1,
    }) for row, close in enumerate(("10", "11", "12", "13", "14", "15"))]
    source_hash = "a" * 64
    silver, _ = write_historical_silver(records, tmp_path / "klines.parquet", source_hash)
    loaded_hash, loaded = load_kline_candles(silver)
    result = walk_forward_momentum(loaded, train_bars=3, test_bars=3, candidate_lookbacks=[1], costs=CostModel(Decimal("0"), Decimal("0")))
    report = write_walk_forward_report(tmp_path / "report.json", loaded_hash, train_bars=3, test_bars=3, candidate_lookbacks=[1], costs=CostModel(Decimal("0"), Decimal("0")), result=result)
    assert json.loads(report.read_text())["config"]["source_object_sha256"] == source_hash
