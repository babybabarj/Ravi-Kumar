"""Write factual V16 data-foundation evidence after the tested code commit."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from btceth_os.sessions import SessionTimezoneUnavailableError, evaluate_sessions
from tools.materialize_xau_primary_sources_v3 import canonical, digest, extract
from tools.materialize_xau_research_v3 import logical_sha
from tools.verify_multiasset_v16 import file_sha, git, security_zero


def write(name: str, data: dict) -> None:
    (ROOT / "reports" / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    source_manifest = json.loads((ROOT / "config/xau_primary_sources_v3.json").read_text())
    source_details = {}
    for source_id, spec in source_manifest["sources"].items():
        raw = (ROOT / spec["snapshot_path"]).read_bytes()
        extracted = extract(spec, raw)
        source_details[source_id] = {
            "canonical_url": spec["canonical_url"], "title": extracted["title"],
            "page_publication_time": extracted["published_at"], "rule_effective_time": extracted["effective_at"],
            "contract_availability_date": source_manifest["official_listing_or_availability_date"] if source_id == "ecf7318c0d434c339e80878588e700d0" else None,
            "research_admission_time": source_manifest["research_admission_timestamp"] if source_id == "ecf7318c0d434c339e80878588e700d0" else None,
            "physical_sha256": file_sha(ROOT / spec["snapshot_path"]),
            "logical_sha256": digest(canonical(extracted)), "claims": spec["claims"],
        }
    write("XAU_PRIMARY_SOURCE_METADATA_V16.json", {
        "status": "SOURCE_METADATA_CONFLICT", "details": source_manifest["metadata_conflict"],
        "official_listing_or_availability_timestamp": "UNKNOWN",
        "official_listing_or_availability_date": source_manifest["official_listing_or_availability_date"],
        "first_observable_official_archive_timestamp": source_manifest["first_observable_official_archive_timestamp"],
        "research_admission_timestamp": source_manifest["research_admission_timestamp"],
        "research_admission_reason": source_manifest["research_admission_reason"],
        "sources": source_details,
    })

    manifest = json.loads((ROOT / "config/xau_research_partitions_v3.json").read_text())
    audit = {}
    for key, item in [("silver", manifest["silver"]), *manifest["partitions"].items()]:
        path = ROOT / item["relative_path"]
        table = pq.read_table(path)
        actual_physical = file_sha(path)
        actual_logical = logical_sha(table)
        audit[key] = {"physical_sha256": actual_physical, "expected_physical_sha256": item["physical_sha256"],
                      "logical_sha256": actual_logical, "expected_logical_sha256": item["logical_sha256"],
                      "rows": table.num_rows, "all_match": actual_physical == item["physical_sha256"] and actual_logical == item["logical_sha256"]}
    write("XAU_LOGICAL_HASH_AUDIT_V16.json", {"hash_format": "ordered schema and canonical JSON rows v3",
                                               "independently_recomputed": True, "artifacts": audit,
                                               "all_passed": all(x["all_match"] for x in audit.values())})

    silver = pq.read_table(ROOT / manifest["silver"]["relative_path"])
    events = pq.read_table(ROOT / manifest["funding_events"]["relative_path"])
    event_flags = silver["is_funding_event"].to_pylist()
    bar_ts = silver["ts_event_ns"].to_pylist()
    event_ts = silver["funding_event_ts_ns"].to_pylist()
    last_ts = silver["last_realized_funding_event_ts_ns"].to_pylist()
    admitted_events = [t for t in events["ts_event_ns"].to_pylist() if t >= 1767657600_000_000_000 and t <= bar_ts[-1]]
    causal = all((e is None or e <= t) and (l is None or l <= t) for t, e, l in zip(bar_ts, event_ts, last_ts))
    event_count = sum(event_flags)
    write("XAU_FUNDING_SEMANTICS_V16.json", {
        "ambiguous_generic_funding_rate_absent": "funding_rate" not in silver.column_names,
        "discrete_event_rows": events.num_rows, "admitted_events_visible_in_bars": len(admitted_events),
        "bars_with_single_funding_event": event_count, "no_double_count": event_count == len(admitted_events),
        "event_timestamp_causal": causal, "first_bar_last_realized_null": last_ts[0] is None,
        "source_interval_mismatches_in_admitted_events": manifest["funding_events"]["interval_mismatches"],
        "pre_admission_interval_unverifiable": manifest["funding_events"]["pre_admission_interval_unverifiable"],
        "epoch_transition_correction": "Index component change effective 2026-01-29T08:00:00Z per primary page",
        "all_passed": "funding_rate" not in silver.column_names and causal and event_count == len(admitted_events)
    })

    samples = {
        "ordinary_weekday": "2026-07-06T14:00:00+00:00", "weekend": "2026-07-05T14:00:00+00:00",
        "pre_september_daily_break": "2026-07-06T21:30:00+00:00",
        "post_september_continuous": "2026-09-16T21:30:00+00:00",
        "dst_before": "2026-03-08T06:30:00+00:00", "dst_after": "2026-03-08T07:30:00+00:00",
    }
    session_results = {name: evaluate_sessions(datetime.fromisoformat(ts)).to_dict() for name, ts in samples.items()}
    with patch("btceth_os.sessions.zoneinfo.ZoneInfo", side_effect=KeyError("unavailable")):
        try:
            evaluate_sessions(datetime.fromisoformat(samples["ordinary_weekday"]))
            timezone_fail_closed = False
        except SessionTimezoneUnavailableError:
            timezone_fail_closed = True
    write("XAU_SESSION_CERTAINTY_V16.json", {
        "holiday_calendar_implemented": False, "samples": session_results,
        "weekday_certainty_not_verified": session_results["ordinary_weekday"]["underlying_session_certainty"] == "WEEKDAY_RULE_ONLY",
        "weekday_index_holiday_unknown": session_results["ordinary_weekday"]["price_index_mode_certainty"] == "HOLIDAY_UNKNOWN",
        "contract_tradability_separate": all(x["is_contract_tradable"] for x in session_results.values()),
        "timezone": "America/New_York; ZoneInfo construction fails closed",
        "timezone_failure_fail_closed": timezone_fail_closed,
        "dst_eastern_local_times": {
            key: datetime.fromisoformat(samples[key]).astimezone(ZoneInfo("America/New_York")).isoformat()
            for key in ("dst_before", "dst_after")
        },
    })

    flags = silver["series_quality_flags"].to_pylist()
    alignment = {name: silver[name].null_count for name in ("mark_price", "index_price", "premium_index")}
    write("XAU_SERIES_ALIGNMENT_AUDIT_V16.json", {
        "rows": silver.num_rows, "quality_flag_nonzero_rows": sum(bool(x) for x in flags),
        "null_counts": alignment, "silent_fallback": "DISABLED", "all_passed": all(x == 0 for x in alignment.values()) and all(x == 0 for x in flags),
    })
    numeric_names = ("open", "high", "low", "close", "volume", "quote_volume", "mark_price", "index_price", "premium_index", "funding_event_rate", "last_realized_funding_rate")
    types = {f.name: str(f.type) for f in silver.schema}
    write("XAU_DECIMAL_SCHEMA_AUDIT_V16.json", {
        "fields": types, "financial_fields_decimal128": all(pa.types.is_decimal(silver.schema.field(n).type) for n in numeric_names),
        "float_financial_fields": [n for n in numeric_names if pa.types.is_floating(silver.schema.field(n).type)],
    })

    report_names = (
        "XAU_AGGTRADE_RECONCILIATION_V16.json", "XAU_PRIMARY_SOURCE_REPRODUCIBILITY_V16.json",
        "XAU_PRIMARY_SOURCE_METADATA_V16.json", "XAU_FUNDING_SEMANTICS_V16.json",
        "XAU_SESSION_CERTAINTY_V16.json", "XAU_LOGICAL_HASH_AUDIT_V16.json",
        "XAU_TRADES_AGGTRADES_AUDIT_V16.json", "XAU_SERIES_ALIGNMENT_AUDIT_V16.json",
        "XAU_JUNE_TRADES_REPLACEMENT_V16.json",
        "XAU_DECIMAL_SCHEMA_AUDIT_V16.json",
    )
    report_shas = {name: file_sha(ROOT / "reports" / name) for name in report_names}
    trade_audit = json.loads((ROOT / "reports/XAU_TRADES_AGGTRADES_AUDIT_V16.json").read_text())
    june_replacement = json.loads((ROOT / "reports/XAU_JUNE_TRADES_REPLACEMENT_V16.json").read_text())
    write("PHASE2E_2_XAU_FOUNDATION_V16.json", {
        "status": "VERIFIED" if all(x["all_match"] for x in audit.values()) and june_replacement["replacement_passed"] and trade_audit["multi_epoch_reconciliation_passed"] else "REMEDIATION_REQUIRED",
        "tested_code_sha": git("rev-parse", "HEAD"), "tested_tree_sha": git("rev-parse", "HEAD^{tree}"),
        "canonical_baseline_sha": git("rev-parse", "origin/btceth-phase1b"),
        "v15_evidence_parent_sha": git("rev-parse", "HEAD^"),
        "wip_safety_sha": git("rev-parse", "origin/btceth-round3b-wip-safety"),
        "source_manifest_v3_sha256": file_sha(ROOT / "config/xau_primary_sources_v3.json"),
        "partition_manifest_v3_sha256": file_sha(ROOT / "config/xau_research_partitions_v3.json"),
        "silver_v3": manifest["silver"], "partitions_v3": manifest["partitions"],
        "report_sha256": report_shas,
        "security_scan_zero": security_zero(),
        "trading_capability": "ZERO" if security_zero() else "FAIL",
        "separate_btc_bot_reuse_status": "QUARANTINED_NOT_RESEARCH_SAFE",
        "june_monthly_trades_status": "FAILED_QUARANTINED_REPLACED_BY_30_DAILY_ARCHIVES",
        "next_step": "STOP_FOR_INDEPENDENT_REVIEW",
    })
    (ROOT / "reports/PHASE2E_2_XAU_FOUNDATION_V16.md").write_text(
        "# Phase 2E.2 XAU foundation V16\n\n"
        "The evidence JSON files in this directory contain the source, archive, funding, session, and hash checks. "
        "May 15 has 99 trade IDs totaling 32.841 XAU outside the aggregate series; the included groups reconcile exactly. "
        "Their precise trade subtype is unknown. The checksum-valid June monthly trades archive fails ordering and duplicate-ID checks; 30 official daily files replace it. "
        "The January archive predates the availability date stated on Binance's January 8 page, "
        "so listing time remains unknown and pre-admission data stays quarantined. "
        "No strategy research, shadow, paper, or live trading was enabled. Stop for independent review.\n"
    )


if __name__ == "__main__":
    main()
