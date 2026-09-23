"""Read-only Binance instrument rules with immutable source snapshots."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.request import Request, urlopen

from ...instruments import InstrumentSpec, resolve_instrument


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decimal(value: object | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".part-", delete=False) as handle:
        part = Path(handle.name)
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(part, path)
        finally:
            part.unlink(missing_ok=True)


class InstrumentSpecProvider:
    """Refresh public Binance rules. A refresh never approves a spec for orders."""

    def __init__(self, snapshot_dir: Path) -> None:
        self.snapshot_dir = Path(snapshot_dir)

    def _fetch(self, url: str) -> bytes:
        with urlopen(Request(url, headers={"User-Agent": "TradingOS-ReadOnly-Research/1.0"}), timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"Exchange metadata HTTP {response.status}: {url}")
            return response.read()

    def _snapshot(self, url: str) -> tuple[object, dict[str, object]]:
        raw = self._fetch(url)
        parsed = json.loads(raw, parse_float=str)
        physical_sha = _sha(raw)
        receipt = {
            "source_endpoint": url,
            "retrieved_at_ns": time.time_ns(),
            "physical_sha256": physical_sha,
            "logical_sha256": _sha(_json_bytes(parsed)),
            "raw_file": f"raw/{physical_sha}.json",
        }
        raw_path = self.snapshot_dir / str(receipt["raw_file"])
        if raw_path.exists():
            if _sha(raw_path.read_bytes()) != physical_sha:
                raise RuntimeError(f"Existing raw snapshot has wrong SHA: {raw_path}")
        else:
            _atomic_write(raw_path, raw)
        return parsed, receipt

    def refresh(self, instrument: str) -> InstrumentSpec:
        instrument_id = resolve_instrument(instrument)
        _, product_family, symbol = instrument_id.split(":")
        is_spot = product_family == "SPOT"
        is_xau = product_family == "TRADFI_COMMODITY_PERP"
        base = "https://api.binance.com" if is_spot else "https://fapi.binance.com"
        endpoint = f"/api/v3/exchangeInfo?symbol={symbol}" if is_spot else "/fapi/v1/exchangeInfo"
        exchange_info, exchange_receipt = self._snapshot(base + endpoint)
        if not isinstance(exchange_info, dict):
            raise RuntimeError("EXCHANGE_INFO_INVALID")
        matches = [row for row in exchange_info.get("symbols", []) if row.get("symbol") == symbol]
        if len(matches) != 1:
            raise RuntimeError(f"EXCHANGE_SYMBOL_MISSING_OR_DUPLICATE: {symbol}")
        row = matches[0]
        filters = {item["filterType"]: item for item in row.get("filters", [])}
        if "PRICE_FILTER" not in filters or "LOT_SIZE" not in filters:
            raise RuntimeError(f"EXCHANGE_FILTERS_INCOMPLETE: {symbol}")
        if is_xau and (row.get("contractType") != "TRADIFI_PERPETUAL" or row.get("underlyingType") != "COMMODITY"):
            raise RuntimeError("XAU_PRODUCT_IDENTITY_MISMATCH")
        receipts = [exchange_receipt]
        funding = None
        if not is_spot:
            funding_info, funding_receipt = self._snapshot(base + "/fapi/v1/fundingInfo")
            receipts.append(funding_receipt)
            funding_matches = [item for item in funding_info if item.get("symbol") == symbol]
            if len(funding_matches) > 1:
                raise RuntimeError(f"DUPLICATE_FUNDING_RULE: {symbol}")
            funding = funding_matches[0] if funding_matches else None
            if is_xau and funding is None:
                raise RuntimeError("XAU_FUNDING_RULE_UNKNOWN")
        if is_xau:
            schedule, schedule_receipt = self._snapshot(base + "/fapi/v1/tradingSchedule")
            receipts.append(schedule_receipt)
            sessions = schedule.get("marketSchedules", {}).get("COMMODITY", {}).get("sessions", [])
            if not sessions:
                raise RuntimeError("XAU_COMMODITY_SCHEDULE_UNKNOWN")
            premium, premium_receipt = self._snapshot(base + f"/fapi/v1/premiumIndex?symbol={symbol}")
            receipts.append(premium_receipt)
            if premium.get("symbol") != symbol or not premium.get("markPrice") or not premium.get("indexPrice"):
                raise RuntimeError("XAU_MARK_INDEX_UNAVAILABLE")
        price_filter = filters["PRICE_FILTER"]
        lot_filter = filters["LOT_SIZE"]
        notional_filter = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
        retrieved_at_ns = time.time_ns()
        spec = InstrumentSpec(
            instrument_id=instrument_id,
            venue="BINANCE",
            symbol=symbol,
            base_asset=row["baseAsset"],
            quote_asset=row["quoteAsset"],
            settlement_asset=row.get("marginAsset", row["quoteAsset"]),
            product_family=product_family,
            market_type="SPOT" if is_spot else "PERPETUAL",
            contract_type="NONE" if is_spot else row["contractType"],
            underlying_type="CRYPTO" if is_spot else row["underlyingType"],
            tradfi_asset_class=row["underlyingType"] if is_xau else None,
            listing_ts=None,  # onboardDate is not proof of first executable trading.
            status=row["status"],
            price_precision=row.get("quotePrecision") if is_spot else row.get("pricePrecision"),
            quantity_precision=row.get("baseAssetPrecision") if is_spot else row.get("quantityPrecision"),
            tick_size=_decimal(price_filter.get("tickSize")),
            step_size=_decimal(lot_filter.get("stepSize")),
            min_qty=_decimal(lot_filter.get("minQty")),
            max_qty=_decimal(lot_filter.get("maxQty")),
            min_notional=_decimal(notional_filter.get("minNotional", notional_filter.get("notional"))),
            max_notional=_decimal(notional_filter.get("maxNotional")),
            contract_size=_decimal(row.get("contractSize")),
            funding_enabled=not is_spot,
            current_funding_interval=int(funding["fundingIntervalHours"]) * 3600 if funding else None,
            leverage_supported=not is_spot,
            exchange_max_leverage=None,  # Account-specific leverage brackets require separate verification.
            session_calendar_id="BINANCE:COMMODITY" if is_xau else None,
            price_index_type=None,
            mark_price_type=None,
            api_segment="spot" if is_spot else "usdm",
            exchange_info_snapshot_sha=str(exchange_receipt["physical_sha256"]),
            effective_from_ts=retrieved_at_ns,
            retrieved_at_ts=retrieved_at_ns,
        )
        rules = {"exchange_symbol": row, "funding_adjustment": funding}
        rules_logical_sha = _sha(_json_bytes(rules))
        spec_data = {
            key: format(value, "f") if isinstance(value, Decimal) else value
            for key, value in asdict(spec).items()
        }
        snapshot = {
            "instrument_id": instrument_id,
            "retrieved_at_ns": retrieved_at_ns,
            "source_snapshots": receipts,
            "rules_logical_sha256": rules_logical_sha,
            "parsed_instrument_spec": spec_data,
            "execution_approval": "NOT_ACCEPTED",
        }
        filename = f"{instrument_id.replace(':', '_')}-{retrieved_at_ns}.json"
        _atomic_write(self.snapshot_dir / "specs" / filename, json.dumps(snapshot, indent=2, sort_keys=True).encode() + b"\n")
        return spec
