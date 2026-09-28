#!/usr/bin/env python3
"""Offline real-data validator for T007: St Petersburg INCART v1.0.0.

Requires an already-acquired local dataset (scripts/acquire_incart.py). No network access
here. Fails clearly (INCART_DATA_NOT_ACQUIRED) rather than silently skipping.

Does not split patients, map AAMI classes, run inference, or compute any performance metric
-- INCART is LOCKED_EXTERNAL_ECG_EVALUATION, owned exclusively by T020.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import wfdb
import yaml

from datasets.incart import (
    DATASET_ID,
    DATASET_VERSION,
    EXPECTED_FS_HZ,
    EXPECTED_SOURCE_CHANNEL_COUNT,
    LEAD_POLICY_ID,
    REQUIRED_LEAD_NAME,
    data_not_acquired_error,
    inspect_record,
    list_records,
    read_header,
    validate_record,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data/raw/incartdb/1.0.0"
ACQUISITION_METADATA = ROOT / "reports/t007/incart_acquisition_metadata.json"
MANIFEST_DIR = ROOT / "manifests/datasets"
REPORT_DIR = ROOT / "reports/t007"

REQUIRED_ROLE_BY_EXTENSION = {"hea": "header", "dat": "signal", "atr": "annotation"}
REQUIRED_EXTENSIONS = ("hea", "dat", "atr")
EXPECTED_RECORD_COUNT = 75
EXPECTED_UNIQUE_PATIENTS = 32

# Verified real-data finding (reports/t007/incart_validation.json known_source_anomalies):
# 7 of the 75 official records each carry exactly one beat annotation with a small negative
# sample index (observed range: -8 to -17, i.e. <=66ms before the signal's t=0; confirmed
# across every one of the 75 records that zero annotations fall at/above sig_len). This
# threshold is set well above the observed magnitude (not fit to it) to distinguish that
# benign leading-edge artifact from a genuine out-of-range/corrupted annotation, which would
# still be treated as a hard DATASET_SOURCE_CONFLICT below.
MAX_ACCEPTABLE_LEADING_NEGATIVE_SAMPLES = 50


def required_files_for(records: list[str]) -> list[str]:
    return [f"{record}.{ext}" for record in records for ext in REQUIRED_EXTENSIONS]


def load_acquisition_metadata() -> dict[str, Any]:
    if not ACQUISITION_METADATA.exists():
        raise FileNotFoundError(
            "INCART_DATA_NOT_ACQUIRED: reports/t007/incart_acquisition_metadata.json is "
            "missing. Run scripts/acquire_incart.py first; real local data is required."
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
                "relative_path": f"data/raw/incartdb/1.0.0/{filename}",
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

    expected_files = set(required_files_for(records))
    file_rows = verify_file_hashes(acquisition)
    if {row["relative_path"].rsplit("/", 1)[-1] for row in file_rows} != expected_files:
        raise RuntimeError("DATASET_SOURCE_CONFLICT: acquired file set does not match required set")
    hashes_verified = all(row["verified"] for row in file_rows)
    if not hashes_verified:
        mismatched = [row["relative_path"] for row in file_rows if not row["verified"]]
        raise RuntimeError(f"DATASET_HASH_MISMATCH: {mismatched}")
    hash_by_record_role = {
        (row["record_id"], row["role"]): row["local_sha256"] for row in file_rows
    }

    record_validation_rows: list[dict[str, Any]] = []
    eligible_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    patient_map_rows: list[dict[str, Any]] = []
    lead_decisions: dict[str, Any] = {}

    headers_parsed = signals_parsed = annotations_parsed = 0
    fs_failures = channel_count_failures = 0
    nonfinite_signal_failures = annotation_bound_failures = 0
    patient_id_failures = 0
    observed_patient_ids: set[int] = set()
    known_source_anomalies: list[dict[str, Any]] = []

    for record_id in records:
        validation = validate_record(record_id, RAW_ROOT)
        selection = inspect_record(record_id, RAW_ROOT)
        lead_decisions[record_id] = {
            "all_signal_names": list(selection.all_signal_names),
            "ii_present": selection.ii_present,
            "ii_channel_index": selection.ii_channel_index,
            "eligible": selection.eligible,
            "exclusion_reason": selection.exclusion_reason,
        }

        headers_parsed += int(validation["header_parsed"])
        signals_parsed += int(validation["signal_parsed"])
        annotations_parsed += int(validation["annotation_parsed"])
        if validation["header_parsed"] and not validation["fs_ok"]:
            fs_failures += 1
        if validation["header_parsed"] and not validation["channel_count_ok"]:
            channel_count_failures += 1
        if validation["signal_parsed"] and not validation["signal_finite"]:
            nonfinite_signal_failures += 1
        if validation["annotation_parsed"] and not validation["annotation_nondecreasing_ok"]:
            annotation_bound_failures += 1
        if validation["annotation_parsed"] and not validation["annotation_bounds_ok"]:
            above = validation["annotation_samples_at_or_above_sig_len"]
            below = validation["annotation_samples_below_zero"]
            if above or any(
                abs(value) > MAX_ACCEPTABLE_LEADING_NEGATIVE_SAMPLES for value in below
            ):
                annotation_bound_failures += 1
            elif below:
                known_source_anomalies.append(
                    {
                        "record_id": record_id,
                        "finding": (
                            "This record carries one or more beat annotations with a small "
                            "negative sample index, i.e. positioned before the signal's own "
                            "t=0. Verified across all 75 official records that none exceed "
                            f"{MAX_ACCEPTABLE_LEADING_NEGATIVE_SAMPLES} samples in magnitude "
                            "and none fall at/above sig_len; treated as a benign source "
                            "leading-edge artifact, not corruption. Structurally recorded, "
                            "never silently dropped -- see "
                            "reports/t007/incart_record_validation.csv."
                        ),
                        "annotation_samples_below_zero": below,
                    }
                )
        if not validation["source_patient_id_parsed"]:
            patient_id_failures += 1
        else:
            observed_patient_ids.add(validation["source_patient_id"])

        record_validation_rows.append(
            {
                "record_id": record_id,
                "header_parsed": validation["header_parsed"],
                "signal_parsed": validation["signal_parsed"],
                "annotation_parsed": validation["annotation_parsed"],
                "fs_ok": validation["fs_ok"],
                "channel_count_ok": validation["channel_count_ok"],
                "signal_finite": validation["signal_finite"],
                "annotation_count": validation["annotation_count"],
                "annotation_samples_below_zero": ";".join(
                    str(value) for value in validation["annotation_samples_below_zero"]
                ),
                "annotation_samples_at_or_above_sig_len": ";".join(
                    str(value)
                    for value in validation["annotation_samples_at_or_above_sig_len"]
                ),
                "source_patient_id": validation["source_patient_id"],
                "eligible": selection.eligible,
                "exclusion_reason": selection.exclusion_reason,
                "errors": ";".join(validation["errors"]),
            }
        )
        patient_map_rows.append(
            {"record_id": record_id, "source_patient_id": validation["source_patient_id"]}
        )

        if selection.eligible:
            header = read_header(record_id, RAW_ROOT)
            eligible_rows.append(
                {
                    "record_id": record_id,
                    "ii_channel_index": selection.ii_channel_index,
                    "fs": header.fs,
                    "sig_len": header.sig_len,
                    "duration_seconds": round(header.duration_seconds, 3),
                    "source_patient_id": validation["source_patient_id"],
                    "header_sha256": hash_by_record_role.get((record_id, "header"), ""),
                    "signal_sha256": hash_by_record_role.get((record_id, "signal"), ""),
                    "annotation_sha256": hash_by_record_role.get((record_id, "annotation"), ""),
                }
            )
        else:
            exclusion_rows.append(
                {
                    "record_id": record_id,
                    "signal_names": ";".join(selection.all_signal_names),
                    "reason": selection.exclusion_reason,
                    "source_policy": LEAD_POLICY_ID,
                }
            )

    hard_integrity_ok = (
        headers_parsed == EXPECTED_RECORD_COUNT
        and signals_parsed == EXPECTED_RECORD_COUNT
        and annotations_parsed == EXPECTED_RECORD_COUNT
        and fs_failures == 0
        and channel_count_failures == 0
        and nonfinite_signal_failures == 0
        and annotation_bound_failures == 0
    )
    if not hard_integrity_ok:
        raise RuntimeError(
            "DATASET_SOURCE_CONFLICT: real INCART v1.0.0 failed a hard integrity invariant "
            f"(headers_parsed={headers_parsed}, signals_parsed={signals_parsed}, "
            f"annotations_parsed={annotations_parsed}, fs_failures={fs_failures}, "
            f"channel_count_failures={channel_count_failures}, "
            f"nonfinite_signal_failures={nonfinite_signal_failures}, "
            f"annotation_bound_failures={annotation_bound_failures})"
        )
    if patient_id_failures > 0:
        raise RuntimeError(
            f"DATASET_SOURCE_CONFLICT: {patient_id_failures} INCART records had no "
            "parseable source patient identity comment"
        )
    if len(observed_patient_ids) != EXPECTED_UNIQUE_PATIENTS:
        raise RuntimeError(
            "DATASET_SOURCE_CONFLICT: observed "
            f"{len(observed_patient_ids)} unique source patient IDs, documentation states "
            f"{EXPECTED_UNIQUE_PATIENTS}. Stopping rather than silently claiming the "
            "documented count."
        )

    # --- write manifests ---
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(
        MANIFEST_DIR / "incart_v1_files.csv",
        ["relative_path", "record_id", "role", "official_sha256", "local_sha256", "verified"],
        file_rows,
    )
    write_csv(
        MANIFEST_DIR / "incart_lead_ii_records.csv",
        [
            "record_id",
            "ii_channel_index",
            "fs",
            "sig_len",
            "duration_seconds",
            "source_patient_id",
            "header_sha256",
            "signal_sha256",
            "annotation_sha256",
        ],
        sorted(eligible_rows, key=lambda row: row["record_id"]),
    )
    write_csv(
        MANIFEST_DIR / "incart_lead_ii_exclusions.csv",
        ["record_id", "signal_names", "reason", "source_policy"],
        sorted(exclusion_rows, key=lambda row: row["record_id"]),
    )
    write_csv(
        MANIFEST_DIR / "incart_patient_map.csv",
        ["record_id", "source_patient_id"],
        sorted(patient_map_rows, key=lambda row: row["record_id"]),
    )

    records_file_hash = hash_file(RAW_ROOT / "RECORDS")
    official_sha256_manifest_hash = hash_file(RAW_ROOT / "SHA256SUMS.txt")

    manifest_yaml = {
        "dataset_id": DATASET_ID,
        "official_name": "St Petersburg INCART 12-lead Arrhythmia Database",
        "version": DATASET_VERSION,
        "provider": "PhysioNet",
        "source_url": acquisition["source_url"],
        "files_base_url": acquisition["files_base_url"],
        "doi": acquisition["doi"],
        "license": acquisition["license"],
        "downloaded_at_utc": acquisition["downloaded_at_utc"],
        "documented_source": {
            "record_count": acquisition["documented_source"]["record_count"],
            "source_patient_count": acquisition["documented_source"][
                "source_patient_count_documented"
            ],
            "sampling_rate_hz": acquisition["documented_source"]["sampling_rate_hz"],
            "source_channel_count": acquisition["documented_source"]["source_channel_count"],
        },
        "observed_local_validation": {
            "records_in_RECORDS": len(records),
            "parsed_records": headers_parsed,
            "eligible_exact_II": len(eligible_rows),
            "excluded_no_exact_II": len(exclusion_rows),
            "unique_source_patient_ids_observed": len(observed_patient_ids),
        },
        "sampling_rate_hz": EXPECTED_FS_HZ,
        "source_channel_count": EXPECTED_SOURCE_CHANNEL_COUNT,
        "required_files": ["hea", "dat", "atr"],
        "records_file_hash": records_file_hash,
        "official_sha256_manifest_hash": official_sha256_manifest_hash,
        "lead_policy_id": LEAD_POLICY_ID,
        "lead_name_required": REQUIRED_LEAD_NAME,
        "eligible_record_count": len(eligible_rows),
        "excluded_record_count": len(exclusion_rows),
        "eligible_manifest_path": "manifests/datasets/incart_lead_ii_records.csv",
        "exclusion_manifest_path": "manifests/datasets/incart_lead_ii_exclusions.csv",
        "patient_map_path": "manifests/datasets/incart_patient_map.csv",
        "role": "LOCKED_EXTERNAL_ECG_EVALUATION",
        "owning_task": "T020",
        "raw_data_root": str(RAW_ROOT.relative_to(ROOT)),
        "raw_data_committed": False,
        "wfdb_version": wfdb.__version__,
        "validation_status": "PASS",
    }
    temporary = (MANIFEST_DIR / "incart_v1.yaml").with_suffix(".yaml.tmp")
    temporary.write_text(yaml.safe_dump(manifest_yaml, sort_keys=True), encoding="utf-8")
    temporary.replace(MANIFEST_DIR / "incart_v1.yaml")

    # --- write reports ---
    write_csv(
        REPORT_DIR / "incart_record_validation.csv",
        [
            "record_id",
            "header_parsed",
            "signal_parsed",
            "annotation_parsed",
            "fs_ok",
            "channel_count_ok",
            "signal_finite",
            "annotation_count",
            "annotation_samples_below_zero",
            "annotation_samples_at_or_above_sig_len",
            "source_patient_id",
            "eligible",
            "exclusion_reason",
            "errors",
        ],
        record_validation_rows,
    )

    incart_validation = {
        "dataset_id": DATASET_ID,
        "version": DATASET_VERSION,
        "record_count_expected": EXPECTED_RECORD_COUNT,
        "record_count_observed": len(records),
        "headers_parsed": headers_parsed,
        "signals_parsed": signals_parsed,
        "annotations_parsed": annotations_parsed,
        "hashes_verified": hashes_verified,
        "sampling_rate_failures": fs_failures,
        "channel_count_failures": channel_count_failures,
        "nonfinite_signal_failures": nonfinite_signal_failures,
        "annotation_bound_failures": annotation_bound_failures,
        "exact_ii_eligible_count": len(eligible_rows),
        "exact_ii_excluded_count": len(exclusion_rows),
        "excluded_records": sorted(row["record_id"] for row in exclusion_rows),
        "source_patient_id_parse_failures": patient_id_failures,
        "unique_source_patient_ids_observed": len(observed_patient_ids),
        "unique_source_patient_ids_documented": EXPECTED_UNIQUE_PATIENTS,
        "known_source_anomalies": known_source_anomalies,
        "overall_status": "PASS",
    }
    write_json(REPORT_DIR / "incart_validation.json", incart_validation)

    lead_policy_audit = {
        "policy_id": LEAD_POLICY_ID,
        "selection_key": "WFDB header sig_name, exact string equality",
        "required_value": REQUIRED_LEAD_NAME,
        "fallback_allowed": False,
        "selection_before_split": True,
        "performance_based_selection": False,
        "eligible_count": len(eligible_rows),
        "excluded_count": len(exclusion_rows),
        "record_decisions": lead_decisions,
        "eligible_manifest_path": "manifests/datasets/incart_lead_ii_records.csv",
        "exclusion_manifest_path": "manifests/datasets/incart_lead_ii_exclusions.csv",
    }
    write_json(REPORT_DIR / "incart_lead_policy_audit.json", lead_policy_audit)

    print(
        f"INCART validation: PASS records={len(records)} "
        f"eligible={len(eligible_rows)} excluded={len(exclusion_rows)} "
        f"unique_patients={len(observed_patient_ids)}"
    )


if __name__ == "__main__":
    main()
