#!/usr/bin/env python3
"""Offline real-data validator for T007: BIDMC PPG and Respiration Dataset v1.0.0.

Requires an already-acquired local dataset (scripts/acquire_bidmc.py). No network access
here. Fails clearly (BIDMC_DATA_NOT_ACQUIRED) rather than silently skipping.

Audits exact channel availability only -- no PPG filter, pulse detector, HR/PR agreement,
SpO2 validity classifier, or multimodal synchronization experiment runs here (T012/T013/T021).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from datasets.bidmc import (
    DATASET_ID,
    DATASET_VERSION,
    EXPECTED_NUMERICS_FS_HZ,
    EXPECTED_WAVEFORM_FS_HZ,
    data_not_acquired_error,
    list_records,
    read_numeric_header,
    validate_record,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data/raw/bidmc/1.0.0"
ACQUISITION_METADATA = ROOT / "reports/t007/bidmc_acquisition_metadata.json"
MANIFEST_DIR = ROOT / "manifests/datasets"
REPORT_DIR = ROOT / "reports/t007"

EXPECTED_RECORD_COUNT = 53


def required_files_for(records: list[str]) -> list[str]:
    required = []
    for record in records:
        required += [f"{record}.hea", f"{record}.dat", f"{record}n.hea", f"{record}n.dat"]
    return required


def role_for(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    if stem.endswith("n"):
        return "numeric_header" if filename.endswith(".hea") else "numeric_signal"
    return "waveform_header" if filename.endswith(".hea") else "waveform_signal"


def base_record_for(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    return stem[:-1] if stem.endswith("n") else stem


def load_acquisition_metadata() -> dict[str, Any]:
    if not ACQUISITION_METADATA.exists():
        raise FileNotFoundError(
            "BIDMC_DATA_NOT_ACQUIRED: reports/t007/bidmc_acquisition_metadata.json is "
            "missing. Run scripts/acquire_bidmc.py first; real local data is required."
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
        local_sha256 = hash_file(path) if path.exists() else ""
        rows.append(
            {
                "relative_path": f"data/raw/bidmc/1.0.0/{filename}",
                "record_id": base_record_for(filename),
                "role": role_for(filename),
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

    file_rows = verify_file_hashes(acquisition)
    if {row["relative_path"].rsplit("/", 1)[-1] for row in file_rows} != set(
        required_files_for(records)
    ):
        raise RuntimeError("DATASET_SOURCE_CONFLICT: acquired file set does not match required set")
    hashes_verified = all(row["verified"] for row in file_rows)
    if not hashes_verified:
        mismatched = [row["relative_path"] for row in file_rows if not row["verified"]]
        raise RuntimeError(f"DATASET_HASH_MISMATCH: {mismatched}")

    channel_rows: list[dict[str, Any]] = []
    waveform_headers_parsed = numeric_headers_parsed = 0
    waveform_signals_parsed = numeric_signals_parsed = 0
    waveform_fs_failures = numeric_fs_failures = 0
    pleth_available_count = ii_available_count = 0
    hr_available_count = pulse_available_count = spo2_available_count = 0
    records_missing_ii: list[str] = []
    records_missing_pleth: list[str] = []
    records_missing_hr: list[str] = []
    records_missing_pulse: list[str] = []
    records_missing_spo2: list[str] = []
    parse_failures = 0
    total_missing_numeric_samples: dict[str, int] = {"HR": 0, "PULSE": 0, "SpO2": 0}

    for record_id in records:
        validation = validate_record(record_id, RAW_ROOT)
        if validation["errors"]:
            parse_failures += 1
        waveform_headers_parsed += int(validation["waveform_header_parsed"])
        numeric_headers_parsed += int(validation["numeric_header_parsed"])
        waveform_signals_parsed += int(validation["waveform_signal_parsed"])
        numeric_signals_parsed += int(validation["numeric_signal_parsed"])
        if validation["waveform_header_parsed"] and not validation["waveform_fs_ok"]:
            waveform_fs_failures += 1
        if validation["numeric_header_parsed"] and not validation["numeric_fs_ok"]:
            numeric_fs_failures += 1
        pleth_available_count += int(validation["pleth_available"])
        ii_available_count += int(validation["ii_available"])
        hr_available_count += int(validation["hr_available"])
        pulse_available_count += int(validation["pulse_available"])
        spo2_available_count += int(validation["spo2_available"])
        if not validation["ii_available"]:
            records_missing_ii.append(record_id)
        if not validation["pleth_available"]:
            records_missing_pleth.append(record_id)
        if not validation["hr_available"]:
            records_missing_hr.append(record_id)
        if not validation["pulse_available"]:
            records_missing_pulse.append(record_id)
        if not validation["spo2_available"]:
            records_missing_spo2.append(record_id)
        for name in ("HR", "PULSE", "SpO2"):
            total_missing_numeric_samples[name] += validation["numeric_missing_sample_counts"].get(
                name, 0
            )

        channel_rows.append(
            {
                "record_id": record_id,
                "waveform_fs": validation["waveform_fs"],
                "numeric_fs": validation["numeric_fs"],
                "waveform_sig_name": ";".join(validation["waveform_sig_name"] or []),
                "numeric_sig_name": ";".join(validation["numeric_sig_name"] or []),
                "pleth_available": validation["pleth_available"],
                "ii_available": validation["ii_available"],
                "hr_available": validation["hr_available"],
                "pulse_available": validation["pulse_available"],
                "spo2_available": validation["spo2_available"],
                "waveform_signal_finite": validation["waveform_signal_finite"],
                "hr_missing_samples": validation["numeric_missing_sample_counts"].get("HR", 0),
                "pulse_missing_samples": validation["numeric_missing_sample_counts"].get(
                    "PULSE", 0
                ),
                "spo2_missing_samples": validation["numeric_missing_sample_counts"].get(
                    "SpO2", 0
                ),
                "errors": ";".join(validation["errors"]),
            }
        )

    known_source_anomalies: list[dict[str, Any]] = []
    for record_id in records_missing_spo2:
        raw_numeric_header = read_numeric_header(record_id, RAW_ROOT)
        suspicious = [name for name in raw_numeric_header.raw_sig_name if "(" in name]
        if suspicious:
            known_source_anomalies.append(
                {
                    "record_id": record_id,
                    "finding": (
                        "The official v1.0.0 numerics header encodes an ADC gain field as a "
                        "non-numeric token (observed: garbled signal description below), "
                        "which breaks WFDB's field tokenization for the SpO2 channel line. "
                        "Verified by direct inspection of the raw .hea bytes; not a parser or "
                        "loader bug. The exact-name channel policy correctly reports "
                        "SpO2_UNAVAILABLE rather than fabricating a value for an "
                        "uncalibratable channel."
                    ),
                    "raw_numeric_sig_name": list(raw_numeric_header.raw_sig_name),
                }
            )

    hard_integrity_ok = (
        waveform_headers_parsed == EXPECTED_RECORD_COUNT
        and numeric_headers_parsed == EXPECTED_RECORD_COUNT
        and waveform_signals_parsed == EXPECTED_RECORD_COUNT
        and numeric_signals_parsed == EXPECTED_RECORD_COUNT
        and waveform_fs_failures == 0
        and numeric_fs_failures == 0
        and parse_failures == 0
    )
    if not hard_integrity_ok:
        raise RuntimeError(
            "DATASET_SOURCE_CONFLICT: real BIDMC v1.0.0 failed a hard integrity invariant "
            f"(waveform_headers_parsed={waveform_headers_parsed}, "
            f"numeric_headers_parsed={numeric_headers_parsed}, "
            f"waveform_signals_parsed={waveform_signals_parsed}, "
            f"numeric_signals_parsed={numeric_signals_parsed}, "
            f"waveform_fs_failures={waveform_fs_failures}, "
            f"numeric_fs_failures={numeric_fs_failures}, parse_failures={parse_failures})"
        )

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(
        MANIFEST_DIR / "bidmc_v1_files.csv",
        ["relative_path", "record_id", "role", "official_sha256", "local_sha256", "verified"],
        file_rows,
    )
    write_csv(
        MANIFEST_DIR / "bidmc_channel_availability.csv",
        [
            "record_id",
            "waveform_fs",
            "numeric_fs",
            "waveform_sig_name",
            "numeric_sig_name",
            "pleth_available",
            "ii_available",
            "hr_available",
            "pulse_available",
            "spo2_available",
            "waveform_signal_finite",
            "hr_missing_samples",
            "pulse_missing_samples",
            "spo2_missing_samples",
            "errors",
        ],
        channel_rows,
    )

    records_file_hash = hash_file(RAW_ROOT / "RECORDS")
    official_sha256_manifest_hash = hash_file(RAW_ROOT / "SHA256SUMS.txt")
    manifest_yaml = {
        "dataset_id": DATASET_ID,
        "official_name": "BIDMC PPG and Respiration Dataset",
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
            "waveform_headers_parsed": waveform_headers_parsed,
            "numeric_headers_parsed": numeric_headers_parsed,
            "pleth_available_count": pleth_available_count,
            "ii_available_count": ii_available_count,
            "hr_available_count": hr_available_count,
            "pulse_available_count": pulse_available_count,
            "spo2_available_count": spo2_available_count,
        },
        "records_file_hash": records_file_hash,
        "official_sha256_manifest_hash": official_sha256_manifest_hash,
        "waveform_sampling_rate_hz": EXPECTED_WAVEFORM_FS_HZ,
        "numerics_sampling_rate_hz": EXPECTED_NUMERICS_FS_HZ,
        "excluded_by_design": acquisition.get(
            "excluded_by_design", [".breath", "bidmc_csv/*", "bidmc_data.mat"]
        ),
        "channel_availability_manifest_path": "manifests/datasets/bidmc_channel_availability.csv",
        "records_with_missing_ii": records_missing_ii,
        "role": "MULTIMODAL_ENGINEERING_CONTEXT",
        "owning_tasks": ["T012", "T013", "T021"],
        "raw_data_root": str(RAW_ROOT.relative_to(ROOT)),
        "raw_data_committed": False,
        "validation_status": "PASS",
    }
    temporary = (MANIFEST_DIR / "bidmc_v1.yaml").with_suffix(".yaml.tmp")
    temporary.write_text(yaml.safe_dump(manifest_yaml, sort_keys=True), encoding="utf-8")
    temporary.replace(MANIFEST_DIR / "bidmc_v1.yaml")

    bidmc_validation = {
        "dataset_id": DATASET_ID,
        "version": DATASET_VERSION,
        "record_count_expected": EXPECTED_RECORD_COUNT,
        "record_count_observed": len(records),
        "hashes_verified": hashes_verified,
        "waveform_fs_audit": {
            "expected_hz": EXPECTED_WAVEFORM_FS_HZ,
            "failures": waveform_fs_failures,
        },
        "numeric_fs_audit": {
            "expected_hz": EXPECTED_NUMERICS_FS_HZ,
            "failures": numeric_fs_failures,
        },
        "pleth_availability": {
            "available": pleth_available_count,
            "unavailable": EXPECTED_RECORD_COUNT - pleth_available_count,
            "records_missing_pleth": records_missing_pleth,
        },
        "ii_availability": {
            "available": ii_available_count,
            "unavailable": EXPECTED_RECORD_COUNT - ii_available_count,
            "records_missing_ii": records_missing_ii,
        },
        "hr_availability": {
            "available": hr_available_count,
            "records_missing_hr": records_missing_hr,
        },
        "pulse_availability": {
            "available": pulse_available_count,
            "records_missing_pulse": records_missing_pulse,
        },
        "spo2_availability": {
            "available": spo2_available_count,
            "records_missing_spo2": records_missing_spo2,
        },
        "missing_numeric_sample_totals": total_missing_numeric_samples,
        "known_source_anomalies": known_source_anomalies,
        "overall_status": "PASS",
    }
    write_json(REPORT_DIR / "bidmc_validation.json", bidmc_validation)

    print(
        f"BIDMC validation: PASS records={len(records)} pleth={pleth_available_count} "
        f"ii={ii_available_count} hr={hr_available_count}"
    )


if __name__ == "__main__":
    main()
