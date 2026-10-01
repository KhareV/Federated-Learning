#!/usr/bin/env python3
"""Freeze GATEWAY_FP32_V1 before deployment-only INTERNAL_TEST access."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    paths = [
        "configs/gateway_artifact_v1.yaml",
        "deployment/export.py",
        "deployment/runtime.py",
        "deployment/benchmark.py",
        "scripts/export_gateway_t029.py",
        "scripts/run_gateway_t029.py",
        "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts",
        "checkpoints/MODEL_V1.pt",
        "artifacts/CAL_V1.json",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "tests/fixtures/model_v1_test_vector.npz",
        "reports/t029/export_development_audit.json",
        "reports/t029/gateway_host.json",
        "reports/t029/model_size.json",
    ]
    lock = {
        "lock_id": "GATEWAY_FP32_METHOD_V1",
        "status": "FROZEN_PRE_INTERNAL_TEST_METHOD",
        "artifact_id": "GATEWAY_FP32_V1",
        "format": "TORCHSCRIPT_SCRIPT",
        "input_contract": "GATEWAY_MODEL_INPUT_V1:[1,1,2500]:float32",
        "device": "CPU",
        "threads": {"intraop": 1, "interop": 1},
        "development_max_absolute_raw_logit_delta": 1e-5,
        "internal_equivalence": {
            "max_raw_logit_delta": 1e-5,
            "max_AUPRC_delta": 1e-6,
            "max_pooled_F1_delta": 1e-6,
            "max_patient_macro_F1_delta": 1e-6,
            "required_decision_agreement": 1.0,
        },
        "benchmark": {"warmups": 100, "measured_windows": 1000, "batch_size": 1},
        "test_access_role": "DEPLOYMENT_EQUIVALENCE_ONLY",
        "bound_artifacts": {path: hash_file(ROOT / path) for path in paths},
    }
    destination = ROOT / "artifacts/GATEWAY_FP32_METHOD_V1.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(destination))


if __name__ == "__main__":
    main()
