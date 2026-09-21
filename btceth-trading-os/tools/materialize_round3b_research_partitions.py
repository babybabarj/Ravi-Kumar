#!/usr/bin/env python3
"""Materialize and cryptographically verify the 8 physical research partitions.

Research Round 3B.0D: Reproducible Research Partition Closure.
Deterministic partition materialization from parent Silver v3 datasets.
Enforces:
- Cryptographic SHA-256 verification of parent Silver artifacts before splitting
- Hard-coded temporal boundaries (DEV: 2020-2022, VAL: 2023)
- Atomic .part file writing and verification before promotion
- Verification of partition row counts, min/max timestamps, and physical SHA-256
- Computation and cryptographic verification of independent partition logical content hashes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
DEFAULT_CONFIG_PATH = ROOT / "config" / "research_partitions_v1.json"
DEFAULT_PARENT_DIR = ROOT / "artifacts" / "research" / "silver_v3"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "research" / "partitions"

SPLIT_DEV_VAL_TS_NS = 1672531200_000_000_000  # 2023-01-01T00:00:00Z
HOLDOUT_START_TS_NS = 1704067200_000_000_000  # 2024-01-01T00:00:00Z


def compute_file_sha256(path: Path | str, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest for a file on disk."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_partition_logical_sha256(table: pa.Table) -> str:
    """Compute deterministic logical dataset hash independent of Parquet chunking or metadata.

    Hashes:
    1. Schema fields: name and data type in column order
    2. All rows sorted by ts_event_ns: timestamp followed by comma-separated row values
    """
    h = hashlib.sha256()
    # 1. Canonical schema definition
    schema_str = ";".join(f"{f.name}:{f.type}" for f in table.schema)
    h.update(f"SCHEMA:{schema_str}\n".encode("utf-8"))

    # 2. Row data sorted by ts_event_ns
    ts_event_col = table["ts_event_ns"].to_pylist()
    col_names = [f.name for f in table.schema if f.name != "ts_event_ns"]
    cols_data = [table[c].to_pylist() for c in col_names]

    for i, ts in enumerate(ts_event_col):
        row_vals = ",".join(str(cols_data[c_idx][i]) for c_idx in range(len(col_names)))
        line = f"{ts}:{row_vals}\n"
        h.update(line.encode("utf-8"))

    return h.hexdigest()


def verify_parent_artifacts(manifest: dict[str, Any], parent_dir: Path) -> dict[str, dict[str, Any]]:
    """Verify presence and physical SHA-256 digests of parent Silver artifacts."""
    results: dict[str, dict[str, Any]] = {}
    parent_artifacts = manifest.get("parent_artifacts", {})

    for fname, meta in parent_artifacts.items():
        p = parent_dir / fname
        if not p.is_file():
            results[fname] = {
                "file_exists": False,
                "error": f"Parent artifact missing: {p}",
                "matches": False,
            }
            continue

        actual_sha = compute_file_sha256(p)
        expected_sha = meta["physical_sha256"]
        matches = (actual_sha == expected_sha)
        results[fname] = {
            "file_exists": True,
            "actual_sha256": actual_sha,
            "expected_sha256": expected_sha,
            "matches": matches,
        }
        if not matches:
            results[fname]["error"] = f"SHA mismatch: expected {expected_sha}, got {actual_sha}"

    return results


def verify_partition_file(
    partition_cfg: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Verify a single partition file against manifest requirements."""
    fname = partition_cfg["file_name"]
    p = output_dir / fname
    if not p.is_file():
        return {
            "file_name": fname,
            "exists": False,
            "error": f"File does not exist: {p}",
            "verified": False,
        }

    actual_physical_sha = compute_file_sha256(p)
    expected_physical_sha = partition_cfg["expected_physical_sha256"]
    physical_matches = (actual_physical_sha == expected_physical_sha)

    t = pq.read_table(p)
    num_rows = t.num_rows
    expected_rows = partition_cfg["expected_rows"]
    rows_match = (num_rows == expected_rows)

    min_ts = pc.min(t["ts_event_ns"]).as_py()
    max_ts = pc.max(t["ts_event_ns"]).as_py()
    bounds_match = (min_ts == partition_cfg["start_ts_ns"]) and (max_ts == partition_cfg["end_ts_ns"])

    # Temporal boundary check
    role = partition_cfg["role"]
    if role == "DEVELOPMENT":
        role_bounds_ok = (max_ts < SPLIT_DEV_VAL_TS_NS)
    elif role == "VALIDATION":
        role_bounds_ok = (min_ts >= SPLIT_DEV_VAL_TS_NS) and (max_ts < HOLDOUT_START_TS_NS)
    else:
        role_bounds_ok = False

    # Independent logical SHA verification
    actual_logical_sha = compute_partition_logical_sha256(t)
    expected_logical_sha = partition_cfg["partition_logical_sha256"]
    logical_matches = (actual_logical_sha == expected_logical_sha)

    verified = physical_matches and rows_match and bounds_match and role_bounds_ok and logical_matches

    return {
        "file_name": fname,
        "partition_id": partition_cfg["dataset_id"],
        "role": role,
        "exists": True,
        "actual_physical_sha256": actual_physical_sha,
        "expected_physical_sha256": expected_physical_sha,
        "physical_matches": physical_matches,
        "actual_rows": num_rows,
        "expected_rows": expected_rows,
        "rows_match": rows_match,
        "actual_start_ts_ns": min_ts,
        "expected_start_ts_ns": partition_cfg["start_ts_ns"],
        "actual_end_ts_ns": max_ts,
        "expected_end_ts_ns": partition_cfg["end_ts_ns"],
        "bounds_match": bounds_match,
        "role_bounds_ok": role_bounds_ok,
        "actual_logical_sha256": actual_logical_sha,
        "expected_logical_sha256": expected_logical_sha,
        "logical_matches": logical_matches,
        "verified": verified,
    }


def materialize_single_partition(
    partition_cfg: dict[str, Any],
    parent_dir: Path,
    output_dir: Path,
    force: bool = False,
) -> dict[str, Any]:
    """Materialize a single partition file atomically."""
    fname = partition_cfg["file_name"]
    pid = partition_cfg["dataset_id"]
    role = partition_cfg["role"]
    target_path = output_dir / fname
    part_path = output_dir / f"{fname}.part"

    # If file exists and valid, skip unless force
    if target_path.is_file() and not force:
        v_res = verify_partition_file(partition_cfg, output_dir)
        if v_res.get("verified"):
            v_res["action"] = "SKIPPED_ALREADY_VALID"
            return v_res

    # 1. Read parent artifact
    parent_fname = partition_cfg["parent_artifact"]
    parent_path = parent_dir / parent_fname
    if not parent_path.is_file():
        raise FileNotFoundError(f"Parent artifact not found: {parent_path}")

    parent_actual_sha = compute_file_sha256(parent_path)
    if parent_actual_sha != partition_cfg["parent_physical_sha256"]:
        raise ValueError(
            f"Parent artifact {parent_fname} SHA mismatch! "
            f"Expected {partition_cfg['parent_physical_sha256']}, got {parent_actual_sha}"
        )

    t = pq.read_table(parent_path)

    # 2. Apply deterministic temporal filter
    ts_field = pc.field("ts_event_ns")
    if role == "DEVELOPMENT":
        mask = (ts_field >= 1577836800_000_000_000) & (ts_field < SPLIT_DEV_VAL_TS_NS)
    elif role == "VALIDATION":
        mask = (ts_field >= SPLIT_DEV_VAL_TS_NS) & (ts_field < HOLDOUT_START_TS_NS)
    else:
        raise ValueError(f"Unknown partition role: {role}")

    filtered_t = t.filter(mask)

    if filtered_t.num_rows != partition_cfg["expected_rows"]:
        raise ValueError(
            f"Filtered row count mismatch for {pid}: "
            f"got {filtered_t.num_rows}, expected {partition_cfg['expected_rows']}"
        )

    min_ts = pc.min(filtered_t["ts_event_ns"]).as_py()
    max_ts = pc.max(filtered_t["ts_event_ns"]).as_py()

    if min_ts != partition_cfg["start_ts_ns"] or max_ts != partition_cfg["end_ts_ns"]:
        raise ValueError(
            f"Timestamp bounds mismatch for {pid}: "
            f"got [{min_ts}, {max_ts}], expected [{partition_cfg['start_ts_ns']}, {partition_cfg['end_ts_ns']}]"
        )

    # 3. Attach custom metadata
    custom_meta = {
        b"dataset_role": role.encode("utf-8"),
        b"partition_id": pid.encode("utf-8"),
        b"start_ts_ns": str(min_ts).encode("utf-8"),
        b"end_ts_ns": str(max_ts).encode("utf-8"),
    }
    filtered_t = filtered_t.replace_schema_metadata(custom_meta)

    # 4. Verify logical content hash before writing
    actual_logical_sha = compute_partition_logical_sha256(filtered_t)
    expected_logical_sha = partition_cfg["partition_logical_sha256"]
    if actual_logical_sha != expected_logical_sha:
        raise ValueError(
            f"Logical content hash mismatch for {pid}: "
            f"got {actual_logical_sha}, expected {expected_logical_sha}"
        )

    # 5. Write to atomic .part file
    output_dir.mkdir(parents=True, exist_ok=True)
    if part_path.is_file():
        part_path.unlink()

    pq.write_table(filtered_t, part_path, compression="snappy")

    # 6. Verify physical SHA-256 of written .part file
    actual_physical_sha = compute_file_sha256(part_path)
    expected_physical_sha = partition_cfg["expected_physical_sha256"]
    if actual_physical_sha != expected_physical_sha:
        part_path.unlink()
        raise ValueError(
            f"Physical SHA-256 mismatch for {pid}: "
            f"got {actual_physical_sha}, expected {expected_physical_sha}"
        )

    # 7. Atomic rename
    part_path.replace(target_path)

    v_res = verify_partition_file(partition_cfg, output_dir)
    v_res["action"] = "MATERIALIZED"
    return v_res


def materialize_all(
    manifest_path: Path = DEFAULT_CONFIG_PATH,
    parent_dir: Path = DEFAULT_PARENT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    verify_only: bool = False,
    force: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Verify or materialize all 8 physical partitions."""
    if not manifest_path.is_file():
        return False, {"error": f"Manifest not found: {manifest_path}"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 1. Parent artifact verification
    parent_results = verify_parent_artifacts(manifest, parent_dir)
    parent_ok = all(r.get("matches", False) for r in parent_results.values())
    if not parent_ok:
        return False, {
            "error": "Parent artifact verification failed",
            "parent_results": parent_results,
        }

    # 2. Partition verification / materialization
    partitions = manifest.get("partitions", {})
    partition_results: dict[str, Any] = {}
    all_ok = True

    for pid, p_cfg in partitions.items():
        if verify_only:
            res = verify_partition_file(p_cfg, output_dir)
        else:
            res = materialize_single_partition(p_cfg, parent_dir, output_dir, force=force)
        partition_results[pid] = res
        if not res.get("verified", False):
            all_ok = False

    return all_ok, {
        "parent_artifacts": parent_results,
        "partitions": partition_results,
        "all_verified": all_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize and verify Round 3B research partitions")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to partition manifest JSON")
    parser.add_argument("--parent-dir", type=Path, default=DEFAULT_PARENT_DIR, help="Directory containing parent Silver datasets")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory to output physical partitions")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing partitions without materializing")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing partitions")
    args = parser.parse_args()

    print("=== BTCETH Trading OS: Research Partition Materializer ===")
    print(f"Manifest: {args.config}")
    print(f"Parent Dir: {args.parent_dir}")
    print(f"Output Dir: {args.output_dir}")
    print(f"Mode: {'VERIFY_ONLY' if args.verify_only else 'MATERIALIZE'}")

    success, details = materialize_all(
        manifest_path=args.config,
        parent_dir=args.parent_dir,
        output_dir=args.output_dir,
        verify_only=args.verify_only,
        force=args.force,
    )

    if not success:
        print("\n[ERROR] Partition verification / materialization FAILED:")
        print(json.dumps(details, indent=2))
        return 1

    print("\n[SUCCESS] All 8 physical partitions verified and cryptographically bound:")
    for pid, res in details.get("partitions", {}).items():
        action = res.get("action", "VERIFIED")
        sha = res.get("actual_physical_sha256", "")[:16]
        logical_sha = res.get("actual_logical_sha256", "")[:16]
        rows = res.get("actual_rows", 0)
        print(f"  {pid:30s} | {action:12s} | rows={rows:5d} | phy={sha}... | log={logical_sha}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
