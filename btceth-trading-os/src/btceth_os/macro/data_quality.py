"""
NEWS/MACRO-1A: Fail-closed macro data quality framework.

Data quality is fail-closed: ambiguous or unavailable data is marked
explicitly rather than silently passed through.

TRADING_CAPABILITY = ZERO
"""
from __future__ import annotations

from btceth_os.macro.types import MacroDataQuality


# ---------------------------------------------------------------------------
# Quality state definitions (for documentation and verifier inspection)
# ---------------------------------------------------------------------------

QUALITY_DESCRIPTIONS: dict[MacroDataQuality, str] = {
    MacroDataQuality.GOOD: (
        "Observation is causally available (published_at_utc <= snapshot_time_utc), "
        "within the recency window, and passes all integrity checks."
    ),
    MacroDataQuality.STALE: (
        "Observation is causally available but older than the recency window. "
        "The value is the most-recent-available vintage at snapshot_time_utc."
    ),
    MacroDataQuality.MISSING: (
        "No observation is available for this series or period. "
        "The value field will be None."
    ),
    MacroDataQuality.VINTAGE_AMBIGUOUS: (
        "Multiple revisions exist and the exact vintage for the snapshot_time "
        "cannot be determined with certainty."
    ),
    MacroDataQuality.NOT_CONFIGURED: (
        "Provider credentials or configuration are absent. "
        "Data cannot be fetched. Returns None."
    ),
    MacroDataQuality.NOT_IMPLEMENTED: (
        "Provider integration not yet built for this data family. "
        "Returns None."
    ),
    MacroDataQuality.PROVIDER_REQUIRED: (
        "Data type exists and is needed but no authorised provider is configured. "
        "Returns None. Explicitly flagged for future implementation."
    ),
    MacroDataQuality.CAUSAL_VIOLATION: (
        "BLOCKED: observation.published_at_utc > snapshot_time_utc. "
        "Using this observation would constitute look-ahead bias. "
        "Value is never returned."
    ),
}

# States that are safe to surface in a snapshot (data may be None but no violation)
SAFE_QUALITY_STATES: frozenset[MacroDataQuality] = frozenset({
    MacroDataQuality.GOOD,
    MacroDataQuality.STALE,
    MacroDataQuality.MISSING,
    MacroDataQuality.NOT_CONFIGURED,
    MacroDataQuality.NOT_IMPLEMENTED,
    MacroDataQuality.PROVIDER_REQUIRED,
    MacroDataQuality.VINTAGE_AMBIGUOUS,
})

# States that must block the data from being used
BLOCKED_QUALITY_STATES: frozenset[MacroDataQuality] = frozenset({
    MacroDataQuality.CAUSAL_VIOLATION,
})


def is_usable(quality: MacroDataQuality) -> bool:
    """
    Return True if the quality state permits the observation value to be used.

    Only GOOD and STALE are considered "usable" (value is non-None and causal).
    STALE is usable with explicit awareness of staleness.

    All other states return False.
    """
    return quality in {MacroDataQuality.GOOD, MacroDataQuality.STALE}


def is_causal_violation(quality: MacroDataQuality) -> bool:
    """Return True if the quality state represents a causal (look-ahead) violation."""
    return quality == MacroDataQuality.CAUSAL_VIOLATION


def aggregate_quality(qualities: list[MacroDataQuality]) -> MacroDataQuality:
    """
    Aggregate a list of quality states to the worst-case state.

    Priority (worst first): CAUSAL_VIOLATION > MISSING > VINTAGE_AMBIGUOUS >
    PROVIDER_REQUIRED > NOT_IMPLEMENTED > NOT_CONFIGURED > STALE > GOOD.

    Returns MISSING if the list is empty.
    """
    if not qualities:
        return MacroDataQuality.MISSING

    priority: list[MacroDataQuality] = [
        MacroDataQuality.CAUSAL_VIOLATION,
        MacroDataQuality.MISSING,
        MacroDataQuality.VINTAGE_AMBIGUOUS,
        MacroDataQuality.PROVIDER_REQUIRED,
        MacroDataQuality.NOT_IMPLEMENTED,
        MacroDataQuality.NOT_CONFIGURED,
        MacroDataQuality.STALE,
        MacroDataQuality.GOOD,
    ]

    for state in priority:
        if state in qualities:
            return state

    return MacroDataQuality.MISSING
