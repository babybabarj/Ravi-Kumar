from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ...quality.contracts import FinancialDecimal, resolve_spot_timestamp
from ...core import ns_from_source_timestamp
from .models import ArchiveObjectSpec


class ArchiveSchemaError(ValueError):
    """An archive member has an unknown header, shape, or timestamp representation."""


@dataclass(frozen=True)
class BronzeRecord:
    dataset_id: str
    instrument_id: str
    source_dataset_name: str
    source_member: str
    row_number: int
    ts_event_ns: int
    source_ts_raw: int
    source_ts_unit: str
    source_precision: str
    values: dict[str, str | int | bool]


KLINE_HEADER = (
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
)
FUNDING_HEADER = ("calc_time", "funding_interval_hours", "last_funding_rate")
TRADE_HEADER = ("id", "price", "qty", "quote_qty", "time", "is_buyer_maker", "is_best_match")
USDM_TRADE_HEADER = TRADE_HEADER[:-1]
AGG_TRADE_HEADER = ("agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker")


def iter_bronze_records(path: Path | str, spec: ArchiveObjectSpec) -> Iterator[BronzeRecord]:
    """Strictly stream one CSV member from a checksum-verified RAW ZIP object.

    Values remain strings or integers; callers must never receive binary floats.
    """
    archive_path = Path(path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            if len(members) != 1:
                raise ArchiveSchemaError(f"expected exactly one CSV member, found {members!r}")
            member = members[0]
            if not member.lower().endswith(".csv"):
                raise ArchiveSchemaError(f"expected CSV member, got {member!r}")
            with archive.open(member) as binary, io.TextIOWrapper(binary, encoding="utf-8", newline="") as text:
                rows = csv.reader(text)
                first = next(rows, None)
                if first is None:
                    raise ArchiveSchemaError("archive CSV is empty")
                header, pending = _header_or_first_row(first, spec.source_dataset_name, spec.market)
                row_number = 1 if pending is None else 0
                if pending is not None:
                    row_number += 1
                    yield _parse_row(pending, header, spec, member, row_number)
                for row in rows:
                    row_number += 1
                    yield _parse_row(row, header, spec, member, row_number)
    except zipfile.BadZipFile as exc:
        raise ArchiveSchemaError("RAW object is not a valid ZIP archive") from exc


def _header_or_first_row(first: list[str], dataset: str, market: str) -> tuple[tuple[str, ...], list[str] | None]:
    if first and first[0].lstrip("-").isdigit():
        return _default_header(dataset, market), first
    normalized = tuple(_normalize(column) for column in first)
    expected = _default_header(dataset, market)
    if normalized != expected:
        raise ArchiveSchemaError(f"unexpected {dataset!r} header: {first!r}")
    return expected, None


def _default_header(dataset: str, market: str) -> tuple[str, ...]:
    if dataset in {"klines", "markPriceKlines", "indexPriceKlines", "premiumIndexKlines"}:
        return KLINE_HEADER
    if dataset == "fundingRate":
        return FUNDING_HEADER
    if dataset == "trades":
        return TRADE_HEADER if market == "spot" else USDM_TRADE_HEADER
    if dataset == "aggTrades":
        return AGG_TRADE_HEADER
    raise ArchiveSchemaError(f"unsupported Binance source dataset {dataset!r}")


def _normalize(value: str) -> str:
    aliases = {
        "trade_id": "id", "tradeid": "id", "quoteqty": "quote_qty", "quote_quantity": "quote_qty",
        "isbuyermaker": "is_buyer_maker", "isbestmatch": "is_best_match",
        "aggregate_trade_id": "agg_trade_id", "aggtradeid": "agg_trade_id",
        "first_trade_id": "first_trade_id", "last_trade_id": "last_trade_id",
        "transact_time": "transact_time", "time": "time", "quantity": "quantity",
        "quote_asset_volume": "quote_volume", "number_of_trades": "count",
        "taker_buy_base_asset_volume": "taker_buy_volume",
        "taker_buy_quote_asset_volume": "taker_buy_quote_volume",
    }
    compact = value.strip().lower().replace(" ", "_")
    return aliases.get(compact, compact)


def _parse_row(row: list[str], header: tuple[str, ...], spec: ArchiveObjectSpec, member: str, row_number: int) -> BronzeRecord:
    if len(row) != len(header) or any(value == "" for value in row):
        raise ArchiveSchemaError(f"row {row_number} has {len(row)} fields; expected {len(header)} non-empty fields")
    values: dict[str, str | int | bool] = dict(zip(header, row, strict=True))
    timestamp_key = "calc_time" if spec.source_dataset_name == "fundingRate" else ("transact_time" if spec.source_dataset_name == "aggTrades" else ("time" if spec.source_dataset_name == "trades" else "open_time"))
    raw_ts = _integer(values[timestamp_key], timestamp_key, row_number)
    event_ns, unit = _event_time(spec, raw_ts)
    for key in _decimal_fields(spec.source_dataset_name):
        FinancialDecimal.parse(str(values[key]))
    for key in _integer_fields(spec.source_dataset_name):
        values[key] = _integer(values[key], key, row_number)
    for key in ("is_buyer_maker", "is_best_match"):
        if key in values:
            values[key] = _boolean(values[key], key, row_number)
    return BronzeRecord(
        dataset_id=spec.dataset_id, instrument_id=spec.instrument, source_dataset_name=spec.source_dataset_name,
        source_member=member, row_number=row_number, ts_event_ns=event_ns, source_ts_raw=raw_ts,
        source_ts_unit=unit, source_precision=unit, values=values,
    )


def _event_time(spec: ArchiveObjectSpec, raw_ts: int) -> tuple[int, str]:
    if spec.market == "spot":
        return resolve_spot_timestamp(raw_ts)
    return ns_from_source_timestamp(raw_ts, "ms"), "ms"  # type: ignore[return-value]


def _integer(value: str | int | bool, field: str, row_number: int) -> int:
    try:
        return int(str(value))
    except ValueError as exc:
        raise ArchiveSchemaError(f"row {row_number} field {field!r} is not an integer: {value!r}") from exc


def _boolean(value: str | int | bool, field: str, row_number: int) -> bool:
    if str(value).lower() in {"true", "1"}:
        return True
    if str(value).lower() in {"false", "0"}:
        return False
    raise ArchiveSchemaError(f"row {row_number} field {field!r} is not a boolean: {value!r}")


def _decimal_fields(dataset: str) -> tuple[str, ...]:
    if dataset == "fundingRate":
        return ("last_funding_rate",)
    if dataset == "trades":
        return ("price", "qty", "quote_qty")
    if dataset == "aggTrades":
        return ("price", "quantity")
    return ("open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "taker_buy_quote_volume")


def _integer_fields(dataset: str) -> tuple[str, ...]:
    if dataset == "fundingRate":
        return ("calc_time", "funding_interval_hours")
    if dataset == "trades":
        return ("id", "time")
    if dataset == "aggTrades":
        return ("agg_trade_id", "first_trade_id", "last_trade_id", "transact_time")
    return ("open_time", "close_time", "count", "ignore")
