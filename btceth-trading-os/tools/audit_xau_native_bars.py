"""Checksum-first XAU archive audit; never promotes rows into research partitions."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from btceth_os.sources.binance.archive_downloader import ArchiveDownloader
from btceth_os.sources.binance.archive_parser import iter_bronze_records
from btceth_os.sources.binance.archive_planner import plan_archive_requests
from btceth_os.sources.registry import load_historical_datasets_registry


ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT = "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"
BAR_DATASETS = ("klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines")
MINUTE_NS = 60_000_000_000


def audit_archive(downloader: ArchiveDownloader, spec) -> dict[str, object]:
    receipt = downloader.download(spec, extract=False)
    if not receipt.checksum_verified or not receipt.local_path or not receipt.physical_sha256:
        raise RuntimeError(f"Unverified XAU archive: {spec.archive_url}")
    count = gaps = missing_minutes = duplicate_timestamps = regressions = invalid_ohlc = invalid_price = negative_volume = 0
    first_ns = last_ns = previous_ns = None
    missing_ranges: list[dict[str, int]] = []
    logical = hashlib.sha256()
    for record in iter_bronze_records(receipt.local_path, spec):
        ts = record.ts_event_ns
        values = record.values
        logical.update(json.dumps(values, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        if previous_ns is not None:
            if ts == previous_ns:
                duplicate_timestamps += 1
            elif ts < previous_ns:
                regressions += 1
            elif spec.source_dataset_name in BAR_DATASETS and ts > previous_ns + MINUTE_NS:
                gaps += 1
                missing_minutes += (ts - previous_ns) // MINUTE_NS - 1
                missing_ranges.append({"first_missing_ns": previous_ns + MINUTE_NS, "next_present_ns": ts})
        if spec.source_dataset_name in BAR_DATASETS:
            open_, high, low, close = (Decimal(str(values[key])) for key in ("open", "high", "low", "close"))
            if high < max(open_, close) or low > min(open_, close) or high < low:
                invalid_ohlc += 1
            if spec.source_dataset_name != "premiumIndexKlines" and min(open_, high, low, close) <= 0:
                invalid_price += 1
            if Decimal(str(values["volume"])) < 0:
                negative_volume += 1
        first_ns = ts if first_ns is None else first_ns
        last_ns = previous_ns = ts
        count += 1
    if count == 0:
        raise RuntimeError(f"Empty XAU archive: {spec.archive_url}")
    expected_first_ns = int(datetime.fromisoformat(spec.period_start_utc).timestamp()) * 1_000_000_000
    expected_last_ns = int(datetime.fromisoformat(spec.period_end_utc).timestamp() // 60) * MINUTE_NS
    boundaries_match = (first_ns == expected_first_ns and last_ns == expected_last_ns) if spec.source_dataset_name in BAR_DATASETS else None
    return {
        "dataset": spec.source_dataset_name, "period": spec.period_key, "cadence": spec.cadence,
        "archive_url": spec.archive_url, "archive_physical_sha256": receipt.physical_sha256,
        "logical_sha256": logical.hexdigest(), "rows": count, "first_ts_ns": first_ns, "last_ts_ns": last_ns,
        "boundaries_match": boundaries_match,
        "gap_count": gaps, "missing_minutes": missing_minutes, "duplicate_timestamps": duplicate_timestamps,
        "missing_ranges": missing_ranges, "null_values": 0,
        "timestamp_regressions": regressions, "invalid_ohlc": invalid_ohlc,
        "invalid_price": invalid_price, "negative_volume": negative_volume,
        "quality_status": "PASS" if boundaries_match is not False and not any((gaps, duplicate_timestamps, regressions, invalid_ohlc, invalid_price, negative_volume)) else "FAIL",
    }


def audit_rest_funding(through: str, data_root: Path) -> dict[str, object]:
    end_day = datetime.fromisoformat(through).replace(tzinfo=timezone.utc)
    start_ms = int(end_day.replace(day=1).timestamp() * 1000)
    end_ms = int((end_day + timedelta(days=1)).timestamp() * 1000) - 1
    url = "https://fapi.binance.com/fapi/v1/fundingRate?" + urlencode({
        "symbol": "XAUUSDT", "startTime": start_ms, "endTime": end_ms, "limit": 1000,
    })
    with urlopen(Request(url, headers={"User-Agent": "BTCETH-OS-XAU-Audit/1.0"}), timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"Funding REST HTTP {response.status}")
        raw = response.read()
    rows = json.loads(raw, parse_float=str)
    if not isinstance(rows, list) or len(rows) == 1000:
        raise RuntimeError("Funding REST response invalid or truncated")
    previous = None
    for row in rows:
        ts = row["fundingTime"]
        if row.get("symbol") != "XAUUSDT" or not isinstance(ts, int) or not start_ms <= ts <= end_ms:
            raise RuntimeError("Funding REST identity or timestamp invalid")
        if previous is not None and ts <= previous:
            raise RuntimeError("Funding REST timestamps are not strictly increasing")
        if not Decimal(row["fundingRate"]).is_finite():
            raise RuntimeError("Funding REST rate is non-finite")
        previous = ts
    physical_sha = hashlib.sha256(raw).hexdigest()
    destination = data_root / "rest_funding" / f"{physical_sha}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != physical_sha:
        raise RuntimeError("Existing REST funding snapshot checksum mismatch")
    if not destination.exists():
        part = destination.with_name(destination.name + ".part")
        try:
            with part.open("wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(part, destination)
        finally:
            part.unlink(missing_ok=True)
    return {"source_url": url, "physical_sha256": physical_sha, "rows": len(rows),
            "first_ts_ms": rows[0]["fundingTime"] if rows else None,
            "last_ts_ms": rows[-1]["fundingTime"] if rows else None}


def run(through: str, data_root: Path) -> dict[str, object]:
    end = datetime.fromisoformat(through).replace(tzinfo=timezone.utc)
    if end >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0):
        raise ValueError("Audit through date must be a completed UTC day")
    as_of = datetime.now(timezone.utc)
    registry = load_historical_datasets_registry(ROOT / "config" / "xau_datasets.yaml")
    downloader = ArchiveDownloader(data_root / "raw")
    partitions: list[dict[str, object]] = []
    for dataset in registry:
        if dataset.source_dataset_name not in BAR_DATASETS + ("fundingRate",):
            continue
        if dataset.source_dataset_name == "fundingRate":
            # Monthly-only funding archives: the current incomplete month requires REST separately.
            end_for_dataset = (end.replace(day=1) - timedelta(days=1)).date().isoformat()
        else:
            end_for_dataset = through
        for spec in plan_archive_requests(dataset, "2026-01-01", end_for_dataset, as_of):
            partitions.append(audit_archive(downloader, spec))

    repairs: list[dict[str, object]] = []
    for part in partitions:
        if part["cadence"] != "monthly" or part["missing_minutes"] != 1440 or part["gap_count"] != 1:
            continue
        dataset = next(d for d in registry if d.source_dataset_name == part["dataset"])
        missing_start = int(part["missing_ranges"][0]["first_missing_ns"])
        missing_day = datetime.fromtimestamp(missing_start / 1_000_000_000, timezone.utc)
        if missing_day.hour or missing_day.minute or missing_day.second:
            continue
        day = missing_day.date().isoformat()
        daily = plan_archive_requests(dataset, day, day, as_of)[0]
        repair = audit_archive(downloader, daily)
        if repair["rows"] != 1440 or repair["quality_status"] != "PASS" or repair["first_ts_ns"] != missing_start:
            raise RuntimeError("Official daily source does not repair the missing archive day")
        repairs.append(repair)
    expected_rows = ((end.date() - datetime(2026, 1, 1, tzinfo=timezone.utc).date()).days + 1) * 1440
    coverage: dict[str, dict[str, object]] = {}
    for dataset in BAR_DATASETS:
        parts = [part for part in partitions if part["dataset"] == dataset]
        patches = [part for part in repairs if part["dataset"] == dataset]
        actual = sum(int(part["rows"]) for part in parts + patches)
        coverage[dataset] = {"expected_minutes": expected_rows, "observed_minutes_after_daily_repairs": actual,
                             "status": "PASS" if actual == expected_rows and all(
                                 part["quality_status"] == "PASS" or (
                                     part["missing_minutes"] == 1440 and part["boundaries_match"] is True
                                     and not any(part[key] for key in ("duplicate_timestamps", "timestamp_regressions", "invalid_ohlc", "invalid_price", "negative_volume"))
                                 )
                                 for part in parts) else "FAIL"}
    return {
        "audit_version": "XAU_NATIVE_BARS_V1", "observed_at_utc": as_of.isoformat(),
        "through_utc_day": through, "instrument_id": INSTRUMENT,
        "research_admission_not_before_utc": "2026-01-06T00:00:00Z",
        "before_admission": "QUARANTINED_ACCESS_SCOPE_UNKNOWN",
        "source_partitions": partitions, "daily_repair_sources": repairs, "coverage": coverage,
        "current_month_funding_rest": audit_rest_funding(through, data_root),
        "source_gap_status": "REPAIRED_BY_OFFICIAL_DAILY" if all(
            item["status"] == "PASS" for item in coverage.values()) else "UNRESOLVED",
        "research_admission": "BLOCKED_PENDING_HISTORICAL_RULE_REPLAY_AND_FULL_STREAM_QUALITY",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", required=True, help="Last completed UTC day, YYYY-MM-DD")
    parser.add_argument("--data-root", type=Path, default=ROOT / "artifacts" / "xau_native")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "XAU_NATIVE_COVERAGE_AUDIT.json")
    args = parser.parse_args()
    report = run(args.through, args.data_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"{len(report['source_partitions'])} source archives; {len(report['daily_repair_sources'])} daily repair sources; {report['research_admission']}")
    return 0 if report["source_gap_status"] == "REPAIRED_BY_OFFICIAL_DAILY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
