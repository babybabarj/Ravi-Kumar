from __future__ import annotations

import json
import urllib.request
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Sequence

from .schema_inspector import FundingRateRecord


@dataclass(frozen=True)
class RestFundingRateItem:
    symbol: str
    funding_time: int
    funding_rate: Decimal
    raw_payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RestFundingRateItem:
        # Strict mapping for known fields; forward-compatible tolerance for optional fields
        return cls(
            symbol=str(data["symbol"]),
            funding_time=int(data["fundingTime"]),
            funding_rate=Decimal(str(data["fundingRate"])),
            raw_payload=dict(data),  # preserves all fields including markPrice, rateType, etc.
        )


@dataclass(frozen=True)
class ParityMatchItem:
    calc_time: int
    calc_time_utc: str
    archive_rate: Decimal
    rest_rate: Decimal
    status: str  # MATCHED, RATE_MISMATCH


@dataclass(frozen=True)
class FundingParityReport:
    symbol: str
    archive_count: int
    rest_count: int
    matched_count: int
    archive_only_count: int
    rest_only_count: int
    rate_mismatch_count: int
    duplicate_settlement_count: int
    matches: list[dict[str, Any]]
    archive_only_timestamps: list[int]
    rest_only_timestamps: list[int]
    rate_mismatches: list[dict[str, Any]]
    optional_fields_observed: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FundingParityAuditor:
    """Reconciles historical Binance archive funding rates against live REST fundingRate API."""

    @staticmethod
    def parse_rest_response(json_payload: list[dict[str, Any]] | str) -> list[RestFundingRateItem]:
        """Parse REST response with forward-compatible optional field tolerance."""
        if isinstance(json_payload, str):
            items = json.loads(json_payload)
        else:
            items = json_payload

        records = []
        for item in items:
            records.append(RestFundingRateItem.from_dict(item))
        return records

    @staticmethod
    def fetch_live_rest_funding(
        symbol: str,
        limit: int = 100,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> list[RestFundingRateItem]:
        """Fetch live funding rate records from Binance public REST endpoint."""
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "BTCETH-Trading-OS/FundingParity"})
        op = opener or urllib.request.build_opener()
        with op.open(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return FundingParityAuditor.parse_rest_response(data)

    @staticmethod
    def audit_overlap(
        symbol: str,
        archive_records: Sequence[FundingRateRecord],
        rest_records: Sequence[RestFundingRateItem],
    ) -> FundingParityReport:
        """Compares archive records against REST records over their mutual temporal range."""
        archive_by_ts: dict[int, list[FundingRateRecord]] = {}
        for r in archive_records:
            archive_by_ts.setdefault(r.calc_time_raw, []).append(r)

        rest_by_ts: dict[int, list[RestFundingRateItem]] = {}
        optional_fields: set[str] = set()
        for item in rest_records:
            rest_by_ts.setdefault(item.funding_time, []).append(item)
            optional_fields.update(item.raw_payload.keys() - {"symbol", "fundingTime", "fundingRate"})

        duplicate_count = 0
        for ts, recs in archive_by_ts.items():
            if len(recs) > 1:
                duplicate_count += len(recs) - 1
        for ts, items in rest_by_ts.items():
            if len(items) > 1:
                duplicate_count += len(items) - 1

        all_timestamps = sorted(set(archive_by_ts.keys()) | set(rest_by_ts.keys()))
        matched: list[dict[str, Any]] = []
        archive_only: list[int] = []
        rest_only: list[int] = []
        rate_mismatches: list[dict[str, Any]] = []

        for ts in all_timestamps:
            in_arch = ts in archive_by_ts
            in_rest = ts in rest_by_ts

            if in_arch and in_rest:
                arch_r = archive_by_ts[ts][0]
                rest_r = rest_by_ts[ts][0]
                if arch_r.last_funding_rate == rest_r.funding_rate:
                    matched.append({
                        "calc_time": ts,
                        "calc_time_utc": arch_r.calc_time_utc,
                        "funding_rate": str(arch_r.last_funding_rate),
                        "status": "MATCHED",
                    })
                else:
                    rate_mismatches.append({
                        "calc_time": ts,
                        "calc_time_utc": arch_r.calc_time_utc,
                        "archive_rate": str(arch_r.last_funding_rate),
                        "rest_rate": str(rest_r.funding_rate),
                        "diff": str(arch_r.last_funding_rate - rest_r.funding_rate),
                        "status": "RATE_MISMATCH",
                    })
            elif in_arch:
                archive_only.append(ts)
            else:
                rest_only.append(ts)

        return FundingParityReport(
            symbol=symbol,
            archive_count=len(archive_records),
            rest_count=len(rest_records),
            matched_count=len(matched),
            archive_only_count=len(archive_only),
            rest_only_count=len(rest_only),
            rate_mismatch_count=len(rate_mismatches),
            duplicate_settlement_count=duplicate_count,
            matches=matched,
            archive_only_timestamps=archive_only,
            rest_only_timestamps=rest_only,
            rate_mismatches=rate_mismatches,
            optional_fields_observed=sorted(list(optional_fields)),
        )
