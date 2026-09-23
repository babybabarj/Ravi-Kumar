"""Reconcile official XAU trade IDs with aggregate trade constituent IDs."""

from __future__ import annotations

import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

BASE = "https://data.binance.vision/data/futures/um/daily"
DAY = "2026-05-15"


def official_rows(kind: str, day: str) -> tuple[list[list[str]], dict[str, str]]:
    name = f"XAUUSDT-{kind}-{day}.zip"
    url = f"{BASE}/{kind}/XAUUSDT/{name}"
    with urllib.request.urlopen(url + ".CHECKSUM", timeout=30) as response:
        expected = response.read().decode().split()[0].lower()
    with urllib.request.urlopen(url, timeout=120) as response:
        payload = response.read()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"Official checksum mismatch: {url}")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        with archive.open(archive.namelist()[0]) as member:
            rows = list(csv.reader(io.TextIOWrapper(member, encoding="utf-8")))
    return rows[1:], {"url": url, "physical_sha256": actual}


def reconcile(trades: list[list[str]], aggregate: list[list[str]]) -> dict[str, object]:
    trade_qty = {int(row[0]): Decimal(row[2]) for row in trades}
    if len(trade_qty) != len(trades):
        raise ValueError("Duplicate trade IDs")
    covered: set[int] = set()
    aggregate_volume = Decimal(0)
    previous_agg_id = None
    quantity_mismatches = 0
    for row in aggregate:
        agg_id, first_id, last_id = int(row[0]), int(row[3]), int(row[4])
        if previous_agg_id is not None and agg_id != previous_agg_id + 1:
            raise ValueError("Aggregate ID gap")
        previous_agg_id = agg_id
        ids = range(first_id, last_id + 1)
        if any(i in covered for i in ids):
            raise ValueError("Overlapping aggregate constituent IDs")
        covered.update(ids)
        qty = Decimal(row[2])
        aggregate_volume += qty
        if all(i in trade_qty for i in ids) and sum((trade_qty[i] for i in ids), Decimal(0)) != qty:
            quantity_mismatches += 1
    missing = sorted(trade_qty.keys() - covered)
    missing_volume = sum((trade_qty[i] for i in missing), Decimal(0))
    trade_volume = sum(trade_qty.values(), Decimal(0))
    exact_covered = quantity_mismatches == 0 and trade_volume == aggregate_volume + missing_volume
    return {
        "trade_count": len(trades), "aggregate_count": len(aggregate),
        "trades_volume": str(trade_volume), "aggregate_volume": str(aggregate_volume),
        "uncovered_trade_count": len(missing), "uncovered_trade_volume": str(missing_volume),
        "uncovered_first_trade_id": missing[0] if missing else None,
        "uncovered_last_trade_id": missing[-1] if missing else None,
        "aggregate_group_quantity_mismatches": quantity_mismatches,
        "covered_constituent_exact": exact_covered,
        "calendar_day_volume_exact": trade_volume == aggregate_volume,
        "policy": "SOURCE_SEMANTICALLY_CONSISTENT" if exact_covered else "FAILED",
        "uncovered_trade_subtype": "UNKNOWN",
    }


def monthly_may15_summary() -> dict[str, object]:
    url = "https://data.binance.vision/data/futures/um/monthly/aggTrades/XAUUSDT/XAUUSDT-aggTrades-2026-05.zip"
    with urllib.request.urlopen(url + ".CHECKSUM", timeout=30) as response:
        expected = response.read().decode().split()[0].lower()
    with urllib.request.urlopen(url, timeout=180) as response:
        raw = response.read()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError("Monthly May aggregate archive checksum mismatch")
    rows = 0
    volume = Decimal(0)
    first = last = None
    start_ms, end_ms = 1778803200000, 1778889600000
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        with archive.open(archive.namelist()[0]) as member:
            reader = csv.reader(io.TextIOWrapper(member, encoding="utf-8"))
            next(reader)
            for row in reader:
                if start_ms <= int(row[5]) < end_ms:
                    rows += 1
                    volume += Decimal(row[2])
                    first = first or row
                    last = row
    return {"url": url, "physical_sha256": actual, "may15_rows": rows,
            "may15_volume": str(volume), "first_agg_id": int(first[0]), "last_agg_id": int(last[0])}


def main() -> int:
    trades, trade_source = official_rows("trades", DAY)
    agg, agg_source = official_rows("aggTrades", DAY)
    previous, previous_source = official_rows("aggTrades", "2026-05-14")
    following, following_source = official_rows("aggTrades", "2026-05-16")
    result = reconcile(trades, agg)
    boundaries = {
        "previous_day_last_agg_id": int(previous[-1][0]),
        "may15_first_agg_id": int(agg[0][0]),
        "may15_last_agg_id": int(agg[-1][0]),
        "following_day_first_agg_id": int(following[0][0]),
        "agg_ids_continuous_across_days": int(previous[-1][0]) + 1 == int(agg[0][0])
        and int(agg[-1][0]) + 1 == int(following[0][0]),
        "previous_day_last_constituent_trade_id": int(previous[-1][4]),
        "may15_first_trade_id": int(trades[0][0]),
        "may15_last_trade_id": int(trades[-1][0]),
        "following_day_first_constituent_trade_id": int(following[0][3]),
        "trade_ids_continuous_across_days": int(previous[-1][4]) + 1 == int(trades[0][0])
        and int(trades[-1][0]) + 1 == int(following[0][3]),
        "first_trade_timestamp_ms": int(trades[0][4]),
        "last_trade_timestamp_ms": int(trades[-1][4]),
        "first_aggregate_timestamp_ms": int(agg[0][5]),
        "last_aggregate_timestamp_ms": int(agg[-1][5]),
    }
    result["boundary_analysis"] = boundaries
    result["neighbor_sources"] = [previous_source, following_source]
    monthly = monthly_may15_summary()
    result["monthly_archive_comparison"] = monthly
    result["monthly_daily_match"] = (
        monthly["may15_rows"] == len(agg)
        and Decimal(monthly["may15_volume"]) == Decimal(result["aggregate_volume"])
        and monthly["first_agg_id"] == int(agg[0][0])
        and monthly["last_agg_id"] == int(agg[-1][0])
    )
    if not boundaries["agg_ids_continuous_across_days"] or not boundaries["trade_ids_continuous_across_days"]:
        result["policy"] = "FAILED"
    if not result["monthly_daily_match"]:
        result["policy"] = "FAILED"
    result.update({"benchmark_day": DAY, "trades_source": trade_source, "aggtrades_source": agg_source,
                   "source_semantics_url": "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data",
                   "explanation": "Binance documents aggregate trades as market trades only. The exact subtype of uncovered archival trades is not exposed by these CSVs."})
    path = Path(__file__).resolve().parents[1] / "reports" / "XAU_AGGTRADE_RECONCILIATION_V16.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["policy"] == "SOURCE_SEMANTICALLY_CONSISTENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
