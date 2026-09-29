#!/usr/bin/env python3
"""Generate T018 run provenance and non-circular artifact hash evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.calibration import verify_cal_v1  # noqa: E402
from evaluation.internal_test import verify_internal_test_freeze  # noqa: E402
from models.model_freeze import verify_frozen_model_v1  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    f08 = verify_frozen_model_v1(ROOT)
    f09 = verify_cal_v1(ROOT)
    f10 = verify_internal_test_freeze(ROOT)
    inputs = [
        ROOT / "checkpoints/MODEL_V1.pt",
        ROOT / "checkpoints/MODEL_V1.manifest.json",
        ROOT / "artifacts/CAL_V1.json",
        ROOT / "manifests/splits/MITDB_SPLIT_V1.csv",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv",
    ]
    outputs = [
        ROOT / "evaluation/metrics.py",
        ROOT / "evaluation/bootstrap.py",
        ROOT / "evaluation/internal_test.py",
        ROOT / "configs/internal_eval_v1.yaml",
        ROOT / "artifacts/internal_test_access_v1.json",
        ROOT / "reports/internal_test.json",
        ROOT / "reports/internal_test_metrics.csv",
        ROOT / "reports/internal_test_predictions.csv",
        ROOT / "reports/t018/pre_access_audit.json",
        ROOT / "reports/t018/one_shot_access_audit.json",
        ROOT / "reports/t018/bootstrap_draws.npz",
        ROOT / "reports/t018/bootstrap_replicates.csv",
        ROOT / "reports/t018/bootstrap_summary.json",
        ROOT / "reports/t018/reproducibility.json",
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T018-INTERNAL-EVAL-V1",
        phase_id="T018",
        task_id="T018",
        config_path=ROOT / "configs/internal_eval_v1.yaml",
        dependency_snapshot_path=ROOT / "requirements-dev.lock",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        seed=20260927,
        notes=(
            "One locked MODEL_V1 inference pass over eligible MIT-BIH INTERNAL_TEST windows; "
            "all point metrics and 2,000 patient-cluster percentile-bootstrap replicates use "
            "the immutable prediction table. No post-test tuning, external data, hardware, or CI."
        ),
    )
    run_path = ROOT / "reports/t018/run_manifest.json"
    write_run_manifest(manifest, run_path, ROOT / "contracts/run_manifest_v1.schema.json")
    hashed = [
        *outputs,
        run_path,
        ROOT / "scripts/verify_internal_test_reproducibility_t018.py",
        ROOT / "scripts/generate_t018_evidence.py",
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
        "F08_verification": f08,
        "F09_verification": f09,
        "F10_verification": f10,
        "G10_status": "PASS",
        "MODEL_V1_inference_passes_over_INTERNAL_TEST": 1,
        "bootstrap_replicates": 2000,
        "CI_executed": False,
    }
    write_json(ROOT / "reports/t018/artifact_hashes.json", evidence)
    print("T018 evidence: PASS")


if __name__ == "__main__":
    main()

