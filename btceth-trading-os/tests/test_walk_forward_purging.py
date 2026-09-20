from __future__ import annotations

import pytest

from btceth_os.research.walk_forward import generate_walk_forward_folds


def test_walk_forward_purging_and_embargo_boundaries():
    total_bars = 10000
    train_bars = 2000
    test_bars = 500
    step_bars = 500
    purge_bars = 30
    embargo_bars = 60

    folds = generate_walk_forward_folds(
        total_bars=total_bars,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        purge_bars=purge_bars,
        embargo_bars=embargo_bars,
    )

    assert len(folds) > 0
    total_buffer = purge_bars + embargo_bars

    for f in folds:
        # Train window length
        assert f.train_end - f.train_start == train_bars
        # Purge + embargo buffer strictly separates train_end from test_start
        assert f.test_start - f.train_end == total_buffer
        # Test window length
        assert f.test_end - f.test_start == test_bars
        # Zero overlap between train and test
        assert f.train_end < f.test_start
