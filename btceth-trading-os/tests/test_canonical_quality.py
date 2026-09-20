from btceth_os.quality.canonical import detect_missing_kline_minutes, validate_bronze_records
from btceth_os.quality.reconciliation import reconcile_kline_records
from btceth_os.sources.binance.archive_parser import BronzeRecord


def bar(row: int, ts: int, close: str = "1.5") -> BronzeRecord:
    return BronzeRecord("x", "i", "klines", "x.csv", row, ts, ts // 1_000_000, "ms", "ms", {
        "open": "1", "high": "2", "low": "0.5", "close": close, "volume": "1", "quote_volume": "1", "count": 1,
    })


def test_detects_gaps_without_filling_them():
    findings = detect_missing_kline_minutes([bar(1, 0), bar(2, 180_000_000_000)])
    assert findings[0].code == "MISSING_INTERVAL"
    assert "2 missing" in findings[0].detail


def test_rejects_invalid_ohlc_and_out_of_order_timestamps():
    invalid = bar(2, 0, "3")
    findings = validate_bronze_records([bar(1, 60_000_000_000), invalid])
    assert {finding.code for finding in findings} == {"TIMESTAMP_OUT_OF_ORDER", "INVALID_OHLC"}


def test_reconciliation_reports_disagreement_without_changing_source_records():
    primary = [bar(1, 0), bar(2, 60_000_000_000)]
    comparison = [bar(1, 0, "1.7"), bar(3, 120_000_000_000)]
    findings = reconcile_kline_records(primary, comparison)
    assert {(finding.code, finding.ts_event_ns) for finding in findings} == {
        ("KLINE_VALUE_MISMATCH", 0),
        ("MISSING_FROM_COMPARISON", 60_000_000_000),
        ("MISSING_FROM_PRIMARY", 120_000_000_000),
    }
