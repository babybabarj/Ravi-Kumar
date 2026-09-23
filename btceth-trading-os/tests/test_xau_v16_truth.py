from datetime import datetime, timezone
from decimal import Decimal
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from btceth_os.research.data_guard import (
    CANONICAL_DATASET_REGISTRY, HoldoutAccessDeniedError, ResearchDataAccessGuard,
    ResearchOperation,
)
from btceth_os.sessions import evaluate_sessions
from tools.audit_xau_aggtrade_v16 import reconcile
from tools.materialize_xau_primary_sources_v3 import ROOT, canonical, digest, extract
from tools.materialize_xau_research_v3 import ADMISSION_NS, align_funding_events, logical_sha


def test_aggtrade_coverage_is_not_calendar_volume_exact():
    trades = [["1", "10", "1", "10", "1", "false"],
              ["2", "10", "2", "20", "2", "false"],
              ["3", "10", "3", "30", "3", "false"]]
    agg = [["7", "10", "4", "1", "3", "1", "false"]]
    assert not reconcile(trades, agg)["covered_constituent_exact"]
    agg = [["7", "10", "1", "1", "1", "1", "false"],
           ["8", "10", "3", "3", "3", "3", "false"]]
    result = reconcile(trades, agg)
    assert result["covered_constituent_exact"]
    assert not result["calendar_day_volume_exact"]
    assert result["uncovered_trade_volume"] == "2"


def test_source_logical_hash_is_recomputed_from_content():
    manifest = json.loads((ROOT / "config/xau_primary_sources_v3.json").read_text())
    spec = manifest["sources"]["ecf7318c0d434c339e80878588e700d0"]
    raw = (ROOT / spec["snapshot_path"]).read_bytes()
    assert digest(canonical(extract(spec, raw))) == spec["expected_logical_sha256"]
    altered = raw.replace(b"2026-01-05", b"2026-01-04")
    assert altered != raw
    try:
        changed = digest(canonical(extract(spec, altered)))
    except ValueError:
        changed = None
    assert changed != spec["expected_logical_sha256"]


def test_logical_hash_ignores_parquet_compression_but_catches_price_change(tmp_path):
    schema = pa.schema([("ts_event_ns", pa.int64()), ("close", pa.decimal128(18, 4)),
                        ("instrument_id", pa.string()), ("contract_rule_epoch_id", pa.string())])
    rows = {"ts_event_ns": [1], "close": [Decimal("100.0000")],
            "instrument_id": ["BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"], "contract_rule_epoch_id": ["XAU_EPOCH_1"]}
    table = pa.Table.from_pydict(rows, schema=schema)
    p1, p2 = tmp_path / "a.parquet", tmp_path / "b.parquet"
    pq.write_table(table, p1, compression="snappy")
    pq.write_table(table, p2, compression="gzip")
    assert p1.read_bytes() != p2.read_bytes()
    assert logical_sha(pq.read_table(p1)) == logical_sha(pq.read_table(p2))
    changed = table.set_column(1, "close", pa.array([Decimal("100.0001")], type=pa.decimal128(18, 4)))
    assert logical_sha(table) != logical_sha(changed)


def test_unverified_weekday_holiday_never_looks_verified():
    snap = evaluate_sessions(datetime(2026, 7, 6, 14, tzinfo=timezone.utc))
    assert snap.is_contract_tradable
    assert snap.holiday_status == "NOT_IMPLEMENTED"
    assert snap.underlying_session_certainty == "WEEKDAY_RULE_ONLY"
    assert snap.price_index_mode_certainty == "HOLIDAY_UNKNOWN"


def test_v3_holdout_and_pristine_remain_locked():
    for dataset_id in ("XAUUSDT_HOLDOUT_2026_08_09_V3", "XAUUSDT_PROSPECTIVE_PRISTINE_V3"):
        assert dataset_id in CANONICAL_DATASET_REGISTRY
        with pytest.raises(HoldoutAccessDeniedError):
            ResearchDataAccessGuard.check_access(ResearchOperation.BACKTEST, dataset_id, dataset_version="v3.0.0")


def test_funding_event_milliseconds_do_not_leak_into_prior_bar():
    start = ADMISSION_NS
    aligned = align_funding_events([start, start + 60_000_000_000], [
        {"ts_event_ns": start + 1_000_000, "funding_rate": Decimal("0.001")}
    ])
    assert aligned["is_funding_event"] == [False, True]
    assert aligned["last_realized_funding_rate"] == [None, Decimal("0.001")]
    assert aligned["funding_event_ts_ns"] == [None, start + 1_000_000]
