#!/usr/bin/env python3
"""Acquire and hash-verify the exact PhysioNet MIT-BIH Arrhythmia Database v1.0.0.

Network access required. Downloads only the required core scientific files
(<record>.hea, <record>.dat, <record>.atr) for the official 48 records, verifies each
against PhysioNet's own SHA256SUMS.txt (the remote expected-hash authority), and writes
acquisition provenance. Idempotent: a local file that already matches its expected hash is
not re-downloaded. A local file with the wrong hash is never trusted silently.

Does not download x_mitdb/, mitdbdir/, .xws, or historical backup annotation files
(e.g. 102-0.atr) -- those are not part of the required core scientific file set.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "MITDB"
DATASET_VERSION = "1.0.0"
SOURCE_URL = "https://physionet.org/content/mitdb/1.0.0/"
FILES_BASE_URL = "https://physionet.org/files/mitdb/1.0.0/"
DOI = "10.13026/C2F305"
LICENSE = "Open Data Commons Attribution License v1.0"
RAW_ROOT = ROOT / "data/raw/mitdb/1.0.0"
REQUIRED_EXTENSIONS = ("hea", "dat", "atr")

DOCUMENTED_SOURCE = {
    "record_count": 48,
    "subject_count_documented": 47,
    "sampling_rate_hz": 360,
    "source_channel_count": 2,
}


def _fetch_text(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _fetch_bytes(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def fetch_records_list() -> list[str]:
    text = _fetch_text(FILES_BASE_URL + "RECORDS")
    return [line.strip() for line in text.splitlines() if line.strip()]


def fetch_official_sha256sums() -> dict[str, str]:
    text = _fetch_text(FILES_BASE_URL + "SHA256SUMS.txt")
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


def required_files_for(records: list[str]) -> list[str]:
    return [f"{record}.{ext}" for record in records for ext in REQUIRED_EXTENSIONS]


def download_and_verify(filename: str, expected_sha256: str, *, force: bool = False) -> dict:
    dest = RAW_ROOT / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
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
    data = _fetch_bytes(FILES_BASE_URL + filename)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Redownload even if a verified copy exists"
    )
    args = parser.parse_args()

    print(f"Acquiring {DATASET_ID} v{DATASET_VERSION} from {FILES_BASE_URL}")
    records = fetch_records_list()
    if len(records) != DOCUMENTED_SOURCE["record_count"]:
        raise RuntimeError(
            f"DATASET_SOURCE_CONFLICT: official RECORDS lists {len(records)} records, "
            f"expected {DOCUMENTED_SOURCE['record_count']}"
        )
    if len(set(records)) != len(records):
        raise RuntimeError("DATASET_SOURCE_CONFLICT: duplicate record IDs in official RECORDS")

    official_hashes = fetch_official_sha256sums()
    required = required_files_for(records)
    missing_from_sums = [name for name in required if name not in official_hashes]
    if missing_from_sums:
        raise RuntimeError(
            "DATASET_SOURCE_CONFLICT: SHA256SUMS.txt missing expected entries: "
            f"{missing_from_sums[:5]}"
        )

    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    actions = []
    for filename in required:
        result = download_and_verify(filename, official_hashes[filename], force=args.force)
        actions.append(result)
        print(f"  {result['action']:>16}  {filename}")

    # Persist the exact official record list and the required-file hash subset locally so the
    # source can be reconstructed/re-verified even if PhysioNet's presentation changes later.
    # .gitignore explicitly allows tracking data/raw/**/SHA256SUMS.txt (not raw payload bytes).
    (RAW_ROOT / "RECORDS").write_text("\n".join(records) + "\n", encoding="utf-8")
    (RAW_ROOT / "SHA256SUMS.txt").write_text(
        "\n".join(f"{official_hashes[name]} {name}" for name in required) + "\n", encoding="utf-8"
    )

    acquisition_metadata = {
        "dataset_id": DATASET_ID,
        "version": DATASET_VERSION,
        "source_url": SOURCE_URL,
        "files_base_url": FILES_BASE_URL,
        "doi": DOI,
        "license": LICENSE,
        "downloaded_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "documented_source": DOCUMENTED_SOURCE,
        "record_count": len(records),
        "records": records,
        "required_file_count": len(required),
        "actions": actions,
        "raw_data_root": str(RAW_ROOT.relative_to(ROOT)),
        "raw_data_committed": False,
    }
    output = ROOT / "reports/t006/acquisition_metadata.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(acquisition_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    print(f"Acquisition complete: {len(records)} records, {len(required)} files verified.")


if __name__ == "__main__":
    main()
