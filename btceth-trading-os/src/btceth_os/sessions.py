"""Historical session semantics for TradFi commodity perpetuals (XAUUSDT).

Separates:
- UnderlyingReferenceSession (underlying gold spot/futures market hours, holidays, and maintenance breaks)
- PerpetualContractSession (Binance 24/7 contract trading availability)

Enforces:
- Distinct clocks: underlying schedule closure does not equal contract closure.
- Gold session states:
  UNDERLYING_OPEN, UNDERLYING_CLOSED, UNDERLYING_OFF_HOURS_INDEX_MODE,
  CONTRACT_TRADING, CONTRACT_MAINTENANCE, UNKNOWN
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any
import zoneinfo

try:
    ET_TZ = zoneinfo.ZoneInfo("America/New_York")
except Exception:
    # Fallback to standard offset if tzdata not available
    ET_TZ = timezone.utc


class GoldSessionState(str, Enum):
    UNDERLYING_OPEN = "UNDERLYING_OPEN"
    UNDERLYING_CLOSED = "UNDERLYING_CLOSED"
    UNDERLYING_OFF_HOURS_INDEX_MODE = "UNDERLYING_OFF_HOURS_INDEX_MODE"
    CONTRACT_TRADING = "CONTRACT_TRADING"
    CONTRACT_MAINTENANCE = "CONTRACT_MAINTENANCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class UnderlyingReferenceSession:
    """Underlying commodity reference schedule.

    Gold market standard hours (CME / LBMA proxy):
    Sunday 18:00 ET to Friday 17:00 ET, with daily maintenance break 17:00 - 18:00 ET.
    """
    calendar_id: str = "COMMODITY_XAU"

    def get_state(self, dt_utc: datetime, price_index_method: str | None = None) -> GoldSessionState:
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        # Convert to Eastern Time
        dt_et = dt_utc.astimezone(ET_TZ)
        weekday = dt_et.weekday()  # Monday=0, ..., Sunday=6

        # Weekend check: Friday 17:00 ET to Sunday 18:00 ET
        if weekday == 4 and dt_et.time() >= time(17, 0):  # Friday after 17:00 ET
            return GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE
        if weekday == 5:  # Saturday
            return GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE
        if weekday == 6 and dt_et.time() < time(18, 0):  # Sunday before 18:00 ET
            return GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE

        # Daily break: 17:00 to 18:00 ET (Monday - Thursday)
        if time(17, 0) <= dt_et.time() < time(18, 0):
            return GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE

        return GoldSessionState.UNDERLYING_OPEN


@dataclass(frozen=True)
class PerpetualContractSession:
    """Binance TradFi Perpetual contract availability.

    Trades 24/7 continuously, including weekends and underlying market holidays.
    """
    instrument_id: str = "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"

    def get_state(self, dt_utc: datetime) -> GoldSessionState:
        # Default perpetual contract state is continuous trading
        return GoldSessionState.CONTRACT_TRADING


@dataclass(frozen=True)
class CombinedSessionSnapshot:
    timestamp_utc: str
    underlying_state: GoldSessionState
    contract_state: GoldSessionState
    is_contract_tradable: bool
    price_index_regime: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "underlying_state": self.underlying_state.value,
            "contract_state": self.contract_state.value,
            "is_contract_tradable": self.is_contract_tradable,
            "price_index_regime": self.price_index_regime,
        }


def evaluate_sessions(
    dt: datetime | str,
    price_index_method: str = "STANDARD_OR_EWMA",
) -> CombinedSessionSnapshot:
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    underlying_session = UnderlyingReferenceSession()
    contract_session = PerpetualContractSession()

    underlying_st = underlying_session.get_state(dt, price_index_method)
    contract_st = contract_session.get_state(dt)

    return CombinedSessionSnapshot(
        timestamp_utc=dt.isoformat(),
        underlying_state=underlying_st,
        contract_state=contract_st,
        is_contract_tradable=(contract_st == GoldSessionState.CONTRACT_TRADING),
        price_index_regime=price_index_method,
    )
