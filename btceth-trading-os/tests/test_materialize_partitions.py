"""Tests for deterministic partition materialization pipeline.

Research Round 3B.0D: Reproducible Research Partition Closure.
Verifies:
- Manifest structure and parent artifact cryptographics
- All 8 physical partitions match row counts, timestamps, and independent logical hashes
- Rebuild test: materialization in sandbox reproduces exact physical and logical digests
- Fresh git worktree reconstruction test: clean worktree can materialize and verify all 8 partitions
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from tools.materialize_round3b_research_partitions import (
    compute_file_sha256,
    compute_partition_logical_sha256,
    materialize_all,
    verify_parent_artifacts,
    verify_partition_file,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "research_partitions_v1.json"
PARENT_DIR = ROOT / "artifacts" / "research" / "silver_v3"
PARTITIONS_DIR = ROOT / "artifacts" / "research" / "partitions"


def test_manifest_structure():
    """Verify that config/research_partitions_v1.json is valid and contains all 8 partitions."""
    assert MANIFEST_PATH.is_file(), f"Manifest file missing: {MANIFEST_PATH}"
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert "parent_artifacts" in manifest
    assert len(manifest["parent_artifacts"]) == 4

    assert "partitions" in manifest
    assert len(manifest["partitions"]) == 8

    for pid, pcfg in manifest["partitions"].items():
        assert "file_name" in pcfg
        assert "role" in pcfg
        assert pcfg["role"] in ("DEVELOPMENT", "VALIDATION")
        assert "parent_artifact" in pcfg
        assert "parent_physical_sha256" in pcfg
        assert "start_ts_ns" in pcfg
        assert "end_ts_ns" in pcfg
        assert "expected_rows" in pcfg
        assert "partition_logical_sha256" in pcfg
        assert "expected_physical_sha256" in pcfg
        assert len(pcfg["partition_logical_sha256"]) == 64
        assert len(pcfg["expected_physical_sha256"]) == 64


def check_parent_present() -> bool:
    return (PARENT_DIR / "BTCUSDT-resampled-1h-v3.1.0.parquet").is_file()


def test_parent_artifacts_verified():
    """Verify that all 4 parent Silver artifacts match their physical digests."""
    if not check_parent_present():
        pytest.skip("BTCUSDT-resampled-1h-v3.1.0.parquet not present on disk")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    results = verify_parent_artifacts(manifest, PARENT_DIR)

    assert len(results) == 4
    for fname, r in results.items():
        assert r["file_exists"] is True, f"Parent file {fname} missing"
        assert r["matches"] is True, f"Parent file {fname} SHA mismatch: {r.get('error')}"


def test_partitions_verified():
    """Verify that all 8 partitions exist, have correct bounds, rows, and independent logical SHAs."""
    if not check_parent_present():
        pytest.skip("BTCUSDT-resampled-1h-v3.1.0.parquet not present on disk")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    success, details = materialize_all(
        manifest_path=MANIFEST_PATH,
        parent_dir=PARENT_DIR,
        output_dir=PARTITIONS_DIR,
        verify_only=True,
    )
    assert success is True, f"Verification failed: {details}"

    for pid, r in details["partitions"].items():
        assert r["exists"] is True
        assert r["physical_matches"] is True
        assert r["rows_match"] is True
        assert r["bounds_match"] is True
        assert r["role_bounds_ok"] is True
        assert r["logical_matches"] is True
        assert r["verified"] is True


def test_sandbox_partition_rebuild():
    """Materialize partitions into a fresh temporary sandbox and assert exact SHA-256 match."""
    if not check_parent_present():
        pytest.skip("BTCUSDT-resampled-1h-v3.1.0.parquet not present on disk")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_output = Path(tmp_dir)

        success, details = materialize_all(
            manifest_path=MANIFEST_PATH,
            parent_dir=PARENT_DIR,
            output_dir=tmp_output,
            verify_only=False,
            force=True,
        )

        assert success is True, f"Sandbox materialization failed: {details}"

        # Verify all 8 files exist and physical SHAs match production partitions exactly
        for pid, pcfg in manifest["partitions"].items():
            fname = pcfg["file_name"]
            sandbox_file = tmp_output / fname
            assert sandbox_file.is_file(), f"Sandbox partition file missing: {fname}"

            sandbox_sha = compute_file_sha256(sandbox_file)
            assert sandbox_sha == pcfg["expected_physical_sha256"], (
                f"Physical SHA mismatch in sandbox for {fname}: got {sandbox_sha}, expected {pcfg['expected_physical_sha256']}"
            )

            t = pq.read_table(sandbox_file)
            logical_sha = compute_partition_logical_sha256(t)
            assert logical_sha == pcfg["partition_logical_sha256"], (
                f"Logical SHA mismatch in sandbox for {fname}: got {logical_sha}, expected {pcfg['partition_logical_sha256']}"
            )


def test_fresh_worktree_reconstruction():
    """Verify that a fresh isolated git worktree can reconstruct partitions cleanly."""
    if not check_parent_present():
        pytest.skip("BTCUSDT-resampled-1h-v3.1.0.parquet not present on disk")
    with tempfile.TemporaryDirectory() as tmp_dir:
        worktree_path = Path(tmp_dir) / "test_wt"

        # Create worktree
        add_res = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            assert add_res.returncode == 0, f"git worktree add failed: {add_res.stderr}"

            # Run partition materializer inside the fresh worktree, pointing parent to parent dir
            wt_output_dir = worktree_path / "artifacts" / "research" / "partitions"
            wt_config_path = worktree_path / "config" / "research_partitions_v1.json"

            # If config is not yet committed to HEAD, copy current config
            if not wt_config_path.is_file():
                wt_config_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(MANIFEST_PATH, wt_config_path)

            wt_tool_path = worktree_path / "tools" / "materialize_round3b_research_partitions.py"
            if not wt_tool_path.is_file():
                wt_tool_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / "tools" / "materialize_round3b_research_partitions.py", wt_tool_path)

            python_bin = ROOT / ".venv-phase1a" / "bin" / "python"
            run_res = subprocess.run(
                [
                    str(python_bin),
                    str(wt_tool_path),
                    "--config", str(wt_config_path),
                    "--parent-dir", str(PARENT_DIR),
                    "--output-dir", str(wt_output_dir),
                    "--force",
                ],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                check=False,
            )
            assert run_res.returncode == 0, f"Fresh worktree materialization failed:\nSTDOUT:\n{run_res.stdout}\nSTDERR:\n{run_res.stderr}"

            # Verify verify-only passes on fresh worktree
            verify_res = subprocess.run(
                [
                    str(python_bin),
                    str(wt_tool_path),
                    "--config", str(wt_config_path),
                    "--parent-dir", str(PARENT_DIR),
                    "--output-dir", str(wt_output_dir),
                    "--verify-only",
                ],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                check=False,
            )
            assert verify_res.returncode == 0, f"Fresh worktree verify-only failed: {verify_res.stderr}"

        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=ROOT,
                capture_output=True,
                check=False,
            )
