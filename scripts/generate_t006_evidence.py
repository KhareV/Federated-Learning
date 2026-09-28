#!/usr/bin/env python3
"""Generate T006 (MIT-BIH acquisition/validation) evidence with the canonical SHA-256 convention.

Runs the offline real-data validator (scripts/validate_mitdb_t006.py), which itself requires
an already-acquired local dataset (scripts/acquire_mitdb.py). No network access here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t006"

CODE_ARTIFACTS = [
    ROOT / "datasets/mitdb.py",
    ROOT / "scripts/acquire_mitdb.py",
    ROOT / "scripts/validate_mitdb_t006.py",
]
MANIFEST_ARTIFACTS = [
    ROOT / "manifests/datasets/mitdb_v1.yaml",
    ROOT / "manifests/datasets/mitdb_v1_files.csv",
    ROOT / "manifests/datasets/mitdb_mlii_records.csv",
    ROOT / "manifests/datasets/mitdb_mlii_exclusions.csv",
]


def run_validator() -> tuple[Path, Path]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_mitdb_t006.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    return REPORT_DIR / "mitdb_validation.json", REPORT_DIR / "lead_policy_audit.json"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    validation_path, lead_audit_path = run_validator()

    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation["overall_status"] != "PASS":
        raise RuntimeError("T006 evidence requires a passing MITDB validation report")

    record_validation_csv = REPORT_DIR / "record_validation.csv"
    input_paths = [*CODE_ARTIFACTS, ROOT / "requirements-dev.lock"]
    output_paths = [*MANIFEST_ARTIFACTS, validation_path, lead_audit_path, record_validation_csv]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T006-MITDB-ACQUISITION-V1",
        phase_id="T006",
        task_id="T006",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "MIT-BIH v1.0.0 exact acquisition, hash verification, and exact-MLII channel "
            "eligibility. No split, no AAMI mapping, no preprocessing, no model training. "
            "G2/G3 remain open pending T007 (INCART/NSTDB/BIDMC)."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [
        *CODE_ARTIFACTS,
        *MANIFEST_ARTIFACTS,
        validation_path,
        lead_audit_path,
        manifest_path,
    ]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T006 evidence: {missing}")

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
    print("T006 evidence: generated")


if __name__ == "__main__":
    main()
