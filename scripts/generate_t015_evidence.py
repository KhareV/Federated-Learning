#!/usr/bin/env python3
"""Generate T015 run identity and hashes without freezing MODEL_V1/F08."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from models.baseline_freeze import verify_baseline_freeze  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import (  # noqa: E402
    artifact_record,
    create_run_manifest,
    write_run_manifest,
)
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    verify_preproc_freeze(ROOT)
    verify_baseline_freeze(ROOT)
    candidate_manifest = json.loads(
        (ROOT / "checkpoints/candidates/MODEL_V1/candidate_manifest.json").read_text()
    )
    reports = [
        ROOT / "reports/model/model_v1_training.json",
        ROOT / "reports/t015/training_contract_audit.json",
        ROOT / "reports/t015/partition_access_audit.json",
        ROOT / "reports/t015/seed_robustness.json",
        ROOT / "reports/t015/augmentation_audit.json",
        ROOT / "reports/t015/determinism_smoke.json",
    ]
    if candidate_manifest["overall_status"] != "PASS" or any(
        json.loads(path.read_text())["overall_status"] != "PASS" for path in reports
    ):
        raise RuntimeError("T015 evidence component not PASS")
    inputs = [
        ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
        ROOT / "manifests/baselines/BASELINE_V1.lock.json",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv",
    ]
    candidates: list[Path] = []
    for entry in candidate_manifest["candidates"]:
        candidates.extend(
            [
                ROOT / entry["checkpoint_path"],
                ROOT / entry["metadata_path"],
                ROOT / entry["seed_log_path"],
            ]
        )
    outputs = [
        ROOT / "configs/model_v1.yaml",
        ROOT / "models/ecg_cnn.py",
        ROOT / "training/train_central.py",
        ROOT / "artifacts/MODEL_V1_candidate/train_pos_weight.json",
        ROOT / "checkpoints/candidates/MODEL_V1/candidate_manifest.json",
        *candidates,
        *reports,
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T015-MODEL-V1-CANDIDATES",
        phase_id="T015",
        task_id="T015",
        config_path=ROOT / "configs/model_v1.yaml",
        dependency_snapshot_path=ROOT / "requirements-dev.lock",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        seed=20260927,
        notes=(
            "Exact MODEL_V1 candidates trained on TRAIN and selected within-seed by pooled "
            "VALIDATION AUPRC. Release seed fixed to 20260927. Robustness seeds cannot replace "
            "it. No calibration, internal test, external data, final promotion, F08 freeze, or CI."
        ),
    )
    run_path = ROOT / "reports/t015/run_manifest.json"
    write_run_manifest(manifest, run_path, ROOT / "contracts/run_manifest_v1.schema.json")
    hashed = [*outputs, run_path]
    artifact_hashes = {
        "manifest_version": "1.0",
        "algorithm": "sha256",
        "rule": "exact file bytes; this manifest excludes itself to avoid a circular digest",
        "artifacts": {
            str(path.relative_to(ROOT)): hash_file(path) for path in sorted(set(hashed))
        },
        "upstream_frozen_hashes": {
            str(path.relative_to(ROOT)): hash_file(path) for path in inputs
        },
        "candidate_binary_policy": (
            "Generated .pt files remain gitignored; committed candidate manifest and metadata "
            "retain hashes and the normal training command regenerates them."
        ),
        "F08_status": "NOT_FROZEN_T016_OWNED",
    }
    write_json(ROOT / "reports/t015/artifact_hashes.json", artifact_hashes)
    print("T015 evidence: PASS")


if __name__ == "__main__":
    main()
