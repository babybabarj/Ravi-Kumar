from decimal import Decimal

from btceth_os.safety import PaperPortfolio, ProposedPosition, RiskLimits, SafetySnapshot, assess, simulate_paper_fill


def limits() -> RiskLimits:
    return RiskLimits(Decimal("1"), Decimal("0.10"), Decimal("0.05"), 100)


def snapshot(**changes) -> SafetySnapshot:
    values = {"equity": Decimal("100"), "peak_equity": Decimal("100"), "day_start_equity": Decimal("100"), "last_market_event_ns": 1_000, "quality_ok": True}
    values.update(changes)
    return SafetySnapshot(**values)


def test_shadow_fails_closed_for_stale_and_degraded_data():
    proposal = ProposedPosition("BINANCE:SPOT:BTCUSDT", Decimal("1"), 1_000)
    assert assess(proposal, snapshot(last_market_event_ns=1_101), limits(), 1_101).reason == "STALE_SIGNAL"
    assert assess(proposal, snapshot(last_market_event_ns=800), limits(), 1_001).reason == "STALE_MARKET_DATA"
    assert assess(proposal, snapshot(unresolved_gaps=1), limits(), 1_001).reason == "UNRESOLVED_DATA_GAP"
    assert assess(proposal, snapshot(equity=Decimal("90")), limits(), 1_001).reason == "MAX_DRAWDOWN"


def test_paper_fill_is_local_and_respects_the_same_gate():
    proposal = ProposedPosition("BINANCE:SPOT:BTCUSDT", Decimal("1"), 1_000)
    result = simulate_paper_fill(proposal, PaperPortfolio(Decimal("1000")), snapshot(), limits(), now_ns=1_001, mark_price=Decimal("100"), taker_fee_bps=Decimal("10"), slippage_bps=Decimal("5"))
    assert result.decision.mode == "PAPER"
    assert result.portfolio.position == Decimal("1")
    rejected = simulate_paper_fill(proposal, result.portfolio, snapshot(quality_ok=False), limits(), now_ns=1_001, mark_price=Decimal("100"), taker_fee_bps=Decimal("10"), slippage_bps=Decimal("5"))
    assert rejected.portfolio == result.portfolio
    assert rejected.fill_price is None
