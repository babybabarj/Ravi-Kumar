from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any


LEDGER_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS paper_portfolio_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash TEXT NOT NULL,
    equity TEXT NOT NULL,
    peak_equity TEXT NOT NULL,
    day_start_equity TEXT NOT NULL,
    day_start_ts_ns INTEGER NOT NULL,
    updated_at_ns INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_orders (
    order_id TEXT PRIMARY KEY,
    client_order_id TEXT NOT NULL UNIQUE,
    intent_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity TEXT NOT NULL,
    price TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at_ns INTEGER NOT NULL,
    updated_at_ns INTEGER NOT NULL,
    filled_qty TEXT NOT NULL,
    avg_fill_price TEXT NOT NULL,
    fee TEXT NOT NULL,
    slippage TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    position_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    instrument TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity TEXT NOT NULL,
    average_entry TEXT NOT NULL,
    mark_price TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    fees TEXT NOT NULL,
    funding TEXT NOT NULL,
    stop_price TEXT NOT NULL,
    targets_json TEXT NOT NULL,
    opened_at_ns INTEGER NOT NULL,
    updated_at_ns INTEGER NOT NULL,
    closed_at_ns INTEGER,
    exit_reason TEXT,
    highest_price TEXT NOT NULL,
    lowest_price TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS completed_trades (
    trade_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    instrument TEXT NOT NULL,
    side TEXT NOT NULL,
    signal_ts INTEGER NOT NULL,
    decision_ts INTEGER NOT NULL,
    entry_order_ts INTEGER NOT NULL,
    entry_fill_ts INTEGER NOT NULL,
    entry_price TEXT NOT NULL,
    quantity TEXT NOT NULL,
    stop TEXT NOT NULL,
    targets TEXT NOT NULL,
    exit_decision_ts INTEGER NOT NULL,
    exit_fill_ts INTEGER NOT NULL,
    exit_price TEXT NOT NULL,
    exit_reason TEXT NOT NULL,
    gross_pnl TEXT NOT NULL,
    fees TEXT NOT NULL,
    funding TEXT NOT NULL,
    slippage TEXT NOT NULL,
    net_pnl TEXT NOT NULL,
    mae TEXT NOT NULL,
    mfe TEXT NOT NULL,
    holding_time_ns INTEGER NOT NULL,
    market_regime TEXT NOT NULL,
    risk_amount TEXT NOT NULL,
    portfolio_equity_before TEXT NOT NULL,
    portfolio_equity_after TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_ledger (
    decision_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    decision_ts_ns INTEGER NOT NULL,
    reason_code TEXT NOT NULL,
    approved INTEGER NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_ts_ns INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
"""


@dataclass
class PaperPortfolioState:
    cash: Decimal
    equity: Decimal
    peak_equity: Decimal
    day_start_equity: Decimal
    day_start_ts_ns: int
    updated_at_ns: int

    def to_row(self) -> tuple[int, str, str, str, str, int, int]:
        return (
            1,
            format(self.cash, "f"),
            format(self.equity, "f"),
            format(self.peak_equity, "f"),
            format(self.day_start_equity, "f"),
            self.day_start_ts_ns,
            self.updated_at_ns,
        )

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> PaperPortfolioState:
        return cls(
            cash=Decimal(row[1]),
            equity=Decimal(row[2]),
            peak_equity=Decimal(row[3]),
            day_start_equity=Decimal(row[4]),
            day_start_ts_ns=row[5],
            updated_at_ns=row[6],
        )


@dataclass
class PaperOrder:
    order_id: str
    client_order_id: str
    intent_id: str
    strategy_id: str
    instrument: str
    market: str
    side: str  # "BUY" or "SELL"
    order_type: str  # "MARKET"
    quantity: Decimal
    price: Decimal
    status: str  # "CREATED", "ACCEPTED", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"
    created_at_ns: int
    updated_at_ns: int
    filled_qty: Decimal = Decimal("0")
    avg_fill_price: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")


@dataclass
class PaperPosition:
    position_id: str
    strategy_id: str
    strategy_version: str
    instrument: str
    market: str
    side: str  # "LONG" or "SHORT"
    quantity: Decimal
    average_entry: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    fees: Decimal
    funding: Decimal
    stop_price: Decimal
    targets_json: str
    opened_at_ns: int
    updated_at_ns: int
    closed_at_ns: int | None = None
    exit_reason: str | None = None
    highest_price: Decimal = Decimal("0")
    lowest_price: Decimal = Decimal("0")

    @property
    def is_open(self) -> bool:
        return self.closed_at_ns is None and self.quantity > 0


@dataclass(frozen=True)
class CompletedTrade:
    trade_id: str
    strategy_id: str
    strategy_version: str
    instrument: str
    side: str
    signal_ts: int
    decision_ts: int
    entry_order_ts: int
    entry_fill_ts: int
    entry_price: Decimal
    quantity: Decimal
    stop: Decimal
    targets: str
    exit_decision_ts: int
    exit_fill_ts: int
    exit_price: Decimal
    exit_reason: str
    gross_pnl: Decimal
    fees: Decimal
    funding: Decimal
    slippage: Decimal
    net_pnl: Decimal
    mae: Decimal
    mfe: Decimal
    holding_time_ns: int
    market_regime: str
    risk_amount: Decimal
    portfolio_equity_before: Decimal
    portfolio_equity_after: Decimal

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = format(v, "f")
        return d


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    intent_id: str
    strategy_id: str
    decision_ts_ns: int
    reason_code: str
    approved: bool
    details_json: str


class PaperLedger:
    """Durable SQLite WAL ledger ensuring complete state recovery across restarts."""

    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(LEDGER_DDL)
        self.db.commit()

    def load_or_init_portfolio(self, starting_equity: Decimal, now_ns: int) -> PaperPortfolioState:
        cur = self.db.execute("SELECT * FROM paper_portfolio_state WHERE id = 1")
        row = cur.fetchone()
        if row is not None:
            return PaperPortfolioState.from_row(row)
        init_state = PaperPortfolioState(
            cash=starting_equity,
            equity=starting_equity,
            peak_equity=starting_equity,
            day_start_equity=starting_equity,
            day_start_ts_ns=now_ns,
            updated_at_ns=now_ns,
        )
        self.save_portfolio(init_state)
        return init_state

    def save_portfolio(self, state: PaperPortfolioState) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO paper_portfolio_state
                (id, cash, equity, peak_equity, day_start_equity, day_start_ts_ns, updated_at_ns)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                state.to_row(),
            )

    def record_paper_order(self, order: PaperOrder) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO paper_orders (
                    order_id, client_order_id, intent_id, strategy_id, instrument,
                    market, side, order_type, quantity, price, status,
                    created_at_ns, updated_at_ns, filled_qty, avg_fill_price, fee, slippage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.client_order_id,
                    order.intent_id,
                    order.strategy_id,
                    order.instrument,
                    order.market,
                    order.side,
                    order.order_type,
                    format(order.quantity, "f"),
                    format(order.price, "f"),
                    order.status,
                    order.created_at_ns,
                    order.updated_at_ns,
                    format(order.filled_qty, "f"),
                    format(order.avg_fill_price, "f"),
                    format(order.fee, "f"),
                    format(order.slippage, "f"),
                ),
            )

    def get_order_by_client_id(self, client_order_id: str) -> PaperOrder | None:
        cur = self.db.execute("SELECT * FROM paper_orders WHERE client_order_id = ?", (client_order_id,))
        row = cur.fetchone()
        if not row:
            return None
        return PaperOrder(
            order_id=row[0],
            client_order_id=row[1],
            intent_id=row[2],
            strategy_id=row[3],
            instrument=row[4],
            market=row[5],
            side=row[6],
            order_type=row[7],
            quantity=Decimal(row[8]),
            price=Decimal(row[9]),
            status=row[10],
            created_at_ns=row[11],
            updated_at_ns=row[12],
            filled_qty=Decimal(row[13]),
            avg_fill_price=Decimal(row[14]),
            fee=Decimal(row[15]),
            slippage=Decimal(row[16]),
        )

    def save_position(self, pos: PaperPosition) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO paper_positions (
                    position_id, strategy_id, strategy_version, instrument, market, side,
                    quantity, average_entry, mark_price, unrealized_pnl, realized_pnl,
                    fees, funding, stop_price, targets_json, opened_at_ns, updated_at_ns,
                    closed_at_ns, exit_reason, highest_price, lowest_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pos.position_id,
                    pos.strategy_id,
                    pos.strategy_version,
                    pos.instrument,
                    pos.market,
                    pos.side,
                    format(pos.quantity, "f"),
                    format(pos.average_entry, "f"),
                    format(pos.mark_price, "f"),
                    format(pos.unrealized_pnl, "f"),
                    format(pos.realized_pnl, "f"),
                    format(pos.fees, "f"),
                    format(pos.funding, "f"),
                    format(pos.stop_price, "f"),
                    pos.targets_json,
                    pos.opened_at_ns,
                    pos.updated_at_ns,
                    pos.closed_at_ns,
                    pos.exit_reason,
                    format(pos.highest_price, "f"),
                    format(pos.lowest_price, "f"),
                ),
            )

    def get_open_positions(self) -> list[PaperPosition]:
        cur = self.db.execute(
            "SELECT * FROM paper_positions WHERE closed_at_ns IS NULL AND CAST(quantity AS REAL) > 0"
        )
        out: list[PaperPosition] = []
        for row in cur.fetchall():
            out.append(
                PaperPosition(
                    position_id=row[0],
                    strategy_id=row[1],
                    strategy_version=row[2],
                    instrument=row[3],
                    market=row[4],
                    side=row[5],
                    quantity=Decimal(row[6]),
                    average_entry=Decimal(row[7]),
                    mark_price=Decimal(row[8]),
                    unrealized_pnl=Decimal(row[9]),
                    realized_pnl=Decimal(row[10]),
                    fees=Decimal(row[11]),
                    funding=Decimal(row[12]),
                    stop_price=Decimal(row[13]),
                    targets_json=row[14],
                    opened_at_ns=row[15],
                    updated_at_ns=row[16],
                    closed_at_ns=row[17],
                    exit_reason=row[18],
                    highest_price=Decimal(row[19]),
                    lowest_price=Decimal(row[20]),
                )
            )
        return out

    def record_completed_trade(self, trade: CompletedTrade) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO completed_trades (
                    trade_id, strategy_id, strategy_version, instrument, side,
                    signal_ts, decision_ts, entry_order_ts, entry_fill_ts,
                    entry_price, quantity, stop, targets,
                    exit_decision_ts, exit_fill_ts, exit_price, exit_reason,
                    gross_pnl, fees, funding, slippage, net_pnl,
                    mae, mfe, holding_time_ns, market_regime,
                    risk_amount, portfolio_equity_before, portfolio_equity_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.trade_id,
                    trade.strategy_id,
                    trade.strategy_version,
                    trade.instrument,
                    trade.side,
                    trade.signal_ts,
                    trade.decision_ts,
                    trade.entry_order_ts,
                    trade.entry_fill_ts,
                    format(trade.entry_price, "f"),
                    format(trade.quantity, "f"),
                    format(trade.stop, "f"),
                    trade.targets,
                    trade.exit_decision_ts,
                    trade.exit_fill_ts,
                    format(trade.exit_price, "f"),
                    trade.exit_reason,
                    format(trade.gross_pnl, "f"),
                    format(trade.fees, "f"),
                    format(trade.funding, "f"),
                    format(trade.slippage, "f"),
                    format(trade.net_pnl, "f"),
                    format(trade.mae, "f"),
                    format(trade.mfe, "f"),
                    trade.holding_time_ns,
                    trade.market_regime,
                    format(trade.risk_amount, "f"),
                    format(trade.portfolio_equity_before, "f"),
                    format(trade.portfolio_equity_after, "f"),
                ),
            )

    def get_completed_trades(self, limit: int = 50) -> list[CompletedTrade]:
        cur = self.db.execute(
            "SELECT * FROM completed_trades ORDER BY exit_fill_ts DESC LIMIT ?",
            (limit,),
        )
        out: list[CompletedTrade] = []
        for row in cur.fetchall():
            out.append(
                CompletedTrade(
                    trade_id=row[0],
                    strategy_id=row[1],
                    strategy_version=row[2],
                    instrument=row[3],
                    side=row[4],
                    signal_ts=row[5],
                    decision_ts=row[6],
                    entry_order_ts=row[7],
                    entry_fill_ts=row[8],
                    entry_price=Decimal(row[9]),
                    quantity=Decimal(row[10]),
                    stop=Decimal(row[11]),
                    targets=row[12],
                    exit_decision_ts=row[13],
                    exit_fill_ts=row[14],
                    exit_price=Decimal(row[15]),
                    exit_reason=row[16],
                    gross_pnl=Decimal(row[17]),
                    fees=Decimal(row[18]),
                    funding=Decimal(row[19]),
                    slippage=Decimal(row[20]),
                    net_pnl=Decimal(row[21]),
                    mae=Decimal(row[22]),
                    mfe=Decimal(row[23]),
                    holding_time_ns=row[24],
                    market_regime=row[25],
                    risk_amount=Decimal(row[26]),
                    portfolio_equity_before=Decimal(row[27]),
                    portfolio_equity_after=Decimal(row[28]),
                )
            )
        return out

    def record_decision(self, rec: DecisionRecord) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO decision_ledger (
                    decision_id, intent_id, strategy_id, decision_ts_ns, reason_code, approved, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.decision_id,
                    rec.intent_id,
                    rec.strategy_id,
                    rec.decision_ts_ns,
                    rec.reason_code,
                    1 if rec.approved else 0,
                    rec.details_json,
                ),
            )

    def get_recent_decisions(self, limit: int = 50) -> list[DecisionRecord]:
        cur = self.db.execute(
            "SELECT * FROM decision_ledger ORDER BY decision_ts_ns DESC LIMIT ?",
            (limit,),
        )
        out: list[DecisionRecord] = []
        for row in cur.fetchall():
            out.append(
                DecisionRecord(
                    decision_id=row[0],
                    intent_id=row[1],
                    strategy_id=row[2],
                    decision_ts_ns=row[3],
                    reason_code=row[4],
                    approved=bool(row[5]),
                    details_json=row[6],
                )
            )
        return out

    def record_audit(self, event_type: str, details: dict[str, Any], now_ns: int) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO audit_log (event_ts_ns, event_type, detail_json) VALUES (?, ?, ?)",
                (now_ns, event_type, json.dumps(details)),
            )

    def get_recent_audit_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self.db.execute(
            "SELECT event_ts_ns, event_type, detail_json FROM audit_log ORDER BY audit_id DESC LIMIT ?",
            (limit,),
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            try:
                detail = json.loads(row[2])
            except Exception:
                detail = {"raw": row[2]}
            out.append({"ts_ns": row[0], "event": row[1], "detail": detail})
        return out

    def close(self) -> None:
        self.db.close()
