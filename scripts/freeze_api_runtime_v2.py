#!/usr/bin/env python3
"""V2-013 result-phase freeze: create the ALERT_POLICY_V1_MODEL_V2_BINDING lock and the
API_RUNTIME_V2 lock (FROZEN_RESEARCH_RUNTIME). Run strictly AFTER every canonical V2-013
evidence file exists; refuses to freeze if any required result is not PASS."""

from __future__ import annotations

import json
import sys

from fusion.alert_policy_v2_binding import binding_payload
from nhm.hashing import hash_file
from scripts._v2_013_lib import ROOT

EVIDENCE = ROOT / "reports/model_v2/v2_013"
BINDING_LOCK = ROOT / "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json"
RUNTIME_LOCK = ROOT / "artifacts/API_RUNTIME_V2.lock.json"

BINDING_BOUND = [
    "fusion/alert_policy_v2_binding.py", "configs/alert_policy_v1.yaml",
    "artifacts/ALERT_POLICY_V1.lock.json", "fusion/episode_manager.py",
    "fusion/state_machine.py", "artifacts/CAL_V2.json",
    "reports/model_v2/v2_013/alert_policy_binding_audit.json",
    "reports/model_v2/v2_013/state_sequence_audit.json",
]
RUNTIME_BOUND = [
    "api/app_v2.py", "api/runtime_v2.py", "deployment/gateway_v2.py",
    "simulation/stream_runtime_v2013.py", "simulation/profile_v2013.py",
    "simulation/truth_v2013.py", "configs/model_v2/api_runtime_v2.yaml",
    "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json",
    "artifacts/DASHBOARD_UI_V1_4.lock.json", "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json",
    "artifacts/CAL_V2.json", "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
    "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts", "checkpoints/MODEL_V2_FINAL.pt",
    "contracts/API_SCHEMA_V1.json", "manifests/preprocessing/PREPROC_V1.lock.json",
    "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json",
    "tests/fixtures/e2e/WEARABLE_SIM_V2_REPLAY_V1.manifest.json",
    "scripts/run_research_v2_demo.py",
    *(f"reports/model_v2/v2_013/{n}.json" for n in (
        "api_runtime_equivalence", "api_schema_compatibility", "alert_policy_binding_audit",
        "state_sequence_audit", "v1_default_regression", "runtime_isolation_audit",
        "truth_isolation_audit", "normalization_branch_audit", "runtime_binding_manifest",
        "replay_semantic_digest", "replay_mode_invariance", "frontend_e2e_evidence",
        "demo_report", "simulator_maturity_audit", "simulation_session_manifest")),
]
REQUIRED_PASS = ("api_runtime_equivalence", "api_schema_compatibility",
                 "alert_policy_binding_audit", "state_sequence_audit", "v1_default_regression",
                 "runtime_isolation_audit", "truth_isolation_audit", "normalization_branch_audit",
                 "replay_semantic_digest", "replay_mode_invariance", "frontend_e2e_evidence")


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / f"{name}.json").read_text(encoding="utf-8"))


def main() -> None:
    not_pass = [n for n in REQUIRED_PASS if _load(n).get("status") != "PASS"]
    if not_pass:
        sys.exit(f"V2_013_FREEZE_REFUSED_NOT_PASS:{not_pass}")
    payload = binding_payload(ROOT)
    binding = {
        "lock_id": "ALERT_POLICY_V1_MODEL_V2_BINDING", "status": "FROZEN_RESEARCH_BINDING",
        "owner_task": "V2-013", "policy_id": "ALERT_POLICY_V1", "policy_changed": False,
        "new_clinical_policy": False, "binding": payload,
        "change_control": "Changing the binding module, ALERT_POLICY_V1, CAL_V2 or the episode "
        "engine requires a controlled successor and invalidates this lock.",
        "bound_artifacts": {p: hash_file(ROOT / p) for p in BINDING_BOUND},
    }
    BINDING_LOCK.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    digest = _load("replay_semantic_digest")
    runtime = {
        "lock_id": "API_RUNTIME_V2", "status": "FROZEN_RESEARCH_RUNTIME", "owner_task": "V2-013",
        "gate": "V2G12", "runtime_id": "API_RUNTIME_V2", "bound_model_id": "MODEL_V2_FINAL",
        "gateway_artifact_id": "GATEWAY_ARTIFACT_V2", "calibration_id": "CAL_V2",
        "preprocess_id": "PREPROC_V1", "alert_policy_id": "ALERT_POLICY_V1",
        "alert_policy_binding_id": "ALERT_POLICY_V1_MODEL_V2_BINDING",
        "alert_policy_binding_lock_sha256": hash_file(BINDING_LOCK),
        "api_contract_version": "API_SCHEMA_V1", "api_contract_changed": False,
        "operational_default": "MODEL_V1", "operational_default_changed": False,
        "public_runtime_model_selector": False,
        "launch": "uvicorn --factory api.app_v2:create_default_research_app",
        "demo_command": "python -m scripts.run_research_v2_demo",
        "wearable_sim_to_v2_software_path": "VERIFIED_ENGINEERING_INTEGRATION",
        "software_replay": {
            "replay_id": "WEARABLE_SIM_V2_REPLAY_V1", "status": "FROZEN_COMPLETE",
            "window_count": digest["window_count"],
            "semantic_digest_sha256": digest["digests"]["run_1_frontend_path"],
            "runs_identical": digest["all_four_identical"],
            "live_speed_equals_accelerated": _load("replay_mode_invariance")[
                "semantic_outputs_identical"],
        },
        "claim_boundary": (
            "engineering evidence from a simulated wearable (virtual participants, not humans); "
            "no clinical accuracy, no real-wearable sensitivity/specificity, no new "
            "AUPRC/AUROC/F1 claim; research runtime, V1 remains the operational default"
        ),
        "neural_fits_in_this_phase": 0,
        "protected_partitions_accessed": [],
        "change_control": "Changing any bound file requires a controlled successor lock and "
        "invalidates this lock.",
        "bound_artifacts": {p: hash_file(ROOT / p) for p in RUNTIME_BOUND},
    }
    RUNTIME_LOCK.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(hash_file(BINDING_LOCK))
    print(hash_file(RUNTIME_LOCK))


if __name__ == "__main__":
    main()
