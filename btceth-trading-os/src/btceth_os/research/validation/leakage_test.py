from __future__ import annotations

from typing import Callable, Sequence


def verify_future_leakage_perturbation(
    compute_fn: Callable[[Sequence[float]], Sequence[float]],
    baseline_series: Sequence[float],
    test_index: int,
    perturbation_factor: float = 10.0,
) -> bool:
    """Verifies that altering future rows (index > test_index) does not change feature at index <= test_index."""
    if test_index >= len(baseline_series) - 1:
        raise ValueError("test_index must have subsequent future elements to perturb")

    original_features = compute_fn(baseline_series)

    # Create perturbed future series
    perturbed_series = list(baseline_series)
    for i in range(test_index + 1, len(perturbed_series)):
        perturbed_series[i] = perturbed_series[i] * perturbation_factor + 5000.0

    perturbed_features = compute_fn(perturbed_series)

    # Check that up to and including test_index, features are bit-for-bit or numerically identical
    for i in range(test_index + 1):
        diff = abs(perturbed_features[i] - original_features[i])
        if diff > 1e-9:
            return False
    return True


def verify_truncated_history_equivalence(
    compute_fn: Callable[[Sequence[float]], Sequence[float]],
    baseline_series: Sequence[float],
    cutoff_index: int,
) -> bool:
    """Verifies that feature value at cutoff_index is identical whether computed on full series or truncated series."""
    if cutoff_index < 0 or cutoff_index >= len(baseline_series):
        raise ValueError("cutoff_index must be within series bounds")

    full_features = compute_fn(baseline_series)
    truncated_series = baseline_series[: cutoff_index + 1]
    truncated_features = compute_fn(truncated_series)

    diff = abs(truncated_features[-1] - full_features[cutoff_index])
    return diff <= 1e-9
