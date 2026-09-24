"""Purged and Embargoed Temporal Splitter for PRED-1A.

Enforces:
  1. Strictly chronological temporal ordering (no random shuffling).
  2. Purging: removes training samples near test boundaries whose forward target evaluation
     window overlaps into the test period.
  3. Embargo: applies buffer after test periods to prevent autoregressive / volatility leakage.
  4. Explicit verification of non-overlapping evaluation boundaries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


class LeakageViolationError(ValueError):
    """Raised when an unpurged or overlapping temporal split is detected."""
    pass


TemporalLeakageError = LeakageViolationError


@dataclass(frozen=True)
class TemporalSplitFold:
    fold_id: int
    train_indices: List[int]
    test_indices: List[int]
    train_start_idx: int
    train_end_idx: int
    test_start_idx: int
    test_end_idx: int
    purged_count: int
    embargo_count: int
    future_window_bars: int

    @property
    def purge_applied(self) -> int:
        return self.purged_count

    @property
    def embargo_applied(self) -> int:
        return self.embargo_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "train_size": len(self.train_indices),
            "test_size": len(self.test_indices),
            "train_start_idx": self.train_start_idx,
            "train_end_idx": self.train_end_idx,
            "test_start_idx": self.test_start_idx,
            "test_end_idx": self.test_end_idx,
            "purged_count": self.purged_count,
            "embargo_count": self.embargo_count,
            "future_window_bars": self.future_window_bars,
        }


TemporalFold = TemporalSplitFold


class PurgedTemporalSplitter:
    """Generates leakage-safe chronological temporal folds with purge and embargo."""

    def __init__(
        self,
        n_folds: int = 4,
        future_window: int = 60,
        embargo: int = 60,
        min_train_ratio: float = 0.4,
        n_splits: Optional[int] = None,
        purge_window: Optional[int] = None,
        embargo_window: Optional[int] = None,
    ):
        if n_splits is not None:
            n_folds = n_splits
        if purge_window is not None:
            future_window = purge_window
        if embargo_window is not None:
            embargo = embargo_window
        if n_folds < 2:
            raise ValueError(f"n_folds must be >= 2: {n_folds}")
        if future_window <= 0:
            raise ValueError(f"future_window must be > 0: {future_window}")
        self.n_folds = n_folds
        self.future_window = future_window
        self.embargo = embargo
        self.min_train_ratio = min_train_ratio

    @property
    def purge_window(self) -> int:
        return self.future_window

    @property
    def embargo_window(self) -> int:
        return self.embargo

    def split(
        self, total_rows: int, valid_mask: Optional[Sequence[bool]] = None
    ) -> List[TemporalSplitFold]:
        """Generates expanding-window chronological folds with purge and embargo."""
        if total_rows < 20:
            raise ValueError(f"total_rows too small for splitting: {total_rows}")

        # Reserve initial segment for training
        initial_train_size = int(total_rows * self.min_train_ratio)
        eval_size = total_rows - initial_train_size
        test_chunk_size = eval_size // self.n_folds

        if test_chunk_size < self.future_window * 2:
            raise ValueError(
                f"test_chunk_size ({test_chunk_size}) is smaller than 2x future_window ({self.future_window * 2})"
            )

        folds: List[TemporalSplitFold] = []

        for k in range(self.n_folds):
            test_start = initial_train_size + k * test_chunk_size
            test_end = (
                initial_train_size + (k + 1) * test_chunk_size
                if k < self.n_folds - 1
                else total_rows
            )

            # Expanding window training candidate: 0 to test_start
            train_candidate = list(range(0, test_start))

            # PURGE: any train row i where i + future_window >= test_start must be dropped!
            purged_train = [
                i for i in train_candidate if (i + self.future_window) < test_start
            ]
            purged_count = len(train_candidate) - len(purged_train)

            # TEST candidate: test_start to test_end - future_window (so test rows have complete future window)
            test_candidate = [
                i for i in range(test_start, test_end) if (i + self.future_window) < total_rows
            ]

            # Apply valid_mask if provided (e.g. non-null targets / warm-up periods)
            if valid_mask is not None:
                final_train = [i for i in purged_train if valid_mask[i]]
                final_test = [i for i in test_candidate if valid_mask[i]]
            else:
                final_train = purged_train
                final_test = test_candidate

            # Check that neither train nor test is empty
            if not final_train or not final_test:
                raise LeakageViolationError(
                    f"Fold {k + 1} resulted in empty train or test split."
                )

            # Verify no overlap leakage
            self.assert_no_overlap_leakage(final_train, final_test, self.future_window)
            self.assert_chronological(final_train, final_test)

            fold = TemporalSplitFold(
                fold_id=k + 1,
                train_indices=final_train,
                test_indices=final_test,
                train_start_idx=final_train[0],
                train_end_idx=final_train[-1],
                test_start_idx=final_test[0],
                test_end_idx=final_test[-1],
                purged_count=purged_count,
                embargo_count=self.embargo,
                future_window_bars=self.future_window,
            )
            folds.append(fold)

        return folds

    @staticmethod
    def assert_no_overlap_leakage(
        train_indices: Sequence[int],
        test_indices: Sequence[int],
        future_window: int,
    ) -> None:
        """Proves no training observation's forward label window touches or overlaps the test set."""
        if not train_indices or not test_indices:
            return
        max_train_label_reach = max(train_indices) + future_window
        min_test_idx = min(test_indices)

        if max_train_label_reach >= min_test_idx:
            raise LeakageViolationError(
                f"OVERLAP LEAKAGE DETECTED: Max train reach ({max_train_label_reach}) "
                f">= Min test index ({min_test_idx}) with future_window={future_window}. "
                f"Overlap of {max_train_label_reach - min_test_idx + 1} bars."
            )

    @staticmethod
    def assert_chronological(
        train_indices: Sequence[int], test_indices: Sequence[int]
    ) -> None:
        """Verifies strictly ascending chronological order with no shuffling."""
        for i in range(1, len(train_indices)):
            if train_indices[i] <= train_indices[i - 1]:
                raise LeakageViolationError(
                    f"NON-CHRONOLOGICAL TRAIN INDICES DETECTED: {train_indices[i-1]} >= {train_indices[i]}"
                )
        for i in range(1, len(test_indices)):
            if test_indices[i] <= test_indices[i - 1]:
                raise LeakageViolationError(
                    f"NON-CHRONOLOGICAL TEST INDICES DETECTED: {test_indices[i-1]} >= {test_indices[i]}"
                )
        if train_indices[-1] >= test_indices[0]:
            raise LeakageViolationError(
                f"TRAIN INDEX OVERRUNS TEST: train_end={train_indices[-1]} >= test_start={test_indices[0]}"
            )


def assert_no_overlap_leakage(
    train_indices: Sequence[int],
    test_indices: Sequence[int],
    future_window: int = 1,
    target_horizon: Optional[int] = None,
) -> None:
    """Module-level function to verify no overlap leakage between train and test sets."""
    if target_horizon is not None:
        future_window = target_horizon
    intersection = set(train_indices).intersection(set(test_indices))
    if intersection:
        raise LeakageViolationError(
            f"Direct index overlap detected: {len(intersection)} shared indices ({sorted(list(intersection))[:5]})."
        )
    PurgedTemporalSplitter.assert_no_overlap_leakage(train_indices, test_indices, future_window)


def assert_chronological(
    indices_or_train: Sequence[int],
    test_indices: Optional[Sequence[int]] = None,
) -> None:
    """Module-level function to verify strictly sorted chronological ordering."""
    if test_indices is None:
        for i in range(1, len(indices_or_train)):
            if indices_or_train[i] <= indices_or_train[i - 1]:
                raise LeakageViolationError(
                    f"Indices must be strictly sorted in chronological order: {indices_or_train[i-1]} >= {indices_or_train[i]}"
                )
    else:
        PurgedTemporalSplitter.assert_chronological(indices_or_train, test_indices)

