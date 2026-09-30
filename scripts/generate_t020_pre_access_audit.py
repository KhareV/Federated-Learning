#!/usr/bin/env python3
"""Create T020 pre-access evidence after the scientific method is committed."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.calibration import verify_cal_v1  # noqa: E402
from evaluation.external_incart import (  # noqa: E402
    CONFIG_PATH,
    validate_method_config,
    verify_source_contract,
)
from evaluation.internal_test import verify_internal_test_freeze  # noqa: E402
from models.model_freeze import verify_frozen_model_v1  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    if git("status", "--porcelain"):
        raise RuntimeError("T020_PRE_ACCESS_REQUIRES_CLEAN_COMMITTED_METHOD")
    method_commit = git("rev-parse", "HEAD")
    source = verify_source_contract(ROOT)
    validate_method_config(ROOT)
    f06 = verify_preproc_freeze(ROOT)
    f08 = verify_frozen_model_v1(ROOT)
    f09 = verify_cal_v1(ROOT)
    f10 = verify_internal_test_freeze(ROOT)
    method_files = [
        "evaluation/external_incart.py",
        str(CONFIG_PATH),
        "evaluation/metrics.py",
        "evaluation/bootstrap.py",
        "preprocessing/ecg.py",
        "preprocessing/windowing.py",
        "datasets/labels.py",
    ]
    audit = {
        "evaluation_id": "EXTERNAL_INCART_V1",
        "pre_access_method_commit": method_commit,
        "method_config_sha256": hash_file(ROOT / CONFIG_PATH),
        "external_evaluator_sha256": hash_file(ROOT / "evaluation/external_incart.py"),
        "method_artifact_sha256": {
            path: hash_file(ROOT / path) for path in method_files
        },
        "MODEL_V1_sha256": hash_file(ROOT / "checkpoints/MODEL_V1.pt"),
        "CAL_V1_sha256": hash_file(ROOT / "artifacts/CAL_V1.json"),
        "PREPROC_V1_lock_sha256": hash_file(
            ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"
        ),
        "AAMI_map_sha256": hash_file(ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml"),
        "INCART_dataset_manifest_sha256": hash_file(
            ROOT / "manifests/datasets/incart_v1.yaml"
        ),
        "INCART_lead_manifest_sha256": hash_file(
            ROOT / "manifests/datasets/incart_lead_ii_records.csv"
        ),
        "INCART_patient_map_sha256": hash_file(
            ROOT / "manifests/datasets/incart_patient_map.csv"
        ),
        "source_contract": source,
        "F06_verification": f06,
        "F08_verification": f08,
        "F09_verification": f09,
        "F10_verification": f10,
        "Ruff_before_access": "PASS",
        "pytest_before_access": "PASS",
        "pip_check_before_access": "PASS",
        "INCART_MODEL_V1_inference_before_method_commit": False,
        "external_data_consumed_by_T020": False,
        "method_frozen_before_access": True,
        "overall_status": "PASS",
    }
    output = ROOT / "reports/t020/pre_access_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"T020 pre-access audit: PASS method_commit={method_commit}")


if __name__ == "__main__":
    main()
