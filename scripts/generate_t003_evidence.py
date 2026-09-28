#!/usr/bin/env python3
"""Generate T003 contract evidence with the canonical SHA-256 convention."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t003"

CONTRACT_ARTIFACTS = [
    ROOT / "contracts/HARDWARE_DATA_CONTRACT_V1.md",
    ROOT / "contracts/sample_schema_v1.json",
    ROOT / "contracts/API_SCHEMA_V1.json",
    ROOT / "contracts/LABEL_SCHEMA_V1.md",
]


def run_validator() -> Path:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_contracts_t003.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    return REPORT_DIR / "contract_validation.json"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    validation_path = run_validator()
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation["status"] != "PASS":
        raise RuntimeError("T003 evidence requires a passing contract validation")

    input_paths = [*CONTRACT_ARTIFACTS, *sorted((ROOT / "tests/fixtures/contracts").glob("*.json"))]
    output_paths = [validation_path]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T003-CONTRACT-VALIDATION-V1",
        phase_id="T003",
        task_id="T003",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "Canonical hardware/data/API/label contract skeletons. Hardware physical facts "
            "remain VERIFICATION_REQUIRED; G1 is not marked PASS by this task."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [*CONTRACT_ARTIFACTS, validation_path, manifest_path]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T003 evidence: {missing}")

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
    print("T003 evidence: generated")


if __name__ == "__main__":
    main()
