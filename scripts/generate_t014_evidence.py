#!/usr/bin/env python3
"""Generate T014/G7 run identity and canonical artifact hashes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from models.baseline_freeze import verify_baseline_freeze  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import (  # noqa: E402
    artifact_record,
    create_run_manifest,
    write_run_manifest,
)
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402


def write_json(relative: str, value: dict) -> Path:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> None:
    verify_frozen_split(ROOT)
    verify_preproc_freeze(ROOT)
    baseline = verify_baseline_freeze(ROOT)
    report = json.loads((ROOT / "reports/baselines/baseline_report.json").read_text())
    fit_scope = json.loads((ROOT / "reports/t014/fit_scope_audit.json").read_text())
    reproducibility = json.loads((ROOT / "reports/t014/reproducibility.json").read_text())
    if any(
        item["overall_status"] != "PASS" for item in (report, fit_scope, reproducibility)
    ):
        raise RuntimeError("T014 evidence component not PASS")

    inputs = [
        ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv",
    ]
    outputs = [
        ROOT / "manifests/features/BASELINE_FEATURES_V1.schema.json",
        ROOT / "manifests/features/MITDB_BASELINE_FEATURES_V1.csv",
        ROOT / "artifacts/baselines/BASELINE_V1/feature_transform.joblib",
        ROOT / "artifacts/baselines/BASELINE_V1/majority.json",
        ROOT / "artifacts/baselines/BASELINE_V1/logistic.joblib",
        ROOT / "artifacts/baselines/BASELINE_V1/random_forest.joblib",
        ROOT / "reports/baselines/baseline_report.json",
        ROOT / "reports/baselines/baseline_metrics.csv",
        ROOT / "reports/t014/feature_audit.json",
        ROOT / "reports/t014/fit_scope_audit.json",
        ROOT / "reports/t014/reproducibility.json",
        ROOT / "reports/t014/baseline_freeze_audit.json",
        ROOT / "manifests/baselines/BASELINE_V1.lock.json",
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T014-BASELINE-V1",
        phase_id="T014",
        task_id="T014",
        config_path=ROOT / "configs/baseline_v1.yaml",
        dependency_snapshot_path=ROOT / "requirements-dev.lock",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        seed=20260927,
        notes=(
            "TRAIN-only majority, imputation, scaling, logistic regression, and random forest; "
            "VALIDATION descriptive reporting only. CALIBRATION, INTERNAL_TEST, INCART, NSTDB, "
            "BIDMC, and wearable caches were not accessed. No search, calibration, or CI."
        ),
    )
    run_path = ROOT / "reports/t014/run_manifest.json"
    write_run_manifest(manifest, run_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hashed = [
        ROOT / "features/ecg.py",
        ROOT / "models/baselines.py",
        ROOT / "training/train_baselines.py",
        ROOT / "configs/baseline_v1.yaml",
        *outputs,
        run_path,
    ]
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
        "feature_cache_location": (
            "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/"
            "AAMI_SVF_WINDOW_V1/BASELINE_FEATURES_V1"
        ),
        "feature_cache_policy": "GENERATED_GITIGNORED_MANIFEST_COMMITTED",
        "F07_verification": baseline,
    }
    write_json("reports/t014/artifact_hashes.json", artifact_hashes)
    print("T014 evidence: PASS")


if __name__ == "__main__":
    main()
