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


@dataclass(frozen=True)
class ExecutionAssumptions:
    price_source: PriceSource = PriceSource.NEXT_BAR_OPEN
    execution_delay_bars: int = 1
    decision_latency_ns: int = 1_000_000
    execution_latency_ns: int = 1_000_000
    fill_latency_ns: int = 1_000_000
    allow_open_fallback: bool = False


@dataclass(frozen=True)
class ExecutionObservation:
    bar_index: int
    decision_ts_ns: int
    fill_ts_ns: int
    price_source: PriceSource
    fill_price: Decimal
    fill_price_observation_ts_ns: int

    def __post_init__(self) -> None:
        if self.fill_price_observation_ts_ns < self.decision_ts_ns:
            raise TemporalIntegrityViolationError(
                f"PRICE_CAUSALITY_VIOLATION: fill_price_observation_ts_ns ({self.fill_price_observation_ts_ns}) "
                f"< decision_ts_ns ({self.decision_ts_ns})"
            )
        if self.fill_price <= 0:
            raise ValueError("fill_price must be positive")


@dataclass(frozen=True)
class Candle:
    ts_event_ns: int
    close: Decimal
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if self.close <= 0:
            raise ValueError("candle close must be positive")
        if self.open is not None and self.open <= 0:
            raise ValueError("candle open must be positive")


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
    exec_assumptions = assumptions or ExecutionAssumptions(allow_open_fallback=True)
    folds: list[WalkForwardFold] = []
    for start in range(0, len(candles) - train_bars - test_bars + 1, test_bars):
        train_end, test_end = start + train_bars, start + train_bars + test_bars
        scored = []
        for lookback in candidates:
            pos = _momentum_positions(candles[start:train_end], lookback)
            c_res = run_causal_backtest(candles[start:train_end], pos, costs, assumptions=exec_assumptions)
            scored.append((c_res.result.net_return, -lookback, lookback))
        selected = max(scored)[2]

        positions = _momentum_positions(candles[:test_end], selected)
        c_test_res = run_causal_backtest(candles[train_end:test_end], positions[train_end:test_end], costs, assumptions=exec_assumptions)
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
) -> WalkForwardResult:
    """Select one momentum lookback on each train block and report only its following test block (routed to causal engine)."""
    return walk_forward_causal(
        candles,
        train_bars=train_bars,
        test_bars=test_bars,
        candidate_lookbacks=candidate_lookbacks,
        costs=costs,
        assumptions=ExecutionAssumptions(allow_open_fallback=True),
    )


def _select_lookback(candles: Sequence[Candle], start: int, end: int, candidates: Sequence[int], costs: CostModel) -> int:
    scored = []
    for lookback in candidates:
        positions = _momentum_positions(candles[:end], lookback)
        scored.append((run_causal_backtest(candles[start:end], positions[start:end], costs, assumptions=ExecutionAssumptions(allow_open_fallback=True)).result.net_return, -lookback, lookback))
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


@dataclass(frozen=True)
class CausalBacktestResult:
    result: BacktestResult
    contracts: tuple[TemporalEventContract, ...]
    executions: tuple[CausalExecutionRecord, ...]
    assumptions: ExecutionAssumptions = ExecutionAssumptions()

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
    funding_signals: Optional[Sequence[Any]] = None,
    override_contracts: Optional[Sequence[TemporalEventContract]] = None,
) -> CausalBacktestResult:
    """Run an offline research backtest enforcing strict runtime temporal event contracts and executable-price causality.

    Invariants enforced:
    1. Clock hierarchy: source_ts <= available_ts <= decision_ts <= execution_ts <= fill_ts.
    2. Bar availability: A candle is not available for trading decisions before its close (available_ts >= source_ts).
    3. Price causality: fill_price_observation_ts_ns >= decision_ts_ns.
    4. Executable fill: Default execution occurs at bar N+1 open (not bar N close).
    5. Return accrual:
       When position changes from P_old to P_new at bar N+1 open (O_{N+1}):
       - Return from C_N to O_{N+1} accrues to P_old.
       - Return from O_{N+1} to C_{N+1} accrues to P_new.
       No pre-entry bar N close to bar N+1 open credit for P_new.
    6. Terminal exit: Positions held at end of simulation exit at executable price.
    7. Causal funding boundary: Strategies may only receive ObservableEstimatedFunding or RealizedHistoricalFunding.
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
        d_lat = decision_latency_ns if decision_latency_ns is not None else 1_000_000
        e_lat = execution_latency_ns if execution_latency_ns is not None else 1_000_000
        f_lat = fill_latency_ns if fill_latency_ns is not None else 1_000_000
        exec_assumptions = ExecutionAssumptions(
            price_source=PriceSource.NEXT_BAR_OPEN,
            decision_latency_ns=d_lat,
            execution_latency_ns=e_lat,
            fill_latency_ns=f_lat,
            allow_open_fallback=False,
        )
    else:
        exec_assumptions = assumptions
        if decision_latency_ns is not None or execution_latency_ns is not None or fill_latency_ns is not None:
            exec_assumptions = ExecutionAssumptions(
                price_source=exec_assumptions.price_source,
                decision_latency_ns=decision_latency_ns if decision_latency_ns is not None else exec_assumptions.decision_latency_ns,
                execution_latency_ns=execution_latency_ns if execution_latency_ns is not None else exec_assumptions.execution_latency_ns,
                fill_latency_ns=fill_latency_ns if fill_latency_ns is not None else exec_assumptions.fill_latency_ns,
                allow_open_fallback=exec_assumptions.allow_open_fallback,
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

    for index, candle in enumerate(candles[:-1]):
        next_candle = candles[index + 1]
        target_position = positions[index]

        # Enforce temporal contract on bar decision / execution
        source_ts_ns = candle.ts_event_ns
        available_ts_ns = candle.ts_event_ns  # Bar availability strictly at or after bar close
        decision_ts_ns = available_ts_ns + exec_assumptions.decision_latency_ns
        execution_ts_ns = decision_ts_ns + exec_assumptions.execution_latency_ns
        fill_ts_ns = execution_ts_ns + exec_assumptions.fill_latency_ns

        contract = TemporalEventContract(
            source_ts_ns=source_ts_ns,
            available_ts_ns=available_ts_ns,
            decision_ts_ns=decision_ts_ns,
            execution_ts_ns=execution_ts_ns,
            fill_ts_ns=fill_ts_ns,
        )
        contract.validate()
        contracts.append(contract)

        # Resolve executable fill price
        if exec_assumptions.price_source == PriceSource.NEXT_BAR_OPEN:
            if next_candle.open is not None:
                fill_price = next_candle.open
            elif exec_assumptions.allow_open_fallback:
                fill_price = next_candle.close
            else:
                raise ValueError(
                    f"PRICE_CAUSALITY_VIOLATION: Candle at index {index + 1} has no open price and allow_open_fallback is False."
                )
            fill_obs_ts = fill_ts_ns
        elif exec_assumptions.price_source == PriceSource.NEXT_BAR_CLOSE:
            fill_price = next_candle.close
            fill_obs_ts = max(fill_ts_ns, next_candle.ts_event_ns)
        elif exec_assumptions.price_source == PriceSource.CURRENT_BAR_CLOSE:
            fill_price = candle.close
            fill_obs_ts = fill_ts_ns
        else:
            raise ValueError(f"Unsupported price source: {exec_assumptions.price_source}")

        obs = ExecutionObservation(
            bar_index=index,
            decision_ts_ns=decision_ts_ns,
            fill_ts_ns=fill_ts_ns,
            price_source=exec_assumptions.price_source,
            fill_price=fill_price,
            fill_price_observation_ts_ns=fill_obs_ts,
        )

        turnover = abs(target_position - previous)
        if turnover:
            trades += 1

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
            )
        )
        previous = target_position

    # Terminal flattening at executable price if non-zero position remains
    if previous:
        trades += 1
        last_candle = candles[-1]
        exit_cost = Decimal(abs(previous)) * costs.turnover_rate
        net_equity *= (ONE - exit_cost)
        total_cost += exit_cost
        max_drawdown = max(max_drawdown, ONE - net_equity / peak)

        exit_decision_ts = last_candle.ts_event_ns + exec_assumptions.decision_latency_ns
        exit_exec_ts = exit_decision_ts + exec_assumptions.execution_latency_ns
        exit_fill_ts = exit_exec_ts + exec_assumptions.fill_latency_ns

        exit_contract = TemporalEventContract(
            source_ts_ns=last_candle.ts_event_ns,
            available_ts_ns=last_candle.ts_event_ns,
            decision_ts_ns=exit_decision_ts,
            execution_ts_ns=exit_exec_ts,
            fill_ts_ns=exit_fill_ts,
        )
        exit_contract.validate()
        contracts.append(exit_contract)

        exit_obs = ExecutionObservation(
            bar_index=len(candles) - 1,
            decision_ts_ns=exit_decision_ts,
            fill_ts_ns=exit_fill_ts,
            price_source=exec_assumptions.price_source,
            fill_price=last_candle.close,
            fill_price_observation_ts_ns=exit_fill_ts,
        )
        executions.append(
            CausalExecutionRecord(
                bar_index=len(candles) - 1,
                contract=exit_contract,
                observation=exit_obs,
                position_before=previous,
                position_after=0,
                fill_price=last_candle.close,
                turnover=abs(previous),
                charge=exit_cost,
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
    return CausalBacktestResult(
        result=bt_result,
        contracts=tuple(contracts),
        executions=tuple(executions),
        assumptions=exec_assumptions,
    )

