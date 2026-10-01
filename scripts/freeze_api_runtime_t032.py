#!/usr/bin/env python3
"""Create the API_RUNTIME_V1 component lock (T032).

Per the T032 task packet (Section 5/98): this does NOT create a new canonical Fxx freeze
registry row -- F15 is reserved for RELEASE_V1 / G22. This is a component lock, parallel in
spirit to GATEWAY_FP32_METHOD_V1, binding every frozen artifact the production
POST /v1/infer-window route reads (read-only) plus the API's own source/contract files, so any
future byte-level change to any of them is detectable.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cal = json.loads((ROOT / "artifacts/CAL_V1.json").read_text(encoding="utf-8"))
    alert_policy_lock = json.loads(
        (ROOT / "artifacts/ALERT_POLICY_V1.lock.json").read_text(encoding="utf-8")
    )
    gateway_lock = json.loads(
        (ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json").read_text(encoding="utf-8")
    )

    bound_paths = [
        "contracts/API_SCHEMA_V1.json",
        "contracts/openapi_v1.json",
        "api/app.py",
        "api/schemas.py",
        "api/runtime.py",
        "api/session.py",
        "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
        "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts",
        "checkpoints/MODEL_V1.pt",
        "artifacts/CAL_V1.json",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "artifacts/ALERT_POLICY_V1.lock.json",
        "artifacts/ECG_HR_CONTEXT_V2.lock.json",
        "configs/alert_policy_v1.yaml",
    ]

    lock = {
        "lock_id": "API_RUNTIME_V1",
        "status": "FROZEN_ENGINEERING_INTERFACE",
        "route": "POST /v1/infer-window",
        "contract_version": "API_SCHEMA_V1",
        "target_id": "AAMI_SVF_WINDOW_V1",
        "model_id": cal["model_id"],
        "model_checkpoint_sha256": cal["model_checkpoint_sha256"],
        "preproc_id": cal["preproc_id"],
        "calibration_id": cal["calibration_id"],
        "calibration_domain": cal["calibration_domain"],
        "calibration_patient_count": cal["calibration_patient_count"],
        "gateway_artifact_id": "GATEWAY_FP32_V1",
        "gateway_artifact_lock_sha256": hash_file(
            ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
        ),
        "deployment_artifact_sha256": gateway_lock["bound_artifacts"][
            "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
        ],
        "alert_policy_id": alert_policy_lock["policy_id"],
        "alert_policy_lock_sha256": hash_file(ROOT / "artifacts/ALERT_POLICY_V1.lock.json"),
        "ecg_hr_context_id": alert_policy_lock["ecg_hr_context_id"],
        "ecg_hr_context_lock_sha256": hash_file(
            ROOT / "artifacts/ECG_HR_CONTEXT_V2.lock.json"
        ),
        "error_semantics": {
            "400": "REQUEST_SCHEMA_ERROR or application-level request-contract error",
            "422": "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW -- MODEL_V1 is never run",
            "500": "INTERNAL_SERVER_ERROR -- safe generic body, never a traceback",
        },
        "response_version": "API_SCHEMA_V1",
        "monitoring_state_vocabulary": alert_policy_lock["monitoring_state_vocabulary"],
        "session_state": "PROCESS_LOCAL_IN_MEMORY_PER_SESSION_ID",
        "framework_versions": {
            "fastapi": "0.138.2",
            "pydantic": "2.13.5",
            "starlette": "1.3.1",
            "uvicorn": "0.49.0",
        },
        "no_dataset_access": True,
        "no_training_access": True,
        "no_simulation_truth_access": True,
        "change_control": (
            "Changing api/app.py, api/schemas.py, api/runtime.py, api/session.py, "
            "contracts/API_SCHEMA_V1.json, or contracts/openapi_v1.json requires a "
            "controlled API_RUNTIME_V2 and invalidates this lock."
        ),
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/API_RUNTIME_V1.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(destination))


if __name__ == "__main__":
    main()
