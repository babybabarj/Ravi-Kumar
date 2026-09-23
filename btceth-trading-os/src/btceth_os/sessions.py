"""Historical session semantics for TradFi commodity perpetuals (XAUUSDT).

Separates:
- UnderlyingReferenceSession (underlying gold spot/futures market hours, holidays, and maintenance breaks)
- PerpetualContractSession (Binance 24/7 contract trading availability)

Enforces:
- Distinct clocks: underlying schedule closure does not equal contract closure.
- Gold session states:
  UNDERLYING_OPEN, UNDERLYING_CLOSED, UNDERLYING_OFF_HOURS_INDEX_MODE,
  CONTRACT_TRADING, CONTRACT_MAINTENANCE, UNKNOWN
- Fail-closed timezone: requires genuine America/New_York zoneinfo without silent UTC fallback.
- Epoch-aware session policies: pre-September 17:00-18:00 ET daily break vs September 15+ continuous trading.
- Explicit holiday status decoupling: unverified holidays marked NOT_IMPLEMENTED / UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any
import zoneinfo


class SessionTimezoneUnavailableError(RuntimeError):
    """Raised when America/New_York timezone information is not available."""
    pass


try:
    ET_TZ = zoneinfo.ZoneInfo("America/New_York")
except Exception as exc:
    raise SessionTimezoneUnavailableError(f"America/New_York timezone unavailable: {exc}") from exc


class GoldSessionState(str, Enum):
    UNDERLYING_OPEN = "UNDERLYING_OPEN"
    UNDERLYING_CLOSED = "UNDERLYING_CLOSED"
    UNDERLYING_OFF_HOURS_INDEX_MODE = "UNDERLYING_OFF_HOURS_INDEX_MODE"
    CONTRACT_TRADING = "CONTRACT_TRADING"
    CONTRACT_MAINTENANCE = "CONTRACT_MAINTENANCE"
    UNKNOWN = "UNKNOWN"


class HolidayStatus(str, Enum):
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNKNOWN = "UNKNOWN"
    PROVEN_CLOSED = "PROVEN_CLOSED"


# September 15, 2026 21:00 UTC regime switch point
SEP_REGIME_START_UTC = datetime(2026, 9, 15, 21, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class UnderlyingReferenceSession:
    """Underlying commodity reference schedule.

    Gold market standard hours (CME / LBMA proxy):
    - Prior to Epoch 6: Sunday 18:00 ET to Friday 17:00 ET, with daily maintenance break 17:00 - 18:00 ET.
    - Epoch 6 (2026-09-15 21:00 UTC onward): Continuous Sunday 18:00 ET to Friday 17:00 ET without daily break.
    """
    calendar_id: str = "COMMODITY_XAU"
    has_daily_break: bool = True

    def get_holiday_status(self, dt: datetime | str) -> HolidayStatus:
        """Explicit stance on holiday verification: fail closed as NOT_IMPLEMENTED."""
        return HolidayStatus.NOT_IMPLEMENTED

    def get_state(self, dt_utc: datetime | str, price_index_method: str | None = None) -> GoldSessionState:
        if isinstance(dt_utc, str):
            dt_utc = datetime.fromisoformat(dt_utc)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        # Convert to Eastern Time with fail-closed guarantee
        try:
            et_tz = zoneinfo.ZoneInfo("America/New_York")
        except Exception as exc:
            raise SessionTimezoneUnavailableError(f"FAIL CLOSED: America/New_York timezone unavailable: {exc}") from exc

        dt_et = dt_utc.astimezone(et_tz)
        weekday = dt_et.weekday()  # Monday=0, ..., Sunday=6

        # Weekend check: Friday 17:00 ET to Sunday 18:00 ET
        if weekday == 4 and dt_et.time() >= time(17, 0):  # Friday after 17:00 ET
            return GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE
        if weekday == 5:  # Saturday
            return GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE
        if weekday == 6 and dt_et.time() < time(18, 0):  # Sunday before 18:00 ET
            return GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE

        # Daily break: 17:00 to 18:00 ET (Monday - Thursday) if policy has daily break
        if self.has_daily_break and (time(17, 0) <= dt_et.time() < time(18, 0)):
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
    holiday_status: str = HolidayStatus.NOT_IMPLEMENTED.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "underlying_state": self.underlying_state.value,
            "contract_state": self.contract_state.value,
            "is_contract_tradable": self.is_contract_tradable,
            "price_index_regime": self.price_index_regime,
            "holiday_status": self.holiday_status,
        }


def evaluate_sessions(
    dt: datetime | str,
    price_index_method: str = "STANDARD_OR_EWMA",
    epoch_id: str | None = None,
) -> CombinedSessionSnapshot:
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    # Determine whether daily break applies
    is_epoch6 = (epoch_id == "XAU_EPOCH_6_ET_SESSION_CALENDAR_REGIME") or (dt >= SEP_REGIME_START_UTC)
    has_daily_break = not is_epoch6

    underlying_session = UnderlyingReferenceSession(has_daily_break=has_daily_break)
    contract_session = PerpetualContractSession()

    underlying_st = underlying_session.get_state(dt, price_index_method)
    contract_st = contract_session.get_state(dt)

    return CombinedSessionSnapshot(
        timestamp_utc=dt.isoformat(),
        underlying_state=underlying_st,
        contract_state=contract_st,
        is_contract_tradable=(contract_st == GoldSessionState.CONTRACT_TRADING),
        price_index_regime=price_index_method,
        holiday_status=HolidayStatus.NOT_IMPLEMENTED.value,
    )
