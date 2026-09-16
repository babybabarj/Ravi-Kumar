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


def compute_logical_sha256(
    record_keys_or_pairs: Iterable[tuple[str, str]] | Sequence[str],
    payload_hashes: Sequence[str] | None = None,
) -> str:
    """Compute deterministic logical dataset hash independent of filesystem or compression metadata.

    The logical hash represents semantic content identity based on sorted (record_key, payload_hash) pairs.
    Accepts either:
      - A single iterable of (record_key, payload_hash) tuples
      - Two sequences: record_keys and payload_hashes of identical length
    """
    pairs: list[tuple[str, str]] = []
    if payload_hashes is not None:
        keys_seq = list(record_keys_or_pairs)  # type: ignore[arg-type]
        hashes_seq = list(payload_hashes)
        if len(keys_seq) != len(hashes_seq):
            raise ValueError(
                f"Length mismatch in compute_logical_sha256: record_keys={len(keys_seq)} != payload_hashes={len(hashes_seq)}"
            )
        pairs = list(zip(keys_seq, hashes_seq))
    else:
        for item in record_keys_or_pairs:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ValueError(f"Expected (record_key, payload_hash) tuple, got: {item!r}")
            pairs.append((str(item[0]), str(item[1])))

    # Sort deterministically by the entire semantic pair (key, payload_hash)
    pairs.sort(key=lambda x: (x[0], x[1]))

    # Use unambiguous length-prefixed framing: {len_key}:{key}:{len_hash}:{hash}\n
    h = hashlib.sha256()
    for key, phash in pairs:
        framed = f"{len(key)}:{key}:{len(phash)}:{phash}\n"
        h.update(framed.encode("utf-8"))
    return h.hexdigest()
