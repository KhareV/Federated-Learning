#!/usr/bin/env python3
"""Generate T012 (causal ECG/PPG filters + GAP_POLICY_V1) evidence with the canonical
SHA-256 convention.

Runs filter design, filter causality, and gap-policy proofs (which themselves verify F05
before/after), then writes preproc_component_status.json, run_manifest.json, and
artifact_hashes.json. Never rewrites historical T011 evidence -- only references its hashes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t012"
COEFFICIENT_DIR = ROOT / "preprocessing/coefficients"

CODE_ARTIFACTS = [
    ROOT / "preprocessing/gaps.py",
    ROOT / "preprocessing/filters.py",
    ROOT / "preprocessing/ecg.py",
    ROOT / "preprocessing/ppg.py",
    ROOT / "scripts/design_filters_t012.py",
    ROOT / "scripts/run_filter_causality_t012.py",
    ROOT / "scripts/run_gap_policy_tests_t012.py",
]
CONFIG_ARTIFACTS = [ROOT / "configs/preproc_v1.yaml"]
COEFFICIENT_ARTIFACTS = [
    COEFFICIENT_DIR / "manifest.json",
    COEFFICIENT_DIR / "PREPROC_V1_ECG_FILTER_V1.npy",
    COEFFICIENT_DIR / "PREPROC_V1_PPG_FILTER_V1.npy",
]
REPORT_ARTIFACTS = [
    ROOT / "reports/preprocessing/filter_causality.json",
    ROOT / "reports/preprocessing/gap_tests.json",
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


def build_component_status_report() -> dict:
    filter_causality = json.loads(
        (ROOT / "reports/preprocessing/filter_causality.json").read_text(encoding="utf-8")
    )
    gap_tests = json.loads(
        (ROOT / "reports/preprocessing/gap_tests.json").read_text(encoding="utf-8")
    )
    resampler_causality = json.loads(
        (ROOT / "reports/preprocessing/resampler_causality.json").read_text(encoding="utf-8")
    )
    return {
        "task_id": "T012",
        "preproc_id": "PREPROC_V1",
        "components": {
            "resampler": {
                "status": "PASS_T011",
                "resampler_id": resampler_causality["resampler_id"],
                "evidence": "reports/preprocessing/resampler_causality.json",
            },
            "ecg_filter": {
                "status": "PASS_T012",
                "filter_id": "PREPROC_V1_ECG_FILTER_V1",
                "evidence": "reports/preprocessing/filter_causality.json",
            },
            "ppg_filter": {
                "status": "PASS_T012",
                "filter_id": "PREPROC_V1_PPG_FILTER_V1",
                "evidence": "reports/preprocessing/filter_causality.json",
            },
            "gap_policy": {
                "status": "PASS_T012",
                "policy_id": "GAP_POLICY_V1",
                "evidence": "reports/preprocessing/gap_tests.json",
            },
            "windowing": {"status": "DEFERRED_T013"},
            "quality": {"status": "DEFERRED_T013"},
        },
        "filter_causality_overall_status": filter_causality["overall_status"],
        "gap_tests_overall_status": gap_tests["overall_status"],
        "resampler_causality_overall_status": resampler_causality["overall_status"],
        "gate_status": {
            "G6": "NOT_STARTED",
            "F06": "NOT_FROZEN",
            "pending": ["T013 windowing", "T013 quality", "T013 real-window leakage audit"],
        },
        "overall_status": (
            "PASS"
            if filter_causality["overall_status"] == "PASS"
            and gap_tests["overall_status"] == "PASS"
            and resampler_causality["overall_status"] == "PASS"
            else "FAIL"
        ),
    }


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_script("scripts/design_filters_t012.py")
    run_script("scripts/run_filter_causality_t012.py")
    run_script("scripts/run_gap_policy_tests_t012.py")

    component_status = build_component_status_report()
    if component_status["overall_status"] != "PASS":
        raise RuntimeError(f"T012 evidence requires all components PASS: {component_status}")

    status_path = REPORT_DIR / "preproc_component_status.json"
    temporary = status_path.with_suffix(f"{status_path.suffix}.tmp")
    temporary.write_text(
        json.dumps(component_status, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(status_path)

    input_paths = [
        *CODE_ARTIFACTS,
        ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json",
        ROOT / "preprocessing/resample.py",
        ROOT / "reports/preprocessing/resampler_causality.json",
    ]
    output_paths = [*CONFIG_ARTIFACTS, *COEFFICIENT_ARTIFACTS, *REPORT_ARTIFACTS, status_path]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T012-CAUSAL-FILTERS-AND-GAP-POLICY-V1",
        phase_id="T012",
        task_id="T012",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "Causal 4th-order Butterworth SOS bandpass filters (ECG 0.5-40Hz@250Hz, PPG "
            "0.5-8Hz@100Hz) and GAP_POLICY_V1 (exact 100ms short/long-gap classification, "
            "causal last-value ZOH short-gap fill, no-fill long-gap segment reset). "
            "Integration pipeline enforces the locked order: source -> GAP_POLICY_V1 -> "
            "validated T011 resampler -> ECG filter. F05 split freeze verified unchanged "
            "before and after; T011 resampler coefficients/behavior unmodified and its full "
            "test suite still passes. G6 remains open and F06 remains NOT_FROZEN -- T013 "
            "still owns real windows, quality, and the real-window leakage audit."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [
        *CODE_ARTIFACTS, *CONFIG_ARTIFACTS, *COEFFICIENT_ARTIFACTS, *REPORT_ARTIFACTS,
        status_path, manifest_path,
    ]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T012 evidence: {missing}")

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
    print("T012 evidence: generated")


if __name__ == "__main__":
    main()
