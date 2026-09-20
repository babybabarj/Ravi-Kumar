from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


ONE = Decimal("1")
BPS = Decimal("10000")


@dataclass(frozen=True)
class RiskLimits:
    max_abs_position: Decimal
    max_drawdown: Decimal
    max_daily_loss: Decimal
    max_data_age_ns: int

    def __post_init__(self) -> None:
        if self.max_abs_position <= 0 or min(self.max_drawdown, self.max_daily_loss) < 0 or self.max_data_age_ns < 0:
            raise ValueError("risk limits must be non-negative, with a positive maximum position")


@dataclass(frozen=True)
class SafetySnapshot:
    equity: Decimal
    peak_equity: Decimal
    day_start_equity: Decimal
    last_market_event_ns: int
    quality_ok: bool
    unresolved_gaps: int = 0

    def __post_init__(self) -> None:
        if min(self.equity, self.peak_equity, self.day_start_equity) <= 0 or self.unresolved_gaps < 0:
            raise ValueError("equity must be positive and gaps cannot be negative")


@dataclass(frozen=True)
class ProposedPosition:
    instrument_id: str
    target_position: Decimal
    signal_event_ns: int


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    mode: str = "SHADOW"


@dataclass(frozen=True)
class PaperPortfolio:
    cash: Decimal
    position: Decimal = Decimal("0")

    def equity_at(self, mark_price: Decimal) -> Decimal:
        if mark_price <= 0:
            raise ValueError("mark price must be positive")
        return self.cash + self.position * mark_price


@dataclass(frozen=True)
class PaperResult:
    decision: GateDecision
    portfolio: PaperPortfolio
    fill_price: Decimal | None
    fee: Decimal


def assess(proposal: ProposedPosition, snapshot: SafetySnapshot, limits: RiskLimits, now_ns: int) -> GateDecision:
    """Fail closed before shadow or local paper processing; this function has no exchange side effects."""
    if not snapshot.quality_ok:
        return GateDecision(False, "DATA_QUALITY_FAILED")
    if snapshot.unresolved_gaps:
        return GateDecision(False, "UNRESOLVED_DATA_GAP")
    if now_ns < snapshot.last_market_event_ns or now_ns - snapshot.last_market_event_ns > limits.max_data_age_ns:
        return GateDecision(False, "STALE_MARKET_DATA")
    if now_ns < proposal.signal_event_ns or now_ns - proposal.signal_event_ns > limits.max_data_age_ns:
        return GateDecision(False, "STALE_SIGNAL")
    if ONE - snapshot.equity / snapshot.peak_equity >= limits.max_drawdown:
        return GateDecision(False, "MAX_DRAWDOWN")
    if ONE - snapshot.equity / snapshot.day_start_equity >= limits.max_daily_loss:
        return GateDecision(False, "MAX_DAILY_LOSS")
    if abs(proposal.target_position) > limits.max_abs_position:
        return GateDecision(False, "MAX_POSITION")
    return GateDecision(True, "SHADOW_ACCEPTED")


def simulate_paper_fill(
    proposal: ProposedPosition,
    portfolio: PaperPortfolio,
    snapshot: SafetySnapshot,
    limits: RiskLimits,
    *,
    now_ns: int,
    mark_price: Decimal,
    taker_fee_bps: Decimal,
    slippage_bps: Decimal,
) -> PaperResult:
    """Apply an approved proposal only to an in-memory paper portfolio; it never contacts an exchange."""
    if mark_price <= 0 or min(taker_fee_bps, slippage_bps) < 0:
        raise ValueError("price must be positive and costs cannot be negative")
    decision = assess(proposal, snapshot, limits, now_ns)
    if not decision.allowed:
        return PaperResult(decision, portfolio, None, Decimal("0"))
    delta = proposal.target_position - portfolio.position
    if not delta:
        return PaperResult(GateDecision(True, "PAPER_NO_CHANGE", "PAPER"), portfolio, None, Decimal("0"))
    direction = ONE if delta >= 0 else -ONE
    fill_price = mark_price * (ONE + direction * slippage_bps / BPS)
    fee = abs(delta * fill_price) * taker_fee_bps / BPS
    updated = PaperPortfolio(portfolio.cash - delta * fill_price - fee, proposal.target_position)
    if updated.cash < 0:
        return PaperResult(GateDecision(False, "INSUFFICIENT_PAPER_CASH", "PAPER"), portfolio, None, Decimal("0"))
    return PaperResult(GateDecision(True, "PAPER_FILLED", "PAPER"), updated, fill_price, fee)
