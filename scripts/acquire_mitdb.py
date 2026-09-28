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
from datetime import UTC, datetime
from pathlib import Path

from datasets.physionet import (
    download_and_verify,
    fetch_text,
    parse_records_list,
    parse_sha256_manifest,
    write_local_provenance,
)

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


def required_files_for(records: list[str]) -> list[str]:
    return [f"{record}.{ext}" for record in records for ext in REQUIRED_EXTENSIONS]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Redownload even if a verified copy exists"
    )
    args = parser.parse_args()

    print(f"Acquiring {DATASET_ID} v{DATASET_VERSION} from {FILES_BASE_URL}")
    records = parse_records_list(fetch_text(FILES_BASE_URL + "RECORDS"))
    if len(records) != DOCUMENTED_SOURCE["record_count"]:
        raise RuntimeError(
            f"DATASET_SOURCE_CONFLICT: official RECORDS lists {len(records)} records, "
            f"expected {DOCUMENTED_SOURCE['record_count']}"
        )
    if len(set(records)) != len(records):
        raise RuntimeError("DATASET_SOURCE_CONFLICT: duplicate record IDs in official RECORDS")

    official_hashes = parse_sha256_manifest(fetch_text(FILES_BASE_URL + "SHA256SUMS.txt"))
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
        result = download_and_verify(
            RAW_ROOT / filename,
            FILES_BASE_URL + filename,
            official_hashes[filename],
            force=args.force,
        )
        actions.append(result)
        print(f"  {result['action']:>16}  {filename}")

    write_local_provenance(RAW_ROOT, records, {name: official_hashes[name] for name in required})

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
