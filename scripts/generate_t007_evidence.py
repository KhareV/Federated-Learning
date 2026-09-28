#!/usr/bin/env python3
"""Generate T007 (INCART/NSTDB/BIDMC) evidence with the canonical SHA-256 convention.

Runs the three offline real-data validators plus the dataset-role audit, all of which
require already-acquired local datasets (scripts/acquire_incart.py, acquire_nstdb.py,
acquire_bidmc.py). No network access here.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t007"

CODE_ARTIFACTS = [
    ROOT / "datasets/physionet.py",
    ROOT / "datasets/incart.py",
    ROOT / "datasets/nstdb.py",
    ROOT / "datasets/bidmc.py",
    ROOT / "scripts/acquire_incart.py",
    ROOT / "scripts/acquire_nstdb.py",
    ROOT / "scripts/acquire_bidmc.py",
    ROOT / "scripts/validate_incart_t007.py",
    ROOT / "scripts/validate_nstdb_t007.py",
    ROOT / "scripts/validate_bidmc_t007.py",
    ROOT / "scripts/audit_dataset_roles_t007.py",
]
MANIFEST_ARTIFACTS = [
    ROOT / "manifests/datasets/dataset_roles_v1.yaml",
    ROOT / "manifests/datasets/incart_v1.yaml",
    ROOT / "manifests/datasets/incart_v1_files.csv",
    ROOT / "manifests/datasets/incart_lead_ii_records.csv",
    ROOT / "manifests/datasets/incart_lead_ii_exclusions.csv",
    ROOT / "manifests/datasets/incart_patient_map.csv",
    ROOT / "manifests/datasets/nstdb_v1.yaml",
    ROOT / "manifests/datasets/nstdb_v1_files.csv",
    ROOT / "manifests/datasets/nstdb_records.csv",
    ROOT / "manifests/datasets/bidmc_v1.yaml",
    ROOT / "manifests/datasets/bidmc_v1_files.csv",
    ROOT / "manifests/datasets/bidmc_channel_availability.csv",
]
REPORT_ARTIFACTS = [
    REPORT_DIR / "incart_validation.json",
    REPORT_DIR / "incart_lead_policy_audit.json",
    REPORT_DIR / "incart_record_validation.csv",
    REPORT_DIR / "nstdb_validation.json",
    REPORT_DIR / "nstdb_record_validation.csv",
    REPORT_DIR / "bidmc_validation.json",
    REPORT_DIR / "dataset_role_audit.json",
]


def run_script(relative_path: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / relative_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")


def write_acquisition_audit() -> Path:
    """Populate G2's generic evidence path (reports/data/acquisition_audit.json) as a thin
    index over each dataset's real acquisition_metadata.json -- license, hash-verification
    status, and file counts, referenced not duplicated."""
    acquisition_index = {
        "MITDB": "reports/t006/acquisition_metadata.json",
        "INCART": "reports/t007/incart_acquisition_metadata.json",
        "NSTDB": "reports/t007/nstdb_acquisition_metadata.json",
        "BIDMC": "reports/t007/bidmc_acquisition_metadata.json",
    }
    summary = {}
    for dataset_id, relative in acquisition_index.items():
        metadata = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        all_verified = all(action["match"] for action in metadata["actions"])
        summary[dataset_id] = {
            "version": metadata["version"],
            "license": metadata["license"],
            "doi": metadata["doi"],
            "record_count": metadata["record_count"],
            "required_file_count": metadata["required_file_count"],
            "all_files_hash_verified": all_verified,
        }

    output_path = ROOT / "reports/data/acquisition_audit.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "index_of": acquisition_index,
                "summary_by_dataset": summary,
                "overall_status": (
                    "PASS"
                    if all(row["all_files_hash_verified"] for row in summary.values())
                    else "FAIL"
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return output_path


def write_gate_evidence_index() -> tuple[Path, Path]:
    """Populate the generic G2/G3 required_artifacts paths from the gate registry as thin
    indexes over the real per-dataset reports -- they reference, not duplicate, the
    authoritative evidence in reports/t006/ and reports/t007/."""
    validation_index = {
        "MITDB": "reports/t006/mitdb_validation.json",
        "INCART": "reports/t007/incart_validation.json",
        "NSTDB": "reports/t007/nstdb_validation.json",
        "BIDMC": "reports/t007/bidmc_validation.json",
    }
    statuses = {}
    for dataset_id, relative in validation_index.items():
        report = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        statuses[dataset_id] = report["overall_status"]

    validation_report_path = ROOT / "reports/data/validation_report.json"
    validation_report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = validation_report_path.with_suffix(f"{validation_report_path.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "index_of": validation_index,
                "status_by_dataset": statuses,
                "overall_status": "PASS" if all(v == "PASS" for v in statuses.values()) else "FAIL",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(validation_report_path)

    exclusion_sources = {
        "MITDB": (
            ROOT / "manifests/datasets/mitdb_mlii_exclusions.csv",
            "record_id",
            "signal_names",
            "reason",
            "source_policy",
        ),
        "INCART": (
            ROOT / "manifests/datasets/incart_lead_ii_exclusions.csv",
            "record_id",
            "signal_names",
            "reason",
            "source_policy",
        ),
    }
    channel_exclusions_path = ROOT / "manifests/datasets/channel_exclusions.csv"
    rows = []
    for dataset_id, (path, *_fields) in exclusion_sources.items():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                rows.append({"dataset_id": dataset_id, **row})
    temporary_csv = channel_exclusions_path.with_suffix(".csv.tmp")
    with temporary_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["dataset_id", "record_id", "signal_names", "reason", "source_policy"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary_csv.replace(channel_exclusions_path)

    return validation_report_path, channel_exclusions_path


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_script("scripts/validate_incart_t007.py")
    run_script("scripts/validate_nstdb_t007.py")
    run_script("scripts/validate_bidmc_t007.py")
    run_script("scripts/audit_dataset_roles_t007.py")

    for report_path, status_key in (
        (REPORT_DIR / "incart_validation.json", "overall_status"),
        (REPORT_DIR / "nstdb_validation.json", "overall_status"),
        (REPORT_DIR / "bidmc_validation.json", "overall_status"),
        (REPORT_DIR / "dataset_role_audit.json", "status"),
    ):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report[status_key] != "PASS":
            raise RuntimeError(f"T007 evidence requires {report_path.name} to PASS")

    gate_validation_report, gate_channel_exclusions = write_gate_evidence_index()
    gate_acquisition_audit = write_acquisition_audit()

    input_paths = [*CODE_ARTIFACTS, ROOT / "requirements-dev.lock"]
    output_paths = [
        *MANIFEST_ARTIFACTS,
        *REPORT_ARTIFACTS,
        gate_validation_report,
        gate_channel_exclusions,
        gate_acquisition_audit,
    ]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T007-DATASET-ACQUISITION-V1",
        phase_id="T007",
        task_id="T007",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "INCART/NSTDB/BIDMC exact acquisition, hash verification, structural validation, "
            "locked exact-Lead-II policy, and role enforcement. No split, no AAMI mapping, "
            "no preprocessing, no external evaluation, no robustness experiment, no "
            "multimodal engineering experiment, no model training. G2/G3 close only if their "
            "documented criteria are fully met by T006+T007 together."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [
        *CODE_ARTIFACTS,
        *MANIFEST_ARTIFACTS,
        *REPORT_ARTIFACTS,
        gate_validation_report,
        gate_channel_exclusions,
        gate_acquisition_audit,
        manifest_path,
    ]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T007 evidence: {missing}")

    output = REPORT_DIR / "artifact_hashes.json"
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "algorithm": "sha256",
                "rule": (
                    "exact file bytes; this manifest excludes itself to avoid a circular digest"
                ),
                "artifacts": {
                    str(path.relative_to(ROOT)): hash_file(path) for path in sorted(hash_paths)
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print("T007 evidence: generated")


if __name__ == "__main__":
    main()
