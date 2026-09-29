#!/usr/bin/env python3
"""Generate non-circular T019 run and artifact provenance."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest  # noqa: E402
from scripts.verify_noise_robustness_t019 import verify_noise_robustness  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    verification = verify_noise_robustness(ROOT)
    inputs = [
        ROOT / "manifests/datasets/nstdb_v1.yaml",
        ROOT / "manifests/datasets/nstdb_v1_files.csv",
        ROOT / "manifests/datasets/nstdb_records.csv",
        ROOT / "checkpoints/MODEL_V1.pt",
        ROOT / "checkpoints/MODEL_V1.manifest.json",
        ROOT / "artifacts/CAL_V1.json",
        ROOT / "reports/internal_test.json",
        ROOT / "artifacts/internal_test_access_v1.json",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
    ]
    outputs = [
        ROOT / "evaluation/noise.py",
        ROOT / "configs/noise_robustness_v1.yaml",
        ROOT / "reports/noise_robustness.json",
        ROOT / "reports/noise_robustness.csv",
        ROOT / "reports/noise_robustness.svg",
        ROOT / "reports/t019/nstdb_predictions.csv",
        ROOT / "reports/t019/noise_robustness_by_record.csv",
        ROOT / "reports/t019/protocol_audit.json",
        ROOT / "reports/t019/pairing_audit.json",
        ROOT / "reports/t019/quality_by_snr.json",
        ROOT / "reports/t019/pure_noise_source_audit.json",
        ROOT / "reports/t019/reproducibility.json",
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T019-NSTDB-NOISE-ROBUSTNESS-V1",
        phase_id="T019",
        task_id="T019",
        config_path=ROOT / "configs/noise_robustness_v1.yaml",
        dependency_snapshot_path=ROOT / "requirements-dev.lock",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        seed=None,
        notes=(
            "Two deterministic CPU inference calculations over official NSTDB v1.0.0 "
            "stress records. Fixed paired label-eligible positions across six SNR levels; "
            "pure-noise records remain unlabeled; no tuning, adaptation, INTERNAL_TEST, "
            "INCART, hardware, or CI access. Protocol commit: "
            "f32ec164e43c901fec1480ec4ba7bde02d7dc9c5."
        ),
    )
    run_path = ROOT / "reports/t019/run_manifest.json"
    write_run_manifest(manifest, run_path, ROOT / "contracts/run_manifest_v1.schema.json")
    hashed = [
        *outputs,
        run_path,
        ROOT / "scripts/verify_noise_robustness_t019.py",
        ROOT / "scripts/generate_t019_evidence.py",
    ]
    evidence = {
        "manifest_version": "1.0",
        "algorithm": "sha256",
        "rule": "exact file bytes; this manifest excludes itself to avoid a circular digest",
        "artifacts": {
            str(path.relative_to(ROOT)): hash_file(path) for path in sorted(set(hashed))
        },
        "upstream_frozen_hashes": {
            str(path.relative_to(ROOT)): hash_file(path) for path in inputs
        },
        "protocol_commit": "f32ec164e43c901fec1480ec4ba7bde02d7dc9c5",
        "verification": verification,
        "T019_status": "PASS",
        "G10_status": "PASS",
        "new_freeze_created": False,
        "CI_executed": False,
    }
    write_json(ROOT / "reports/t019/artifact_hashes.json", evidence)
    print("T019 evidence: PASS")


if __name__ == "__main__":
    main()
