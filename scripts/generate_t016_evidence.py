#!/usr/bin/env python3
"""Generate T016 run identity and canonical artifact hashes without model training."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from models.model_freeze import verify_frozen_model_v1  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    verification = verify_frozen_model_v1(ROOT)
    inputs = [
        ROOT / "checkpoints/candidates/MODEL_V1/candidate_manifest.json",
        ROOT / "checkpoints/candidates/MODEL_V1/MODEL_V1_seed_20260927_best.metadata.json",
        ROOT / "configs/model_v1.yaml",
        ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
        ROOT / "manifests/baselines/BASELINE_V1.lock.json",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv",
    ]
    outputs = [
        ROOT / "checkpoints/MODEL_V1.pt",
        ROOT / "checkpoints/MODEL_V1.manifest.json",
        ROOT / "configs/model_v1_frozen.yaml",
        ROOT / "tests/fixtures/model_v1_test_vector.npz",
        ROOT / "tests/fixtures/model_v1_test_vector.metadata.json",
        ROOT / "models/model_freeze.py",
        ROOT / "scripts/generate_model_v1_test_vector_t016.py",
        ROOT / "reports/t016/model_freeze_audit.json",
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T016-MODEL-V1-FREEZE",
        phase_id="T016",
        task_id="T016",
        config_path=ROOT / "configs/model_v1_frozen.yaml",
        dependency_snapshot_path=ROOT / "requirements-dev.lock",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        seed=20260927,
        notes=(
            "Byte-identical T015 release-candidate promotion and synthetic deterministic "
            "fixed-vector verification only. No training or dataset cache access; no "
            "calibration, threshold, internal test, external data, hardware, or CI."
        ),
    )
    run_path = ROOT / "reports/t016/run_manifest.json"
    write_run_manifest(manifest, run_path, ROOT / "contracts/run_manifest_v1.schema.json")
    hashed = [ROOT / "models/ecg_cnn.py", *outputs, run_path]
    artifact_hashes = {
        "manifest_version": "1.0",
        "algorithm": "sha256",
        "rule": "exact file bytes; this manifest excludes itself to avoid a circular digest",
        "artifacts": {
            str(path.relative_to(ROOT)): hash_file(path) for path in sorted(set(hashed))
        },
        "upstream_frozen_hashes": {
            str(path.relative_to(ROOT)): hash_file(path) for path in inputs[3:]
        },
        "verification": verification,
        "training_executed": False,
        "dataset_cache_access_count": 0,
        "CI_executed": False,
    }
    write_json(ROOT / "reports/t016/artifact_hashes.json", artifact_hashes)
    print("T016 evidence: PASS")


if __name__ == "__main__":
    main()
