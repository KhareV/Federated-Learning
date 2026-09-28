#!/usr/bin/env python3
"""Offline real-data validator for T006: MIT-BIH Arrhythmia Database v1.0.0.

Requires an already-acquired local dataset (run scripts/acquire_mitdb.py first). No network
access here -- this script only reads local files and recomputes local SHA-256 hashes,
comparing them against the officially-verified hashes recorded at acquisition time. Fails
clearly (MITDB_DATA_NOT_ACQUIRED) rather than silently skipping when the real dataset is
absent; T006 cannot PASS without a real verified local acquisition.

Does not split patients, map AAMI classes, create windows, preprocess signals, or train
models -- that is T008/T009/T011-T014's scope, not this validator's.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import wfdb
import yaml

from datasets.mitdb import (
    DATASET_ID,
    DATASET_VERSION,
    DEFAULT_RAW_ROOT,
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
RAW_ROOT = ROOT / DEFAULT_RAW_ROOT
ACQUISITION_METADATA = ROOT / "reports/t006/acquisition_metadata.json"
MANIFEST_DIR = ROOT / "manifests/datasets"
REPORT_DIR = ROOT / "reports/t006"

REQUIRED_ROLE_BY_EXTENSION = {"hea": "header", "dat": "signal", "atr": "annotation"}
EXPECTED_RECORD_COUNT = 48

# Official documentation notes used only as a post-hoc cross-check, never as the selection
# algorithm itself (see datasets/mitdb.py select_mlii_channel, which reads headers only).
DOCUMENTED_MLII_EXCEPTIONS = {
    "102": "MLII could not be used",
    "104": "MLII could not be used",
    "114": "signals were reversed",
}


def load_acquisition_metadata() -> dict[str, Any]:
    if not ACQUISITION_METADATA.exists():
        raise FileNotFoundError(
            "MITDB_DATA_NOT_ACQUIRED: reports/t006/acquisition_metadata.json is missing. "
            "Run scripts/acquire_mitdb.py first; real local data is required."
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
                "relative_path": f"data/raw/mitdb/1.0.0/{filename}",
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

    file_rows = verify_file_hashes(acquisition)
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
    lead_decisions: dict[str, Any] = {}

    headers_parsed = signals_parsed = annotations_parsed = 0
    sampling_rate_failures = channel_count_failures = 0
    nonfinite_signal_failures = annotation_bound_failures = 0

    for record_id in records:
        validation = validate_record(record_id, RAW_ROOT)
        selection = inspect_record(record_id, RAW_ROOT)
        lead_decisions[record_id] = {
            "all_signal_names": list(selection.all_signal_names),
            "mlii_present": selection.mlii_present,
            "mlii_channel_index": selection.mlii_channel_index,
            "eligible": selection.eligible,
            "exclusion_reason": selection.exclusion_reason,
        }

        headers_parsed += int(validation["header_parsed"])
        signals_parsed += int(validation["signal_parsed"])
        annotations_parsed += int(validation["annotation_parsed"])
        if validation["header_parsed"] and not validation["fs_ok"]:
            sampling_rate_failures += 1
        if validation["header_parsed"] and not validation["channel_count_ok"]:
            channel_count_failures += 1
        if validation["signal_parsed"] and not validation["signal_finite"]:
            nonfinite_signal_failures += 1
        if validation["annotation_parsed"] and not (
            validation["annotation_bounds_ok"] and validation["annotation_nondecreasing_ok"]
        ):
            annotation_bound_failures += 1

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
                "annotation_bounds_ok": validation["annotation_bounds_ok"],
                "eligible": selection.eligible,
                "exclusion_reason": selection.exclusion_reason,
                "errors": ";".join(validation["errors"]),
            }
        )

        if selection.eligible:
            header = read_header(record_id, RAW_ROOT)
            eligible_rows.append(
                {
                    "record_id": record_id,
                    "mlii_channel_index": selection.mlii_channel_index,
                    "fs": header.fs,
                    "sig_len": header.sig_len,
                    "duration_seconds": round(header.duration_seconds, 3),
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
        and sampling_rate_failures == 0
        and channel_count_failures == 0
        and nonfinite_signal_failures == 0
        and annotation_bound_failures == 0
    )
    if not hard_integrity_ok:
        raise RuntimeError(
            "DATASET_SOURCE_CONFLICT: real MIT-BIH v1.0.0 failed a hard integrity invariant "
            f"(headers_parsed={headers_parsed}, signals_parsed={signals_parsed}, "
            f"annotations_parsed={annotations_parsed}, "
            f"sampling_rate_failures={sampling_rate_failures}, "
            f"channel_count_failures={channel_count_failures}, "
            f"nonfinite_signal_failures={nonfinite_signal_failures}, "
            f"annotation_bound_failures={annotation_bound_failures})"
        )

    # --- write manifests ---
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    files_csv_rows = [
        {
            "relative_path": row["relative_path"],
            "record_id": row["record_id"],
            "role": row["role"],
            "official_sha256": row["official_sha256"],
            "local_sha256": row["local_sha256"],
            "verified": row["verified"],
        }
        for row in file_rows
    ]
    write_csv(
        MANIFEST_DIR / "mitdb_v1_files.csv",
        ["relative_path", "record_id", "role", "official_sha256", "local_sha256", "verified"],
        files_csv_rows,
    )
    write_csv(
        MANIFEST_DIR / "mitdb_mlii_records.csv",
        [
            "record_id",
            "mlii_channel_index",
            "fs",
            "sig_len",
            "duration_seconds",
            "header_sha256",
            "signal_sha256",
            "annotation_sha256",
        ],
        sorted(eligible_rows, key=lambda row: row["record_id"]),
    )
    write_csv(
        MANIFEST_DIR / "mitdb_mlii_exclusions.csv",
        ["record_id", "signal_names", "reason", "source_policy"],
        sorted(exclusion_rows, key=lambda row: row["record_id"]),
    )

    records_file_hash = hash_file(RAW_ROOT / "RECORDS")
    official_sha256_manifest_hash = hash_file(RAW_ROOT / "SHA256SUMS.txt")

    manifest_yaml = {
        "dataset_id": DATASET_ID,
        "official_name": "MIT-BIH Arrhythmia Database",
        "version": DATASET_VERSION,
        "provider": "PhysioNet",
        "source_url": acquisition["source_url"],
        "files_base_url": acquisition["files_base_url"],
        "doi": acquisition["doi"],
        "license": acquisition["license"],
        "downloaded_at_utc": acquisition["downloaded_at_utc"],
        "documented_source": {
            "record_count": acquisition["documented_source"]["record_count"],
            "subject_count": acquisition["documented_source"]["subject_count_documented"],
            "sampling_rate_hz": acquisition["documented_source"]["sampling_rate_hz"],
        },
        "observed_local_validation": {
            "records_in_RECORDS": len(records),
            "parsed_records": headers_parsed,
            "eligible_exact_MLII": len(eligible_rows),
            "excluded_no_exact_MLII": len(exclusion_rows),
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
        "eligible_manifest_path": "manifests/datasets/mitdb_mlii_records.csv",
        "exclusion_manifest_path": "manifests/datasets/mitdb_mlii_exclusions.csv",
        "raw_data_root": str(RAW_ROOT.relative_to(ROOT)),
        "raw_data_committed": False,
        "wfdb_version": wfdb.__version__,
        "validation_status": "PASS",
    }
    temporary = (MANIFEST_DIR / "mitdb_v1.yaml").with_suffix(".yaml.tmp")
    temporary.write_text(yaml.safe_dump(manifest_yaml, sort_keys=True), encoding="utf-8")
    temporary.replace(MANIFEST_DIR / "mitdb_v1.yaml")

    # --- write reports ---
    write_csv(
        REPORT_DIR / "record_validation.csv",
        [
            "record_id",
            "header_parsed",
            "signal_parsed",
            "annotation_parsed",
            "fs_ok",
            "channel_count_ok",
            "signal_finite",
            "annotation_count",
            "annotation_bounds_ok",
            "eligible",
            "exclusion_reason",
            "errors",
        ],
        record_validation_rows,
    )

    mitdb_validation = {
        "dataset_id": DATASET_ID,
        "version": DATASET_VERSION,
        "record_count_expected": EXPECTED_RECORD_COUNT,
        "record_count_observed": len(records),
        "headers_parsed": headers_parsed,
        "signals_parsed": signals_parsed,
        "annotations_parsed": annotations_parsed,
        "hashes_verified": hashes_verified,
        "sampling_rate_failures": sampling_rate_failures,
        "channel_count_failures": channel_count_failures,
        "nonfinite_signal_failures": nonfinite_signal_failures,
        "annotation_bound_failures": annotation_bound_failures,
        "exact_mlii_eligible_count": len(eligible_rows),
        "exact_mlii_excluded_count": len(exclusion_rows),
        "excluded_records": sorted(row["record_id"] for row in exclusion_rows),
        "overall_status": "PASS",
    }
    write_json(REPORT_DIR / "mitdb_validation.json", mitdb_validation)

    documented_cross_check = {
        record_id: {
            "documented_note": note,
            "observed_sig_name": lead_decisions.get(record_id, {}).get("all_signal_names"),
            "observed_mlii_channel_index": lead_decisions.get(record_id, {}).get(
                "mlii_channel_index"
            ),
            "observed_eligible": lead_decisions.get(record_id, {}).get("eligible"),
        }
        for record_id, note in DOCUMENTED_MLII_EXCEPTIONS.items()
        if record_id in lead_decisions
    }
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
        "documented_exceptions_cross_check": documented_cross_check,
        "eligible_manifest_path": "manifests/datasets/mitdb_mlii_records.csv",
        "exclusion_manifest_path": "manifests/datasets/mitdb_mlii_exclusions.csv",
    }
    write_json(REPORT_DIR / "lead_policy_audit.json", lead_policy_audit)

    print(
        f"MITDB validation: PASS records={len(records)} "
        f"eligible={len(eligible_rows)} excluded={len(exclusion_rows)}"
    )


if __name__ == "__main__":
    main()
