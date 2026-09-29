#!/usr/bin/env python3
"""Generate the T017 run manifest and canonical hash evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.calibration import verify_cal_v1  # noqa: E402
from models.model_freeze import verify_frozen_model_v1  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    f08 = verify_frozen_model_v1(ROOT)
    f09 = verify_cal_v1(ROOT)
    inputs = [
        ROOT / "checkpoints/MODEL_V1.pt",
        ROOT / "checkpoints/MODEL_V1.manifest.json",
        ROOT / "configs/model_v1_frozen.yaml",
        ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        ROOT / "manifests/splits/MITDB_SPLIT_V1.csv",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv",
    ]
    outputs = [
        ROOT / "evaluation/calibration.py",
        ROOT / "configs/calibration_v1.yaml",
        ROOT / "artifacts/CAL_V1.json",
        ROOT / "reports/calibration/calibration_predictions.csv",
        ROOT / "reports/calibration/reliability.json",
        ROOT / "reports/calibration/reliability_diagram.svg",
        ROOT / "reports/t017/calibration_audit.json",
        ROOT / "reports/t017/threshold_search.json",
        ROOT / "reports/t017/partition_access_audit.json",
        ROOT / "reports/t017/reproducibility.json",
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T017-CAL-V1",
        phase_id="T017",
        task_id="T017",
        config_path=ROOT / "configs/calibration_v1.yaml",
        dependency_snapshot_path=ROOT / "requirements-dev.lock",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        seed=None,
        notes=(
            "One float64 temperature and one pooled-window F1 threshold fitted only on eligible "
            "MIT-BIH CALIBRATION windows. INTERNAL_TEST and all external datasets remained sealed; "
            "MODEL_V1 was not trained or modified; CI was not executed."
        ),
    )
    run_path = ROOT / "reports/t017/run_manifest.json"
    write_run_manifest(manifest, run_path, ROOT / "contracts/run_manifest_v1.schema.json")
    hashed = [*outputs, run_path, ROOT / "scripts/verify_calibration_reproducibility_t017.py"]
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
        "F08_verification": f08,
        "F09_verification": f09,
        "G10_status": "NOT_STARTED_PENDING_T018",
        "internal_test_access_count": 0,
        "external_data_access_count": 0,
        "CI_executed": False,
    }
    write_json(ROOT / "reports/t017/artifact_hashes.json", artifact_hashes)
    print("T017 evidence: PASS")


if __name__ == "__main__":
    main()
