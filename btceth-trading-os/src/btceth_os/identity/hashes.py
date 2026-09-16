from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def compute_bytes_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest for in-memory bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(path: Path | str, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest for a file on disk using streaming chunks."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found for hash calculation: {path}")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


class IncrementalSha256:
    """Incremental streaming SHA-256 hasher for downloads and streaming I/O."""

    def __init__(self) -> None:
        self._hasher = hashlib.sha256()
        self._bytes_hashed = 0

    def update(self, chunk: bytes) -> None:
        self._hasher.update(chunk)
        self._bytes_hashed += len(chunk)

    @property
    def bytes_hashed(self) -> int:
        return self._bytes_hashed

    def hexdigest(self) -> str:
        return self._hasher.hexdigest()


def compute_logical_sha256(record_keys: Iterable[str], payload_hashes: Iterable[str]) -> str:
    """Compute deterministic logical dataset hash independent of filesystem or compression metadata.

    The logical hash represents semantic content identity based on sorted record keys and payload hashes.
    """
    paired = sorted(zip(record_keys, payload_hashes), key=lambda x: x[0])
    h = hashlib.sha256()
    for key, phash in paired:
        line = f"{key}:{phash}\n"
        h.update(line.encode("utf-8"))
    return h.hexdigest()
