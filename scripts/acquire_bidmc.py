#!/usr/bin/env python3
"""Acquire and hash-verify the exact PhysioNet BIDMC PPG and Respiration Dataset v1.0.0.

Network access required. Downloads only the WFDB files required for NHM's engineering role:
<record>.hea/.dat (waveform, 125 Hz target) and <record>n.hea/.dat (numerics, 1 Hz target)
for the official 53 records. Verifies each against PhysioNet's own SHA256SUMS.txt.
Idempotent: an existing, correctly-hashed local file is never re-downloaded.

Deliberately does NOT acquire: .breath annotation files (not part of NHM's PPG/SpO2/HR role;
see contracts/WEARABLE_SIM_V1.md-style role boundaries), the bidmc_csv/ or bidmc_data.mat
alternate representations (the WFDB files are the single authoritative representation per
task instructions Section 16), or documentation/ANNOTATORS/DBS/LICENSE/README files.
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
DATASET_ID = "BIDMC"
DATASET_VERSION = "1.0.0"
SOURCE_URL = "https://physionet.org/content/bidmc/1.0.0/"
FILES_BASE_URL = "https://physionet.org/files/bidmc/1.0.0/"
DOI = "10.13026/C2208R"
LICENSE = "Open Data Commons Attribution License v1.0"
RAW_ROOT = ROOT / "data/raw/bidmc/1.0.0"

DOCUMENTED_SOURCE = {
    "record_count": 53,
    "duration_minutes": 8,
    "waveform_sampling_rate_hz": 125,
    "numerics_sampling_rate_hz": 1,
}


def required_files_for(records: list[str]) -> list[str]:
    required = []
    for record in records:
        required += [f"{record}.hea", f"{record}.dat", f"{record}n.hea", f"{record}n.dat"]
    return required


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
        "excluded_by_design": [".breath", "bidmc_csv/*", "bidmc_data.mat"],
        "actions": actions,
        "raw_data_root": str(RAW_ROOT.relative_to(ROOT)),
        "raw_data_committed": False,
    }
    output = ROOT / "reports/t007/bidmc_acquisition_metadata.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(acquisition_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    print(f"Acquisition complete: {len(records)} records, {len(required)} files verified.")


if __name__ == "__main__":
    main()
