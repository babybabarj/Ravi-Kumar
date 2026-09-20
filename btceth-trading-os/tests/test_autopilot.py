from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from btceth_os.autopilot.ledger import (
    CompletedTrade,
    PaperLedger,
    PaperPortfolioState,
    PaperPosition,
)
from btceth_os.autopilot.live_approval import (
    LiveApprovalGate,
    MockExecutionAdapter,
    ProposalStatus,
)
from btceth_os.autopilot.modes import OperatingMode, SystemControlState
from btceth_os.autopilot.orchestrator import (
    MarketEvent,
    OrchestratorConfig,
    TradingOrchestrator,
)
from btceth_os.autopilot.position_manager import PositionManager
from btceth_os.autopilot.risk_brain import (
    InstrumentSelector,
    RiskBrain,
    RiskBrainConfig,
)
from btceth_os.autopilot.strategy_registry import (
    StrategyIntent,
    StrategyRegistry,
    StrategyState,
    SyntheticTestStrategy,
    TargetSpec,
)
from btceth_os.sources.binance.account_readonly import BinanceCredentials


def test_no_approved_strategy_generates_no_validated_edge(tmp_path: Path):
    """Section 42 & 66: If zero approved paper strategies, generates NO_VALIDATED_EDGE and zero trades."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
        default_mode=OperatingMode.PAPER_AUTO,
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    orch.startup(now)
    # Default registry has zero strategies
    assert len(orch.registry.get_approved_for_paper()) == 0

    events = [MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)]
    res = orch.step(events, now)

    assert res["open_positions"] == 0
    assert res["latest_decision"] == "NO_VALIDATED_EDGE"
    orch.shutdown(now)


def test_happy_path_paper_cycle(tmp_path: Path):
    """Section 41: Complete paper lifecycle: signal -> risk -> entry -> target -> exit -> P&L."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
        default_mode=OperatingMode.PAPER_AUTO,
        taker_fee_bps=Decimal("10"),
        slippage_bps=Decimal("5"),
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    # Inject synthetic test strategy
    strat = SyntheticTestStrategy(strategy_id="TEST_MOMENTUM")
    orch.registry.register(strat)

    orch.startup(now)

    # Queue an intent: Buy BTC at 50,000, stop at 49,000, target at 51,000
    intent = StrategyIntent.create(
        strategy_id="TEST_MOMENTUM",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("51000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)

    # Step 1: Market event at 50,000 triggers entry
    events = [MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)]
    step1 = orch.step(events, now)

    assert step1["open_positions"] == 1
    open_pos = orch.ledger.get_open_positions()
    assert len(open_pos) == 1
    assert open_pos[0].side == "LONG"
    # Fill price should include 5 bps upward slippage
    expected_fill = Decimal("50000") * (Decimal("1") + Decimal("5") / Decimal("10000"))
    assert open_pos[0].average_entry == expected_fill

    # Step 2: Market price moves to 51,500 (hits TP target)
    now_later = now + 1_000_000_000
    events_tp = [MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("51500"), now_later, is_healthy=True)]
    step2 = orch.step(events_tp, now_later)

    assert step2["open_positions"] == 0
    trades = orch.ledger.get_completed_trades()
    assert len(trades) == 1
    assert trades[0].exit_reason == "TARGET_TP1"
    assert trades[0].net_pnl > Decimal("0")
    assert trades[0].fees > Decimal("0")
    assert trades[0].holding_time_ns == 1_000_000_000

    orch.shutdown(now_later)


def test_paper_stop_loss_trigger(tmp_path: Path):
    """Section 49: Price crosses stop loss triggers automatic exit and records net loss."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
        default_mode=OperatingMode.PAPER_AUTO,
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    strat = SyntheticTestStrategy()
    orch.registry.register(strat)
    orch.startup(now)

    intent = StrategyIntent.create(
        strategy_id="TEST_STOP",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("52000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)

    # Entry at 50,000
    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)], now)
    assert len(orch.ledger.get_open_positions()) == 1

    # Stop triggered at 48,900
    now_exit = now + 500_000_000
    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("48900"), now_exit, is_healthy=True)], now_exit)

    assert len(orch.ledger.get_open_positions()) == 0
    trades = orch.ledger.get_completed_trades()
    assert len(trades) == 1
    assert trades[0].exit_reason == "STOP_LOSS"
    assert trades[0].net_pnl < Decimal("0")

    orch.shutdown(now_exit)


def test_paper_partial_targets(tmp_path: Path):
    """Section 50: Target 1 closes partial percentage; remaining stays open."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
        default_mode=OperatingMode.PAPER_AUTO,
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    strat = SyntheticTestStrategy()
    orch.registry.register(strat)
    orch.startup(now)

    # 50% at 51,000, remaining 50% at 52,000
    intent = StrategyIntent.create(
        strategy_id="TEST_PARTIAL",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(
            TargetSpec(target_price=Decimal("51000"), exit_fraction=Decimal("0.5")),
            TargetSpec(target_price=Decimal("52000"), exit_fraction=Decimal("0.5")),
        ),
    )
    strat.queue_intent(intent)

    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)], now)
    pos = orch.ledger.get_open_positions()[0]
    initial_qty = pos.quantity

    # TP1 reached at 51,200
    now_tp1 = now + 1_000_000_000
    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("51200"), now_tp1, is_healthy=True)], now_tp1)

    open_pos = orch.ledger.get_open_positions()
    assert len(open_pos) == 1
    assert open_pos[0].quantity == initial_qty * Decimal("0.5")

    # TP2 reached at 52,500
    now_tp2 = now + 2_000_000_000
    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("52500"), now_tp2, is_healthy=True)], now_tp2)
    assert len(orch.ledger.get_open_positions()) == 0

    trades = orch.ledger.get_completed_trades()
    assert len(trades) == 2
    assert trades[0].exit_reason == "TARGET_TP2"
    assert trades[1].exit_reason == "TARGET_TP1"

    orch.shutdown(now_tp2)


def test_restart_recovery(tmp_path: Path):
    """Section 48: Crash with open position -> restart recovers full state without duplicating position."""
    db_path = tmp_path / "ledger.sqlite"
    state_path = tmp_path / "state.json"
    now = 1_700_000_000_000_000_000

    config = OrchestratorConfig(db_path=db_path, dashboard_state_path=state_path)
    orch1 = TradingOrchestrator(config)
    strat = SyntheticTestStrategy()
    orch1.registry.register(strat)
    orch1.startup(now)

    intent = StrategyIntent.create(
        strategy_id="TEST_RESTART",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)
    orch1.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)], now)

    open_pos1 = orch1.ledger.get_open_positions()
    assert len(open_pos1) == 1
    pos1_id = open_pos1[0].position_id
    equity1 = orch1.portfolio.equity

    # Simulate termination / crash without explicit clean shutdown
    orch1.ledger.close()

    # Restart in a completely new Orchestrator instance
    orch2 = TradingOrchestrator(config)
    strat2 = SyntheticTestStrategy()
    orch2.registry.register(strat2)
    # Queue the same intent again to test idempotency during recovery
    strat2.queue_intent(intent)

    orch2.startup(now + 10_000_000)

    # Verify recovered open positions
    open_pos2 = orch2.ledger.get_open_positions()
    assert len(open_pos2) == 1
    assert open_pos2[0].position_id == pos1_id
    assert orch2.portfolio.equity == equity1

    # Step again with identical intent: should NOT duplicate position
    orch2.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50200"), now + 20_000_000, is_healthy=True)], now + 20_000_000)
    assert len(orch2.ledger.get_open_positions()) == 1

    orch2.shutdown(now + 30_000_000)


def test_duplicate_signal_idempotency(tmp_path: Path):
    """Section 47: Identical strategy intent submitted twice produces exactly one position."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    strat = SyntheticTestStrategy()
    orch.registry.register(strat)
    orch.startup(now)

    intent = StrategyIntent.create(
        strategy_id="TEST_IDEMPOTENCY",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
    )
    # Queue twice
    strat.queue_intent(intent)
    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)], now)

    strat.queue_intent(intent)
    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now + 1_000_000, is_healthy=True)], now + 1_000_000)

    assert len(orch.ledger.get_open_positions()) == 1
    orch.shutdown(now)


def test_risk_rejection_blocks_trade(tmp_path: Path):
    """Section 43: Invalid stop distance is rejected by Risk Brain and records NO_TRADE."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    strat = SyntheticTestStrategy()
    orch.registry.register(strat)
    orch.startup(now)

    # Stop is ABOVE entry price for LONG -> invalid stop
    intent = StrategyIntent.create(
        strategy_id="TEST_BAD_STOP",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("51000"),
        stop_price=Decimal("51000"),  # Error: stop above 50,000 for LONG
        targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)

    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)], now)

    assert len(orch.ledger.get_open_positions()) == 0
    decisions = orch.ledger.get_recent_decisions()
    assert len(decisions) >= 1
    assert decisions[0].reason_code == "STOP_ABOVE_LONG_ENTRY"
    assert not decisions[0].approved

    orch.shutdown(now)


def test_stale_data_blocks_entry(tmp_path: Path):
    """Section 44: Stale market data timestamp blocks entry."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000
    stale_event_ts = now - 120_000_000_000  # 120s old (> 60s limit)

    strat = SyntheticTestStrategy()
    orch.registry.register(strat)
    orch.startup(now)

    intent = StrategyIntent.create(
        strategy_id="TEST_STALE",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)

    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), stale_event_ts, is_healthy=True)], now)

    assert len(orch.ledger.get_open_positions()) == 0
    decisions = orch.ledger.get_recent_decisions()
    assert decisions[0].reason_code == "STALE_MARKET_DATA"

    orch.shutdown(now)


def test_data_gap_blocks_entry(tmp_path: Path):
    """Section 45: Open data gaps block entry."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    strat = SyntheticTestStrategy()
    orch.registry.register(strat)
    orch.startup(now)

    intent = StrategyIntent.create(
        strategy_id="TEST_GAP",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)

    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True, open_gaps=2)], now)

    assert len(orch.ledger.get_open_positions()) == 0
    assert orch.ledger.get_recent_decisions()[0].reason_code == "OPEN_DATA_GAP"

    orch.shutdown(now)


def test_max_daily_loss_halts_entries(tmp_path: Path):
    """Section 46: Exceeding daily loss threshold halts all new entries."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    strat = SyntheticTestStrategy()
    orch.registry.register(strat)
    orch.startup(now)

    # Force starting portfolio into daily loss > 5%
    orch.portfolio.day_start_equity = Decimal("1000")
    orch.portfolio.equity = Decimal("940")  # 6% loss
    orch.portfolio.cash = Decimal("940")

    intent = StrategyIntent.create(
        strategy_id="TEST_DAILY_LOSS",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)

    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)], now)

    assert len(orch.ledger.get_open_positions()) == 0
    assert orch.ledger.get_recent_decisions()[0].reason_code == "MAX_DAILY_LOSS"

    orch.shutdown(now)


def test_mode_isolation(tmp_path: Path):
    """Section 51: SHADOW_AUTO never creates paper orders or fills."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
        default_mode=OperatingMode.SHADOW_AUTO,
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    strat = SyntheticTestStrategy(state=StrategyState.APPROVED_FOR_SHADOW)
    orch.registry.register(strat)
    orch.startup(now)

    intent = StrategyIntent.create(
        strategy_id="TEST_SHADOW",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)

    orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)], now)

    # In shadow mode, zero paper positions and zero paper orders must exist
    assert len(orch.ledger.get_open_positions()) == 0
    audit = orch.ledger.get_recent_audit_logs()
    assert any(a["event"] == "SHADOW_ORDER_RECORDED" for a in audit)

    orch.shutdown(now)


def test_live_approval_mock_gate(tmp_path: Path):
    """Section 53: Future live approval gate lifecycle with mock adapter isolation."""
    gate = LiveApprovalGate(default_ttl_seconds=10)
    now = 1_700_000_000_000_000_000

    proposal = gate.generate_proposal(
        instrument="BINANCE:USD_M_PERP:BTCUSDT",
        market="usdm",
        side="BUY",
        entry_type="MARKET",
        proposed_quantity=Decimal("0.01"),
        current_price=Decimal("50000"),
        stop_price=Decimal("49000"),
        targets_str="[]",
        max_expected_loss=Decimal("10"),
        estimated_fees=Decimal("0.5"),
        estimated_funding=Decimal("0"),
        estimated_slippage=Decimal("0.25"),
        strategy_id="TEST_LIVE",
        strategy_version="1.0.0",
        market_regime="TRENDING",
        reason="Test proposal",
        signal_ts_ns=now,
        now_ns=now,
    )

    # Check 1: Pending proposal
    assert len(gate.get_pending(now)) == 1

    # Check 2: Expired proposal cannot be approved
    expired_time = now + 15_000_000_000  # 15s > 10s TTL
    ok_exp, reason_exp = gate.approve(proposal.proposal_id, expired_time)
    assert not ok_exp
    assert reason_exp == "APPROVAL_EXPIRED"
    assert proposal.status == ProposalStatus.EXPIRED

    # Check 3: New proposal approved routes to mock adapter ONLY
    prop2 = gate.generate_proposal(
        instrument="BINANCE:USD_M_PERP:BTCUSDT",
        market="usdm",
        side="BUY",
        entry_type="MARKET",
        proposed_quantity=Decimal("0.01"),
        current_price=Decimal("50000"),
        stop_price=Decimal("49000"),
        targets_str="[]",
        max_expected_loss=Decimal("10"),
        estimated_fees=Decimal("0.5"),
        estimated_funding=Decimal("0"),
        estimated_slippage=Decimal("0.25"),
        strategy_id="TEST_LIVE",
        strategy_version="1.0.0",
        market_regime="TRENDING",
        reason="Test proposal 2",
        signal_ts_ns=now,
        now_ns=now,
    )

    ok_app, reason_app = gate.approve(prop2.proposal_id, now + 1_000_000_000)
    assert ok_app
    assert reason_app == "APPROVED_MOCK_DISPATCHED"
    assert len(gate.mock_adapter.dispatched_proposals) == 1
    assert gate.mock_adapter.dispatched_proposals[0].proposal_id == prop2.proposal_id


def test_credential_safety():
    """Section 52: BinanceCredentials api_secret is never displayed in repr or serialized."""
    creds = BinanceCredentials(api_key="TEST_PUBLIC_KEY", api_secret="SUPER_SECRET_VALUE")
    rep = repr(creds)
    assert "SUPER_SECRET_VALUE" not in rep
    assert "TEST_PUBLIC_KEY" in rep


def test_kill_switch(tmp_path: Path):
    """Section 31: Kill switch (pause) immediately prevents new entries."""
    config = OrchestratorConfig(
        db_path=tmp_path / "ledger.sqlite",
        dashboard_state_path=tmp_path / "state.json",
    )
    orch = TradingOrchestrator(config)
    now = 1_700_000_000_000_000_000

    strat = SyntheticTestStrategy()
    orch.registry.register(strat)
    orch.startup(now)

    orch.control.pause("TEST_KILL_SWITCH")

    intent = StrategyIntent.create(
        strategy_id="TEST_KILL",
        strategy_version="1.0.0",
        instrument_candidate="BTCUSDT",
        direction="LONG",
        signal_ts_ns=now,
        signal_expiry_ns=now + 60_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("49000"),
        stop_price=Decimal("49000"),
        targets=(TargetSpec(target_price=Decimal("55000"), exit_fraction=Decimal("1.0")),),
    )
    strat.queue_intent(intent)

    step_res = orch.step([MarketEvent("BINANCE:SPOT:BTCUSDT", Decimal("50000"), now, is_healthy=True)], now)
    assert step_res["status"] == "PAUSED"
    assert len(orch.ledger.get_open_positions()) == 0

    orch.shutdown(now)


def test_instrument_selector_prevents_spot_shorting():
    """Section 14: Short intent must route to perpetuals, never fabricating Spot shorting."""
    intent = StrategyIntent.create(
        strategy_id="TEST_SHORT",
        strategy_version="1.0.0",
        instrument_candidate="BINANCE:SPOT:BTCUSDT",
        direction="SHORT",
        signal_ts_ns=1_000_000_000,
        signal_expiry_ns=2_000_000_000,
        expected_holding_horizon="1h",
        invalidation_price=Decimal("52000"),
        stop_price=Decimal("52000"),
        targets=(TargetSpec(target_price=Decimal("48000"), exit_fraction=Decimal("1.0")),),
    )
    inst, market = InstrumentSelector.select(intent)
    assert market == "usdm"
    assert "PERP" in inst
