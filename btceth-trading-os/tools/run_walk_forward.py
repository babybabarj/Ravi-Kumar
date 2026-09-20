from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from btceth_os.research import CostModel, load_kline_candles, walk_forward_momentum, write_walk_forward_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic, cost-aware walk-forward research on one Silver kline object.")
    parser.add_argument("input", type=Path, help="immutable historical Silver kline Parquet path")
    parser.add_argument("output", type=Path, help="new JSON report path; an existing report is never overwritten")
    parser.add_argument("--train-bars", required=True, type=int)
    parser.add_argument("--test-bars", required=True, type=int)
    parser.add_argument("--lookbacks", required=True, help="comma-separated positive momentum lookbacks")
    parser.add_argument("--taker-fee-bps", required=True, type=Decimal)
    parser.add_argument("--slippage-bps", required=True, type=Decimal)
    parser.add_argument("--carry-bps-per-bar", default=Decimal("0"), type=Decimal)
    args = parser.parse_args()
    lookbacks = [int(value) for value in args.lookbacks.split(",")]
    source_hash, candles = load_kline_candles(args.input)
    costs = CostModel(args.taker_fee_bps, args.slippage_bps, args.carry_bps_per_bar)
    result = walk_forward_momentum(candles, train_bars=args.train_bars, test_bars=args.test_bars, candidate_lookbacks=lookbacks, costs=costs)
    report = write_walk_forward_report(args.output, source_hash, train_bars=args.train_bars, test_bars=args.test_bars, candidate_lookbacks=lookbacks, costs=costs, result=result)
    print(f"research_report={report}")
    print(f"out_of_sample_net_return={result.net_return}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
