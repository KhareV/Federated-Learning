#!/usr/bin/env python3
"""Create and verify F07/BASELINE_V1 after G7 evidence is complete."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from features.ecg import detector_metadata, feature_schema_sha256  # noqa: E402
from models.baseline_freeze import verify_baseline_freeze  # noqa: E402
from models.baselines import library_versions  # noqa: E402
from nhm.hashing import hash_canonical_json, hash_file  # noqa: E402
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402

LOCK_PATH = ROOT / "manifests/baselines/BASELINE_V1.lock.json"
BOUND_ARTIFACTS = [
    "features/ecg.py",
    "models/baselines.py",
    "training/train_baselines.py",
    "configs/baseline_v1.yaml",
    "manifests/features/BASELINE_FEATURES_V1.schema.json",
    "manifests/features/MITDB_BASELINE_FEATURES_V1.csv",
    "artifacts/baselines/BASELINE_V1/feature_transform.joblib",
    "artifacts/baselines/BASELINE_V1/majority.json",
    "artifacts/baselines/BASELINE_V1/logistic.joblib",
    "artifacts/baselines/BASELINE_V1/random_forest.joblib",
    "reports/baselines/baseline_report.json",
    "reports/baselines/baseline_metrics.csv",
    "reports/t014/feature_audit.json",
    "reports/t014/fit_scope_audit.json",
    "reports/t014/reproducibility.json",
]
UPSTREAM = [
    "manifests/labels/AAMI_SVF_MAP_V1.yaml",
    "manifests/splits/MITDB_SPLIT_V1.lock.json",
    "manifests/preprocessing/PREPROC_V1.lock.json",
    "manifests/windows/MITDB_WINDOWS_V1.csv",
]


def main() -> None:
    verify_frozen_split(ROOT)
    verify_preproc_freeze(ROOT)
    report = json.loads((ROOT / "reports/baselines/baseline_report.json").read_text())
    reproducibility = json.loads((ROOT / "reports/t014/reproducibility.json").read_text())
    if report["overall_status"] != "PASS" or reproducibility["overall_status"] != "PASS":
        raise RuntimeError("G7 evidence not PASS")
    lock = {
        "freeze_id": "F07",
        "status": "FROZEN",
        "frozen_by_task": "T014",
        "baseline_id": "BASELINE_V1",
        "feature_set_id": "BASELINE_FEATURES_V1",
        "feature_schema_sha256": feature_schema_sha256(),
        "detector_id": detector_metadata()["detector_id"],
        "detector_config_sha256": hash_canonical_json(detector_metadata()),
        "fit_partition": "TRAIN",
        "validation_role": "EVALUATE_ONLY",
        "forbidden_access": ["CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"],
        "seed": 20260927,
        "library_versions": library_versions(),
        "artifact_sha256": {relative: hash_file(ROOT / relative) for relative in BOUND_ARTIFACTS},
        "upstream_frozen_sha256": {relative: hash_file(ROOT / relative) for relative in UPSTREAM},
        "change_control": (
            "Feature schema/order, detector, train-fit transforms, majority policy, or fixed "
            "LR/RF configuration changes require a versioned Class C baseline revision."
        ),
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = verify_baseline_freeze(ROOT)
    audit = {
        "task_id": "T014",
        "gate_id": "G7",
        "freeze_id": "F07",
        "lock_path": str(LOCK_PATH.relative_to(ROOT)),
        "lock_sha256": hash_file(LOCK_PATH),
        "verification": result,
        "tamper_test_status": "PASS_TEST_SUITE",
        "overall_status": "PASS",
    }
    path = ROOT / "reports/t014/baseline_freeze_audit.json"
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("T014 F07 freeze: PASS")


if __name__ == "__main__":
    main()
