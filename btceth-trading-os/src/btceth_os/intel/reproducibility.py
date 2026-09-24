"""Deterministic Logical Hashing Engine for Intelligence Outputs in INTEL-1A.

Provides physical compression-independent, canonical in-memory representation hashing
for feature arrays, market state sequences, and intelligence snapshots.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Sequence


def _canonical_json(obj: Any) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, float):
            if o != o:  # NaN
                return "NaN"
            return f"{o:.10g}"
        if hasattr(o, "to_dict"):
            return o.to_dict()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=default)


def compute_intel_logical_hash(data: Any) -> str:
    """Computes SHA-256 digest of canonical ordered JSON representation."""
    canonical_repr = _canonical_json(data)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def compute_feature_table_logical_hash(
    feature_dict: Mapping[str, Sequence[Any]], sample_stride: int = 1
) -> str:
    """Computes logical SHA-256 for a feature dictionary of column vectors."""
    keys = sorted(feature_dict.keys())
    if not keys:
        return hashlib.sha256(b"EMPTY_FEATURE_DICT").hexdigest()

    n = len(feature_dict[keys[0]])
    h = hashlib.sha256()
    h.update(f"FEATURE_SCHEMA:{','.join(keys)}\n".encode("utf-8"))

    for i in range(0, n, sample_stride):
        row = [feature_dict[k][i] for k in keys]
        h.update(_canonical_json(row).encode("utf-8") + b"\n")

    return h.hexdigest()
