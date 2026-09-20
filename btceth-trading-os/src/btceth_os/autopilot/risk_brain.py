from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .strategy_registry import StrategyIntent


BPS = Decimal("10000")
ONE = Decimal("1")


@dataclass(frozen=True)
class RiskBrainConfig:
    starting_equity: Decimal = Decimal("1000")
    max_risk_per_trade_bps: Decimal = Decimal("100")  # 1.00%
    max_btc_exposure_usd: Decimal = Decimal("2000")
    max_eth_exposure_usd: Decimal = Decimal("1000")
    max_combined_crypto_exposure_usd: Decimal = Decimal("2500")
    max_daily_loss_pct: Decimal = Decimal("0.05")  # 5.00%
    max_drawdown_pct: Decimal = Decimal("0.10")    # 10.00%
    max_concurrent_positions: int = 2
    max_data_age_ns: int = 60_000_000_000          # 60s
    min_notional_usd: Decimal = Decimal("10")
    btc_step_size: Decimal = Decimal("0.001")
    eth_step_size: Decimal = Decimal("0.01")


@dataclass(frozen=True)
class RiskDecision:
    decision_id: str
    intent_id: str
    approved: bool
    reason_code: str
    selected_instrument: str | None
    selected_market: str | None  # "spot" or "usdm"
    allocated_quantity: Decimal
    max_loss_usd: Decimal
    stop_distance_pct: Decimal
    portfolio_exposure_before: Decimal
    portfolio_exposure_after: Decimal
    drawdown_pct: Decimal
    daily_pnl_usd: Decimal
    timestamp_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "intent_id": self.intent_id,
            "approved": self.approved,
            "reason_code": self.reason_code,
            "selected_instrument": self.selected_instrument,
            "selected_market": self.selected_market,
            "allocated_quantity": str(self.allocated_quantity),
            "max_loss_usd": str(self.max_loss_usd),
            "stop_distance_pct": str(self.stop_distance_pct),
            "portfolio_exposure_before": str(self.portfolio_exposure_before),
            "portfolio_exposure_after": str(self.portfolio_exposure_after),
            "drawdown_pct": str(self.drawdown_pct),
            "daily_pnl_usd": str(self.daily_pnl_usd),
            "timestamp_ns": self.timestamp_ns,
        }


class InstrumentSelector:
    """Selects suitable execution market and instrument for an intent.

    Prevents fabricated shorting on Spot.
    """

    @staticmethod
    def select(intent: StrategyIntent) -> tuple[str, str]:
        """Returns (instrument_id, market_kind) e.g. ('BINANCE:SPOT:BTCUSDT', 'spot')."""
        cand = intent.instrument_candidate.upper()
        direction = intent.direction.upper()

        if direction == "SHORT":
            # Spot shorting is impossible without existing inventory; must route to perpetuals
            if "ETH" in cand:
                return "BINANCE:USD_M_PERP:ETHUSDT", "usdm"
            return "BINANCE:USD_M_PERP:BTCUSDT", "usdm"

        # Direction is LONG
        if "USD_M_PERP" in cand or "PERP" in cand or "FUTURES" in cand:
            if "ETH" in cand:
                return "BINANCE:USD_M_PERP:ETHUSDT", "usdm"
            return "BINANCE:USD_M_PERP:BTCUSDT", "usdm"

        if "ETH" in cand:
            return "BINANCE:SPOT:ETHUSDT", "spot"
        return "BINANCE:SPOT:BTCUSDT", "spot"


class RiskBrain:
    """Fail-closed Risk Brain enforcing strict portfolio risk boundaries."""

    def __init__(self, config: RiskBrainConfig | None = None) -> None:
        self.config = config or RiskBrainConfig()

    def evaluate(
        self,
        intent: StrategyIntent,
        *,
        now_ns: int,
        current_equity: Decimal,
        peak_equity: Decimal,
        day_start_equity: Decimal,
        current_positions: list[Any],
        market_price: Decimal,
        market_data_healthy: bool,
        last_market_event_ns: int,
        unresolved_gaps: int = 0,
        kill_switch_active: bool = False,
    ) -> RiskDecision:
        seed = f"{intent.intent_id}:{now_ns}"
        decision_id = hashlib.sha256(seed.encode()).hexdigest()[:16]

        drawdown = Decimal("0")
        if peak_equity > 0:
            drawdown = max(Decimal("0"), (peak_equity - current_equity) / peak_equity)

        daily_loss = Decimal("0")
        daily_pnl = current_equity - day_start_equity
        if day_start_equity > 0 and current_equity < day_start_equity:
            daily_loss = (day_start_equity - current_equity) / day_start_equity

        # Exposure before
        exposure_before = sum(
            (Decimal(str(getattr(p, "quantity", 0))) * Decimal(str(getattr(p, "mark_price", market_price))))
            for p in current_positions
        )

        def reject(code: str) -> RiskDecision:
            return RiskDecision(
                decision_id=decision_id,
                intent_id=intent.intent_id,
                approved=False,
                reason_code=code,
                selected_instrument=None,
                selected_market=None,
                allocated_quantity=Decimal("0"),
                max_loss_usd=Decimal("0"),
                stop_distance_pct=Decimal("0"),
                portfolio_exposure_before=exposure_before,
                portfolio_exposure_after=exposure_before,
                drawdown_pct=drawdown,
                daily_pnl_usd=daily_pnl,
                timestamp_ns=now_ns,
            )

        if kill_switch_active:
            return reject("KILL_SWITCH_ACTIVE")

        if not market_data_healthy:
            return reject("DATA_QUALITY_FAILED")

        if unresolved_gaps > 0:
            return reject("OPEN_DATA_GAP")

        if now_ns < last_market_event_ns or (now_ns - last_market_event_ns) > self.config.max_data_age_ns:
            return reject("STALE_MARKET_DATA")

        if now_ns > intent.signal_expiry_ns or now_ns < intent.signal_ts_ns:
            return reject("STALE_SIGNAL")

        if drawdown >= self.config.max_drawdown_pct:
            return reject("MAX_DRAWDOWN")

        if daily_loss >= self.config.max_daily_loss_pct:
            return reject("MAX_DAILY_LOSS")

        if len(current_positions) >= self.config.max_concurrent_positions:
            return reject("MAX_CONCURRENT_POSITIONS")

        # Instrument selection
        selected_instrument, selected_market = InstrumentSelector.select(intent)

        # Stop distance check
        stop_dist = abs(market_price - intent.stop_price)
        if stop_dist <= 0 or market_price <= 0:
            return reject("INVALID_STOP_PRICE")

        # Validate stop is on the correct side
        if intent.direction == "LONG" and intent.stop_price >= market_price:
            return reject("STOP_ABOVE_LONG_ENTRY")
        if intent.direction == "SHORT" and intent.stop_price <= market_price:
            return reject("STOP_BELOW_SHORT_ENTRY")

        stop_dist_pct = stop_dist / market_price

        # Sizing from allowed risk
        allowed_risk_usd = current_equity * (self.config.max_risk_per_trade_bps / BPS)
        raw_qty = allowed_risk_usd / stop_dist

        # Quantize to step size
        step = self.config.eth_step_size if "ETH" in selected_instrument else self.config.btc_step_size
        allocated_qty = (raw_qty // step) * step

        if allocated_qty <= 0:
            return reject("SIZE_BELOW_MINIMUM_STEP")

        notional = allocated_qty * market_price
        if notional < self.config.min_notional_usd:
            return reject("NOTIONAL_BELOW_MINIMUM")

        # Instrument exposure limit
        is_btc = "BTC" in selected_instrument
        max_inst_exp = self.config.max_btc_exposure_usd if is_btc else self.config.max_eth_exposure_usd

        inst_exposure_before = sum(
            Decimal(str(getattr(p, "quantity", 0))) * Decimal(str(getattr(p, "mark_price", market_price)))
            for p in current_positions
            if ("BTC" in getattr(p, "instrument", "") if is_btc else "ETH" in getattr(p, "instrument", ""))
        )

        if inst_exposure_before + notional > max_inst_exp:
            return reject("MAX_INSTRUMENT_EXPOSURE")

        # Combined portfolio exposure
        exposure_after = exposure_before + notional
        if exposure_after > self.config.max_combined_crypto_exposure_usd:
            return reject("PORTFOLIO_EXPOSURE_EXCEEDED")

        max_loss_usd = allocated_qty * stop_dist

        return RiskDecision(
            decision_id=decision_id,
            intent_id=intent.intent_id,
            approved=True,
            reason_code="APPROVED",
            selected_instrument=selected_instrument,
            selected_market=selected_market,
            allocated_quantity=allocated_qty,
            max_loss_usd=max_loss_usd,
            stop_distance_pct=stop_dist_pct,
            portfolio_exposure_before=exposure_before,
            portfolio_exposure_after=exposure_after,
            drawdown_pct=drawdown,
            daily_pnl_usd=daily_pnl,
            timestamp_ns=now_ns,
        )
