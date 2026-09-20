from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .ledger import CompletedTrade, PaperLedger, PaperPosition


BPS = Decimal("10000")
ONE = Decimal("1")


@dataclass(frozen=True)
class PositionExitEvent:
    position: PaperPosition
    closed_qty: Decimal
    exit_price: Decimal
    exit_reason: str
    exit_ts_ns: int
    gross_pnl: Decimal
    fees: Decimal
    funding: Decimal
    slippage: Decimal
    net_pnl: Decimal
    mae: Decimal
    mfe: Decimal
    is_full_close: bool


class PositionManager:
    """Monitors open positions, accrues funding, and executes automatic stops and target exits."""

    def __init__(
        self,
        ledger: PaperLedger,
        *,
        taker_fee_bps: Decimal = Decimal("10"),  # 0.10%
        slippage_bps: Decimal = Decimal("5"),    # 0.05%
    ) -> None:
        self.ledger = ledger
        self.taker_fee_bps = taker_fee_bps
        self.slippage_bps = slippage_bps

    def update_position_market(
        self,
        pos: PaperPosition,
        mark_price: Decimal,
        now_ns: int,
        funding_rate: Decimal | None = None,
    ) -> list[PositionExitEvent]:
        """Update mark-to-market and check stop/target triggers."""
        if not pos.is_open or mark_price <= 0:
            return []

        pos.mark_price = mark_price
        pos.updated_at_ns = now_ns

        # Update MFE / MAE trackers
        if pos.highest_price <= 0 or mark_price > pos.highest_price:
            pos.highest_price = mark_price
        if pos.lowest_price <= 0 or mark_price < pos.lowest_price:
            pos.lowest_price = mark_price

        # Unrealized PnL
        if pos.side == "LONG":
            pos.unrealized_pnl = (mark_price - pos.average_entry) * pos.quantity
        else:
            pos.unrealized_pnl = (pos.average_entry - mark_price) * pos.quantity

        # Optional funding accrual for USD-M perps
        if pos.market == "usdm" and funding_rate is not None:
            notional = pos.quantity * mark_price
            funding_charge = notional * funding_rate if pos.side == "LONG" else -notional * funding_rate
            pos.funding += funding_charge

        exits: list[PositionExitEvent] = []

        # 1. Hard Stop Check
        stop_hit = False
        if pos.side == "LONG" and mark_price <= pos.stop_price:
            stop_hit = True
        elif pos.side == "SHORT" and mark_price >= pos.stop_price:
            stop_hit = True

        if stop_hit:
            exit_event = self._close_partial_or_full(pos, pos.quantity, mark_price, "STOP_LOSS", now_ns)
            exits.append(exit_event)
            return exits

        # 2. Target Checks (TP1, TP2, TP3)
        try:
            targets = json.loads(pos.targets_json)
        except Exception:
            targets = []

        targets_updated = False
        for idx, t in enumerate(targets):
            if t.get("hit", False):
                continue
            tp_price = Decimal(str(t["target_price"]))
            fraction = Decimal(str(t["exit_fraction"]))

            tp_hit = False
            if pos.side == "LONG" and mark_price >= tp_price:
                tp_hit = True
            elif pos.side == "SHORT" and mark_price <= tp_price:
                tp_hit = True

            if tp_hit:
                t["hit"] = True
                targets_updated = True
                is_last_target = (idx == len(targets) - 1)
                qty_to_close = pos.quantity if is_last_target else min(pos.quantity, pos.quantity * fraction)
                if qty_to_close > 0:
                    exit_event = self._close_partial_or_full(
                        pos, qty_to_close, mark_price, f"TARGET_TP{idx + 1}", now_ns
                    )
                    exits.append(exit_event)
                    if not pos.is_open:
                        break

        if targets_updated:
            pos.targets_json = json.dumps(targets)

        self.ledger.save_position(pos)
        return exits

    def _close_partial_or_full(
        self,
        pos: PaperPosition,
        qty_to_close: Decimal,
        market_price: Decimal,
        reason: str,
        now_ns: int,
    ) -> PositionExitEvent:
        # Slippage penalty on exit
        if pos.side == "LONG":
            exit_price = market_price * (ONE - self.slippage_bps / BPS)
            gross_pnl = (exit_price - pos.average_entry) * qty_to_close
            slippage_usd = (market_price - exit_price) * qty_to_close
        else:
            exit_price = market_price * (ONE + self.slippage_bps / BPS)
            gross_pnl = (pos.average_entry - exit_price) * qty_to_close
            slippage_usd = (exit_price - market_price) * qty_to_close

        exit_fee = (qty_to_close * exit_price) * (self.taker_fee_bps / BPS)
        total_fees = pos.fees + exit_fee
        funding = pos.funding
        net_pnl = gross_pnl - total_fees - funding

        # MAE and MFE
        if pos.side == "LONG":
            mae = max(Decimal("0"), pos.average_entry - pos.lowest_price)
            mfe = max(Decimal("0"), pos.highest_price - pos.average_entry)
        else:
            mae = max(Decimal("0"), pos.highest_price - pos.average_entry)
            mfe = max(Decimal("0"), pos.average_entry - pos.lowest_price)

        is_full_close = qty_to_close >= pos.quantity
        if is_full_close:
            pos.quantity = Decimal("0")
            pos.closed_at_ns = now_ns
            pos.exit_reason = reason
            pos.realized_pnl += net_pnl
            pos.unrealized_pnl = Decimal("0")
        else:
            pos.quantity -= qty_to_close
            pos.realized_pnl += net_pnl

        pos.updated_at_ns = now_ns
        self.ledger.save_position(pos)

        return PositionExitEvent(
            position=pos,
            closed_qty=qty_to_close,
            exit_price=exit_price,
            exit_reason=reason,
            exit_ts_ns=now_ns,
            gross_pnl=gross_pnl,
            fees=total_fees,
            funding=funding,
            slippage=slippage_usd,
            net_pnl=net_pnl,
            mae=mae,
            mfe=mfe,
            is_full_close=is_full_close,
        )
