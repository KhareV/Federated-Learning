"""Shared PhysioNet acquisition primitives, extracted from the T006 MITDB pattern.

Generic download/verify/parse helpers only. No dataset-specific record semantics, channel
policies, or role logic live here -- those stay in datasets/mitdb.py, datasets/incart.py,
datasets/nstdb.py, and datasets/bidmc.py respectively.
"""

from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file

RETRYABLE_ERRORS = (
    TimeoutError,
    ConnectionError,
    urllib.error.URLError,
    http.client.IncompleteRead,
    http.client.HTTPException,
)


def fetch_text(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_bytes(url: str, timeout: int = 300, *, attempts: int = 8) -> bytes:
    """Fetch `url`, retrying a bounded number of times on transient network errors
    (timeouts, connection resets) with linear backoff. Does not retry on HTTP error
    responses (4xx/5xx) or non-network failures -- those propagate immediately."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read()
        except RETRYABLE_ERRORS as error:
            last_error = error
            if attempt < attempts:
                time.sleep(min(5 * attempt, 30))
    assert last_error is not None
    raise last_error


def parse_records_list(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_sha256_manifest(text: str) -> dict[str, str]:
    """Parse a PhysioNet SHA256SUMS.txt-style ``<hex digest>  <filename>`` listing."""
    hashes: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts
        hashes[name] = digest
    return hashes


def download_and_verify(
    dest: Path, url: str, expected_sha256: str, *, force: bool = False
) -> dict[str, Any]:
    """Idempotently acquire ``url`` into ``dest``, verifying against ``expected_sha256``.

    An existing file that already matches is not re-downloaded ("already_verified"). An
    existing file with the wrong hash is never trusted or silently overwritten -- it raises
    DATASET_HASH_MISMATCH. A freshly downloaded file is hash-verified before being atomically
    moved into place; a bad download is discarded, never left as a corrupt partial file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    filename = dest.name
    if dest.exists() and not force:
        local_hash = hash_file(dest)
        if local_hash == expected_sha256:
            return {
                "file": filename,
                "action": "already_verified",
                "sha256": local_hash,
                "match": True,
            }
        raise RuntimeError(
            f"DATASET_HASH_MISMATCH: existing {filename} has sha256={local_hash}, "
            f"expected {expected_sha256}. Refusing to trust or overwrite it silently; "
            "remove the file and rerun, or investigate local corruption."
        )
    data = fetch_bytes(url)
    temporary = dest.with_name(dest.name + ".part")
    temporary.write_bytes(data)
    local_hash = hash_file(temporary)
    if local_hash != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"DATASET_HASH_MISMATCH: downloaded {filename} has sha256={local_hash}, "
            f"expected {expected_sha256}."
        )
    temporary.replace(dest)
    return {"file": filename, "action": "downloaded", "sha256": local_hash, "match": True}


def write_local_provenance(
    raw_root: Path, records: list[str], hashes_by_file: dict[str, str]
) -> None:
    """Persist the exact official record list and required-file hash subset locally.

    .gitignore explicitly allows tracking data/raw/**/SHA256SUMS.txt (not raw payload bytes),
    so this file becomes committed provenance even though the dataset itself is not.
    """
    (raw_root / "RECORDS").write_text("\n".join(records) + "\n", encoding="utf-8")
    (raw_root / "SHA256SUMS.txt").write_text(
        "\n".join(f"{digest} {name}" for name, digest in hashes_by_file.items()) + "\n",
        encoding="utf-8",
    )
