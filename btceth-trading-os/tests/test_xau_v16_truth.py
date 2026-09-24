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


def test_jan30_funding_epoch_transition_4h_8h_4h():
    """Regression: Jan 30 2026 had a brief 8h window (12:15–18:15 UTC) then returned to 4h.
    Epoch 4A: 2026-01-30T12:15Z → 18:15Z, funding_interval=8h.
    The single event in epoch 4A is at 2026-01-30 16:00 UTC.
    Before (epoch 3, 4h): last event 2026-01-30 12:00 UTC.
    After (epoch 4B, 4h): events at 20:00, 2026-01-31 00:00, 04:00, 08:00 UTC.
    """
    import json
    from pathlib import Path
    import pyarrow.parquet as pq
    from collections import Counter
    from datetime import datetime

    ROOT = Path(__file__).resolve().parents[1]
    fund_path = ROOT / "artifacts/research/silver_xau/XAUUSDT-funding-events-silver-v3.parquet"
    if not fund_path.exists():
        pytest.skip("Funding events artifact not materialized")

    t = pq.read_table(fund_path)
    epochs = {x.as_py(): y.as_py() for x, y in zip(t["ts_event_ns"], t["contract_rule_epoch_id"])}
    intervals = {x.as_py(): y.as_py() for x, y in zip(t["ts_event_ns"], t["funding_interval_hours"])}
    timestamps = sorted(epochs.keys())
    HOUR_NS = 3_600_000_000_000

    # Epoch 4A: exactly 1 event at 2026-01-30 16:00 UTC, interval_hours=8
    ep4a_events = [ts for ts, ep in epochs.items() if ep == "XAU_EPOCH_4A_8H_TEMPORARY_FUNDING"]
    assert len(ep4a_events) == 1, f"Expected 1 event in epoch 4A, got {len(ep4a_events)}"
    ep4a_ts = ep4a_events[0]
    ep4a_dt = datetime.fromtimestamp(ep4a_ts / 1e9, tz=timezone.utc)
    assert ep4a_dt.hour == 16 and ep4a_dt.day == 30 and ep4a_dt.month == 1
    assert intervals[ep4a_ts] == 8

    # Prev event must be epoch 3 at 12:00, delta ~4h
    idx = timestamps.index(ep4a_ts)
    prev_ts = timestamps[idx - 1]
    assert epochs[prev_ts] == "XAU_EPOCH_3_INDEX_WEIGHT_REBALANCE"
    assert datetime.fromtimestamp(prev_ts / 1e9, tz=timezone.utc).hour == 12
    assert abs((ep4a_ts - prev_ts) / HOUR_NS - 4.0) < 0.01

    # Next event must be epoch 4B at 20:00, delta ~4h
    next_ts = timestamps[idx + 1]
    assert epochs[next_ts] == "XAU_EPOCH_4B_4H_FUNDING_AND_CAP_EXPANSION"
    assert datetime.fromtimestamp(next_ts / 1e9, tz=timezone.utc).hour == 20
    assert abs((next_ts - ep4a_ts) / HOUR_NS - 4.0) < 0.01

    # 2026-01-31 00:00, 04:00, 08:00 must all be in epoch 4B
    for h in (0, 4, 8):
        target_ns = int(datetime(2026, 1, 31, h, 0, tzinfo=timezone.utc).timestamp() * 1e9)
        closest_ts = min(timestamps, key=lambda ts: abs(ts - target_ns))
        assert abs(closest_ts - target_ns) < HOUR_NS
        assert epochs[closest_ts] == "XAU_EPOCH_4B_4H_FUNDING_AND_CAP_EXPANSION"

    # Overall: exactly 1 epoch-8h event, >1500 epoch-4h events (excluding pre-admission)
    admitted_intervals = Counter(
        intervals[ts] for ts in timestamps
        if epochs[ts] != "XAU_EPOCH_0_QUARANTINED_PRE_ADMISSION"
    )
    assert admitted_intervals[8] == 1
    assert admitted_intervals[4] > 1500


def test_v3_partition_research_admission_boundaries():
    """No DEV or VAL row may precede research admission (2026-01-06 00:00:00 UTC).
    Partition name XAUUSDT_DEV_2026_01_04 reflects epoch range, NOT a Jan-4 start date.
    """
    import json
    from pathlib import Path
    import pyarrow.parquet as pq

    ROOT = Path(__file__).resolve().parents[1]
    pv3_path = ROOT / "config/xau_research_partitions_v3.json"
    if not pv3_path.exists():
        pytest.skip("Partition manifest V3 not found")
    pv3 = json.loads(pv3_path.read_text())
    RESEARCH_ADMISSION_NS = 1_767_657_600_000_000_000  # 2026-01-06 00:00:00 UTC

    for pid in ("XAUUSDT_DEV_2026_01_04_V3", "XAUUSDT_VAL_2026_05_07_V3"):
        path = ROOT / pv3["partitions"][pid]["relative_path"]
        if not path.exists():
            pytest.skip(f"Partition not found: {path}")
        ts_vals = [x.as_py() for x in pq.read_table(path)["ts_event_ns"]]
        assert min(ts_vals) >= RESEARCH_ADMISSION_NS, (
            f"{pid}: earliest row {min(ts_vals)} precedes research_admission {RESEARCH_ADMISSION_NS}"
        )


def test_pre_admission_funding_events_did_not_leak_into_dev_val():
    """30 PRE_ADMISSION_UNVERIFIABLE funding events must not appear in
    DEV or VAL funding_event_ts_ns or last_realized_funding_event_ts_ns.
    """
    import json
    from pathlib import Path
    import pyarrow.parquet as pq

    ROOT = Path(__file__).resolve().parents[1]
    pv3_path = ROOT / "config/xau_research_partitions_v3.json"
    if not pv3_path.exists():
        pytest.skip("Partition manifest V3 not found")
    pv3 = json.loads(pv3_path.read_text())
    RESEARCH_ADMISSION_NS = 1_767_657_600_000_000_000

    for pid in ("XAUUSDT_DEV_2026_01_04_V3", "XAUUSDT_VAL_2026_05_07_V3"):
        path = ROOT / pv3["partitions"][pid]["relative_path"]
        if not path.exists():
            pytest.skip(f"Partition not found: {path}")
        t = pq.read_table(path)
        for col in ("funding_event_ts_ns", "last_realized_funding_event_ts_ns"):
            if col not in t.column_names:
                continue
            pre = [x.as_py() for x in t[col] if x.as_py() is not None and x.as_py() < RESEARCH_ADMISSION_NS]
            assert len(pre) == 0, (
                f"{pid}.{col}: {len(pre)} pre-admission timestamps leaked: {pre[:3]}"
            )

