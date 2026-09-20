from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import re
import json
from pathlib import Path
from typing import Iterable, Sequence

import pyarrow.parquet as pq

from ..core import canonical_json


ONE = Decimal("1")
BPS = Decimal("10000")


@dataclass(frozen=True)
class Candle:
    ts_event_ns: int
    close: Decimal

    def __post_init__(self) -> None:
        if self.close <= 0:
            raise ValueError("candle close must be positive")


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
    table = pq.read_table(path, columns=["source_object_sha256", "ts_event_ns", "close"])
    hashes = set(table.column("source_object_sha256").to_pylist())
    if len(hashes) != 1 or not re.fullmatch(r"[0-9a-f]{64}", next(iter(hashes), "")):
        raise ValueError("Silver research input must have one valid source SHA-256")
    candles = tuple(Candle(int(timestamp), Decimal(str(close))) for timestamp, close in zip(
        table.column("ts_event_ns").to_pylist(), table.column("close").to_pylist(), strict=True
    ))
    if len(candles) < 2 or any(later.ts_event_ns <= earlier.ts_event_ns for earlier, later in zip(candles, candles[1:])):
        raise ValueError("Silver kline input must contain at least two strictly increasing candles")
    return next(iter(hashes)), candles


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
    """Mark-to-market a signal at the next close; force-flat at the end and charge every turnover."""
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


def walk_forward_momentum(
    candles: Sequence[Candle],
    *,
    train_bars: int,
    test_bars: int,
    candidate_lookbacks: Iterable[int],
    costs: CostModel,
) -> WalkForwardResult:
    """Select one momentum lookback on each train block and report only its following test block."""
    candidates = tuple(sorted(set(candidate_lookbacks)))
    if not candidates or min(candidates) < 1 or train_bars <= max(candidates) or test_bars < 2:
        raise ValueError("need positive lookbacks, train_bars above them, and at least two test bars")
    folds: list[WalkForwardFold] = []
    for start in range(0, len(candles) - train_bars - test_bars + 1, test_bars):
        train_end, test_end = start + train_bars, start + train_bars + test_bars
        selected = _select_lookback(candles, start, train_end, candidates, costs)
        positions = _momentum_positions(candles[:test_end], selected)
        result = run_backtest(candles[train_end:test_end], positions[train_end:test_end], costs)
        folds.append(WalkForwardFold(start, train_end, train_end, test_end, selected, result))
    if not folds:
        raise ValueError("not enough candles for one walk-forward fold")
    equity = ONE
    for fold in folds:
        equity *= ONE + fold.result.net_return
    return WalkForwardResult(tuple(folds), equity - ONE, sum(fold.result.trades for fold in folds))


def _select_lookback(candles: Sequence[Candle], start: int, end: int, candidates: Sequence[int], costs: CostModel) -> int:
    scored = []
    for lookback in candidates:
        positions = _momentum_positions(candles[:end], lookback)
        scored.append((run_backtest(candles[start:end], positions[start:end], costs).net_return, -lookback, lookback))
    return max(scored)[2]


def _momentum_positions(candles: Sequence[Candle], lookback: int) -> list[int]:
    return [0 if index < lookback else (1 if candle.close > candles[index - lookback].close else -1) for index, candle in enumerate(candles)]
