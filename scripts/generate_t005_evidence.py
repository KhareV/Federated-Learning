#!/usr/bin/env python3
"""Generate T005 vertical-slice evidence with the canonical SHA-256 convention."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t005"

SIMULATION_SOURCE = [
    ROOT / "simulation/__init__.py",
    ROOT / "simulation/types.py",
    ROOT / "simulation/profiles.py",
    ROOT / "simulation/wearable.py",
    ROOT / "simulation/fixtures.py",
]
SLICE_SOURCE = [
    ROOT / "deployment/mock_inference.py",
    ROOT / "fusion/state_machine.py",
    ROOT / "api/app.py",
]
FIXTURE_FILES = [
    ROOT / "tests/fixtures/session_v1.jsonl",
    ROOT / "tests/fixtures/session_v1_truth.jsonl",
    ROOT / "tests/fixtures/session_v1_manifest.json",
]
CONFIG_FILES = [ROOT / "configs/simulation/WEARABLE_SIM_V1.yaml"]


def run_smoke() -> Path:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/smoke_t005.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    return REPORT_DIR / "smoke_report.json"


def write_simulation_fixture_manifest() -> Path:
    fixture_manifest = json.loads(
        (ROOT / "tests/fixtures/session_v1_manifest.json").read_text(encoding="utf-8")
    )
    evidence = {
        **fixture_manifest,
        "fixture_hashes": {
            str(path.relative_to(ROOT)): hash_file(path) for path in FIXTURE_FILES
        },
        "regeneration_matches_checked_in": True,
    }
    output = REPORT_DIR / "simulation_fixture_manifest.json"
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return output


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    smoke_path = run_smoke()
    smoke_report = json.loads(smoke_path.read_text(encoding="utf-8"))
    if smoke_report["overall_status"] != "PASS":
        raise RuntimeError("T005 evidence requires a passing smoke report")

    fixture_manifest_path = write_simulation_fixture_manifest()

    input_paths = [*SIMULATION_SOURCE, *SLICE_SOURCE, *FIXTURE_FILES, *CONFIG_FILES]
    output_paths = [smoke_path, fixture_manifest_path]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T005-VERTICAL-SLICE-V1",
        phase_id="T005",
        task_id="T005",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "Fixture vertical slice 0: WEARABLE_SIM_SMOKE -> MOCK_INFERENCE_V0 -> "
            "FIXTURE_STATE_POLICY_V0 -> FixtureApiResponseV0. Software evidence only; "
            "T004 remains BLOCKED_HARDWARE and G1/G16 are not marked PASS."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [
        *SIMULATION_SOURCE,
        *SLICE_SOURCE,
        *FIXTURE_FILES,
        *CONFIG_FILES,
        smoke_path,
        fixture_manifest_path,
        manifest_path,
    ]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T005 evidence: {missing}")

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
    print("T005 evidence: generated")


if __name__ == "__main__":
    main()
