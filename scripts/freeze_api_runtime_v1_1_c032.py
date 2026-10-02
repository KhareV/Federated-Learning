#!/usr/bin/env python3
"""Create the API_RUNTIME_V1_1 component lock successor (C032-NORM-RUNTIME).

The frozen API_RUNTIME_V1 lock (predecessor) binds api/runtime.py and api/schemas.py, both
corrected by this checkpoint (restores the locked PREPROC_V1 PER_WINDOW_ZSCORE_V1 normalization
immediately before MODEL_V1/gateway inference; corrects an inaccurate ECGWindow docstring). Per
the C032-NORM-RUNTIME directive, the predecessor lock is NEVER mutated in place -- this is an
ADDITIVE successor. No new canonical freeze registry row is introduced.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_LOCK_PATH = ROOT / "artifacts/API_RUNTIME_V1.lock.json"
PREDECESSOR_ID = "API_RUNTIME_V1"
PREDECESSOR_SHA_EXPECTED = "a6bfedc258977cdf27ecb36e7b326f69800c4897d4cacb09c796b280eebff971"


def main() -> None:
    predecessor_sha = hash_file(PREDECESSOR_LOCK_PATH)
    if predecessor_sha != PREDECESSOR_SHA_EXPECTED:
        raise RuntimeError(
            f"API_RUNTIME_V1_PREDECESSOR_SHA_MISMATCH: expected {PREDECESSOR_SHA_EXPECTED}, "
            f"got {predecessor_sha}"
        )
    predecessor_lock = json.loads(PREDECESSOR_LOCK_PATH.read_text(encoding="utf-8"))

    runtime_equivalence = json.loads(
        (ROOT / "reports/c032_norm_runtime/runtime_equivalence.json").read_text(encoding="utf-8")
    )
    hr_branch_separation = json.loads(
        (ROOT / "reports/c032_norm_runtime/hr_branch_separation.json").read_text(
            encoding="utf-8"
        )
    )
    public_replay_impact = json.loads(
        (ROOT / "reports/c032_norm_runtime/public_replay_impact.json").read_text(
            encoding="utf-8"
        )
    )

    bound_paths = [
        "api/app.py",
        "api/runtime.py",
        "api/schemas.py",
        "api/session.py",
        "artifacts/ALERT_POLICY_V1.lock.json",
        "artifacts/CAL_V1.json",
        "artifacts/ECG_HR_CONTEXT_V2.lock.json",
        "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
        "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts",
        "checkpoints/MODEL_V1.pt",
        "configs/alert_policy_v1.yaml",
        "contracts/API_SCHEMA_V1.json",
        "contracts/openapi_v1.json",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "preprocessing/windowing.py",
        "reports/c032_norm_runtime/defect_reconstruction.json",
        "reports/c032_norm_runtime/normalization_reference.json",
        "reports/c032_norm_runtime/public_replay_impact.json",
        "reports/c032_norm_runtime/public_replay_impact.csv",
        "reports/c032_norm_runtime/downstream_impact_analysis.json",
        "reports/c032_norm_runtime/runtime_equivalence.json",
        "reports/c032_norm_runtime/hr_branch_separation.json",
        "reports/c032_norm_runtime/api_shape_audit.json",
        "reports/c032_norm_runtime/scope_audit.json",
        "reports/c032_norm_runtime/entry_audit.json",
    ]

    lock = {
        "lock_id": "API_RUNTIME_V1_1",
        "status": "FROZEN_ENGINEERING_INTERFACE",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "checkpoint": "C032-NORM-RUNTIME",
        "reason": (
            "restore the locked PREPROC_V1 PER_WINDOW_ZSCORE_V1 normalization immediately "
            "before MODEL_V1/gateway inference in api/runtime.py::ProductionRuntime.infer, "
            "which T032 incorrectly omitted"
        ),
        "normalization_id": "PER_WINDOW_ZSCORE_V1",
        "normalization_owner": "api.runtime.ProductionRuntime.infer",
        "normalization_helper": "preprocessing.windowing.normalize_window_zscore",
        "normalization_epsilon": 1e-8,
        "hr_branch_receives_normalized_input": False,
        "hr_branch_separation_evidence_sha256": hash_file(
            ROOT / "reports/c032_norm_runtime/hr_branch_separation.json"
        ),
        "hr_branch_separation_status": hr_branch_separation["status"],
        "runtime_equivalence_evidence_sha256": hash_file(
            ROOT / "reports/c032_norm_runtime/runtime_equivalence.json"
        ),
        "runtime_equivalence_decision_agreement_fraction": runtime_equivalence[
            "decision_agreement_fraction"
        ],
        "runtime_equivalence_rows_compared": runtime_equivalence["rows_compared"],
        "public_replay_impact_evidence_sha256": hash_file(
            ROOT / "reports/c032_norm_runtime/public_replay_impact.json"
        ),
        "public_replay_windows_with_decision_change": public_replay_impact[
            "windows_with_decision_change"
        ],
        "model_id": predecessor_lock["model_id"],
        "model_checkpoint_sha256": predecessor_lock["model_checkpoint_sha256"],
        "preproc_id": predecessor_lock["preproc_id"],
        "calibration_id": predecessor_lock["calibration_id"],
        "calibration_domain": predecessor_lock["calibration_domain"],
        "calibration_patient_count": predecessor_lock["calibration_patient_count"],
        "gateway_artifact_id": predecessor_lock["gateway_artifact_id"],
        "gateway_artifact_lock_sha256": hash_file(
            ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
        ),
        "deployment_artifact_sha256": predecessor_lock["deployment_artifact_sha256"],
        "alert_policy_id": predecessor_lock["alert_policy_id"],
        "alert_policy_lock_sha256": hash_file(ROOT / "artifacts/ALERT_POLICY_V1.lock.json"),
        "ecg_hr_context_id": predecessor_lock["ecg_hr_context_id"],
        "ecg_hr_context_lock_sha256": hash_file(
            ROOT / "artifacts/ECG_HR_CONTEXT_V2.lock.json"
        ),
        "error_semantics": predecessor_lock["error_semantics"],
        "response_version": predecessor_lock["response_version"],
        "monitoring_state_vocabulary": predecessor_lock["monitoring_state_vocabulary"],
        "session_state": predecessor_lock["session_state"],
        "route": predecessor_lock["route"],
        "contract_version": predecessor_lock["contract_version"],
        "target_id": predecessor_lock["target_id"],
        "api_contract_byte_identical_to_predecessor": True,
        "api_schema_v1_sha256": hash_file(ROOT / "contracts/API_SCHEMA_V1.json"),
        "no_dataset_access": True,
        "no_training_access": True,
        "no_simulation_truth_access": True,
        "no_new_canonical_freeze_registry_row": True,
        "change_control": (
            "Changing api/app.py, api/schemas.py, api/runtime.py, api/session.py, "
            "contracts/API_SCHEMA_V1.json, or the PER_WINDOW_ZSCORE_V1 normalization call "
            "site requires a further controlled successor and invalidates this lock."
        ),
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/API_RUNTIME_V1_1.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    supersedes = {
        "successor_id": "API_RUNTIME_V1_1",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "predecessor_status_at_supersession": predecessor_lock["status"],
        "predecessor_preserved_unchanged": True,
        "reason": lock["reason"],
        "checkpoint": "C032-NORM-RUNTIME",
        "defect_class": "NORMALIZATION_OMITTED_AT_PRODUCTION_RUNTIME_BOUNDARY",
    }
    supersedes_path = ROOT / "artifacts/API_RUNTIME_V1_1.supersedes.json"
    supersedes_path.write_text(
        json.dumps(supersedes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(hash_file(destination))
    print(hash_file(supersedes_path))


if __name__ == "__main__":
    main()
