from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence


@dataclass(frozen=True)
class WalkForwardFold:
    fold_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    purged_bars: int
    embargo_bars: int


def generate_walk_forward_folds(
    total_bars: int,
    train_bars: int,
    test_bars: int,
    step_bars: int,
    purge_bars: int = 0,
    embargo_bars: int = 0,
) -> list[WalkForwardFold]:
    """Generate rolling walk-forward evaluation windows with strict purging and dynamic embargo boundaries.
    
    Layout per fold:
      [ Train: start -> train_end ] 
      [ Purge: train_end -> train_end + purge_bars ] (discards overlapping labels)
      [ Embargo: train_end + purge_bars -> test_start ] (buffer for autoregressive lookback)
      [ Test (OOS): test_start -> test_end ]
    """
    if train_bars < 100 or test_bars < 50:
        raise ValueError("train_bars and test_bars must be sufficiently large")
    if purge_bars < 0 or embargo_bars < 0:
        raise ValueError("purge_bars and embargo_bars must be non-negative")

    total_buffer = purge_bars + embargo_bars
    folds: list[WalkForwardFold] = []
    current_start = 0
    fold_idx = 0

    while True:
        train_end = current_start + train_bars
        test_start = train_end + total_buffer
        test_end = test_start + test_bars

        if test_end > total_bars:
            break

        folds.append(
            WalkForwardFold(
                fold_index=fold_idx,
                train_start=current_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                purged_bars=purge_bars,
                embargo_bars=embargo_bars,
            )
        )
        fold_idx += 1
        current_start += step_bars

    return folds
