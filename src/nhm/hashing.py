"""The single canonical SHA-256 convention for NHM artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HASH_ALGORITHM = "sha256"


def hash_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 hex digest for *data*."""
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value using the project canonical form.

    The form is UTF-8, sorted by key, compactly separated, Unicode-preserving,
    and rejects non-standard NaN/Infinity values.
    """
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return serialized.encode("utf-8")


def hash_canonical_json(value: Any) -> str:
    """Hash a JSON-compatible value after canonical serialization."""
    return hash_bytes(canonical_json_bytes(value))


def hash_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file without loading the whole artifact into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

