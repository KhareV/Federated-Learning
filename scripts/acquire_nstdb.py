#!/usr/bin/env python3
"""Acquire and hash-verify the exact PhysioNet MIT-BIH Noise Stress Test Database v1.0.0.

Network access required. Downloads only the required core scientific files for the 15
official records: <id>.hea/.dat/.atr for the 12 stress-ECG records (118e*/119e*), and
<id>.hea/.dat only for the 3 pure-noise records (bw/em/ma), which have no beat annotation by
source design. Verifies each file against PhysioNet's own SHA256SUMS.txt. Idempotent.

Does not download old/, .xws, *-suffixed backup headers (e.g. bw.hea-), nstdbgen*, or
documentation files -- those are not part of the required core scientific file set.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from datasets.nstdb import NOISE_TYPE_BY_RECORD, SNR_DB_BY_SUFFIX, STRESS_SOURCES
from datasets.physionet import (
    download_and_verify,
    fetch_text,
    parse_records_list,
    parse_sha256_manifest,
    write_local_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "NSTDB"
DATASET_VERSION = "1.0.0"
SOURCE_URL = "https://physionet.org/content/nstdb/1.0.0/"
FILES_BASE_URL = "https://physionet.org/files/nstdb/1.0.0/"
DOI = "10.13026/C2HS3T"
LICENSE = "Open Data Commons Attribution License v1.0"
RAW_ROOT = ROOT / "data/raw/nstdb/1.0.0"

DOCUMENTED_SOURCE = {
    "record_count": 15,
    "stress_ecg_count": 12,
    "pure_noise_count": 3,
    "sampling_rate_hz": 360,
}


def is_stress_record(record_id: str) -> bool:
    return any(
        record_id.startswith(source + "e") and record_id[len(source) :] in SNR_DB_BY_SUFFIX
        for source in STRESS_SOURCES
    )


def required_files_for(records: list[str]) -> list[str]:
    required = []
    for record in records:
        if record in NOISE_TYPE_BY_RECORD:
            required += [f"{record}.hea", f"{record}.dat"]
        elif is_stress_record(record):
            required += [f"{record}.hea", f"{record}.dat", f"{record}.atr"]
        else:
            raise RuntimeError(
                f"DATASET_SOURCE_CONFLICT: official RECORDS contains unrecognized entry "
                f"{record!r} matching neither the stress-ECG nor pure-noise naming convention"
            )
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

    stress_count = sum(1 for record in records if is_stress_record(record))
    noise_count = sum(1 for record in records if record in NOISE_TYPE_BY_RECORD)
    if stress_count != DOCUMENTED_SOURCE["stress_ecg_count"]:
        raise RuntimeError(
            f"DATASET_SOURCE_CONFLICT: observed {stress_count} stress-ECG records, "
            f"expected {DOCUMENTED_SOURCE['stress_ecg_count']}"
        )
    if noise_count != DOCUMENTED_SOURCE["pure_noise_count"]:
        raise RuntimeError(
            f"DATASET_SOURCE_CONFLICT: observed {noise_count} pure-noise records, "
            f"expected {DOCUMENTED_SOURCE['pure_noise_count']}"
        )

    official_hashes = parse_sha256_manifest(fetch_text(FILES_BASE_URL + "SHA256SUMS.txt"))
    required = required_files_for(records)
    missing_from_sums = [name for name in required if name not in official_hashes]
    if missing_from_sums:
        raise RuntimeError(
            "DATASET_SOURCE_CONFLICT: SHA256SUMS.txt missing expected entries: "
            f"{missing_from_sums}"
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
    output = ROOT / "reports/t007/nstdb_acquisition_metadata.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(acquisition_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    print(f"Acquisition complete: {len(records)} records, {len(required)} files verified.")


if __name__ == "__main__":
    main()
