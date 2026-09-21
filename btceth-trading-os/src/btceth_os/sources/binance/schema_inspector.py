from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Sequence


class SchemaInspectionError(ValueError):
    """Raised when CSV structure or semantic constraints are violated."""
    pass


class FundingParserCatastrophicError(SchemaInspectionError):
    """Raised when funding rate is confused with funding interval or corrupted."""
    pass


# Canonical schemas
KLINES_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]

TRADES_COLUMNS = [
    "trade_id",
    "price",
    "qty",
    "quote_qty",
    "time",
    "is_buyer_maker",
    "is_best_match",
]

AGG_TRADES_COLUMNS = [
    "agg_trade_id",
    "price",
    "qty",
    "first_trade_id",
    "last_trade_id",
    "time",
    "is_buyer_maker",
    "is_best_match",
]

FUNDING_RATE_COLUMNS = [
    "calc_time",
    "funding_interval_hours",
    "last_funding_rate",
]


@dataclass(frozen=True)
class QualityProbeResult:
    row_count: int
    header_detected: bool
    first_timestamp_raw: int | None
    first_timestamp_utc: str | None
    last_timestamp_raw: int | None
    last_timestamp_utc: str | None
    is_monotonic: bool
    duplicate_timestamp_count: int
    malformed_row_count: int
    column_count_violations: int
    price_violations: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FundingRateRecord:
    calc_time_raw: int
    calc_time_utc: str
    funding_interval_hours: int
    last_funding_rate: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "calc_time_raw": self.calc_time_raw,
            "calc_time_utc": self.calc_time_utc,
            "funding_interval_hours": self.funding_interval_hours,
            "last_funding_rate": str(self.last_funding_rate),
        }


def normalize_timestamp(raw_ts: int, expected_unit: str) -> tuple[int, str]:
    """Normalize raw timestamp to unix milliseconds and UTC ISO-8601 string.
    
    Validates declared unit:
    - 'ms': expects ~13 digits (milliseconds)
    - 'us': expects ~16 digits (microseconds)
    """
    if expected_unit == "ms":
        if raw_ts > 9999999999999:  # > 13 digits
            raise SchemaInspectionError(f"Timestamp {raw_ts} has >13 digits but declared unit is 'ms'")
        unix_ms = raw_ts
    elif expected_unit == "us":
        if raw_ts < 1000000000000000:  # < 16 digits
            raise SchemaInspectionError(f"Timestamp {raw_ts} has <16 digits but declared unit is 'us'")
        unix_ms = raw_ts // 1000
    else:
        raise SchemaInspectionError(f"Unknown timestamp unit: {expected_unit}")

    dt = datetime.fromtimestamp(unix_ms / 1000.0, tz=timezone.utc)
    return unix_ms, dt.isoformat()


class SchemaInspector:
    """Inspects raw CSV archives, performs semantic schema mapping and quality probes."""

    @staticmethod
    def detect_header(sample_line: str) -> bool:
        """Determines if the first line is a header by testing if tokens are non-numeric."""
        tokens = [t.strip() for t in sample_line.split(",")]
        if not tokens:
            return False
        first = tokens[0].lower()
        if any(h in first for h in ["open_time", "time", "trade_id", "agg_trade_id", "calc_time", "id"]):
            return True
        try:
            float(tokens[0])
            return False
        except ValueError:
            return True

    @staticmethod
    def parse_funding_rate_csv(
        content: str | Path,
        strict_catastrophic_check: bool = True,
    ) -> list[FundingRateRecord]:
        """Strict semantic parser for Binance USD-M fundingRate monthly archives.
        
        Mandatory safety invariant:
        `funding_interval_hours` (e.g. 8) must NEVER be returned as `last_funding_rate`!
        """
        if isinstance(content, Path):
            text = content.read_text(encoding="utf-8", errors="replace")
        else:
            text = content

        reader = csv.reader(io.StringIO(text))
        first_row = next(reader, None)
        if not first_row:
            return []

        # Determine header indices
        header_map = {}
        if SchemaInspector.detect_header(",".join(first_row)):
            headers = [h.strip().lower() for h in first_row]
            header_map = {name: idx for idx, name in enumerate(headers)}
            data_rows = reader
        else:
            # Headerless fallback by standard 3-column format
            header_map = {"calc_time": 0, "funding_interval_hours": 1, "last_funding_rate": 2}
            data_rows = [first_row, *reader]

        if "calc_time" not in header_map or "funding_interval_hours" not in header_map or "last_funding_rate" not in header_map:
            raise SchemaInspectionError(f"Missing required funding rate headers in: {first_row}")

        time_idx = header_map["calc_time"]
        interval_idx = header_map["funding_interval_hours"]
        rate_idx = header_map["last_funding_rate"]

        # Catastrophic trap check: Ensure column indices are strictly distinct
        if interval_idx == rate_idx:
            raise FundingParserCatastrophicError("CRITICAL: interval_idx == rate_idx in funding parser mapping!")

        records: list[FundingRateRecord] = []
        for line_num, row in enumerate(data_rows, start=2):
            if not row or not any(row):
                continue
            if len(row) < 3:
                raise SchemaInspectionError(f"Row {line_num} has insufficient columns ({len(row)}): {row}")

            try:
                calc_time_raw = int(row[time_idx].strip())
                interval = int(row[interval_idx].strip())
                rate = Decimal(row[rate_idx].strip())
            except (ValueError, InvalidOperation) as e:
                raise SchemaInspectionError(f"Row {line_num} malformed types: {row} - {e}") from e

            # CATASTROPHIC REGRESSION CHECK:
            # A funding rate of 8 (or integer hours) is absurd and indicates column confusion
            if strict_catastrophic_check:
                if rate == Decimal(interval) and interval in (4, 8):
                    raise FundingParserCatastrophicError(
                        f"CATASTROPHIC PARSER DEFECT DETECTED on line {line_num}: "
                        f"last_funding_rate ({rate}) equals funding_interval_hours ({interval})!"
                    )
                if abs(rate) > Decimal("0.1"):  # Absolute funding rate > 10% per interval is impossible
                    raise FundingParserCatastrophicError(
                        f"CATASTROPHIC PARSER DEFECT DETECTED on line {line_num}: "
                        f"last_funding_rate magnitude {rate} exceeds maximum reasonable bound (0.1)!"
                    )

            _, utc_str = normalize_timestamp(calc_time_raw, "ms")
            records.append(
                FundingRateRecord(
                    calc_time_raw=calc_time_raw,
                    calc_time_utc=utc_str,
                    funding_interval_hours=interval,
                    last_funding_rate=rate,
                )
            )

        return records

    @staticmethod
    def run_quality_probe(
        csv_path: Path,
        dataset_name: str,
        expected_unit: str = "ms",
    ) -> QualityProbeResult:
        """Non-destructive data quality probe calculating row counts, timestamp monotonicity, and anomalies."""
        csv_path = Path(csv_path)
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            first_row = next(reader, None)
            if not first_row:
                return QualityProbeResult(
                    row_count=0,
                    header_detected=False,
                    first_timestamp_raw=None,
                    first_timestamp_utc=None,
                    last_timestamp_raw=None,
                    last_timestamp_utc=None,
                    is_monotonic=True,
                    duplicate_timestamp_count=0,
                    malformed_row_count=0,
                    column_count_violations=0,
                    price_violations=0,
                )

            header_detected = SchemaInspector.detect_header(",".join(first_row))
            if header_detected:
                expected_cols = len(first_row)
                rows_iter = reader
            else:
                expected_cols = len(first_row)
                rows_iter = [first_row, *reader]

            name_lower = dataset_name.lower().replace("-", "_")
            header_tokens = [h.strip().lower() for h in first_row] if header_detected else []
            if "premium" in name_lower:
                ts_idx = 0 if not header_detected else (header_tokens.index("open_time") if "open_time" in header_tokens else 0)
                price_idx = None  # Premium index rates are signed spreads and legitimately can be negative
            elif header_detected:
                header_tokens = [h.strip().lower() for h in first_row]
                if "calc_time" in header_tokens:
                    ts_idx = header_tokens.index("calc_time")
                    price_idx = None
                elif "open_time" in header_tokens:
                    ts_idx = header_tokens.index("open_time")
                    price_idx = header_tokens.index("open") if "open" in header_tokens else 1
                elif "transact_time" in header_tokens:
                    ts_idx = header_tokens.index("transact_time")
                    price_idx = header_tokens.index("price") if "price" in header_tokens else 1
                elif "time" in header_tokens:
                    ts_idx = header_tokens.index("time")
                    price_idx = header_tokens.index("price") if "price" in header_tokens else 1
                else:
                    ts_idx = 0
                    price_idx = 1
            elif "funding" in name_lower:
                ts_idx = 0
                price_idx = None
            elif "agg" in name_lower:
                ts_idx = 5
                price_idx = 1
            elif "trade" in name_lower:
                ts_idx = 4
                price_idx = 1
            elif "kline" in name_lower:
                ts_idx = 0
                price_idx = 1  # open price
            else:
                ts_idx = 0
                price_idx = 1

            row_count = 0
            first_ts: int | None = None
            last_ts: int | None = None
            prev_ts: int | None = None
            is_monotonic = True
            dup_count = 0
            malformed_count = 0
            col_violations = 0
            price_violations = 0

            for row in rows_iter:
                if not row or not any(row):
                    continue
                row_count += 1
                if len(row) != expected_cols:
                    col_violations += 1

                if ts_idx < len(row):
                    try:
                        ts = int(row[ts_idx].strip())
                        if first_ts is None:
                            first_ts = ts
                        if prev_ts is not None:
                            if ts < prev_ts:
                                is_monotonic = False
                            elif ts == prev_ts:
                                dup_count += 1
                        prev_ts = ts
                        last_ts = ts
                    except ValueError:
                        malformed_count += 1

                if price_idx is not None and price_idx < len(row):
                    try:
                        p = float(row[price_idx].strip())
                        if p <= 0:
                            price_violations += 1
                    except ValueError:
                        pass

            try:
                first_utc = normalize_timestamp(first_ts, expected_unit)[1] if first_ts is not None else None
            except SchemaInspectionError:
                first_utc = None

            try:
                last_utc = normalize_timestamp(last_ts, expected_unit)[1] if last_ts is not None else None
            except SchemaInspectionError:
                last_utc = None

            return QualityProbeResult(
                row_count=row_count,
                header_detected=header_detected,
                first_timestamp_raw=first_ts,
                first_timestamp_utc=first_utc,
                last_timestamp_raw=last_ts,
                last_timestamp_utc=last_utc,
                is_monotonic=is_monotonic,
                duplicate_timestamp_count=dup_count,
                malformed_row_count=malformed_count,
                column_count_violations=col_violations,
                price_violations=price_violations,
            )
