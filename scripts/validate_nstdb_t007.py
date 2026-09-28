#!/usr/bin/env python3
"""Offline real-data validator for T007: MIT-BIH Noise Stress Test Database v1.0.0.

Requires an already-acquired local dataset (scripts/acquire_nstdb.py). No network access
here. Fails clearly (NSTDB_DATA_NOT_ACQUIRED) rather than silently skipping.

Does not run the noise-robustness experiment (T019's scope) or compute any accuracy/AUPRC.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from datasets.nstdb import (
    DATASET_ID,
    DATASET_VERSION,
    NOISE_TYPE_BY_RECORD,
    PURE_NOISE,
    SNR_DB_BY_SUFFIX,
    STRESS_ECG,
    STRESS_SOURCES,
    data_not_acquired_error,
    list_records,
    validate_record,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data/raw/nstdb/1.0.0"
ACQUISITION_METADATA = ROOT / "reports/t007/nstdb_acquisition_metadata.json"
MANIFEST_DIR = ROOT / "manifests/datasets"
REPORT_DIR = ROOT / "reports/t007"

REQUIRED_ROLE_BY_EXTENSION = {"hea": "header", "dat": "signal", "atr": "annotation"}
EXPECTED_RECORD_COUNT = 15
EXPECTED_STRESS_COUNT = 12
EXPECTED_NOISE_COUNT = 3


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
        else:
            required += [f"{record}.hea", f"{record}.dat", f"{record}.atr"]
    return required


def load_acquisition_metadata() -> dict[str, Any]:
    if not ACQUISITION_METADATA.exists():
        raise FileNotFoundError(
            "NSTDB_DATA_NOT_ACQUIRED: reports/t007/nstdb_acquisition_metadata.json is "
            "missing. Run scripts/acquire_nstdb.py first; real local data is required."
        )
    return json.loads(ACQUISITION_METADATA.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def verify_file_hashes(acquisition: dict[str, Any]) -> list[dict[str, Any]]:
    expected_by_file = {action["file"]: action["sha256"] for action in acquisition["actions"]}
    rows = []
    for filename in sorted(expected_by_file):
        expected = expected_by_file[filename]
        path = RAW_ROOT / filename
        record_id, ext = filename.rsplit(".", 1)
        role = REQUIRED_ROLE_BY_EXTENSION[ext]
        local_sha256 = hash_file(path) if path.exists() else ""
        rows.append(
            {
                "relative_path": f"data/raw/nstdb/1.0.0/{filename}",
                "record_id": record_id,
                "role": role,
                "official_sha256": expected,
                "local_sha256": local_sha256,
                "verified": local_sha256 == expected and local_sha256 != "",
            }
        )
    return rows


def main() -> None:
    if not RAW_ROOT.exists():
        raise data_not_acquired_error(RAW_ROOT)
    acquisition = load_acquisition_metadata()
    records = list_records(RAW_ROOT)

    if len(records) != EXPECTED_RECORD_COUNT:
        raise RuntimeError(
            f"DATASET_SOURCE_CONFLICT: expected {EXPECTED_RECORD_COUNT} local records, "
            f"found {len(records)}"
        )
    if len(set(records)) != len(records):
        raise RuntimeError("DATASET_SOURCE_CONFLICT: duplicate record IDs in local RECORDS")

    stress_count = sum(1 for record in records if is_stress_record(record))
    noise_count = sum(1 for record in records if record in NOISE_TYPE_BY_RECORD)
    if stress_count != EXPECTED_STRESS_COUNT or noise_count != EXPECTED_NOISE_COUNT:
        raise RuntimeError(
            f"DATASET_SOURCE_CONFLICT: observed {stress_count} stress-ECG / {noise_count} "
            f"pure-noise records, expected {EXPECTED_STRESS_COUNT}/{EXPECTED_NOISE_COUNT}"
        )

    file_rows = verify_file_hashes(acquisition)
    if {row["relative_path"].rsplit("/", 1)[-1] for row in file_rows} != set(
        required_files_for(records)
    ):
        raise RuntimeError("DATASET_SOURCE_CONFLICT: acquired file set does not match required set")
    hashes_verified = all(row["verified"] for row in file_rows)
    if not hashes_verified:
        mismatched = [row["relative_path"] for row in file_rows if not row["verified"]]
        raise RuntimeError(f"DATASET_HASH_MISMATCH: {mismatched}")

    record_rows: list[dict[str, Any]] = []
    headers_parsed = signals_parsed = 0
    stress_annotations_parsed = 0
    parse_failures = 0
    snr_mapping_failures = 0
    noise_type_failures = 0

    for record_id in records:
        validation = validate_record(record_id, RAW_ROOT)
        if validation["errors"]:
            parse_failures += 1
        headers_parsed += int(validation["header_parsed"])
        signals_parsed += int(validation["signal_parsed"])
        if validation["role"] == STRESS_ECG:
            stress_annotations_parsed += int(
                validation["annotation_parsed"] and validation["annotation_count"] > 0
            )
            if validation["snr_db"] not in SNR_DB_BY_SUFFIX.values():
                snr_mapping_failures += 1
        elif validation["role"] == PURE_NOISE:
            if validation["noise_type"] not in NOISE_TYPE_BY_RECORD.values():
                noise_type_failures += 1

        record_rows.append(
            {
                "record_id": record_id,
                "role": validation["role"],
                "clean_source_record": validation["clean_source_record"],
                "snr_db": validation["snr_db"],
                "noise_type": validation["noise_type"],
                "header_parsed": validation["header_parsed"],
                "signal_parsed": validation["signal_parsed"],
                "annotation_parsed": validation["annotation_parsed"],
                "annotation_expected": validation["annotation_expected"],
                "fs": validation["fs"],
                "n_sig": validation["n_sig"],
                "signal_finite": validation["signal_finite"],
                "annotation_count": validation["annotation_count"],
                "errors": ";".join(validation["errors"]),
            }
        )

    hard_integrity_ok = (
        headers_parsed == EXPECTED_RECORD_COUNT
        and signals_parsed == EXPECTED_RECORD_COUNT
        and stress_annotations_parsed == EXPECTED_STRESS_COUNT
        and parse_failures == 0
        and snr_mapping_failures == 0
        and noise_type_failures == 0
    )
    if not hard_integrity_ok:
        raise RuntimeError(
            "DATASET_SOURCE_CONFLICT: real NSTDB v1.0.0 failed a hard integrity invariant "
            f"(headers_parsed={headers_parsed}, signals_parsed={signals_parsed}, "
            f"stress_annotations_parsed={stress_annotations_parsed}, "
            f"parse_failures={parse_failures}, snr_mapping_failures={snr_mapping_failures}, "
            f"noise_type_failures={noise_type_failures})"
        )

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(
        MANIFEST_DIR / "nstdb_v1_files.csv",
        ["relative_path", "record_id", "role", "official_sha256", "local_sha256", "verified"],
        file_rows,
    )
    write_csv(
        MANIFEST_DIR / "nstdb_records.csv",
        [
            "record_id",
            "role",
            "clean_source_record",
            "snr_db",
            "noise_type",
            "fs",
            "signal_count",
            "annotation_present",
            "hash_verified",
        ],
        [
            {
                "record_id": row["record_id"],
                "role": row["role"],
                "clean_source_record": row["clean_source_record"],
                "snr_db": row["snr_db"],
                "noise_type": row["noise_type"],
                "fs": row["fs"],
                "signal_count": row["n_sig"],
                "annotation_present": row["annotation_expected"],
                "hash_verified": True,
            }
            for row in record_rows
        ],
    )

    records_file_hash = hash_file(RAW_ROOT / "RECORDS")
    official_sha256_manifest_hash = hash_file(RAW_ROOT / "SHA256SUMS.txt")
    manifest_yaml = {
        "dataset_id": DATASET_ID,
        "official_name": "MIT-BIH Noise Stress Test Database",
        "version": DATASET_VERSION,
        "provider": "PhysioNet",
        "source_url": acquisition["source_url"],
        "files_base_url": acquisition["files_base_url"],
        "doi": acquisition["doi"],
        "license": acquisition["license"],
        "downloaded_at_utc": acquisition["downloaded_at_utc"],
        "documented_source": acquisition["documented_source"],
        "observed_local_validation": {
            "records_in_RECORDS": len(records),
            "parsed_records": headers_parsed,
            "stress_ecg_count": stress_count,
            "pure_noise_count": noise_count,
        },
        "records_file_hash": records_file_hash,
        "official_sha256_manifest_hash": official_sha256_manifest_hash,
        "records_manifest_path": "manifests/datasets/nstdb_records.csv",
        "role": "NOISE_ROBUSTNESS",
        "owning_task": "T019",
        "raw_data_root": str(RAW_ROOT.relative_to(ROOT)),
        "raw_data_committed": False,
        "validation_status": "PASS",
    }
    temporary = (MANIFEST_DIR / "nstdb_v1.yaml").with_suffix(".yaml.tmp")
    temporary.write_text(yaml.safe_dump(manifest_yaml, sort_keys=True), encoding="utf-8")
    temporary.replace(MANIFEST_DIR / "nstdb_v1.yaml")

    write_csv(
        REPORT_DIR / "nstdb_record_validation.csv",
        [
            "record_id",
            "role",
            "clean_source_record",
            "snr_db",
            "noise_type",
            "header_parsed",
            "signal_parsed",
            "annotation_parsed",
            "annotation_expected",
            "fs",
            "n_sig",
            "signal_finite",
            "annotation_count",
            "errors",
        ],
        record_rows,
    )

    nstdb_validation = {
        "dataset_id": DATASET_ID,
        "version": DATASET_VERSION,
        "official_record_count": EXPECTED_RECORD_COUNT,
        "stress_ecg_count": stress_count,
        "pure_noise_count": noise_count,
        "hashes_verified": hashes_verified,
        "snr_mapping_status": "PASS" if snr_mapping_failures == 0 else "FAIL",
        "noise_type_status": "PASS" if noise_type_failures == 0 else "FAIL",
        "parse_failures": parse_failures,
        "stress_annotations_parsed": stress_annotations_parsed,
        "annotation_expectations_by_role": {
            STRESS_ECG: "required",
            PURE_NOISE: "not_applicable_by_source_design",
        },
        "overall_status": "PASS",
    }
    write_json(REPORT_DIR / "nstdb_validation.json", nstdb_validation)

    print(
        f"NSTDB validation: PASS records={len(records)} stress_ecg={stress_count} "
        f"pure_noise={noise_count}"
    )


if __name__ == "__main__":
    main()
