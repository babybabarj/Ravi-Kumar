from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..dashboard import write_dashboard_state
from .ledger import (
    CompletedTrade,
    DecisionRecord,
    PaperLedger,
    PaperOrder,
    PaperPortfolioState,
    PaperPosition,
)
from .live_approval import LiveApprovalGate
from .modes import OperatingMode, SystemControlState
from .position_manager import PositionManager
from .risk_brain import RiskBrain, RiskBrainConfig, RiskDecision
from .strategy_registry import StrategyIntent, StrategyRegistry


BPS = Decimal("10000")
ONE = Decimal("1")


@dataclass
class OrchestratorConfig:
    db_path: Path | str = Path("artifacts/autopilot/ledger.sqlite")
    dashboard_state_path: Path | str = Path("artifacts/dashboard/state.json")
    starting_equity: Decimal = Decimal("1000")
    taker_fee_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("5")
    risk_config: RiskBrainConfig | None = None
    default_mode: OperatingMode = OperatingMode.PAPER_AUTO


@dataclass
class MarketEvent:
    instrument: str
    price: Decimal
    timestamp_ns: int
    funding_rate: Decimal | None = None
    is_healthy: bool = True
    open_gaps: int = 0


class TradingOrchestrator:
    """Canonical runtime orchestrator connecting market data, strategies, risk, and ledger."""

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        self.config = config or OrchestratorConfig()
        self.control = SystemControlState(mode=self.config.default_mode)
        self.registry = StrategyRegistry()
        self.risk_brain = RiskBrain(self.config.risk_config)
        self.ledger = PaperLedger(self.config.db_path)
        self.position_manager = PositionManager(
            self.ledger,
            taker_fee_bps=self.config.taker_fee_bps,
            slippage_bps=self.config.slippage_bps,
        )
        self.live_approval_gate = LiveApprovalGate()
        self.portfolio: PaperPortfolioState | None = None
        self._latest_decision: DecisionRecord | None = None
        self._last_market_price: dict[str, Decimal] = {}
        self._last_market_ts: dict[str, int] = {}
        self._last_market_healthy: bool = True
        self._last_market_gaps: int = 0

    def startup(self, now_ns: int) -> None:
        """Safe startup sequence: recover state before evaluating new decisions."""
        self.portfolio = self.ledger.load_or_init_portfolio(self.config.starting_equity, now_ns)
        self.ledger.record_audit("START", {"mode": self.control.mode.value, "equity": str(self.portfolio.equity)}, now_ns)

    def shutdown(self, now_ns: int) -> None:
        """Safe shutdown sequence: persist state and write audit event."""
        if self.portfolio:
            self.ledger.save_portfolio(self.portfolio)
        self.ledger.record_audit("STOP", {"mode": self.control.mode.value}, now_ns)
        self.ledger.close()

    def step(self, events: list[MarketEvent], now_ns: int) -> dict[str, Any]:
        """Execute one complete atomic evaluation pass."""
        if self.portfolio is None:
            self.startup(now_ns)
            assert self.portfolio is not None

        # 1. Update market state cache
        for ev in events:
            self._last_market_price[ev.instrument] = ev.price
            self._last_market_ts[ev.instrument] = ev.timestamp_ns
            self._last_market_healthy = ev.is_healthy
            self._last_market_gaps = ev.open_gaps

        # 2. Position Management: Update open positions and evaluate stops / targets
        open_positions = self.ledger.get_open_positions()
        for pos in open_positions:
            mark = self._last_market_price.get(pos.instrument)
            if mark is not None and mark > 0:
                ev_rate = next((ev.funding_rate for ev in events if ev.instrument == pos.instrument), None)
                exit_events = self.position_manager.update_position_market(pos, mark, now_ns, ev_rate)
                for exit_ev in exit_events:
                    self._handle_position_exit(exit_ev, now_ns)

        # Re-fetch active open positions after exits
        open_positions = self.ledger.get_open_positions()

        # 3. Mode & Health Gate
        if not self.control.can_enter_new_trades():
            reason = "HALTED" if self.control.halted else ("PAUSED" if self.control.paused else "MODE_OFF")
            self._record_system_decision("SYSTEM", reason, False, now_ns, f"Trading disabled: {reason}")
            self._publish_dashboard(now_ns)
            return {"status": reason, "positions": len(open_positions)}

        # 4. Strategy Evaluation
        strategies = (
            self.registry.get_approved_for_shadow()
            if self.control.mode == OperatingMode.SHADOW_AUTO
            else self.registry.get_approved_for_paper()
        )

        if not strategies:
            self._record_system_decision(
                "REGISTRY",
                "NO_VALIDATED_EDGE",
                False,
                now_ns,
                "Zero approved strategies in registry for active mode",
            )
        else:
            market_state = {
                "prices": {k: str(v) for k, v in self._last_market_price.items()},
                "healthy": self._last_market_healthy,
                "gaps": self._last_market_gaps,
            }
            for strat in strategies:
                intents = strat.evaluate(market_state, open_positions)
                for intent in intents:
                    self._process_intent(intent, open_positions, now_ns)

        # 5. Refresh Equity and publish dashboard
        self._recalculate_equity(now_ns)
        self._publish_dashboard(now_ns)

        return {
            "mode": self.control.mode.value,
            "open_positions": len(self.ledger.get_open_positions()),
            "equity": str(self.portfolio.equity),
            "cash": str(self.portfolio.cash),
            "latest_decision": self._latest_decision.reason_code if self._latest_decision else None,
        }

    def _process_intent(
        self,
        intent: StrategyIntent,
        open_positions: list[PaperPosition],
        now_ns: int,
    ) -> None:
        client_order_id = f"{intent.intent_id}:ENTRY"
        # Idempotency check: ensure we never enter twice for the same intent
        existing_order = self.ledger.get_order_by_client_id(client_order_id)
        if existing_order is not None:
            return

        # Determine reference price for candidate
        ref_instrument = "BINANCE:SPOT:BTCUSDT" if "BTC" in intent.instrument_candidate else "BINANCE:SPOT:ETHUSDT"
        market_price = self._last_market_price.get(ref_instrument, Decimal("0"))
        if market_price <= 0:
            market_price = self._last_market_price.get("BINANCE:USD_M_PERP:BTCUSDT", Decimal("0"))
        if market_price <= 0:
            self._record_intent_decision(intent, "NO_MARKET_DATA", False, now_ns, "Price not available")
            return

        last_ts = self._last_market_ts.get(ref_instrument, now_ns)

        # Risk Brain Evaluation
        assert self.portfolio is not None
        decision = self.risk_brain.evaluate(
            intent,
            now_ns=now_ns,
            current_equity=self.portfolio.equity,
            peak_equity=self.portfolio.peak_equity,
            day_start_equity=self.portfolio.day_start_equity,
            current_positions=open_positions,
            market_price=market_price,
            market_data_healthy=self._last_market_healthy,
            last_market_event_ns=last_ts,
            unresolved_gaps=self._last_market_gaps,
            kill_switch_active=self.control.paused or self.control.halted,
        )

        if not decision.approved:
            self._record_intent_decision(intent, decision.reason_code, False, now_ns, decision.to_dict())
            return

        # Risk approved
        self._record_intent_decision(intent, "APPROVED", True, now_ns, decision.to_dict())
        self.ledger.record_audit("RISK_APPROVED", decision.to_dict(), now_ns)

        # Dispatch by operating mode
        if self.control.mode == OperatingMode.SHADOW_AUTO:
            self.ledger.record_audit("SHADOW_ORDER_RECORDED", {"intent": intent.intent_id, "size": str(decision.allocated_quantity)}, now_ns)
            return

        if self.control.mode == OperatingMode.LIVE_APPROVAL:
            targets_str = json.dumps([{"target_price": str(t.target_price), "exit_fraction": str(t.exit_fraction)} for t in intent.targets])
            self.live_approval_gate.generate_proposal(
                instrument=decision.selected_instrument or intent.instrument_candidate,
                market=decision.selected_market or "spot",
                side="BUY" if intent.direction == "LONG" else "SELL",
                entry_type=intent.entry_preference,
                proposed_quantity=decision.allocated_quantity,
                current_price=market_price,
                stop_price=intent.stop_price,
                targets_str=targets_str,
                max_expected_loss=decision.max_loss_usd,
                estimated_fees=decision.allocated_quantity * market_price * (self.config.taker_fee_bps / BPS),
                estimated_funding=Decimal("0"),
                estimated_slippage=decision.allocated_quantity * market_price * (self.config.slippage_bps / BPS),
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                market_regime=intent.market_regime,
                reason="Strategy signal risk approved",
                signal_ts_ns=intent.signal_ts_ns,
                now_ns=now_ns,
            )
            self.ledger.record_audit("APPROVAL_CREATED", {"intent": intent.intent_id}, now_ns)
            return

        if self.control.mode == OperatingMode.PAPER_AUTO:
            self._execute_paper_entry(intent, decision, market_price, client_order_id, now_ns)

    def _execute_paper_entry(
        self,
        intent: StrategyIntent,
        decision: RiskDecision,
        market_price: Decimal,
        client_order_id: str,
        now_ns: int,
    ) -> None:
        assert self.portfolio is not None
        direction = intent.direction
        qty = decision.allocated_quantity
        market = decision.selected_market or "spot"
        instrument = decision.selected_instrument or intent.instrument_candidate

        # Slippage calculation
        if direction == "LONG":
            fill_price = market_price * (ONE + self.config.slippage_bps / BPS)
            slippage_usd = (fill_price - market_price) * qty
            order_side = "BUY"
        else:
            fill_price = market_price * (ONE - self.config.slippage_bps / BPS)
            slippage_usd = (market_price - fill_price) * qty
            order_side = "SELL"

        fee = (qty * fill_price) * (self.config.taker_fee_bps / BPS)

        # Cash adjustment
        if market == "spot":
            # Spot buy uses full capital
            self.portfolio.cash -= (qty * fill_price) + fee
        else:
            # Perp uses margin; cash only charged the fee
            self.portfolio.cash -= fee

        # Create PaperOrder
        order_id = hashlib.sha256(f"{client_order_id}:{now_ns}".encode()).hexdigest()[:16]
        order = PaperOrder(
            order_id=order_id,
            client_order_id=client_order_id,
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            instrument=instrument,
            market=market,
            side=order_side,
            order_type=intent.entry_preference,
            quantity=qty,
            price=market_price,
            status="FILLED",
            created_at_ns=now_ns,
            updated_at_ns=now_ns,
            filled_qty=qty,
            avg_fill_price=fill_price,
            fee=fee,
            slippage=slippage_usd,
        )
        self.ledger.record_paper_order(order)

        # Create PaperPosition
        pos_id = hashlib.sha256(f"{order_id}:POS".encode()).hexdigest()[:16]
        targets_payload = [{"target_price": str(t.target_price), "exit_fraction": str(t.exit_fraction), "hit": False} for t in intent.targets]
        pos = PaperPosition(
            position_id=pos_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            instrument=instrument,
            market=market,
            side=direction,
            quantity=qty,
            average_entry=fill_price,
            mark_price=fill_price,
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            fees=fee,
            funding=Decimal("0"),
            stop_price=intent.stop_price,
            targets_json=json.dumps(targets_payload),
            opened_at_ns=now_ns,
            updated_at_ns=now_ns,
            highest_price=fill_price,
            lowest_price=fill_price,
        )
        self.ledger.save_position(pos)
        self.ledger.record_audit(
            "POSITION_OPENED",
            {"position_id": pos_id, "instrument": instrument, "side": direction, "qty": str(qty), "price": str(fill_price)},
            now_ns,
        )

    def _handle_position_exit(self, exit_ev: PositionExitEvent, now_ns: int) -> None:
        assert self.portfolio is not None
        pos = exit_ev.position

        # Return capital to cash
        if pos.market == "spot":
            self.portfolio.cash += (exit_ev.closed_qty * exit_ev.exit_price) - exit_ev.fees
        else:
            self.portfolio.cash += exit_ev.gross_pnl - exit_ev.fees - exit_ev.funding

        # Record completed trade
        trade_id = hashlib.sha256(f"{pos.position_id}:{exit_ev.exit_reason}:{now_ns}".encode()).hexdigest()[:16]
        holding_time = now_ns - pos.opened_at_ns
        trade = CompletedTrade(
            trade_id=trade_id,
            strategy_id=pos.strategy_id,
            strategy_version=pos.strategy_version,
            instrument=pos.instrument,
            side=pos.side,
            signal_ts=pos.opened_at_ns,
            decision_ts=pos.opened_at_ns,
            entry_order_ts=pos.opened_at_ns,
            entry_fill_ts=pos.opened_at_ns,
            entry_price=pos.average_entry,
            quantity=exit_ev.closed_qty,
            stop=pos.stop_price,
            targets=pos.targets_json,
            exit_decision_ts=now_ns,
            exit_fill_ts=now_ns,
            exit_price=exit_ev.exit_price,
            exit_reason=exit_ev.exit_reason,
            gross_pnl=exit_ev.gross_pnl,
            fees=exit_ev.fees,
            funding=exit_ev.funding,
            slippage=exit_ev.slippage,
            net_pnl=exit_ev.net_pnl,
            mae=exit_ev.mae,
            mfe=exit_ev.mfe,
            holding_time_ns=holding_time,
            market_regime="NORMAL",
            risk_amount=pos.average_entry * exit_ev.closed_qty,
            portfolio_equity_before=self.portfolio.equity,
            portfolio_equity_after=self.portfolio.equity + exit_ev.net_pnl,
        )
        self.ledger.record_completed_trade(trade)
        self.ledger.record_audit(
            "POSITION_CLOSED" if exit_ev.is_full_close else "POSITION_REDUCED",
            {"trade_id": trade_id, "net_pnl": str(exit_ev.net_pnl), "reason": exit_ev.exit_reason},
            now_ns,
        )

    def _recalculate_equity(self, now_ns: int) -> None:
        assert self.portfolio is not None
        open_positions = self.ledger.get_open_positions()

        total_value = self.portfolio.cash
        for p in open_positions:
            if p.market == "spot":
                total_value += p.quantity * p.mark_price
            else:
                total_value += p.unrealized_pnl - p.funding

        self.portfolio.equity = max(Decimal("0"), total_value)
        self.portfolio.peak_equity = max(self.portfolio.peak_equity, self.portfolio.equity)
        self.portfolio.updated_at_ns = now_ns
        self.ledger.save_portfolio(self.portfolio)

    def _record_system_decision(self, strat_id: str, reason: str, approved: bool, now_ns: int, detail: Any) -> None:
        seed = f"{strat_id}:{reason}:{now_ns}"
        dec_id = hashlib.sha256(seed.encode()).hexdigest()[:16]
        rec = DecisionRecord(
            decision_id=dec_id,
            intent_id="SYSTEM",
            strategy_id=strat_id,
            decision_ts_ns=now_ns,
            reason_code=reason,
            approved=approved,
            details_json=json.dumps(detail) if not isinstance(detail, str) else detail,
        )
        self.ledger.record_decision(rec)
        self._latest_decision = rec

    def _record_intent_decision(self, intent: StrategyIntent, reason: str, approved: bool, now_ns: int, detail: Any) -> None:
        seed = f"{intent.intent_id}:{reason}:{now_ns}"
        dec_id = hashlib.sha256(seed.encode()).hexdigest()[:16]
        rec = DecisionRecord(
            decision_id=dec_id,
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            decision_ts_ns=now_ns,
            reason_code=reason,
            approved=approved,
            details_json=json.dumps(detail) if not isinstance(detail, str) else detail,
        )
        self.ledger.record_decision(rec)
        self._latest_decision = rec

    def _publish_dashboard(self, now_ns: int) -> None:
        assert self.portfolio is not None
        open_positions = self.ledger.get_open_positions()
        recent_trades = self.ledger.get_completed_trades(limit=10)
        recent_decisions = self.ledger.get_recent_decisions(limit=10)
        pending_proposals = self.live_approval_gate.get_pending(now_ns)

        btc_p = self._last_market_price.get("BINANCE:SPOT:BTCUSDT") or self._last_market_price.get("BINANCE:USD_M_PERP:BTCUSDT")
        total_pnl = self.portfolio.equity - self.config.starting_equity
        daily_pnl = self.portfolio.equity - self.portfolio.day_start_equity

        # Calculate statistics
        wins = sum(1 for t in recent_trades if t.net_pnl > 0)
        losses = sum(1 for t in recent_trades if t.net_pnl < 0)
        win_rate = f"{(wins / len(recent_trades) * 100):.1f}%" if recent_trades else "0.0%"

        state = {
            "system_control": {
                "mode": self.control.mode.value,
                "paused": self.control.paused,
                "halted": self.control.halted,
                "pause_reason": self.control.pause_reason,
                "halt_reason": self.control.halt_reason,
            },
            "data_health": {
                "status": "HEALTHY" if self._last_market_healthy and self._last_market_gaps == 0 else "DEGRADED",
                "last_event_ns": max(self._last_market_ts.values(), default=now_ns),
                "open_gaps": self._last_market_gaps,
            },
            "market": {
                "status": "LIVE" if self._last_market_healthy else "STALE",
                "instrument": "BINANCE:SPOT:BTCUSDT",
                "price": str(btc_p) if btc_p else None,
                "all_prices": {k: str(v) for k, v in self._last_market_price.items()},
            },
            "signal": {
                "status": self._latest_decision.reason_code if self._latest_decision else "NO_SIGNAL",
                "target_position": "0",
                "reason": self._latest_decision.reason_code if self._latest_decision else "Awaiting evaluated edge",
            },
            "paper": {
                "status": "PAPER_AUTO_ACTIVE" if not self.control.paused else "PAPER_PAUSED",
                "cash": str(self.portfolio.cash),
                "position": str(sum(p.quantity for p in open_positions)),
                "equity": str(self.portfolio.equity),
                "pnl": str(total_pnl),
                "daily_pnl": str(daily_pnl),
                "open_positions": [
                    {
                        "position_id": p.position_id,
                        "instrument": p.instrument,
                        "side": p.side,
                        "quantity": str(p.quantity),
                        "average_entry": str(p.average_entry),
                        "mark_price": str(p.mark_price),
                        "unrealized_pnl": str(p.unrealized_pnl),
                        "stop_price": str(p.stop_price),
                    }
                    for p in open_positions
                ],
                "stats": {
                    "completed_trades": len(recent_trades),
                    "wins": wins,
                    "losses": losses,
                    "win_rate": win_rate,
                },
            },
            "recent_decisions": [
                {
                    "ts_ns": d.decision_ts_ns,
                    "strategy": d.strategy_id,
                    "reason": d.reason_code,
                    "approved": d.approved,
                }
                for d in recent_decisions
            ],
            "proposals": [p.to_dict() for p in pending_proposals],
            "account": {
                "status": "NOT_CONNECTED",
                "last_sync_ns": None,
                "spot": {"balances": [], "open_orders": 0},
                "usdm": {"balances": [], "positions": [], "open_orders": 0},
                "error": None,
            },
        }

        write_dashboard_state(self.config.dashboard_state_path, state)
