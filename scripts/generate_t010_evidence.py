#!/usr/bin/env python3
"""Generate T010 (independent leakage audit / MITDB_SPLIT_V1 freeze) evidence with the
canonical SHA-256 convention.

Orchestrates, in strict order: the independent split audit (recomputes G5 invariants from
authoritative artifacts), the synthetic window-leakage harness, the leakage control matrix,
and -- only if both audits PASS -- the freeze lock. No network access, no model/result input.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t010"
SPLIT_REPORT_DIR = ROOT / "reports/splits"
SPLIT_DIR = ROOT / "manifests/splits"

CODE_ARTIFACTS = [
    ROOT / "evaluation/leakage_audit.py",
    ROOT / "scripts/audit_split_leakage_t010.py",
    ROOT / "scripts/run_window_leakage_harness_t010.py",
    ROOT / "scripts/freeze_mitdb_split_t010.py",
    ROOT / "scripts/build_leakage_control_matrix_t010.py",
]
SPLIT_ARTIFACTS = [
    SPLIT_DIR / "MITDB_SPLIT_V1.csv",
    SPLIT_DIR / "MITDB_SPLIT_V1.yaml",
    SPLIT_DIR / "mitdb_groups.csv",
    SPLIT_DIR / "mitdb_patient_strata.csv",
    SPLIT_DIR / "partition_roles_v1.yaml",
    SPLIT_DIR / "MITDB_SPLIT_V1.lock.json",
]
REPORT_ARTIFACTS = [
    SPLIT_REPORT_DIR / "split_audit.json",
    SPLIT_REPORT_DIR / "window_audit.json",
    REPORT_DIR / "leakage_control_matrix.json",
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
    split_hash_before_anything = hash_file(SPLIT_DIR / "MITDB_SPLIT_V1.csv")

    run_script("scripts/audit_split_leakage_t010.py")
    run_script("scripts/run_window_leakage_harness_t010.py")
    run_script("scripts/build_leakage_control_matrix_t010.py")
    run_script("scripts/freeze_mitdb_split_t010.py")

    split_hash_after_everything = hash_file(SPLIT_DIR / "MITDB_SPLIT_V1.csv")
    if split_hash_before_anything != split_hash_after_everything:
        raise RuntimeError(
            "SPLIT_HASH_MISMATCH: MITDB_SPLIT_V1.csv changed during T010 evidence generation "
            f"({split_hash_before_anything} -> {split_hash_after_everything})"
        )

    for report_path, status_key in (
        (SPLIT_REPORT_DIR / "split_audit.json", "overall_status"),
        (SPLIT_REPORT_DIR / "window_audit.json", "overall_status"),
        (REPORT_DIR / "leakage_control_matrix.json", "overall_status"),
    ):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report[status_key] != "PASS":
            raise RuntimeError(f"T010 evidence requires {report_path.name} to PASS")

    lock = json.loads((SPLIT_DIR / "MITDB_SPLIT_V1.lock.json").read_text(encoding="utf-8"))
    if lock["status"] != "FROZEN":
        raise RuntimeError("T010 evidence requires MITDB_SPLIT_V1.lock.json status=FROZEN")

    input_paths = [
        *CODE_ARTIFACTS,
        ROOT / "manifests/datasets/mitdb_mlii_records.csv",
        ROOT / "manifests/datasets/mitdb_mlii_exclusions.csv",
        ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        ROOT / "datasets/labels.py",
        ROOT / "datasets/grouping.py",
        ROOT / "reports/t009/split_generation.json",
    ]
    output_paths = [*SPLIT_ARTIFACTS, *REPORT_ARTIFACTS]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T010-LEAKAGE-AUDIT-AND-SPLIT-FREEZE-V1",
        phase_id="T010",
        task_id="T010",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "Independent leakage audit of the T009 candidate MITDB_SPLIT_V1: every G5 "
            "invariant recomputed from authoritative T006/T008/T009 artifacts, not trusted "
            "from T009's own report. Candidate split byte-identical before/after audit. "
            "Synthetic window-manifest leakage harness validated (real windows deferred to "
            "T013). G5=PASS, F05=FROZEN via manifests/splits/MITDB_SPLIT_V1.lock.json. G6 "
            "remains open -- causal resampling/filtering/gaps/windows are not implemented."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [*CODE_ARTIFACTS, *SPLIT_ARTIFACTS, *REPORT_ARTIFACTS, manifest_path]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T010 evidence: {missing}")

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
    print("T010 evidence: generated")


if __name__ == "__main__":
    main()
