"""Rebuild causal XAU Silver V3 and locked partition artifacts from verified V2 data."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from btceth_os.contract_rule_epochs import ContractRuleEpochRegistry
from btceth_os.sessions import evaluate_sessions
from tools.materialize_xau_research_partitions import compute_file_sha256

SILVER = ROOT / "artifacts/research/silver_xau"
PARTITIONS = ROOT / "artifacts/research/partitions"
V2_MANIFEST = ROOT / "config/xau_research_partitions_v2.json"
V3_MANIFEST = ROOT / "config/xau_research_partitions_v3.json"
ADMISSION_NS = 1767657600_000_000_000


def logical_sha(table: pa.Table) -> str:
    """Hash ordered typed rows, including explicit nulls, independently of Parquet layout."""
    h = hashlib.sha256()
    h.update(json.dumps([(f.name, str(f.type), f.nullable) for f in table.schema], separators=(",", ":")).encode() + b"\n")
    for batch in table.to_batches(max_chunksize=4096):
        for row in batch.to_pylist():
            typed = {k: (format(v, "f") if isinstance(v, Decimal) else v) for k, v in row.items()}
            h.update(json.dumps(typed, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode() + b"\n")
    return h.hexdigest()


def replace(table: pa.Table, name: str, values: list[object], dtype: pa.DataType) -> pa.Table:
    idx = table.schema.get_field_index(name)
    if idx >= 0:
        return table.set_column(idx, pa.field(name, dtype), pa.array(values, type=dtype))
    return table.append_column(pa.field(name, dtype), pa.array(values, type=dtype))


def align_funding_events(bar_times: list[int], events: list[dict[str, object]]) -> dict[str, list[object]]:
    """Expose an event only at the first bar open at or after its actual timestamp."""
    admitted = [row for row in events if row["ts_event_ns"] >= ADMISSION_NS]
    out: dict[str, list[object]] = {key: [] for key in ("is_funding_event", "funding_event_rate",
        "funding_event_ts_ns", "last_realized_funding_event_ts_ns", "last_realized_funding_rate")}
    event_idx = 0
    last_event = None
    for ts in bar_times:
        current_event = None
        while event_idx < len(admitted) and admitted[event_idx]["ts_event_ns"] <= ts:
            current_event = admitted[event_idx]
            last_event = current_event
            event_idx += 1
        out["is_funding_event"].append(current_event is not None)
        out["funding_event_rate"].append(current_event["funding_rate"] if current_event else None)
        out["funding_event_ts_ns"].append(current_event["ts_event_ns"] if current_event else None)
        out["last_realized_funding_event_ts_ns"].append(last_event["ts_event_ns"] if last_event else None)
        out["last_realized_funding_rate"].append(last_event["funding_rate"] if last_event else None)
    return out


def build() -> dict[str, object]:
    old_manifest = json.loads(V2_MANIFEST.read_text())
    parent = old_manifest["parent_artifacts"]["XAUUSDT-resampled-1m-silver-v2.parquet"]
    parent_path = ROOT / parent["relative_path"]
    if compute_file_sha256(parent_path) != parent["physical_sha256"]:
        raise ValueError("Silver V2 parent physical SHA mismatch")
    old_funding = old_manifest["parent_artifacts"]["XAUUSDT-funding-events-silver-v2.parquet"]
    funding_path = ROOT / old_funding["relative_path"]
    if compute_file_sha256(funding_path) != old_funding["physical_sha256"]:
        raise ValueError("Funding V2 parent physical SHA mismatch")

    reg = ContractRuleEpochRegistry.from_yaml(ROOT / "config/xau_contract_rule_epochs_v3.yaml")
    bars = pq.read_table(parent_path).drop(["funding_rate"])
    events = pq.read_table(funding_path)
    times = bars["ts_event_ns"].to_pylist()
    event_rows = events.to_pylist()
    event_rows.sort(key=lambda row: row["ts_event_ns"])
    if len({row["ts_event_ns"] for row in event_rows}) != len(event_rows):
        raise ValueError("Duplicate funding event timestamps")

    epochs: list[str] = []
    underlying_states: list[str] = []
    certainties: list[str] = []
    holidays: list[str] = []
    index_modes: list[str] = []
    index_certainties: list[str] = []
    expected_intervals: list[int | None] = []
    interval_matches: list[bool | None] = []
    event_epochs: list[str] = []
    for event in event_rows:
        dt = datetime.fromtimestamp(event["ts_event_ns"] / 1e9, timezone.utc)
        epoch = reg.get_epoch_for_timestamp(dt)
        expected = epoch.funding_interval_seconds // 3600 if epoch and epoch.funding_interval_seconds else None
        expected_intervals.append(expected)
        interval_matches.append(expected == event["funding_interval_hours"] if expected is not None else None)
        event_epochs.append(epoch.epoch_id if epoch else "UNKNOWN")

    funding_alignment = align_funding_events(times, event_rows)
    for ts in times:
        dt = datetime.fromtimestamp(ts / 1e9, timezone.utc)
        epoch = reg.get_epoch_for_timestamp(dt)
        snap = evaluate_sessions(dt, epoch.price_index_method if epoch else "UNKNOWN", epoch.epoch_id if epoch else None)
        epochs.append(epoch.epoch_id if epoch else "UNKNOWN")
        underlying_states.append(snap.underlying_state.value)
        certainties.append(snap.underlying_session_certainty)
        holidays.append(snap.holiday_status)
        index_modes.append(snap.price_index_mode)
        index_certainties.append(snap.price_index_mode_certainty)

    funding_v3 = replace(events, "contract_rule_epoch_id", event_epochs, pa.string())
    funding_v3 = replace(funding_v3, "expected_funding_interval_hours", expected_intervals, pa.int32())
    funding_v3 = replace(funding_v3, "interval_matches_epoch", interval_matches, pa.bool_())
    funding_v3_path = SILVER / "XAUUSDT-funding-events-silver-v3.parquet"
    pq.write_table(funding_v3, funding_v3_path, compression="snappy")
    bars = replace(bars, "is_funding_event", funding_alignment["is_funding_event"], pa.bool_())
    bars = replace(bars, "funding_event_rate", funding_alignment["funding_event_rate"], pa.decimal128(18, 8))
    bars = replace(bars, "funding_event_ts_ns", funding_alignment["funding_event_ts_ns"], pa.int64())
    bars = replace(bars, "last_realized_funding_event_ts_ns", funding_alignment["last_realized_funding_event_ts_ns"], pa.int64())
    bars = replace(bars, "last_realized_funding_rate", funding_alignment["last_realized_funding_rate"], pa.decimal128(18, 8))
    bars = replace(bars, "contract_rule_epoch_id", epochs, pa.string())
    bars = replace(bars, "underlying_session_state", underlying_states, pa.string())
    bars = replace(bars, "underlying_session_certainty", certainties, pa.string())
    bars = replace(bars, "holiday_status", holidays, pa.string())
    bars = replace(bars, "price_index_mode", index_modes, pa.string())
    bars = replace(bars, "price_index_mode_certainty", index_certainties, pa.string())
    silver_path = SILVER / "XAUUSDT-resampled-1m-silver-v3.parquet"
    pq.write_table(bars, silver_path, compression="snappy")
    silver_physical = compute_file_sha256(silver_path)
    manifest: dict[str, object] = {
        "manifest_version": "3.0.0", "instrument_id": old_manifest["instrument_id"],
        "v2_parent_physical_sha256": parent["physical_sha256"],
        "silver": {"relative_path": str(silver_path.relative_to(ROOT)), "physical_sha256": silver_physical,
                   "logical_sha256": logical_sha(bars), "rows": bars.num_rows},
        "funding_events": {"relative_path": str(funding_v3_path.relative_to(ROOT)),
                           "physical_sha256": compute_file_sha256(funding_v3_path),
                           "logical_sha256": logical_sha(funding_v3), "rows": funding_v3.num_rows,
                           "interval_mismatches": interval_matches.count(False),
                           "pre_admission_interval_unverifiable": interval_matches.count(None)},
        "partitions": {},
    }
    for old_id, old in old_manifest["partitions"].items():
        new_id = old_id.removesuffix("_V2") + "_V3"
        mask = pc.and_(pc.greater_equal(bars["ts_event_ns"], old["start_ts_ns"]),
                       pc.less_equal(bars["ts_event_ns"], old["end_ts_ns"]))
        part = bars.filter(mask)
        path = PARTITIONS / f"{new_id}.parquet"
        pq.write_table(part, path, compression="snappy")
        manifest["partitions"][new_id] = {
            "dataset_id": new_id, "role": old["role"], "relative_path": str(path.relative_to(ROOT)),
            "start_ts_ns": old["start_ts_ns"], "end_ts_ns": old["end_ts_ns"],
            "rows": part.num_rows, "physical_sha256": compute_file_sha256(path),
            "logical_sha256": logical_sha(part), "parent_physical_sha256": silver_physical,
        }
    V3_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    result = build()
    print(json.dumps({"silver_rows": result["silver"]["rows"], "funding_rows": result["funding_events"]["rows"],
                      "funding_interval_mismatches": result["funding_events"]["interval_mismatches"],
                      "partitions": {k: v["rows"] for k, v in result["partitions"].items()}}, indent=2))
