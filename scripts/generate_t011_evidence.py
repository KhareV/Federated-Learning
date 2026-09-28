#!/usr/bin/env python3
"""Generate T011 (causal stateful PREPROC_V1 resampler) evidence with the canonical SHA-256
convention.

Runs the resampler causality proofs (which themselves verify F05 before/after) and writes the
compact machine-readable resampler_spec.json, run_manifest.json, and artifact_hashes.json.
No network access, no model/result input, no dataset acquisition.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t011"
COEFFICIENT_DIR = ROOT / "preprocessing/coefficients"

CODE_ARTIFACTS = [
    ROOT / "preprocessing/resample.py",
    ROOT / "scripts/design_resampler_t011.py",
    ROOT / "scripts/run_resampler_causality_t011.py",
]
CONFIG_ARTIFACTS = [
    ROOT / "configs/preproc_v1.yaml",
]
COEFFICIENT_ARTIFACTS = [
    COEFFICIENT_DIR / "manifest.json",
    COEFFICIENT_DIR / "MITDB_360_TO_250_V1.npy",
    COEFFICIENT_DIR / "INCART_257_TO_250_V1.npy",
]
REPORT_ARTIFACTS = [
    ROOT / "reports/preprocessing/resampler_causality.json",
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


def build_resampler_spec_report() -> dict:
    manifest = json.loads((COEFFICIENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    causality = json.loads(
        (ROOT / "reports/preprocessing/resampler_causality.json").read_text(encoding="utf-8")
    )
    return {
        "task_id": "T011",
        "preproc_id": manifest["preproc_id"],
        "resampler_id": manifest["resampler_id"],
        "design_id": manifest["design_id"],
        "scipy_version": manifest["scipy_version"],
        "numpy_version": manifest["numpy_version"],
        "conversions": manifest["conversions"],
        "causality_overall_status": causality["overall_status"],
        "split_freeze_verified": causality["split_freeze_verified"],
        "gap_handling": "DEFERRED_T012",
        "filters": "DEFERRED_T012",
        "windowing": "DEFERRED_T013",
        "overall_status": causality["overall_status"],
    }


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_script("scripts/design_resampler_t011.py")
    run_script("scripts/run_resampler_causality_t011.py")

    causality = json.loads(
        (ROOT / "reports/preprocessing/resampler_causality.json").read_text(encoding="utf-8")
    )
    if causality["overall_status"] != "PASS":
        raise RuntimeError(f"T011 evidence requires resampler_causality.json to PASS: {causality}")

    spec_report = build_resampler_spec_report()
    spec_report_path = REPORT_DIR / "resampler_spec.json"
    temporary = spec_report_path.with_suffix(f"{spec_report_path.suffix}.tmp")
    temporary.write_text(json.dumps(spec_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(spec_report_path)

    input_paths = [*CODE_ARTIFACTS, ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json"]
    output_paths = [*CONFIG_ARTIFACTS, *COEFFICIENT_ARTIFACTS, *REPORT_ARTIFACTS, spec_report_path]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T011-CAUSAL-RESAMPLER-V1",
        phase_id="T011",
        task_id="T011",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "Stateful causal rational/polyphase FIR resampler (PREPROC_V1_RESAMPLER_V1) for "
            "MITDB (360->250 Hz, up=25/down=36) and INCART (257->250 Hz, up=250/down=257). "
            "Bounded-memory streaming polyphase implementation, cross-checked against a slow "
            "direct causal reference; future-append and chunk-equivalence proven to "
            "machine-epsilon tolerance. No centered/offline resample_poly/resample/filtfilt "
            "in the production path (statically audited). Group delay 10 output samples "
            "(40ms) for both conversions, exposed as explicit metadata, never backdated. F05 "
            "split freeze verified unchanged before and after. No GAP_POLICY_V1, no "
            "physiological bandpass filtering, no real windows, no normalization, no model "
            "training. G6 remains open -- T012/T013 still required."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [
        *CODE_ARTIFACTS, *CONFIG_ARTIFACTS, *COEFFICIENT_ARTIFACTS, *REPORT_ARTIFACTS,
        spec_report_path, manifest_path,
    ]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T011 evidence: {missing}")

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
    print("T011 evidence: generated")


if __name__ == "__main__":
    main()
