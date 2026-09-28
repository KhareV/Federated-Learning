#!/usr/bin/env python3
"""Generate T009 (patient grouping / MITDB_SPLIT_V1 draft) evidence with the canonical
SHA-256 convention.

Runs the deterministic split builder and the split-independence audit, both of which require
the already-acquired, hash-verified local MITDB raw data (T006) and the frozen AAMI_SVF_MAP_V1
mapper (T008/G4/F04). No network access, no model/result input. Does not close G5 or freeze
F05 -- that is T010's job.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t009"

CODE_ARTIFACTS = [
    ROOT / "datasets/grouping.py",
    ROOT / "scripts/build_mitdb_split_t009.py",
    ROOT / "scripts/audit_split_independence_t009.py",
]
SPLIT_ARTIFACTS = [
    ROOT / "manifests/splits/mitdb_groups.csv",
    ROOT / "manifests/splits/mitdb_patient_strata.csv",
    ROOT / "manifests/splits/MITDB_SPLIT_V1.csv",
    ROOT / "manifests/splits/MITDB_SPLIT_V1.yaml",
    ROOT / "manifests/splits/partition_roles_v1.yaml",
]
REPORT_ARTIFACTS = [
    REPORT_DIR / "split_generation.json",
    REPORT_DIR / "class_coverage.csv",
    REPORT_DIR / "split_independence_audit.json",
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


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_script("scripts/build_mitdb_split_t009.py")
    run_script("scripts/audit_split_independence_t009.py")

    split_generation_path = REPORT_DIR / "split_generation.json"
    split_generation = json.loads(split_generation_path.read_text(encoding="utf-8"))
    if split_generation["overall_status"] != "PASS":
        raise RuntimeError(
            f"T009 evidence requires split_generation.json to PASS: {split_generation}"
        )
    independence_path = REPORT_DIR / "split_independence_audit.json"
    independence = json.loads(independence_path.read_text(encoding="utf-8"))
    if independence["status"] != "PASS":
        raise RuntimeError(
            f"T009 evidence requires split_independence_audit.json to PASS: {independence}"
        )

    input_paths = [
        *CODE_ARTIFACTS,
        ROOT / "manifests/datasets/mitdb_mlii_records.csv",
        ROOT / "manifests/datasets/mitdb_mlii_exclusions.csv",
        ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        ROOT / "datasets/labels.py",
    ]
    output_paths = [*SPLIT_ARTIFACTS, *REPORT_ARTIFACTS]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T009-MITDB-SPLIT-DRAFT-V1",
        phase_id="T009",
        task_id="T009",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "Deterministic MITDB_SPLIT_V1 patient-group partition (TRAIN/VALIDATION/"
            "CALIBRATION/INTERNAL_TEST) from the frozen T006 exact-MLII eligible pool and the "
            "frozen AAMI_SVF_MAP_V1 mapper. Records 201/202 grouped before allocation. One "
            "deterministic seed (20260927), one predeclared algorithm, no seed search, no "
            "manual movement, no model/result input. Draft only: split_status=DRAFT_VALIDATED, "
            "freeze_status=NOT_FROZEN. G5/F05 are not closed here -- T010 owns the independent "
            "leakage audit and freeze."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [*CODE_ARTIFACTS, *SPLIT_ARTIFACTS, *REPORT_ARTIFACTS, manifest_path]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T009 evidence: {missing}")

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
    print("T009 evidence: generated")


if __name__ == "__main__":
    main()
