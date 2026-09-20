from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol


class StrategyState(StrEnum):
    IDEA = "IDEA"
    RESEARCHING = "RESEARCHING"
    FAILED = "FAILED"
    VALIDATED = "VALIDATED"
    APPROVED_FOR_SHADOW = "APPROVED_FOR_SHADOW"
    APPROVED_FOR_PAPER = "APPROVED_FOR_PAPER"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class TargetSpec:
    target_price: Decimal
    exit_fraction: Decimal  # e.g., Decimal("0.5") for 50%

    def __post_init__(self) -> None:
        if self.target_price <= 0:
            raise ValueError("target_price must be positive")
        if self.exit_fraction <= 0 or self.exit_fraction > 1:
            raise ValueError("exit_fraction must be in (0, 1]")


@dataclass(frozen=True)
class StrategyIntent:
    intent_id: str
    strategy_id: str
    strategy_version: str
    instrument_candidate: str
    direction: str  # "LONG" or "SHORT"
    signal_ts_ns: int
    signal_expiry_ns: int
    expected_holding_horizon: str
    invalidation_price: Decimal
    stop_price: Decimal
    targets: tuple[TargetSpec, ...]
    entry_preference: str = "MARKET"
    confidence: Decimal = Decimal("1.0")
    market_regime: str = "NORMAL"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in ("LONG", "SHORT"):
            raise ValueError(f"direction must be 'LONG' or 'SHORT', got {self.direction!r}")
        if self.stop_price <= 0:
            raise ValueError("stop_price must be positive")
        if self.invalidation_price <= 0:
            raise ValueError("invalidation_price must be positive")
        if self.signal_expiry_ns <= self.signal_ts_ns:
            raise ValueError("signal_expiry_ns must be after signal_ts_ns")
        total_exit = sum(t.exit_fraction for t in self.targets)
        if total_exit > Decimal("1.0"):
            raise ValueError(f"sum of target exit fractions cannot exceed 1.0, got {total_exit}")

    @classmethod
    def create(
        cls,
        *,
        strategy_id: str,
        strategy_version: str,
        instrument_candidate: str,
        direction: str,
        signal_ts_ns: int,
        signal_expiry_ns: int,
        expected_holding_horizon: str,
        invalidation_price: Decimal,
        stop_price: Decimal,
        targets: tuple[TargetSpec, ...],
        entry_preference: str = "MARKET",
        confidence: Decimal = Decimal("1.0"),
        market_regime: str = "NORMAL",
        metadata: dict[str, Any] | None = None,
    ) -> StrategyIntent:
        # Deterministic intent_id based on semantic signal attributes
        raw_seed = f"{strategy_id}:{strategy_version}:{instrument_candidate}:{direction}:{signal_ts_ns}:{stop_price}"
        intent_id = hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:16]
        return cls(
            intent_id=intent_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            instrument_candidate=instrument_candidate,
            direction=direction,
            signal_ts_ns=signal_ts_ns,
            signal_expiry_ns=signal_expiry_ns,
            expected_holding_horizon=expected_holding_horizon,
            invalidation_price=invalidation_price,
            stop_price=stop_price,
            targets=targets,
            entry_preference=entry_preference,
            confidence=confidence,
            market_regime=market_regime,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class StrategyMetadata:
    strategy_id: str
    version: str
    state: StrategyState
    description: str
    supported_instruments: tuple[str, ...]
    max_holding_horizon: str
    validation_evidence_id: str | None = None


class StrategyProtocol(Protocol):
    @property
    def metadata(self) -> StrategyMetadata: ...

    def evaluate(self, market_state: dict[str, Any], current_positions: list[Any]) -> list[StrategyIntent]: ...


class StrategyRegistry:
    """Registry maintaining life-cycle state of all trading strategies.

    By default, zero strategies qualify as APPROVED_FOR_PAPER.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyProtocol] = {}

    def register(self, strategy: StrategyProtocol) -> None:
        self._strategies[strategy.metadata.strategy_id] = strategy

    def get(self, strategy_id: str) -> StrategyProtocol | None:
        return self._strategies.get(strategy_id)

    def all_metadata(self) -> list[StrategyMetadata]:
        return [s.metadata for s in self._strategies.values()]

    def get_approved_for_paper(self) -> list[StrategyProtocol]:
        return [
            s for s in self._strategies.values()
            if s.metadata.state == StrategyState.APPROVED_FOR_PAPER
        ]

    def get_approved_for_shadow(self) -> list[StrategyProtocol]:
        return [
            s for s in self._strategies.values()
            if s.metadata.state in (StrategyState.APPROVED_FOR_SHADOW, StrategyState.APPROVED_FOR_PAPER)
        ]


class SyntheticTestStrategy:
    """Explicitly isolated synthetic strategy used ONLY for mechanical test harnesses.

    Never approved for paper in production registry.
    """

    def __init__(
        self,
        strategy_id: str = "SYNTHETIC_TEST_STRATEGY",
        version: str = "1.0.0",
        state: StrategyState = StrategyState.APPROVED_FOR_PAPER,
        supported_instruments: tuple[str, ...] = ("BINANCE:SPOT:BTCUSDT", "BINANCE:USD_M_PERP:BTCUSDT"),
    ) -> None:
        self._metadata = StrategyMetadata(
            strategy_id=strategy_id,
            version=version,
            state=state,
            description="Synthetic test strategy strictly for integration tests",
            supported_instruments=supported_instruments,
            max_holding_horizon="1h",
            validation_evidence_id="test-synthetic-only",
        )
        self.next_intents: list[StrategyIntent] = []

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    def queue_intent(self, intent: StrategyIntent) -> None:
        self.next_intents.append(intent)

    def evaluate(self, market_state: dict[str, Any], current_positions: list[Any]) -> list[StrategyIntent]:
        intents = list(self.next_intents)
        self.next_intents.clear()
        return intents
