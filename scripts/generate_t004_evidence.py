#!/usr/bin/env python3
"""Generate T004 hardware-deferral and simulation-foundation evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t004"

DOC_ARTIFACTS = [
    ROOT / "docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md",
    ROOT / "docs/LEGACY_FIRMWARE_V0_FINDINGS.md",
    ROOT / "contracts/WEARABLE_SIM_V1.md",
    ROOT / "configs/simulation/WEARABLE_SIM_V1.yaml",
]


def run_validator() -> tuple[Path, Path]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_t004_deferral.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    return REPORT_DIR / "hardware_deferral.json", REPORT_DIR / "simulation_foundation.json"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    hardware_deferral_path, simulation_foundation_path = run_validator()

    hardware_deferral = json.loads(hardware_deferral_path.read_text(encoding="utf-8"))
    simulation_foundation = json.loads(simulation_foundation_path.read_text(encoding="utf-8"))
    if hardware_deferral["deferral_record_status"] != "PASS":
        raise RuntimeError("T004 hardware deferral record did not validate")
    if simulation_foundation["status"] != "PASS":
        raise RuntimeError("T004 simulation foundation record did not validate")

    input_paths = [*DOC_ARTIFACTS, ROOT / "manifests/task_registry_v1.csv"]
    output_paths = [hardware_deferral_path, simulation_foundation_path]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T004-HARDWARE-DEFERRAL-V1",
        phase_id="T004",
        task_id="T004",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "T004 canonical hardware verification is BLOCKED_HARDWARE; this evidence records "
            "the deferral/fallback preparation and WEARABLE_SIM_V1 contract only. G1/G16 are "
            "not marked PASS and the hardware/data contract is not marked FROZEN."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [*DOC_ARTIFACTS, hardware_deferral_path, simulation_foundation_path, manifest_path]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T004 evidence: {missing}")

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
    print("T004 evidence: generated")


if __name__ == "__main__":
    main()
