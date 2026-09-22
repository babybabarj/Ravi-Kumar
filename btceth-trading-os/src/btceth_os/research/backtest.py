from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import hashlib
from hashlib import sha256
import re
import json
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import pyarrow.parquet as pq

from ..core import canonical_json
from .temporal import (
    FutureUnsettledRealizedFunding,
    ObservableEstimatedFunding,
    RealizedHistoricalFunding,
    TemporalEventContract,
    TemporalIntegrityViolationError,
)


ONE = Decimal("1")
BPS = Decimal("10000")


class PriceSource(str, Enum):
    NEXT_BAR_OPEN = "NEXT_BAR_OPEN"
    NEXT_BAR_TWAP = "NEXT_BAR_TWAP"
    NEXT_BAR_CLOSE = "NEXT_BAR_CLOSE"
    CURRENT_BAR_CLOSE = "CURRENT_BAR_CLOSE"
    BID_ASK_TOUCH = "BID_ASK_TOUCH"
    TRADE_PRINT = "TRADE_PRINT"
    BAR_OPEN_IDEALIZED = "BAR_OPEN_IDEALIZED"
    BAR_CLOSE_CONSERVATIVE = "BAR_CLOSE_CONSERVATIVE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionMode(str, Enum):
    BID_ASK_TOUCH = "BID_ASK_TOUCH"
    TRADE_PRINT = "TRADE_PRINT"
    BAR_OPEN_IDEALIZED = "BAR_OPEN_IDEALIZED"
    BAR_CLOSE_CONSERVATIVE = "BAR_CLOSE_CONSERVATIVE"


LATENCY_VALUES_SOURCE = "ASSUMPTION"

NAMED_LATENCY_PROFILES: dict[str, dict[str, int]] = {
    "IDEALIZED": {
        "decision_latency_ns": 0,
        "execution_latency_ns": 0,
        "fill_latency_ns": 0,
    },
    "BASE_CONSERVATIVE": {
        "decision_latency_ns": 50_000_000,   # 50 ms
        "execution_latency_ns": 100_000_000, # 100 ms
        "fill_latency_ns": 10_000_000,       # 10 ms
    },
    "STRESSED": {
        "decision_latency_ns": 200_000_000,  # 200 ms
        "execution_latency_ns": 500_000_000, # 500 ms
        "fill_latency_ns": 50_000_000,       # 50 ms
    },
}


@dataclass(frozen=True)
class BarObservation:
    bar_open_ts_ns: int
    bar_close_ts_ns: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    source_instrument: Optional[str] = None
    source_dataset_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.bar_close_ts_ns <= self.bar_open_ts_ns:
            raise ValueError("bar_close_ts_ns must be strictly greater than bar_open_ts_ns")
        if self.close <= 0:
            raise ValueError("close must be positive")


@dataclass(frozen=True)
class ExecutionPriceObservation:
    ts_event_ns: int
    price: Optional[Decimal] = None
    price_source: PriceSource = PriceSource.BID_ASK_TOUCH
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    trade_price: Optional[Decimal] = None
    source_instrument: Optional[str] = None
    source_dataset_id: Optional[str] = None
    instrument_id: Optional[str] = None
    dataset_id: Optional[str] = None
    market_type: Optional[str] = "USD_M_PERP"
    venue: Optional[str] = "BINANCE"
    sequence_id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive")
        if self.bid is not None and self.bid <= 0:
            raise ValueError("bid must be positive")
        if self.ask is not None and self.ask <= 0:
            raise ValueError("ask must be positive")
        if self.trade_price is not None and self.trade_price <= 0:
            raise ValueError("trade_price must be positive")
        if self.price is None and self.bid is None and self.ask is None and self.trade_price is None:
            raise ValueError("At least one price field must be provided")

    @property
    def resolved_instrument_id(self) -> Optional[str]:
        return self.instrument_id or self.source_instrument

    @property
    def resolved_dataset_id(self) -> Optional[str]:
        return self.dataset_id or self.source_dataset_id


@dataclass(frozen=True)
class ExecutionAssumptions:
    price_source: PriceSource = PriceSource.NEXT_BAR_OPEN
    execution_mode: ExecutionMode = ExecutionMode.BID_ASK_TOUCH
    execution_delay_bars: int = 1
    decision_latency_ns: int = 0
    execution_latency_ns: int = 0
    fill_latency_ns: int = 0
    latency_profile: Optional[str] = None
    allow_open_fallback: bool = False
    signal_timeframe: str = "1h"
    execution_timeframe: str = "1h"
    execution_model_version: str = "ROUND3B_0E_EXECUTION_ARRIVAL_CAUSAL"
    latency_values_source: str = LATENCY_VALUES_SOURCE

    def __post_init__(self) -> None:
        if self.latency_profile is not None and self.latency_profile in NAMED_LATENCY_PROFILES:
            profile = NAMED_LATENCY_PROFILES[self.latency_profile]
            if self.decision_latency_ns == 0 and self.execution_latency_ns == 0 and self.fill_latency_ns == 0:
                object.__setattr__(self, "decision_latency_ns", profile["decision_latency_ns"])
                object.__setattr__(self, "execution_latency_ns", profile["execution_latency_ns"])
                object.__setattr__(self, "fill_latency_ns", profile["fill_latency_ns"])


@dataclass(frozen=True)
class ExecutionObservation:
    bar_index: int
    decision_ts_ns: int
    fill_ts_ns: int
    price_source: PriceSource
    fill_price: Decimal
    fill_price_observation_ts_ns: int = 0
    source_instrument: Optional[str] = None
    source_dataset_id: Optional[str] = None
    signal_available_ts_ns: Optional[int] = None
    order_submit_ts_ns: Optional[int] = None
    exchange_arrival_ts_ns: Optional[int] = None
    execution_eligible_ts_ns: Optional[int] = None
    raw_observed_price: Optional[Decimal] = None
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    side: Optional[OrderSide] = None
    market_type: Optional[str] = "USD_M_PERP"
    venue: Optional[str] = "BINANCE"
    terminal: bool = False
    price_observation_ts_ns: Optional[int] = None

    def __post_init__(self) -> None:
        if self.price_observation_ts_ns is not None and not self.fill_price_observation_ts_ns:
            object.__setattr__(self, "fill_price_observation_ts_ns", self.price_observation_ts_ns)
        elif self.fill_price_observation_ts_ns and self.price_observation_ts_ns is None:
            object.__setattr__(self, "price_observation_ts_ns", self.fill_price_observation_ts_ns)

        if self.fill_price <= 0:
            raise ValueError("fill_price must be positive")

        sig_avail = self.signal_available_ts_ns if self.signal_available_ts_ns is not None else self.decision_ts_ns
        ord_sub = self.order_submit_ts_ns if self.order_submit_ts_ns is not None else self.decision_ts_ns
        arr_ts = self.exchange_arrival_ts_ns if self.exchange_arrival_ts_ns is not None else self.decision_ts_ns
        elig_ts = self.execution_eligible_ts_ns if self.execution_eligible_ts_ns is not None else arr_ts
        obs_ts = self.fill_price_observation_ts_ns

        # Strict temporal order validation:
        # signal_available_ts_ns <= decision_ts_ns <= order_submit_ts_ns <= exchange_arrival_ts_ns <= execution_eligible_ts_ns <= price_observation_ts_ns <= fill_ts_ns
        if self.decision_ts_ns < sig_avail:
            raise TemporalIntegrityViolationError(
                f"PRICE_CAUSALITY_VIOLATION: decision_ts_ns ({self.decision_ts_ns}) < signal_available_ts_ns ({sig_avail})"
            )
        if ord_sub < self.decision_ts_ns:
            raise TemporalIntegrityViolationError(
                f"PRICE_CAUSALITY_VIOLATION: order_submit_ts_ns ({ord_sub}) < decision_ts_ns ({self.decision_ts_ns})"
            )
        if arr_ts < ord_sub:
            raise TemporalIntegrityViolationError(
                f"PRICE_CAUSALITY_VIOLATION: exchange_arrival_ts_ns ({arr_ts}) < order_submit_ts_ns ({ord_sub})"
            )
        if elig_ts < arr_ts:
            raise TemporalIntegrityViolationError(
                f"PRICE_CAUSALITY_VIOLATION: execution_eligible_ts_ns ({elig_ts}) < exchange_arrival_ts_ns ({arr_ts})"
            )
        if obs_ts < elig_ts:
            raise TemporalIntegrityViolationError(
                f"PRICE_CAUSALITY_VIOLATION: price_observation_ts_ns ({obs_ts}) < execution_eligible_ts_ns ({elig_ts})"
            )
        if self.fill_ts_ns < obs_ts:
            raise TemporalIntegrityViolationError(
                f"PRICE_CAUSALITY_VIOLATION: fill_ts_ns ({self.fill_ts_ns}) < price_observation_ts_ns ({obs_ts})"
            )


def select_first_executable_observation(
    execution_stream: Sequence[ExecutionPriceObservation],
    *,
    execution_eligible_ts_ns: int,
    order_side: OrderSide,
    instrument_id: Optional[str] = None,
    market_type: Optional[str] = "USD_M_PERP",
    venue: Optional[str] = "BINANCE",
    execution_mode: ExecutionMode = ExecutionMode.BID_ASK_TOUCH,
) -> tuple[ExecutionPriceObservation, Decimal, Decimal]:
    """Centralized auditable helper to select first eligible observation.

    Returns: (matching_obs, fill_price, raw_observed_price)
    Fails closed with TemporalIntegrityViolationError if:
    - Stream is empty: NO_VALID_EXECUTION_OBSERVATION
    - Stream is not monotonic: EXECUTION_STREAM_NOT_MONOTONIC
    - Stream has ambiguous duplicate timestamps: AMBIGUOUS_EXECUTION_OBSERVATION
    - No eligible observation found >= execution_eligible_ts_ns matching criteria: NO_VALID_EXECUTION_OBSERVATION
    """
    if not execution_stream:
        raise TemporalIntegrityViolationError("NO_VALID_EXECUTION_OBSERVATION: Execution stream is empty")

    # 1. Monotonicity & Duplicate Timestamp Validation
    for i in range(len(execution_stream) - 1):
        curr_obs = execution_stream[i]
        next_obs = execution_stream[i + 1]
        if next_obs.ts_event_ns < curr_obs.ts_event_ns:
            raise TemporalIntegrityViolationError(
                f"EXECUTION_STREAM_NOT_MONOTONIC: Observation at index {i + 1} ({next_obs.ts_event_ns}) "
                f"< observation at index {i} ({curr_obs.ts_event_ns})"
            )
        if next_obs.ts_event_ns == curr_obs.ts_event_ns:
            curr_seq = curr_obs.sequence_id
            next_seq = next_obs.sequence_id
            if curr_seq is None or next_seq is None or next_seq <= curr_seq:
                if (curr_obs.price != next_obs.price or curr_obs.bid != next_obs.bid or curr_obs.ask != next_obs.ask or curr_obs.trade_price != next_obs.trade_price):
                    raise TemporalIntegrityViolationError(
                        f"AMBIGUOUS_EXECUTION_OBSERVATION: Duplicate timestamp ({curr_obs.ts_event_ns}) "
                        f"with differing prices and no strictly increasing sequence_id"
                    )

    # 2. Candidate Filtering
    for s_obs in execution_stream:
        # Pre-arrival observations are strictly rejected
        if s_obs.ts_event_ns < execution_eligible_ts_ns:
            continue

        # Same-instrument check
        obs_inst = s_obs.instrument_id or s_obs.source_instrument
        if instrument_id is not None and obs_inst is not None:
            if obs_inst != instrument_id:
                continue

        # Market-type check
        if market_type is not None and s_obs.market_type is not None:
            if s_obs.market_type != market_type:
                continue

        # Venue check
        if venue is not None and s_obs.venue is not None:
            if s_obs.venue != venue:
                continue

        # Side-aware executable touch derivation
        raw_price = s_obs.price or s_obs.trade_price
        fill_price: Optional[Decimal] = None

        if order_side == OrderSide.BUY:
            if execution_mode == ExecutionMode.BID_ASK_TOUCH:
                if s_obs.ask is not None:
                    fill_price = s_obs.ask
                    raw_price = s_obs.ask
                elif s_obs.price is not None:
                    fill_price = s_obs.price
                    raw_price = s_obs.price
            else:
                fill_price = s_obs.trade_price or s_obs.price
                raw_price = fill_price
        elif order_side == OrderSide.SELL:
            if execution_mode == ExecutionMode.BID_ASK_TOUCH:
                if s_obs.bid is not None:
                    fill_price = s_obs.bid
                    raw_price = s_obs.bid
                elif s_obs.price is not None:
                    fill_price = s_obs.price
                    raw_price = s_obs.price
            else:
                fill_price = s_obs.trade_price or s_obs.price
                raw_price = fill_price
        else:
            fill_price = s_obs.price or s_obs.trade_price
            raw_price = fill_price

        if fill_price is not None and fill_price > 0:
            return s_obs, fill_price, raw_price

    raise TemporalIntegrityViolationError(
        f"NO_VALID_EXECUTION_OBSERVATION: No matching observation found >= {execution_eligible_ts_ns} "
        f"for instrument={instrument_id}, side={order_side}"
    )


@dataclass(frozen=True)
class Candle:
    ts_event_ns: int
    close: Decimal
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    bar_open_ts_ns: Optional[int] = None
    bar_close_ts_ns: Optional[int] = None
    source_instrument: Optional[str] = None
    source_dataset_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.close <= 0:
            raise ValueError("candle close must be positive")
        if self.open is not None and self.open <= 0:
            raise ValueError("candle open must be positive")

    @property
    def resolved_bar_open_ts_ns(self) -> int:
        return self.bar_open_ts_ns if self.bar_open_ts_ns is not None else self.ts_event_ns

    @property
    def resolved_bar_close_ts_ns(self) -> int:
        if self.bar_close_ts_ns is not None:
            return self.bar_close_ts_ns
        return self.resolved_bar_open_ts_ns + 3_600_000_000_000


def resolve_candle_close_ts(
    candle: Candle,
    next_candle: Optional[Candle] = None,
    bar_duration_ns: Optional[int] = None,
) -> int:
    if candle.bar_close_ts_ns is not None:
        return candle.bar_close_ts_ns
    if next_candle is not None and next_candle.ts_event_ns > candle.ts_event_ns:
        return next_candle.resolved_bar_open_ts_ns
    if bar_duration_ns is not None and bar_duration_ns > 0:
        return candle.resolved_bar_open_ts_ns + bar_duration_ns
    return candle.resolved_bar_open_ts_ns + 3_600_000_000_000


@dataclass(frozen=True)
class CostModel:
    """Conservative per-turnover taker, slippage, and per-bar carry costs in basis points."""

    taker_fee_bps: Decimal
    slippage_bps: Decimal
    carry_bps_per_bar: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if min(self.taker_fee_bps, self.slippage_bps, self.carry_bps_per_bar) < 0:
            raise ValueError("costs cannot be negative")

    @property
    def turnover_rate(self) -> Decimal:
        return (self.taker_fee_bps + self.slippage_bps) / BPS


@dataclass(frozen=True)
class BacktestResult:
    bars: int
    trades: int
    gross_return: Decimal
    net_return: Decimal
    total_cost: Decimal
    max_drawdown: Decimal


@dataclass(frozen=True)
class WalkForwardFold:
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    lookback: int
    result: BacktestResult


@dataclass(frozen=True)
class WalkForwardResult:
    folds: tuple[WalkForwardFold, ...]
    net_return: Decimal
    trades: int


def load_kline_candles(path: Path | str) -> tuple[str, tuple[Candle, ...]]:
    """Read one provenance-homogeneous historical Silver kline object for offline research."""
    schema_names = pq.read_schema(path).names
    cols = ["source_object_sha256", "ts_event_ns", "close"]
    has_open = "open" in schema_names
    if has_open:
        cols.append("open")
    table = pq.read_table(path, columns=cols)
    hashes = set(table.column("source_object_sha256").to_pylist())
    if len(hashes) != 1 or not re.fullmatch(r"[0-9a-f]{64}", next(iter(hashes), "")):
        raise ValueError("Silver research input must have one valid source SHA-256")
    ts_list = table.column("ts_event_ns").to_pylist()
    close_list = table.column("close").to_pylist()
    open_list = table.column("open").to_pylist() if has_open else [None] * len(ts_list)
    candles = tuple(
        Candle(
            int(timestamp),
            Decimal(str(close)),
            open=Decimal(str(op)) if op is not None else None,
        )
        for timestamp, close, op in zip(ts_list, close_list, open_list, strict=True)
    )
    if len(candles) < 2 or any(later.ts_event_ns <= earlier.ts_event_ns for earlier, later in zip(candles, candles[1:])):
        raise ValueError("Silver kline input must contain at least two strictly increasing candles")
    return next(iter(hashes)), candles


def load_guarded_kline_candles(
    path: Path | str,
    dataset_id: str,
    operation: Any = "backtest",
    open_col: str = "open",
    close_col: str = "close",
) -> tuple[str, tuple[Candle, ...]]:
    """Read a guarded historical Parquet partition for causal research backtests."""
    from .data_guard import load_research_parquet
    tbl = load_research_parquet(file_path=path, dataset_id=dataset_id, operation=operation)
    schema_names = tbl.column_names
    has_close = close_col in schema_names
    has_open = open_col in schema_names
    if not has_close and "spot_close" in schema_names:
        close_col = "spot_close"
        has_close = True
    if not has_open and "spot_open" in schema_names:
        open_col = "spot_open"
        has_open = True
    if not has_close:
        raise ValueError(f"Could not find close price column '{close_col}' in dataset '{dataset_id}'")
    
    ts_list = tbl["ts_event_ns"].to_pylist()
    close_list = tbl[close_col].to_pylist()
    open_list = tbl[open_col].to_pylist() if has_open else [None] * len(ts_list)
    
    candles = tuple(
        Candle(
            ts_event_ns=int(ts),
            close=Decimal(str(c)),
            open=Decimal(str(o)) if o is not None else None,
        )
        for ts, c, o in zip(ts_list, close_list, open_list, strict=True)
    )
    file_sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return file_sha, candles


def write_walk_forward_report(
    destination: Path | str,
    source_object_sha256: str,
    *,
    train_bars: int,
    test_bars: int,
    candidate_lookbacks: Iterable[int],
    costs: CostModel,
    result: WalkForwardResult,
) -> Path:
    """Persist one immutable, deterministic research result tied to its exact RAW source hash."""
    candidates = tuple(sorted(set(candidate_lookbacks)))
    config = {
        "source_object_sha256": source_object_sha256, "train_bars": train_bars,
        "test_bars": test_bars, "candidate_lookbacks": candidates,
        "costs": {"taker_fee_bps": str(costs.taker_fee_bps), "slippage_bps": str(costs.slippage_bps), "carry_bps_per_bar": str(costs.carry_bps_per_bar)},
    }
    if not re.fullmatch(r"[0-9a-f]{64}", source_object_sha256):
        raise ValueError("source_object_sha256 must be a lowercase SHA-256 hex digest")
    payload = {
        "schema_version": "research.v1", "run_id": sha256(canonical_json(config).encode()).hexdigest(), "config": config,
        "result": {"net_return": str(result.net_return), "trades": result.trades, "folds": [
            {"train": [fold.train_start, fold.train_end], "test": [fold.test_start, fold.test_end], "lookback": fold.lookback,
             "net_return": str(fold.result.net_return), "max_drawdown": str(fold.result.max_drawdown), "trades": fold.result.trades}
            for fold in result.folds
        ]},
    }
    output = Path(destination)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite research report: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return output


def run_backtest(candles: Sequence[Candle], positions: Sequence[int], costs: CostModel) -> BacktestResult:
    """[FROZEN LEGACY ENGINE] Legacy non-causal mark-to-market backtest engine.
    
    Mark-to-market a signal at the next close; force-flat at the end and charge every turnover.
    NOTE: This engine is preserved frozen for backwards compatibility with historical test asserts.
    DO NOT USE FOR ACCEPTANCE VERIFICATION OR CAUSAL RESEARCH.
    """
    if len(candles) != len(positions):
        raise ValueError("candles and positions must have equal length")
    if len(candles) < 2:
        raise ValueError("at least two candles are required")
    if any(position not in {-1, 0, 1} for position in positions):
        raise ValueError("positions must be -1, 0, or 1")
    if any(later.ts_event_ns <= earlier.ts_event_ns for earlier, later in zip(candles, candles[1:])):
        raise ValueError("candles must be strictly increasing")

    gross_equity = net_equity = peak = ONE
    max_drawdown = total_cost = Decimal("0")
    previous = 0
    trades = 0
    for index, candle in enumerate(candles[:-1]):
        position = positions[index]
        turnover = abs(position - previous)
        if turnover:
            trades += 1
        charge = Decimal(turnover) * costs.turnover_rate + abs(position) * costs.carry_bps_per_bar / BPS
        gross_period_return = Decimal(position) * (candles[index + 1].close / candle.close - ONE)
        net_period_return = gross_period_return - charge
        if ONE + net_period_return <= 0:
            raise ValueError("cost model or return would exhaust capital")
        gross_equity *= ONE + gross_period_return
        net_equity *= ONE + net_period_return
        total_cost += charge
        peak = max(peak, net_equity)
        max_drawdown = max(max_drawdown, ONE - net_equity / peak)
        previous = position
    if previous:
        trades += 1
        exit_cost = Decimal(abs(previous)) * costs.turnover_rate
        net_equity *= ONE - exit_cost
        total_cost += exit_cost
        max_drawdown = max(max_drawdown, ONE - net_equity / peak)
    return BacktestResult(
        bars=len(candles), trades=trades, gross_return=gross_equity - ONE,
        net_return=net_equity - ONE, total_cost=total_cost, max_drawdown=max_drawdown,
    )


def walk_forward_causal(
    candles: Sequence[Candle],
    *,
    train_bars: int,
    test_bars: int,
    candidate_lookbacks: Iterable[int],
    costs: CostModel,
    assumptions: Optional[ExecutionAssumptions] = None,
) -> WalkForwardResult:
    """Select one momentum lookback on each train block and evaluate on following test block strictly using run_causal_backtest."""
    candidates = tuple(sorted(set(candidate_lookbacks)))
    if not candidates or min(candidates) < 1 or train_bars <= max(candidates) or test_bars < 2:
        raise ValueError("need positive lookbacks, train_bars above them, and at least two test bars")
    exec_assumptions = assumptions or ExecutionAssumptions(
        price_source=PriceSource.NEXT_BAR_OPEN,
        decision_latency_ns=0,
        allow_open_fallback=False,
    )
    folds: list[WalkForwardFold] = []
    for start in range(0, len(candles) - train_bars - test_bars + 1, test_bars):
        train_end, test_end = start + train_bars, start + train_bars + test_bars
        scored = []
        for lookback in candidates:
            pos = _momentum_positions(candles[start:train_end], lookback)
            pos_train = list(pos)
            for k in range(1, exec_assumptions.execution_delay_bars + 2):
                if k <= len(pos_train):
                    pos_train[-k] = 0
            c_res = run_causal_backtest(candles[start:train_end], pos_train, costs, assumptions=exec_assumptions)
            scored.append((c_res.result.net_return, -lookback, lookback))
        selected = max(scored)[2]

        positions = _momentum_positions(candles[:test_end], selected)
        pos_test = list(positions[train_end:test_end])
        exec_stream = None
        if test_end < len(candles):
            fol_c = candles[test_end]
            exec_stream = [
                ExecutionPriceObservation(
                    ts_event_ns=fol_c.resolved_bar_open_ts_ns,
                    price=fol_c.open or fol_c.close,
                    bid=fol_c.open or fol_c.close,
                    ask=fol_c.open or fol_c.close,
                    trade_price=fol_c.open or fol_c.close,
                    price_source=PriceSource.NEXT_BAR_OPEN,
                    instrument_id=fol_c.source_instrument,
                    market_type="USD_M_PERP",
                    venue="BINANCE",
                )
            ]
        else:
            for k in range(1, exec_assumptions.execution_delay_bars + 2):
                if k <= len(pos_test):
                    pos_test[-k] = 0

        c_test_res = run_causal_backtest(
            candles[train_end:test_end],
            pos_test,
            costs,
            assumptions=exec_assumptions,
            execution_stream=exec_stream,
        )
        folds.append(WalkForwardFold(start, train_end, train_end, test_end, selected, c_test_res.result))
    if not folds:
        raise ValueError("not enough candles for one walk-forward fold")
    equity = ONE
    for fold in folds:
        equity *= ONE + fold.result.net_return
    return WalkForwardResult(tuple(folds), equity - ONE, sum(fold.result.trades for fold in folds))


def walk_forward_momentum(
    candles: Sequence[Candle],
    *,
    train_bars: int,
    test_bars: int,
    candidate_lookbacks: Iterable[int],
    costs: CostModel,
    assumptions: Optional[ExecutionAssumptions] = None,
) -> WalkForwardResult:
    """Select one momentum lookback on each train block and report only its following test block (routed to causal engine)."""
    return walk_forward_causal(
        candles,
        train_bars=train_bars,
        test_bars=test_bars,
        candidate_lookbacks=candidate_lookbacks,
        costs=costs,
        assumptions=assumptions or ExecutionAssumptions(
            price_source=PriceSource.NEXT_BAR_OPEN,
            decision_latency_ns=0,
            allow_open_fallback=False,
        ),
    )


def _select_lookback(candles: Sequence[Candle], start: int, end: int, candidates: Sequence[int], costs: CostModel) -> int:
    scored = []
    exec_assumptions = ExecutionAssumptions(price_source=PriceSource.NEXT_BAR_OPEN, decision_latency_ns=0, allow_open_fallback=False)
    for lookback in candidates:
        positions = list(_momentum_positions(candles[:end], lookback))
        pos_slice = list(positions[start:end])
        for k in range(1, 3):
            if k <= len(pos_slice):
                pos_slice[-k] = 0
        scored.append((run_causal_backtest(candles[start:end], pos_slice, costs, assumptions=exec_assumptions).result.net_return, -lookback, lookback))
    return max(scored)[2]


def _momentum_positions(candles: Sequence[Candle], lookback: int) -> list[int]:
    return [0 if index < lookback else (1 if candle.close > candles[index - lookback].close else -1) for index, candle in enumerate(candles)]


@dataclass(frozen=True)
class CausalExecutionRecord:
    bar_index: int
    contract: TemporalEventContract
    observation: ExecutionObservation
    position_before: int
    position_after: int
    fill_price: Decimal
    turnover: int
    charge: Decimal
    signal_available_ts_ns: int = 0
    decision_ts_ns: int = 0
    order_submit_ts_ns: int = 0
    exchange_arrival_ts_ns: int = 0
    execution_eligible_ts_ns: int = 0
    price_observation_ts_ns: int = 0
    fill_ts_ns: int = 0
    instrument_id: Optional[str] = None
    dataset_id: Optional[str] = None
    side: Optional[str] = None
    raw_observed_price: Optional[Decimal] = None
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    simulated_fill_price: Optional[Decimal] = None
    slippage: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    terminal: bool = False


@dataclass(frozen=True)
class CausalBacktestResult:
    result: BacktestResult
    contracts: tuple[TemporalEventContract, ...]
    executions: tuple[CausalExecutionRecord, ...]
    assumptions: ExecutionAssumptions = ExecutionAssumptions()
    execution_model_version: str = "ROUND3B_0E_EXECUTION_ARRIVAL_CAUSAL"
    signal_timeframe: str = "1h"
    execution_timeframe: str = "1h"
    signal_availability_rule: str = "BAR_CLOSE_TIMESTAMP"
    decision_latency: str = "DECISION_LATENCY_EXPLICIT"
    execution_price_source: str = "NEXT_BAR_OPEN"
    execution_observation_rule: str = "AUTHENTIC_MARKET_OBSERVATION"
    slippage_model: str = "CONSERVATIVE_BPS"
    cost_policy_sha256: Optional[str] = None

    def __iter__(self):
        return iter((self.result, self.contracts))


def run_causal_backtest(
    candles: Sequence[Candle],
    positions: Sequence[int],
    costs: CostModel,
    *,
    assumptions: Optional[ExecutionAssumptions] = None,
    decision_latency_ns: Optional[int] = None,
    execution_latency_ns: Optional[int] = None,
    fill_latency_ns: Optional[int] = None,
    execution_stream: Optional[Sequence[ExecutionPriceObservation]] = None,
    funding_signals: Optional[Sequence[Any]] = None,
    override_contracts: Optional[Sequence[TemporalEventContract]] = None,
) -> CausalBacktestResult:
    """Run an offline research backtest enforcing true market-time causality, order-arrival timing, and authentic terminal settlement.

    Invariants enforced:
    1. Clock hierarchy: source_ts <= signal_available_ts <= decision_ts <= order_submit_ts <= exchange_arrival_ts <= execution_eligible_ts <= price_observation_ts <= fill_ts.
    2. Explicit bar timing: Signal from bar N close is available strictly at bar_close_ts_ns (never bar_open_ts_ns).
    3. Price observation authenticity: Execution prices originate from authentic market observations >= execution_eligible_ts_ns.
    4. Execution stream eligibility: Observations prior to exchange arrival are strictly rejected.
    5. Side-aware execution: BUY executes against ask; SELL executes against bid (or trade print).
    6. Monotonic stream and duplicate timestamp policy enforced.
    7. Same-instrument and same-market-type execution enforced.
    8. No unsafe fallback: Missing execution observations fail closed with NO_VALID_EXECUTION_OBSERVATION.
    9. Reject current bar close: CURRENT_BAR_CLOSE cannot be used as execution price for close-derived signals.
    10. Functional execution delay: execution_delay_bars = k delays signal execution by k bars.
    11. Return accrual: Return from candle.close to fill_price accrues to previous; fill_price to next_close accrues to target.
    12. Terminal settlement: Positions held at simulation end exit at authentic post-arrival observation; mark-to-fill return updates equity; exit cost charged once; terminal drawdown included.
    13. Causal funding boundary: Strategies receive only ObservableEstimatedFunding or RealizedHistoricalFunding.
    """
    if len(candles) != len(positions):
        raise ValueError("candles and positions must have equal length")
    if len(candles) < 2:
        raise ValueError("at least two candles are required")
    if any(position not in {-1, 0, 1} for position in positions):
        raise ValueError("positions must be -1, 0, or 1")
    if any(later.ts_event_ns <= earlier.ts_event_ns for earlier, later in zip(candles, candles[1:])):
        raise ValueError("candles must be strictly increasing")

    # Validate strategy funding boundary if funding signals provided
    if funding_signals is not None:
        for idx, sig in enumerate(funding_signals):
            if isinstance(sig, FutureUnsettledRealizedFunding):
                raise TemporalIntegrityViolationError(
                    f"STRATEGY_FUNDING_BOUNDARY_VIOLATION: FutureUnsettledRealizedFunding (settlement: {sig.settlement_ts_ns}) "
                    f"cannot cross strategy boundary before settlement."
                )
            if not isinstance(sig, (ObservableEstimatedFunding, RealizedHistoricalFunding)):
                raise TemporalIntegrityViolationError(
                    f"STRATEGY_FUNDING_BOUNDARY_VIOLATION: Signal at index {idx} must be typed "
                    f"ObservableEstimatedFunding or RealizedHistoricalFunding, got {type(sig).__name__}"
                )

    if assumptions is None:
        d_lat = decision_latency_ns if decision_latency_ns is not None else 0
        e_lat = execution_latency_ns if execution_latency_ns is not None else 0
        f_lat = fill_latency_ns if fill_latency_ns is not None else 0
        exec_assumptions = ExecutionAssumptions(
            price_source=PriceSource.NEXT_BAR_OPEN,
            decision_latency_ns=d_lat,
            execution_latency_ns=e_lat,
            fill_latency_ns=f_lat,
            allow_open_fallback=False,
        )
    else:
        d_lat = decision_latency_ns if decision_latency_ns is not None else assumptions.decision_latency_ns
        e_lat = execution_latency_ns if execution_latency_ns is not None else assumptions.execution_latency_ns
        f_lat = fill_latency_ns if fill_latency_ns is not None else assumptions.fill_latency_ns
        exec_assumptions = ExecutionAssumptions(
            price_source=assumptions.price_source,
            execution_mode=assumptions.execution_mode,
            execution_delay_bars=assumptions.execution_delay_bars,
            decision_latency_ns=d_lat,
            execution_latency_ns=e_lat,
            fill_latency_ns=f_lat,
            latency_profile=assumptions.latency_profile,
            allow_open_fallback=False,
            signal_timeframe=assumptions.signal_timeframe,
            execution_timeframe=assumptions.execution_timeframe,
            execution_model_version=assumptions.execution_model_version,
        )

    # Forbid CURRENT_BAR_CLOSE for close-derived signals
    if exec_assumptions.price_source == PriceSource.CURRENT_BAR_CLOSE:
        raise TemporalIntegrityViolationError(
            "PRICE_CAUSALITY_VIOLATION: CURRENT_BAR_CLOSE cannot be used as execution price for close-derived signal"
        )

    contracts: list[TemporalEventContract] = []
    executions: list[CausalExecutionRecord] = []

    # If override contracts are provided (e.g. adversarial test injection), validate each
    if override_contracts is not None:
        for oc in override_contracts:
            oc.validate()
            contracts.append(oc)

    gross_equity = net_equity = peak = ONE
    max_drawdown = total_cost = Decimal("0")
    previous = 0
    trades = 0

    delay = max(1, exec_assumptions.execution_delay_bars)

    for index, candle in enumerate(candles[:-1]):
        next_candle = candles[index + 1]

        # Functional execution delay: target position executed at next_candle
        sig_idx = index - delay + 1
        target_position = positions[sig_idx] if sig_idx >= 0 else 0

        turnover = abs(target_position - previous)
        if turnover:
            trades += 1
            order_side = OrderSide.BUY if target_position > previous else OrderSide.SELL
        else:
            order_side = OrderSide.BUY

        # Explicit bar timing: signal available strictly at bar close
        source_ts_ns = candle.resolved_bar_open_ts_ns
        available_ts_ns = resolve_candle_close_ts(candle, next_candle)
        decision_ts_ns = available_ts_ns + exec_assumptions.decision_latency_ns
        order_submit_ts_ns = decision_ts_ns
        exchange_arrival_ts_ns = order_submit_ts_ns + exec_assumptions.execution_latency_ns
        execution_eligible_ts_ns = exchange_arrival_ts_ns

        # Resolve executable fill price and authentic observation timestamp
        source_inst = candle.source_instrument
        source_ds_id = candle.source_dataset_id
        obs_bid = None
        obs_ask = None
        raw_observed_price = None

        if execution_stream is not None:
            s_obs, fill_price, raw_observed_price = select_first_executable_observation(
                execution_stream,
                execution_eligible_ts_ns=execution_eligible_ts_ns,
                order_side=order_side,
                instrument_id=source_inst,
                market_type="USD_M_PERP",
                venue="BINANCE",
                execution_mode=exec_assumptions.execution_mode,
            )
            fill_obs_ts = s_obs.ts_event_ns
            fill_ts_ns = max(fill_obs_ts, exchange_arrival_ts_ns) + exec_assumptions.fill_latency_ns
            source_inst = s_obs.instrument_id or s_obs.source_instrument or source_inst
            source_ds_id = s_obs.dataset_id or s_obs.source_dataset_id or source_ds_id
            obs_bid = s_obs.bid
            obs_ask = s_obs.ask

        elif exec_assumptions.price_source in (PriceSource.NEXT_BAR_OPEN, PriceSource.BAR_OPEN_IDEALIZED):
            if next_candle.resolved_bar_open_ts_ns < execution_eligible_ts_ns:
                raise TemporalIntegrityViolationError(
                    f"PRICE_CAUSALITY_VIOLATION: Next-bar open ({next_candle.resolved_bar_open_ts_ns}) "
                    f"occurred before execution eligibility ({execution_eligible_ts_ns})"
                )
            if next_candle.open is not None:
                fill_price = next_candle.open
                raw_observed_price = next_candle.open
            else:
                raise TemporalIntegrityViolationError(
                    f"NO_VALID_EXECUTION_OBSERVATION: Candle at index {index + 1} has no open price"
                )
            fill_obs_ts = next_candle.resolved_bar_open_ts_ns
            fill_ts_ns = max(fill_obs_ts, exchange_arrival_ts_ns) + exec_assumptions.fill_latency_ns

        elif exec_assumptions.price_source in (PriceSource.NEXT_BAR_CLOSE, PriceSource.BAR_CLOSE_CONSERVATIVE):
            next_close_ts = resolve_candle_close_ts(next_candle, candles[index + 2] if index + 2 < len(candles) else None)
            if next_close_ts < execution_eligible_ts_ns:
                raise TemporalIntegrityViolationError(
                    f"PRICE_CAUSALITY_VIOLATION: Next-bar close ({next_close_ts}) "
                    f"occurred before execution eligibility ({execution_eligible_ts_ns})"
                )
            fill_price = next_candle.close
            raw_observed_price = next_candle.close
            fill_obs_ts = next_close_ts
            fill_ts_ns = max(fill_obs_ts, exchange_arrival_ts_ns) + exec_assumptions.fill_latency_ns

        else:
            raise ValueError(f"Unsupported price source: {exec_assumptions.price_source}")

        contract = TemporalEventContract(
            source_ts_ns=source_ts_ns,
            available_ts_ns=available_ts_ns,
            decision_ts_ns=decision_ts_ns,
            execution_ts_ns=exchange_arrival_ts_ns,
            fill_ts_ns=fill_ts_ns,
        )
        contract.validate()
        contracts.append(contract)

        obs = ExecutionObservation(
            bar_index=index,
            decision_ts_ns=decision_ts_ns,
            fill_ts_ns=fill_ts_ns,
            price_source=exec_assumptions.price_source,
            fill_price=fill_price,
            fill_price_observation_ts_ns=fill_obs_ts,
            source_instrument=source_inst,
            source_dataset_id=source_ds_id,
            signal_available_ts_ns=available_ts_ns,
            order_submit_ts_ns=order_submit_ts_ns,
            exchange_arrival_ts_ns=exchange_arrival_ts_ns,
            execution_eligible_ts_ns=execution_eligible_ts_ns,
            raw_observed_price=raw_observed_price if raw_observed_price is not None else fill_price,
            bid=obs_bid,
            ask=obs_ask,
            side=order_side if turnover else None,
            market_type="USD_M_PERP",
            venue="BINANCE",
            terminal=False,
        )

        charge = Decimal(turnover) * costs.turnover_rate + abs(Decimal(target_position)) * costs.carry_bps_per_bar / BPS

        # Return accounting begins AFTER execution:
        # Gap: from candle.close to fill_price, position held is previous
        r_gap = (fill_price - candle.close) / candle.close
        g_gap = Decimal(previous) * r_gap

        # Bar: from fill_price to next_candle.close, position held is target_position
        r_bar = (next_candle.close - fill_price) / fill_price
        g_bar = Decimal(target_position) * r_bar

        period_gross_mult = (ONE + g_gap) * (ONE + g_bar)
        gross_period_return = period_gross_mult - ONE
        net_period_return = gross_period_return - charge

        if ONE + net_period_return <= 0:
            raise ValueError("cost model or return would exhaust capital")

        gross_equity *= ONE + gross_period_return
        net_equity *= ONE + net_period_return
        total_cost += charge
        peak = max(peak, net_equity)
        max_drawdown = max(max_drawdown, ONE - net_equity / peak)

        executions.append(
            CausalExecutionRecord(
                bar_index=index,
                contract=contract,
                observation=obs,
                position_before=previous,
                position_after=target_position,
                fill_price=fill_price,
                turnover=turnover,
                charge=charge,
                signal_available_ts_ns=available_ts_ns,
                decision_ts_ns=decision_ts_ns,
                order_submit_ts_ns=order_submit_ts_ns,
                exchange_arrival_ts_ns=exchange_arrival_ts_ns,
                execution_eligible_ts_ns=execution_eligible_ts_ns,
                price_observation_ts_ns=fill_obs_ts,
                fill_ts_ns=fill_ts_ns,
                instrument_id=source_inst,
                dataset_id=source_ds_id,
                side=order_side.value if turnover else None,
                raw_observed_price=raw_observed_price if raw_observed_price is not None else fill_price,
                bid=obs_bid,
                ask=obs_ask,
                simulated_fill_price=fill_price,
                slippage=Decimal(turnover) * costs.slippage_bps / BPS,
                fee=Decimal(turnover) * costs.taker_fee_bps / BPS,
                terminal=False,
            )
        )
        previous = target_position

    # Terminal flattening at authentic market observation if non-zero position remains
    if previous:
        trades += 1
        last_candle = candles[-1]

        bar_dur = (candles[-1].ts_event_ns - candles[-2].ts_event_ns) if len(candles) >= 2 else None
        terminal_signal_available_ts = resolve_candle_close_ts(last_candle, bar_duration_ns=bar_dur)
        terminal_decision_ts = terminal_signal_available_ts + exec_assumptions.decision_latency_ns
        terminal_order_submit_ts = terminal_decision_ts
        terminal_exchange_arrival_ts = terminal_order_submit_ts + exec_assumptions.execution_latency_ns
        terminal_execution_eligible_ts = terminal_exchange_arrival_ts

        terminal_side = OrderSide.SELL if previous > 0 else OrderSide.BUY

        if execution_stream is not None:
            try:
                term_obs, exit_price, raw_observed_price = select_first_executable_observation(
                    execution_stream,
                    execution_eligible_ts_ns=terminal_execution_eligible_ts,
                    order_side=terminal_side,
                    instrument_id=last_candle.source_instrument,
                    market_type="USD_M_PERP",
                    venue="BINANCE",
                    execution_mode=exec_assumptions.execution_mode,
                )
                exit_obs_ts = term_obs.ts_event_ns
                term_bid = term_obs.bid
                term_ask = term_obs.ask
                term_inst = term_obs.instrument_id or term_obs.source_instrument
                term_ds_id = term_obs.dataset_id or term_obs.source_dataset_id
                exit_fill_ts = max(exit_obs_ts, terminal_exchange_arrival_ts) + exec_assumptions.fill_latency_ns
            except TemporalIntegrityViolationError as exc:
                raise TemporalIntegrityViolationError(
                    f"INVALID_TERMINAL_EXECUTION: TERMINAL_EXECUTION_OBSERVATION_MISSING: {exc}"
                ) from exc
        else:
            raise TemporalIntegrityViolationError(
                "INVALID_TERMINAL_EXECUTION: TERMINAL_EXECUTION_OBSERVATION_MISSING: "
                "No authentic execution observation stream provided for terminal position settlement"
            )

        exit_contract = TemporalEventContract(
            source_ts_ns=last_candle.resolved_bar_open_ts_ns,
            available_ts_ns=terminal_signal_available_ts,
            decision_ts_ns=terminal_decision_ts,
            execution_ts_ns=terminal_exchange_arrival_ts,
            fill_ts_ns=exit_fill_ts,
        )
        exit_contract.validate()
        contracts.append(exit_contract)

        # Terminal mark-to-fill market movement:
        # For long (previous > 0): (exit_price - last_candle.close) / last_candle.close
        # For short (previous < 0): -((exit_price - last_candle.close) / last_candle.close)
        last_mark = last_candle.close
        if previous > 0:
            terminal_return = (exit_price - last_mark) / last_mark
        else:
            terminal_return = -((exit_price - last_mark) / last_mark)

        # Update both gross and net equity
        gross_equity *= (ONE + terminal_return)
        net_equity *= (ONE + terminal_return)

        # Apply terminal exit fee to net equity once
        exit_cost = Decimal(abs(previous)) * costs.turnover_rate
        net_equity *= (ONE - exit_cost)
        total_cost += exit_cost

        # Recompute peak and max drawdown after market movement and exit cost
        peak = max(peak, net_equity)
        max_drawdown = max(max_drawdown, ONE - net_equity / peak)

        exit_obs = ExecutionObservation(
            bar_index=len(candles) - 1,
            signal_available_ts_ns=terminal_signal_available_ts,
            decision_ts_ns=terminal_decision_ts,
            order_submit_ts_ns=terminal_order_submit_ts,
            exchange_arrival_ts_ns=terminal_exchange_arrival_ts,
            execution_eligible_ts_ns=terminal_execution_eligible_ts,
            price_observation_ts_ns=exit_obs_ts,
            fill_ts_ns=exit_fill_ts,
            price_source=PriceSource.BID_ASK_TOUCH,
            fill_price=exit_price,
            raw_observed_price=raw_observed_price,
            bid=term_bid,
            ask=term_ask,
            source_instrument=term_inst or last_candle.source_instrument,
            source_dataset_id=term_ds_id or last_candle.source_dataset_id,
            side=terminal_side,
            market_type="USD_M_PERP",
            venue="BINANCE",
            terminal=True,
        )
        executions.append(
            CausalExecutionRecord(
                bar_index=len(candles) - 1,
                contract=exit_contract,
                observation=exit_obs,
                position_before=previous,
                position_after=0,
                fill_price=exit_price,
                turnover=abs(previous),
                charge=exit_cost,
                signal_available_ts_ns=terminal_signal_available_ts,
                decision_ts_ns=terminal_decision_ts,
                order_submit_ts_ns=terminal_order_submit_ts,
                exchange_arrival_ts_ns=terminal_exchange_arrival_ts,
                execution_eligible_ts_ns=terminal_execution_eligible_ts,
                price_observation_ts_ns=exit_obs_ts,
                fill_ts_ns=exit_fill_ts,
                instrument_id=term_inst or last_candle.source_instrument,
                dataset_id=term_ds_id or last_candle.source_dataset_id,
                side=terminal_side.value,
                raw_observed_price=raw_observed_price,
                bid=term_bid,
                ask=term_ask,
                simulated_fill_price=exit_price,
                slippage=Decimal(abs(previous)) * costs.slippage_bps / BPS,
                fee=Decimal(abs(previous)) * costs.taker_fee_bps / BPS,
                terminal=True,
            )
        )

    bt_result = BacktestResult(
        bars=len(candles),
        trades=trades,
        gross_return=gross_equity - ONE,
        net_return=net_equity - ONE,
        total_cost=total_cost,
        max_drawdown=max_drawdown,
    )

    policy_file = Path(__file__).resolve().parents[3] / "config" / "research_capital_policy_v1.yaml"
    policy_sha = hashlib.sha256(policy_file.read_bytes()).hexdigest() if policy_file.is_file() else None

    return CausalBacktestResult(
        result=bt_result,
        contracts=tuple(contracts),
        executions=tuple(executions),
        assumptions=exec_assumptions,
        execution_model_version=exec_assumptions.execution_model_version,
        signal_timeframe=exec_assumptions.signal_timeframe,
        execution_timeframe=exec_assumptions.execution_timeframe,
        signal_availability_rule="BAR_CLOSE_TIMESTAMP",
        decision_latency="DECISION_LATENCY_EXPLICIT",
        execution_price_source=exec_assumptions.price_source.value,
        execution_observation_rule="AUTHENTIC_MARKET_OBSERVATION",
        slippage_model="CONSERVATIVE_BPS",
        cost_policy_sha256=policy_sha,
    )

