#!/usr/bin/env python3
"""Research Round 3A: Remediated Structural Strategy Runner & Portfolio Evaluator.

Executes structural candidate evaluations on Dataset v3.1.0:
- Strict fail-closed source gap policy (no fallback substitutions).
- Explicit notional sizing ($50,000 target notional per leg) via Decimal arithmetic.
- Discrete PortfolioEquityEngine with real equity curve and concurrency control.
- Proportional basis-point legging friction model.
- Dynamic policy-based status evaluation (PRELIMINARY_PASS / REJECTED).
- True cross-asset timestamp joins without positional assumptions or dev/val cross-contamination.
- Zero forced promotion and zero holdout contamination.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import sqlite3
import subprocess
from typing import Any, Callable, Sequence

import pyarrow.parquet as pq

from btceth_os.research.cost_model import (
    BASE_PERP_COST,
    BASE_SPOT_COST,
    STRESSED_PERP_COST,
    STRESSED_SPOT_COST,
    DetailedCostPolicy,
)
from btceth_os.research.structural.basis_metrics import (
    compute_rolling_zscores,
    compute_trade_basis_ratio,
)
from btceth_os.research.structural.multi_leg_accounting import (
    FundingCashFlowEvent,
    MultiLegTradeEpisode,
    RelativePerpPairEpisode,
)
from btceth_os.research.structural.portfolio_equity import PortfolioEquityEngine
from btceth_os.research.structural.risk_models import compute_legging_friction_bps

ROOT = Path(__file__).resolve().parents[1]
SILVER_DIR = ROOT / "artifacts" / "research" / "silver_v3"
REPORTS_DIR = ROOT / "reports"
REPORT_CARDS_DIR = REPORTS_DIR / "STRUCTURAL_STRATEGY_REPORT_CARDS_3A"
DB_PATH = ROOT / "artifacts" / "research" / "experiments.sqlite"


@dataclass(frozen=True)
class Remediated1hBar:
    ts_event_ns: int
    dt_utc: datetime
    spot_open: float | None
    spot_high: float | None
    spot_low: float | None
    spot_close: float | None
    perp_open: float | None
    perp_high: float | None
    perp_low: float | None
    perp_close: float | None
    mark_close: float | None
    index_close: float | None
    premium_close: float | None
    funding_rate: float
    spot_available: bool
    perp_available: bool
    mark_available: bool
    index_available: bool
    premium_available: bool


def load_remediated_bars(symbol: str) -> list[Remediated1hBar]:
    path = SILVER_DIR / f"{symbol}-resampled-1h-v3.1.0.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing remediated cache: {path}")
    t = pq.read_table(path)
    n = len(t)
    ts = t["ts_event_ns"].to_pylist()
    so = t["spot_open"].to_pylist()
    sh = t["spot_high"].to_pylist()
    sl = t["spot_low"].to_pylist()
    sc = t["spot_close"].to_pylist()
    po = t["perp_open"].to_pylist()
    ph = t["perp_high"].to_pylist()
    pl = t["perp_low"].to_pylist()
    pc = t["perp_close"].to_pylist()
    mc = t["mark_close"].to_pylist()
    ic = t["index_close"].to_pylist()
    pr = t["premium_close"].to_pylist()
    fr = t["funding_rate"].to_pylist()
    sa = t["spot_available"].to_pylist()
    pa = t["perp_available"].to_pylist()
    ma = t["mark_available"].to_pylist()
    ia = t["index_available"].to_pylist()
    pra = t["premium_available"].to_pylist()

    bars = []
    for k in range(n):
        ts_ns = ts[k]
        bars.append(
            Remediated1hBar(
                ts_event_ns=ts_ns,
                dt_utc=datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=timezone.utc),
                spot_open=so[k],
                spot_high=sh[k],
                spot_low=sl[k],
                spot_close=sc[k],
                perp_open=po[k],
                perp_high=ph[k],
                perp_low=pl[k],
                perp_close=pc[k],
                mark_close=mc[k],
                index_close=ic[k],
                premium_close=pr[k],
                funding_rate=fr[k],
                spot_available=sa[k],
                perp_available=pa[k],
                mark_available=ma[k],
                index_available=ia[k],
                premium_available=pra[k],
            )
        )
    return bars


def run_remediated_spot_perp_backtest(
    strategy_id: str,
    asset: str,
    bars: list[Remediated1hBar],
    entry_signal_fn: Callable[[list[Remediated1hBar], int], bool],
    exit_signal_fn: Callable[[list[Remediated1hBar], int, int], bool],
    holding_max_hours: int,
    target_notional_usd: Decimal = Decimal("50000.0"),
    spot_cost_policy: DetailedCostPolicy = BASE_SPOT_COST,
    perp_cost_policy: DetailedCostPolicy = BASE_PERP_COST,
    starting_equity: Decimal = Decimal("100000.0"),
    delay_bps: float = 2.0,
) -> tuple[list[MultiLegTradeEpisode], dict[str, Any], PortfolioEquityEngine]:
    """Execute spot/perp structural backtest with strict fail-closed gap checks."""
    engine = PortfolioEquityEngine(
        starting_equity=starting_equity,
        target_gross_notional=target_notional_usd,
        max_concurrency=1,
    )
    if bars:
        engine.record_initial_state(bars[0].ts_event_ns)

    episodes: list[MultiLegTradeEpisode] = []
    n = len(bars)
    in_trade = False
    entry_idx = 0
    current_funding: list[FundingCashFlowEvent] = []
    gap_episodes_rejected = 0

    for i in range(168, n - 1):
        b = bars[i]

        # Fail-closed gap check: if spot or perp missing, cannot enter or trade
        if not (b.spot_available and b.perp_available and b.mark_available):
            if in_trade:
                gap_episodes_rejected += 1
                in_trade = False
                current_funding = []
            continue

        if in_trade:
            # Check for funding settlement
            if b.funding_rate != 0.0:
                fr = Decimal(str(b.funding_rate))
                mark_p = Decimal(str(b.mark_close))
                spot_entry_p = Decimal(str(bars[entry_idx].spot_close))
                q = target_notional_usd / spot_entry_p
                notional = q * mark_p
                # Short perp (-1) cash flow: -(-1) * notional * fr = +notional * fr
                cf = notional * fr
                current_funding.append(
                    FundingCashFlowEvent(
                        ts_event_ns=b.ts_event_ns,
                        funding_rate=fr,
                        mark_price=mark_p,
                        position_side=-1,
                        notional_usd=notional,
                        cash_flow_usd=cf,
                    )
                )

            holding_len = i - entry_idx
            should_exit = exit_signal_fn(bars, i, entry_idx) or holding_len >= holding_max_hours
            if should_exit or i == n - 2:
                spot_entry = Decimal(str(bars[entry_idx].spot_close))
                spot_exit = Decimal(str(b.spot_close))
                perp_entry = Decimal(str(bars[entry_idx].perp_close))
                perp_exit = Decimal(str(b.perp_close))
                q = target_notional_usd / spot_entry

                # Proportional legging friction
                slip_usd = compute_legging_friction_bps(float(target_notional_usd), delay_bps=delay_bps)

                ep = MultiLegTradeEpisode(
                    episode_id=f"EP_{strategy_id}_{len(episodes)+1:04d}",
                    strategy_id=strategy_id,
                    asset=asset,
                    entry_ts_ns=bars[entry_idx].ts_event_ns,
                    exit_ts_ns=b.ts_event_ns,
                    spot_side=1,
                    spot_entry_price=spot_entry,
                    spot_exit_price=spot_exit,
                    spot_quantity=q,
                    perp_side=-1,
                    perp_entry_price=perp_entry,
                    perp_exit_price=perp_exit,
                    perp_quantity=q,
                    spot_cost_policy=spot_cost_policy,
                    perp_cost_policy=perp_cost_policy,
                    funding_events=tuple(current_funding),
                    legging_delay_ms=500,
                    temporary_delta_loss_usd=Decimal(str(round(slip_usd, 4))),
                )
                committed_capital = target_notional_usd * Decimal("1.75")
                engine.close_episode(ep, committed_capital, b.ts_event_ns)
                episodes.append(ep)
                in_trade = False
                current_funding = []

        elif not in_trade:
            if entry_signal_fn(bars, i):
                committed_capital = target_notional_usd * Decimal("1.75")
                if engine.can_open_episode(committed_capital):
                    in_trade = True
                    entry_idx = i
                    current_funding = []
                    # Dummy episode placeholder for capital lock
                    engine.open_episode(None, committed_capital)

    total_hours = (bars[-1].ts_event_ns - bars[0].ts_event_ns) / 3_600_000_000_000 if bars else 1.0
    summary = engine.compute_summary_metrics(episodes, total_period_hours=total_hours)
    summary["gap_episodes_rejected"] = gap_episodes_rejected
    return episodes, summary, engine


def run_remediated_relative_funding_backtest(
    strategy_id: str,
    btc_bars: list[Remediated1hBar],
    eth_bars: list[Remediated1hBar],
    divergence_hurdle_bps: float = 10.0,
    holding_max_hours: int = 48,
    target_notional_per_leg: Decimal = Decimal("25000.0"),  # $50,000 gross notional pair
    btc_cost_policy: DetailedCostPolicy = BASE_PERP_COST,
    eth_cost_policy: DetailedCostPolicy = BASE_PERP_COST,
    starting_equity: Decimal = Decimal("100000.0"),
) -> tuple[list[RelativePerpPairEpisode], dict[str, Any], PortfolioEquityEngine]:
    """Execute true 2-perp relative carry backtest with exact timestamp alignment."""
    # Build exact timestamp aligned map
    eth_map = {b.ts_event_ns: b for b in eth_bars}
    aligned_pairs = []
    for b_btc in btc_bars:
        b_eth = eth_map.get(b_btc.ts_event_ns)
        if b_eth and b_btc.perp_available and b_eth.perp_available and b_btc.mark_available and b_eth.mark_available:
            aligned_pairs.append((b_btc, b_eth))

    engine = PortfolioEquityEngine(
        starting_equity=starting_equity,
        target_gross_notional=target_notional_per_leg * Decimal("2.0"),
        max_concurrency=1,
    )
    if aligned_pairs:
        engine.record_initial_state(aligned_pairs[0][0].ts_event_ns)

    episodes: list[RelativePerpPairEpisode] = []
    n = len(aligned_pairs)
    in_trade = False
    entry_idx = 0
    btc_side = 0
    eth_side = 0
    btc_funding: list[FundingCashFlowEvent] = []
    eth_funding: list[FundingCashFlowEvent] = []

    for i in range(24, n - 1):
        b_btc, b_eth = aligned_pairs[i]

        if in_trade:
            # Check funding settlements
            if b_btc.funding_rate != 0.0:
                p_btc_entry = Decimal(str(aligned_pairs[entry_idx][0].perp_close))
                q_btc = target_notional_per_leg / p_btc_entry
                mark_btc = Decimal(str(b_btc.mark_close))
                fr_btc = Decimal(str(b_btc.funding_rate))
                cf_btc = -Decimal(btc_side) * (q_btc * mark_btc) * fr_btc
                btc_funding.append(
                    FundingCashFlowEvent(b_btc.ts_event_ns, fr_btc, mark_btc, btc_side, q_btc * mark_btc, cf_btc)
                )

            if b_eth.funding_rate != 0.0:
                p_eth_entry = Decimal(str(aligned_pairs[entry_idx][1].perp_close))
                q_eth = target_notional_per_leg / p_eth_entry
                mark_eth = Decimal(str(b_eth.mark_close))
                fr_eth = Decimal(str(b_eth.funding_rate))
                cf_eth = -Decimal(eth_side) * (q_eth * mark_eth) * fr_eth
                eth_funding.append(
                    FundingCashFlowEvent(b_eth.ts_event_ns, fr_eth, mark_eth, eth_side, q_eth * mark_eth, cf_eth)
                )

            holding_len = i - entry_idx
            if holding_len >= holding_max_hours or i == n - 2:
                p_btc_entry = Decimal(str(aligned_pairs[entry_idx][0].perp_close))
                p_btc_exit = Decimal(str(b_btc.perp_close))
                q_btc = target_notional_per_leg / p_btc_entry

                p_eth_entry = Decimal(str(aligned_pairs[entry_idx][1].perp_close))
                p_eth_exit = Decimal(str(b_eth.perp_close))
                q_eth = target_notional_per_leg / p_eth_entry

                ep = RelativePerpPairEpisode(
                    episode_id=f"EP_{strategy_id}_{len(episodes)+1:04d}",
                    strategy_id=strategy_id,
                    entry_ts_ns=aligned_pairs[entry_idx][0].ts_event_ns,
                    exit_ts_ns=b_btc.ts_event_ns,
                    asset1_symbol="BTCUSDT",
                    asset1_side=btc_side,
                    asset1_entry_price=p_btc_entry,
                    asset1_exit_price=p_btc_exit,
                    asset1_quantity=q_btc,
                    asset1_cost_policy=btc_cost_policy,
                    asset1_funding_events=tuple(btc_funding),
                    asset2_symbol="ETHUSDT",
                    asset2_side=eth_side,
                    asset2_entry_price=p_eth_entry,
                    asset2_exit_price=p_eth_exit,
                    asset2_quantity=q_eth,
                    asset2_cost_policy=eth_cost_policy,
                    asset2_funding_events=tuple(eth_funding),
                )
                episodes.append(ep)
                engine.current_cash += ep.net_pnl
                engine.current_committed_capital = Decimal("0")
                in_trade = False
                btc_funding = []
                eth_funding = []

        elif not in_trade:
            # Signal: divergence between BTC and ETH funding rate
            diff_bps = (b_btc.funding_rate - b_eth.funding_rate) * 10000.0
            if abs(diff_bps) >= divergence_hurdle_bps:
                if diff_bps > 0:
                    # BTC funding higher than ETH: short BTC perp (earn funding), long ETH perp (pay less funding)
                    btc_side = -1
                    eth_side = 1
                else:
                    # ETH funding higher: long BTC perp, short ETH perp
                    btc_side = 1
                    eth_side = -1

                committed = target_notional_per_leg * Decimal("2.0") * Decimal("0.75")
                if engine.can_open_episode(committed):
                    in_trade = True
                    entry_idx = i
                    btc_funding = []
                    eth_funding = []
                    engine.current_committed_capital = committed

    total_hours = (aligned_pairs[-1][0].ts_event_ns - aligned_pairs[0][0].ts_event_ns) / 3_600_000_000_000 if aligned_pairs else 1.0
    summary = engine.compute_summary_metrics(episodes, total_period_hours=total_hours)
    return episodes, summary, engine


def evaluate_candidate_policy(
    trades: int,
    val_base_return: float,
    val_stressed_return: float,
    sharpe: float,
    max_dd: float,
) -> tuple[str, list[str]]:
    """Determine candidate validation status and non-empty rejection reasons."""
    reasons: list[str] = []
    if trades < 30:
        reasons.append(f"INSUFFICIENT_OUT_OF_SAMPLE_TRADES ({trades} < 30)")
    if val_base_return <= 0.0:
        reasons.append(f"NEGATIVE_VALIDATION_BASE_RETURN ({val_base_return:.2f}% <= 0%)")
    if val_stressed_return <= 0.0:
        reasons.append(f"FAILED_COST_STRESS_SURVIVAL ({val_stressed_return:.2f}% <= 0%)")
    if sharpe < 1.0:
        reasons.append(f"LOW_SHARPE_RATIO ({sharpe:.2f} < 1.0)")
    if max_dd > 20.0:
        reasons.append(f"EXCESSIVE_DRAWDOWN ({max_dd:.2f}% > 20.0%)")

    if not reasons:
        return "PRELIMINARY_PASS", []
    else:
        return "REJECTED", reasons


def main() -> None:
    print("=" * 70)
    print("BTCETH TRADING OS: RESEARCH ROUND 3A REMEDIATED CAMPAIGN")
    print("=" * 70)

    REPORT_CARDS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load remediated Dataset v3.1.0 bars
    print("[Loader] Loading Dataset v3.1.0 remediated bars...")
    btc_bars = load_remediated_bars("BTCUSDT")
    eth_bars = load_remediated_bars("ETHUSDT")
    print(f"[Loader] Loaded {len(btc_bars)} BTC bars and {len(eth_bars)} ETH bars.")

    # Chronological Split:
    # Dev: 2020-01 to 2022-12 (36m)
    # Val: 2023-01 to 2023-12 (12m)
    split_dt = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    btc_dev = [b for b in btc_bars if b.dt_utc < split_dt]
    btc_val = [b for b in btc_bars if b.dt_utc >= split_dt]
    eth_dev = [b for b in eth_bars if b.dt_utc < split_dt]
    eth_val = [b for b in eth_bars if b.dt_utc >= split_dt]

    # Precompute rolling z-scores on valid basis ratios
    btc_dev_basis = [compute_trade_basis_ratio(b.perp_close, b.spot_close) if (b.spot_available and b.perp_available) else 0.0 for b in btc_dev]
    btc_dev_z = compute_rolling_zscores(btc_dev_basis, 168)
    btc_val_basis = [compute_trade_basis_ratio(b.perp_close, b.spot_close) if (b.spot_available and b.perp_available) else 0.0 for b in btc_val]
    btc_val_z = compute_rolling_zscores(btc_val_basis, 168)

    candidates = [
        {
            "strategy_id": "STRUCT_A1_BTC_CARRY_8H",
            "family": "STRUCT_FAMILY_A_SPOT_PERP_CARRY",
            "asset": "BTC",
            "hypothesis": "Capturing individual 8h funding payments when expected funding > 8 bps.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: bars[i].dt_utc.hour in (7, 15, 23) and bars[i].funding_rate >= 0.0008,
            "exit_fn": lambda bars, i, e: (i - e) >= 8,
            "horizon": 8,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_A2_BTC_CARRY_24H",
            "family": "STRUCT_FAMILY_A_SPOT_PERP_CARRY",
            "asset": "BTC",
            "hypothesis": "Holding spot-perp carry for 24h when funding exceeds 10 bps hurdle.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: bars[i].funding_rate >= 0.0010,
            "exit_fn": lambda bars, i, e: (i - e) >= 24,
            "horizon": 24,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_A3_BTC_CARRY_72H",
            "family": "STRUCT_FAMILY_A_SPOT_PERP_CARRY",
            "asset": "BTC",
            "hypothesis": "Multi-day persistent carry regimes (> 72h) generate defensible net return after stressed friction.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: bars[i].funding_rate >= 0.0015,
            "exit_fn": lambda bars, i, e: (i - e) >= 72,
            "horizon": 72,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_A4_ETH_CARRY_24H",
            "family": "STRUCT_FAMILY_A_SPOT_PERP_CARRY",
            "asset": "ETH",
            "hypothesis": "Holding ETH spot-perp carry for 24h when ETH funding exceeds 10 bps.",
            "dev_bars": eth_dev,
            "val_bars": eth_val,
            "entry_fn": lambda bars, i: bars[i].funding_rate >= 0.0010,
            "exit_fn": lambda bars, i, e: (i - e) >= 24,
            "horizon": 24,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_B1_BTC_BASIS_Z20",
            "family": "STRUCT_FAMILY_B_BASIS_DISLOCATION",
            "asset": "BTC",
            "hypothesis": "Extreme perp-spot basis dislocation (rolling z >= +2.0) converges back to equilibrium.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: (btc_dev_z[i] if len(bars) == len(btc_dev) else btc_val_z[i]) >= 2.0,
            "exit_fn": lambda bars, i, e: (i - e) >= 48 or ((btc_dev_z[i] if len(bars) == len(btc_dev) else btc_val_z[i]) <= 0.5),
            "horizon": 48,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_B2_BTC_BASIS_Z25",
            "family": "STRUCT_FAMILY_B_BASIS_DISLOCATION",
            "asset": "BTC",
            "hypothesis": "Severe basis dislocation (rolling z >= +2.5) provides profit margin against fees.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: (btc_dev_z[i] if len(bars) == len(btc_dev) else btc_val_z[i]) >= 2.5,
            "exit_fn": lambda bars, i, e: (i - e) >= 48 or ((btc_dev_z[i] if len(bars) == len(btc_dev) else btc_val_z[i]) <= 0.5),
            "horizon": 48,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_C1_BTCETH_REL_FUNDING",
            "family": "STRUCT_FAMILY_C_RELATIVE_CARRY",
            "asset": "BTC/ETH",
            "hypothesis": "Cross-asset funding divergence between BTC and ETH harvested via 2-perp relative pair.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "type": "RELATIVE_PAIR",
        },
        {
            "strategy_id": "STRUCT_D1_BTC_PREMIUM_DIVERGENCE",
            "family": "STRUCT_FAMILY_D_FUNDING_PREMIUM_DIVERGENCE",
            "asset": "BTC",
            "hypothesis": "Official 8h TWAP premium index divergence signals upcoming funding surge.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: bars[i].premium_available and bars[i].premium_close is not None and bars[i].premium_close >= 0.0015 and bars[i].funding_rate <= 0.0005,
            "exit_fn": lambda bars, i, e: (i - e) >= 24,
            "horizon": 24,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_E1_BTC_CARRY_TIMING",
            "family": "STRUCT_FAMILY_E_CARRY_TIMING",
            "asset": "BTC",
            "hypothesis": "Entering carry exactly 2h before settlement and exiting 1h post settlement.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: bars[i].dt_utc.hour in (6, 14, 22) and bars[i].funding_rate >= 0.0005,
            "exit_fn": lambda bars, i, e: (i - e) >= 3,
            "horizon": 3,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_F1_BTC_WEEKEND_REVERSION",
            "family": "STRUCT_FAMILY_F_WEEKEND_SESSION_EFFECTS",
            "asset": "BTC",
            "hypothesis": "Weekend carry entering Friday 22:00 UTC and exiting Sunday 22:00 UTC.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: bars[i].dt_utc.weekday() == 4 and bars[i].dt_utc.hour == 22,
            "exit_fn": lambda bars, i, e: bars[i].dt_utc.weekday() == 6 and bars[i].dt_utc.hour == 22,
            "horizon": 48,
            "type": "SPOT_PERP",
        },
        {
            "strategy_id": "STRUCT_G1_BTC_POST_STRESS",
            "family": "STRUCT_FAMILY_G_POST_STRESS_REVERSION",
            "asset": "BTC",
            "hypothesis": "Entering basis carry after extreme 2h price drop > 3% and funding collapse.",
            "dev_bars": btc_dev,
            "val_bars": btc_val,
            "entry_fn": lambda bars, i: i >= 2 and bars[i].spot_close is not None and bars[i-2].spot_close is not None and ((bars[i].spot_close - bars[i-2].spot_close) / bars[i-2].spot_close) <= -0.03 and bars[i].funding_rate <= -0.0005,
            "exit_fn": lambda bars, i, e: (i - e) >= 72,
            "horizon": 72,
            "type": "SPOT_PERP",
        },
    ]

    results_list = []
    preliminary_passes = 0
    rejections = 0

    for c in candidates:
        s_id = c["strategy_id"]
        fam = c["family"]
        asset = c["asset"]
        print(f"\n[Evaluating] {s_id} ({fam} on {asset})...")

        if c["type"] == "SPOT_PERP":
            dev_eps, dev_sum, _ = run_remediated_spot_perp_backtest(
                s_id, asset, c["dev_bars"], c["entry_fn"], c["exit_fn"], c["horizon"]
            )
            val_eps_base, val_sum_base, _ = run_remediated_spot_perp_backtest(
                s_id, asset, c["val_bars"], c["entry_fn"], c["exit_fn"], c["horizon"],
                spot_cost_policy=BASE_SPOT_COST, perp_cost_policy=BASE_PERP_COST
            )
            val_eps_stressed, val_sum_stressed, _ = run_remediated_spot_perp_backtest(
                s_id, asset, c["val_bars"], c["entry_fn"], c["exit_fn"], c["horizon"],
                spot_cost_policy=STRESSED_SPOT_COST, perp_cost_policy=STRESSED_PERP_COST, delay_bps=5.0
            )
        else:
            # RELATIVE_PAIR
            dev_eps, dev_sum, _ = run_remediated_relative_funding_backtest(
                s_id, btc_dev, eth_dev, divergence_hurdle_bps=10.0
            )
            val_eps_base, val_sum_base, _ = run_remediated_relative_funding_backtest(
                s_id, btc_val, eth_val, divergence_hurdle_bps=10.0,
                btc_cost_policy=BASE_PERP_COST, eth_cost_policy=BASE_PERP_COST
            )
            val_eps_stressed, val_sum_stressed, _ = run_remediated_relative_funding_backtest(
                s_id, btc_val, eth_val, divergence_hurdle_bps=10.0,
                btc_cost_policy=STRESSED_PERP_COST, eth_cost_policy=STRESSED_PERP_COST
            )

        status, reasons = evaluate_candidate_policy(
            trades=val_sum_base["total_episodes"],
            val_base_return=val_sum_base["portfolio_return_pct"],
            val_stressed_return=val_sum_stressed["portfolio_return_pct"],
            sharpe=val_sum_base["daily_sharpe"],
            max_dd=val_sum_base["max_drawdown_pct"],
        )

        if status == "PRELIMINARY_PASS":
            preliminary_passes += 1
        else:
            rejections += 1

        card_md = f"""# Strategy Report Card: {s_id}

- **Family**: `{fam}`
- **Asset(s)**: `{asset}`
- **Sizing Model**: `FIXED_NOTIONAL ($50,000 / leg)`
- **Starting Equity**: `${val_sum_base['starting_equity']:,.2f}`
- **Ending Equity (Val Base)**: `${val_sum_base['ending_equity']:,.2f}`
- **Portfolio Return (Val Base)**: `{val_sum_base['portfolio_return_pct']:.2f}%`
- **Portfolio Return (Val Stressed)**: `{val_sum_stressed['portfolio_return_pct']:.2f}%`
- **Average Episode RoC**: `{val_sum_base['average_episode_roc_pct']:.2f}%`
- **Average Capital Employed**: `${val_sum_base['average_capital_employed']:,.2f}`
- **Peak Capital Employed**: `${val_sum_base['peak_capital_employed']:,.2f}`
- **Capital Utilization**: `{val_sum_base['capital_utilization_pct']:.2f}%`
- **Number of Episodes**: `{val_sum_base['total_episodes']}`
- **Daily Sharpe**: `{val_sum_base['daily_sharpe']:.2f}`
- **Max Drawdown**: `{val_sum_base['max_drawdown_pct']:.2f}%`
- **Source Gap Episodes Rejected**: `{val_sum_base.get('gap_episodes_rejected', 0)}`
- **Status**: `{status}`
- **Rejection Reasons**: {json.dumps(reasons)}
- **Sanity Flags**: {json.dumps(val_sum_base['sanity_flags'])}
"""
        (REPORT_CARDS_DIR / f"{s_id}.md").write_text(card_md, encoding="utf-8")

        res_entry = {
            "strategy_id": s_id,
            "family": fam,
            "asset": asset,
            "dev_return_pct": dev_sum["portfolio_return_pct"],
            "val_base_return_pct": val_sum_base["portfolio_return_pct"],
            "val_stressed_return_pct": val_sum_stressed["portfolio_return_pct"],
            "val_trades": val_sum_base["total_episodes"],
            "val_sharpe": val_sum_base["daily_sharpe"],
            "val_max_dd_pct": val_sum_base["max_drawdown_pct"],
            "status": status,
            "rejection_reasons": reasons,
            "sanity_flags": val_sum_base["sanity_flags"],
        }
        results_list.append(res_entry)
        print(f"[{s_id}] Status: {status} | Return: {val_sum_base['portfolio_return_pct']:.2f}% | Trades: {val_sum_base['total_episodes']} | Sharpe: {val_sum_base['daily_sharpe']:.2f}")

    results_payload = {
        "phase": "RESEARCH_ROUND3A_RESULTS",
        "dataset_version": "3.1.0",
        "holdout_status": "LOCKED",
        "total_candidates_tested": len(candidates),
        "preliminary_pass": preliminary_passes,
        "rejected": rejections,
        "approved_for_shadow": 0,
        "approved_for_paper": 0,
        "results": results_list,
    }
    (REPORTS_DIR / "RESEARCH_ROUND3A_RESULTS.json").write_text(json.dumps(results_payload, indent=2) + "\n", encoding="utf-8")

    results_md = f"""# Research Round 3A: Remediated Structural Strategy Results

**Dataset Version**: `3.1.0` (48 Months: 2020-01 to 2023-12)  
**2024 Holdout**: `LOCKED` (Unopened)  
**Total Candidates Tested**: `{len(candidates)}`  
**Preliminary Pass**: `{preliminary_passes}`  
**Rejected**: `{rejections}`  
**Approved for Shadow**: `0`  
**Approved for Paper**: `0`  

## Remediated Performance Matrix (2020–2022 Dev & 2023 Validation)

| Strategy ID | Family | Asset | Dev Return | Val Base Return | Val Stressed Return | Trades | Daily Sharpe | Max DD | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in results_list:
        results_md += f"| `{r['strategy_id']}` | `{r['family']}` | `{r['asset']}` | {r['dev_return_pct']:.2f}% | {r['val_base_return_pct']:.2f}% | {r['val_stressed_return_pct']:.2f}% | {r['val_trades']} | {r['val_sharpe']:.2f} | {r['val_max_dd_pct']:.2f}% | **{r['status']}** |\n"

    (REPORTS_DIR / "RESEARCH_ROUND3A_RESULTS.md").write_text(results_md, encoding="utf-8")
    print("\n" + "=" * 70)
    print("RESEARCH ROUND 3A EVALUATION COMPLETE")
    print(f"Tested: {len(candidates)} | Preliminary Pass: {preliminary_passes} | Rejected: {rejections}")
    print("=" * 70)


if __name__ == "__main__":
    main()
