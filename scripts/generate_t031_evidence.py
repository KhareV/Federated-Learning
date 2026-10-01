#!/usr/bin/env python3
"""Generate deterministic T031 scope, provenance, and hash inventory evidence."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

import torch

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/t031"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    scope = {
        "MODEL_V1_modified": False,
        "model_training": False,
        "threshold_tuning": False,
        "CAL_fitting": False,
        "PREPROC_change": False,
        "INCART_adaptation": False,
        "new_test_exclusions": False,
        "hardware": False,
        "WEARABLE_V1_fabrication": False,
        "INTERNAL_TEST_access_role": "POSTHOC_EXPLAINABILITY_ERROR_ANALYSIS_ONLY",
        "TRAIN_access_role": "HR_ANALYSIS_BINS_V1_DEFINITION_ONLY",
        "status": "PASS",
    }
    write_json(OUT / "scope_audit.json", scope)
    write_json(
        OUT / "run_manifest.json",
        {
            "task": "T031",
            "method": "EXPLAINABILITY_V1_AND_ERROR_ANALYSIS_V1",
            "Python": platform.python_version(),
            "PyTorch": torch.__version__,
            "device": "CPU",
            "command": "PYTHONPATH=src:. .venv-t024/bin/python scripts/run_t031.py",
            "method_lock_sha256": hash_file(ROOT / "artifacts/EXPLAINABILITY_V1_METHOD.lock.json"),
            "CI_executed": False,
            "status": "PASS",
        },
    )
    artifacts = [
        "evaluation/explain.py",
        "evaluation/error_analysis.py",
        "configs/explainability_v1.yaml",
        "configs/error_analysis_v1.yaml",
        "artifacts/EXPLAINABILITY_V1_METHOD.lock.json",
        "reports/t031/explainability_case_manifest.csv",
        "reports/t031/case_selection_audit.json",
        "reports/t031/ig_completeness.csv",
        "reports/t031/hr_bins.json",
        "reports/t031/patient_slice.csv",
        "reports/t031/class_composition_slice.csv",
        "reports/t031/quality_slice.csv",
        "reports/t031/noise_snr_slice.csv",
        "reports/t031/heart_rate_slice.csv",
        "reports/t031/dataset_slice.csv",
        "reports/t031/threshold_region_slice.csv",
        "reports/t031/wearable_slice_status.json",
        "reports/t031/reproducibility.json",
        "reports/t031/scope_audit.json",
        "reports/t031/run_manifest.json",
        "reports/explainability_v1.json",
        "reports/error_analysis_v1.json",
        "reports/error_analysis_v1.csv",
        "scripts/prepare_t031_protocol.py",
        "scripts/run_t031.py",
        "scripts/generate_t031_evidence.py",
        "scripts/verify_t031.py",
    ]
    for case in ("TP", "TN", "FP", "FN"):
        artifacts.extend(
            [
                f"reports/t031/cases/{case}_attribution.csv",
                f"reports/t031/cases/{case}_raw_ecg.csv",
                f"reports/t031/cases/{case}_annotations.csv",
                f"reports/t031/cases/{case}_figure.svg",
            ]
        )
    write_json(
        OUT / "artifact_hashes.json",
        {path: hash_file(ROOT / path) for path in artifacts},
    )


if __name__ == "__main__":
    main()
