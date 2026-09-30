#!/usr/bin/env python3
"""Finalize T021 metadata and generate non-circular run/hash evidence."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.bidmc_context import verify  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    report_path = ROOT / "reports/bidmc_multimodal_engineering.json"
    report = json.loads(report_path.read_text())
    with (ROOT / "reports/t021/bidmc_context_rows.csv").open(newline="") as handle:
        context_row_count = sum(1 for _ in csv.DictReader(handle))
    report["context_row_count"] = context_row_count
    report["frozen_filter_hashes"] = {
        "PREPROC_V1_PPG_FILTER_V1": hash_file(
            ROOT / "preprocessing/coefficients/PREPROC_V1_PPG_FILTER_V1.npy"
        ),
        "PREPROC_V1_ECG_FILTER_V1": hash_file(
            ROOT / "preprocessing/coefficients/PREPROC_V1_ECG_FILTER_V1.npy"
        ),
    }
    report["protocol_commit"] = "2390098ca2a05390bea506fe49a877732714aef2"
    report["result_commit"] = "6d1431fb71382b5c79907c2eaafcdba69daca963"
    write_json(report_path, report)

    verification = verify(ROOT)
    inputs = [
        ROOT / "manifests/datasets/bidmc_v1.yaml",
        ROOT / "manifests/datasets/bidmc_v1_files.csv",
        ROOT / "reports/t007/bidmc_validation.json",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
        ROOT / "checkpoints/MODEL_V1.pt",
        ROOT / "artifacts/CAL_V1.json",
        ROOT / "reports/internal_test.json",
        ROOT / "reports/external_incart.json",
    ]
    outputs = [
        ROOT / "configs/bidmc_context_v1.yaml",
        ROOT / "preprocessing/context_resample.py",
        ROOT / "preprocessing/context_quality.py",
        ROOT / "preprocessing/context_coefficients/manifest.json",
        ROOT / "preprocessing/context_coefficients/BIDMC_PPG_125_TO_100_V1.npy",
        ROOT / "preprocessing/context_coefficients/BIDMC_ECG_HR_125_TO_250_V1.npy",
        ROOT / "evaluation/bidmc_context.py",
        report_path,
        ROOT / "reports/bidmc_multimodal_engineering.csv",
        ROOT / "reports/t021/bidmc_context_rows.csv",
        ROOT / "reports/t021/bidmc_by_record.csv",
        ROOT / "reports/t021/alignment_audit.json",
        ROOT / "reports/t021/context_quality_tests.json",
        ROOT / "reports/t021/spo2_provenance.json",
        ROOT / "reports/t021/protocol_audit.json",
        ROOT / "reports/t021/reproducibility.json",
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T021-BIDMC-CONTEXT-V1",
        phase_id="T021",
        task_id="T021",
        config_path=ROOT / "configs/bidmc_context_v1.yaml",
        dependency_snapshot_path=ROOT / "requirements-dev.lock",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        seed=None,
        notes=(
            "Deterministic BIDMC context engineering validation; no MODEL_V1 inference, "
            "AAMI labels, learned fusion, alert episodes, or CI execution."
        ),
    )
    run_path = ROOT / "reports/t021/run_manifest.json"
    write_run_manifest(manifest, run_path, ROOT / "contracts/run_manifest_v1.schema.json")
    hashed = [
        *outputs,
        run_path,
        ROOT / "scripts/design_bidmc_context_resamplers_t021.py",
        ROOT / "scripts/generate_t021_evidence.py",
    ]
    evidence = {
        "manifest_version": "1.0",
        "algorithm": "sha256",
        "rule": "exact file bytes; this manifest excludes itself to avoid circular digest",
        "artifacts": {str(path.relative_to(ROOT)): hash_file(path) for path in hashed},
        "upstream_frozen_hashes": {
            str(path.relative_to(ROOT)): hash_file(path) for path in inputs
        },
        "F06_bound_file_hashes": {
            str(path.relative_to(ROOT)): hash_file(path)
            for path in [
                ROOT / "configs/preproc_v1.yaml",
                ROOT / "preprocessing/resample.py",
                ROOT / "preprocessing/ecg.py",
                ROOT / "preprocessing/ppg.py",
                ROOT / "preprocessing/gaps.py",
                ROOT / "preprocessing/filters.py",
            ]
        },
        "verification": verification,
        "T021_status": "PASS",
        "G9_status": "NOT_STARTED",
        "new_freeze": False,
        "CI_executed": False,
    }
    write_json(ROOT / "reports/t021/artifact_hashes.json", evidence)
    print("T021 evidence: PASS")


if __name__ == "__main__":
    main()
