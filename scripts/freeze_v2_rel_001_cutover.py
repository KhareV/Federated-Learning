#!/usr/bin/env python3
# ruff: noqa: E501
"""V2-REL-001 CUTOVER freeze (runs only after the frozen ACCEPT decision): creates the additive
DASHBOARD_UI_V1_5 / E2E_REPLAY_SOFTWARE_V1_4 successors, the rollback and default runtime binding
locks, SOFTWARE_SYSTEM_V2 and the release manifest. No predecessor lock is ever mutated."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
PAGE = "frontend/src/routes/monitoring/+page.svelte"
CHANGED_UI = [PAGE, "frontend/src/routes/+page.svelte", "frontend/src/routes/monitor/+page.svelte",
              "frontend/src/lib/components/landing/SystemArchitecture.svelte",
              "frontend/src/lib/components/hardware/HardwareStudio.svelte"]


def _w(path: Path, data: dict[str, Any]) -> str:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return hash_file(path)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def dashboard_v15() -> None:
    pred_path = ART / "DASHBOARD_UI_V1_4.lock.json"
    pred = json.loads(pred_path.read_text())
    carried = {k: v for k, v in pred.items() if k not in {
        "lock_id", "predecessor_id", "predecessor_sha256", "checkpoint", "reason", "bound_artifacts",
        "default_request_model_id", "frontend_application_sources_changed"}}
    bound = {p: hash_file(ROOT / p) for p in pred["bound_artifacts"]}
    for extra in CHANGED_UI:
        bound.setdefault(extra, hash_file(ROOT / extra))
    reason = ("V2-REL-001 cutover: the normal build requests MODEL_V2_FINAL (default research "
              "runtime) instead of MODEL_V1; the default replay is WEARABLE_SIM_V2_REPLAY_V1; public "
              "copy that referenced MODEL_V1/API_RUNTIME_V1 or overstated privacy/on-device "
              "capability is corrected. Build-time value, not a runtime selector.")
    lock = {**carried, "lock_id": "DASHBOARD_UI_V1_5", "predecessor_id": "DASHBOARD_UI_V1_4",
            "predecessor_sha256": hash_file(pred_path), "checkpoint": "V2-REL-001",
            "status": "FROZEN_ENGINEERING_INTERFACE", "reason": reason,
            "default_request_model_id": "MODEL_V2_FINAL",
            "rollback_request_model_id_build_value": "MODEL_V1",
            "default_replay_id": "WEARABLE_SIM_V2_REPLAY_V1",
            "api_runtime_lock_id": "API_RUNTIME_V2_1", "api_runtime_lock_sha256": hash_file(
                ART / "API_RUNTIME_V2_1.lock.json"),
            "frontend_application_sources_changed": CHANGED_UI,
            "scientific_state_semantics_changed": False, "api_contract_changed": False,
            "public_runtime_model_selector_added": False,
            "public_copy_claims_corrected": True, "bound_artifacts": bound}
    sha = _w(ART / "DASHBOARD_UI_V1_5.lock.json", lock)
    _w(ART / "DASHBOARD_UI_V1_5.supersedes.json", {
        "successor_id": "DASHBOARD_UI_V1_5", "predecessor_id": "DASHBOARD_UI_V1_4",
        "predecessor_sha256": lock["predecessor_sha256"],
        "predecessor_status_at_supersession": pred["status"],
        "predecessor_preserved_unchanged": True, "reason": reason, "checkpoint": "V2-REL-001"})
    print("DASHBOARD_UI_V1_5", sha)


def e2e_v14() -> None:
    pred_path = ART / "E2E_REPLAY_SOFTWARE_V1_3.lock.json"
    pred = json.loads(pred_path.read_text())
    bound = ["artifacts/DASHBOARD_UI_V1_5.lock.json" if p == "artifacts/DASHBOARD_UI_V1_4.lock.json"
             else p for p in pred["bound_artifacts"]]
    dropped = {"lock_id", "predecessor_id", "predecessor_sha256", "checkpoint", "reason",
               "bound_artifacts", "dashboard_ui_lock_id", "dashboard_ui_lock_sha256",
               "canonical_monitoring_route_sha256"}
    reason = ("re-bind the dashboard route and DASHBOARD_UI_V1_5 after the V2-REL-001 default "
              "model-identity change; V1_3 replay digests and reproducibility facts are carried "
              "forward unchanged (the recorded MODEL_V1 replay is reproduced via the explicit "
              "rollback profile)")
    lock = {**{k: v for k, v in pred.items() if k not in dropped},
            "lock_id": "E2E_REPLAY_SOFTWARE_V1_4", "predecessor_id": "E2E_REPLAY_SOFTWARE_V1_3",
            "predecessor_sha256": hash_file(pred_path), "checkpoint": "V2-REL-001",
            "reason": reason, "dashboard_ui_lock_id": "DASHBOARD_UI_V1_5",
            "dashboard_ui_lock_sha256": hash_file(ART / "DASHBOARD_UI_V1_5.lock.json"),
            "canonical_monitoring_route_sha256": hash_file(ROOT / PAGE),
            "bound_artifacts": {p: hash_file(ROOT / p) for p in bound}}
    sha = _w(ART / "E2E_REPLAY_SOFTWARE_V1_4.lock.json", lock)
    _w(ART / "E2E_REPLAY_SOFTWARE_V1_4.supersedes.json", {
        "successor_id": "E2E_REPLAY_SOFTWARE_V1_4", "predecessor_id": "E2E_REPLAY_SOFTWARE_V1_3",
        "predecessor_sha256": lock["predecessor_sha256"],
        "predecessor_status_at_supersession": pred["status"],
        "predecessor_preserved_unchanged": True, "reason": reason, "checkpoint": "V2-REL-001"})
    print("E2E_REPLAY_SOFTWARE_V1_4", sha)


COMMON = ["contracts/API_SCHEMA_V1.json", "contracts/openapi_v1.json", "api/schemas.py",
          "api/session.py", "api/runtime.py", "api/app_default.py", "manifests/preprocessing/PREPROC_V1.lock.json"]


def rollback_lock() -> None:
    cal = json.loads((ROOT / "artifacts/CAL_V1.json").read_text())
    gateway = "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
    files = [*COMMON, "api/app.py", "checkpoints/MODEL_V1.pt", "checkpoints/MODEL_V1.manifest.json",
             "artifacts/CAL_V1.json", gateway, "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
             "artifacts/ALERT_POLICY_V1.lock.json", "artifacts/ECG_HR_CONTEXT_V2.lock.json",
             "artifacts/API_RUNTIME_V1_1.lock.json"]
    lock = {"lock_id": "ROLLBACK_RUNTIME_BINDING_V1", "status": "FROZEN_ROLLBACK_REFERENCE",
            "owner_task": "V2-REL-001", "profile": "rollback-v1",
            "launch": "python -m scripts.run_nhm_default --profile rollback-v1 "
            "(== uvicorn --factory api.app_default:create_rollback_v1_app)",
            "public_model_selector": False, "operator_only": True,
            "identity": {"model_id": "MODEL_V1", "gateway_artifact_id": "GATEWAY_ARTIFACT_V1",
                         "calibration_id": "CAL_V1", "alert_policy_binding_id": "ALERT_POLICY_V1",
                         "alert_policy_id": "ALERT_POLICY_V1", "preprocess_id": "PREPROC_V1",
                         "api_contract_version": "API_SCHEMA_V1"},
            "identity_values": {"gateway_artifact_sha256": hash_file(ROOT / gateway),
                                "cal_v1_threshold": cal.get("threshold")},
            "bound_artifacts": {p: hash_file(ROOT / p) for p in files}}
    print("ROLLBACK_RUNTIME_BINDING_V1", _w(ART / "ROLLBACK_RUNTIME_BINDING_V1.lock.json", lock))


def default_lock() -> None:
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    gateway = "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts"
    files = [*COMMON, "api/app_v2.py", "api/runtime_v2.py", "checkpoints/MODEL_V2_FINAL.pt",
             "checkpoints/MODEL_V2_FINAL.manifest.json", "configs/model_v2_final_frozen.yaml",
             gateway, "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
             "artifacts/CAL_V2.json", "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json",
             "artifacts/ALERT_POLICY_V1.lock.json", "artifacts/ECG_HR_CONTEXT_V2.lock.json",
             "artifacts/API_RUNTIME_V2_1.lock.json", "artifacts/DASHBOARD_UI_V1_5.lock.json",
             "artifacts/E2E_REPLAY_SOFTWARE_V1_4.lock.json",
             "artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json",
             "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json",
             "artifacts/ROLLBACK_RUNTIME_BINDING_V1.lock.json", PAGE]
    lock = {"lock_id": "DEFAULT_RUNTIME_BINDING_V2", "status": "FROZEN_OPERATIONAL_RESEARCH_BINDING",
            "owner_task": "V2-REL-001", "profile": "default",
            "launch": "python -m scripts.run_nhm_default (== uvicorn --factory "
            "api.app_default:create_default_app)",
            "public_model_selector": False, "api_schema_changed": False,
            "federated_checkpoint_deployed": False,
            "frontend_default_identity": {"lock": "DASHBOARD_UI_V1_5",
                                          "default_request_model_id": "MODEL_V2_FINAL"},
            "rollback_binding": "ROLLBACK_RUNTIME_BINDING_V1",
            "identity": {"model_id": "MODEL_V2_FINAL", "gateway_artifact_id": "GATEWAY_ARTIFACT_V2",
                         "calibration_id": "CAL_V2",
                         "alert_policy_binding_id": "ALERT_POLICY_V1_MODEL_V2_BINDING",
                         "alert_policy_id": "ALERT_POLICY_V1", "preprocess_id": "PREPROC_V1",
                         "api_contract_version": "API_SCHEMA_V1"},
            "identity_values": {"gateway_artifact_sha256": hash_file(ROOT / gateway),
                                "threshold": cal["threshold"], "temperature": cal["temperature"],
                                "checkpoint_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
                                "calibration_domain": cal["calibration_domain"]},
            "bound_artifacts": {p: hash_file(ROOT / p) for p in files}}
    print("DEFAULT_RUNTIME_BINDING_V2", _w(ART / "DEFAULT_RUNTIME_BINDING_V2.lock.json", lock))


def system_lock() -> None:
    comps = ["artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
             "artifacts/ROLLBACK_RUNTIME_BINDING_V1.lock.json", "artifacts/CAL_V2.json",
             "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
             "checkpoints/MODEL_V2_FINAL.manifest.json", "manifests/preprocessing/PREPROC_V1.lock.json",
             "artifacts/ECG_HR_CONTEXT_V2.lock.json",
             "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json", "contracts/API_SCHEMA_V1.json",
             "artifacts/DASHBOARD_UI_V1_5.lock.json", "artifacts/E2E_REPLAY_SOFTWARE_V1_4.lock.json",
             "artifacts/API_RUNTIME_V2_1.lock.json", "artifacts/SECAGG_METHOD_V2.lock.json",
             "configs/model_v2/secagg_v2.yaml", "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V1.lock.json",
             "manifests/model_v2/MODEL_V2_FL_PROTOCOL_V2.lock.json",
             "manifests/model_v2/V2_FL_EVAL_PROTOCOL_V1.lock.json",
             "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json",
             "manifests/model_v2/WEARABLE_SIM_FL_COHORT_V1.json",
             "artifacts/MODEL_V2_COMPLETE_REPRO_V1.lock.json",
             "artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json",
             "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json"]
    lock = {"lock_id": "SOFTWARE_SYSTEM_V2", "status": "FROZEN_RESEARCH_SOFTWARE_DEFAULT",
            "owner_task": "V2-REL-001", "release_level": "RESEARCH_SOFTWARE_OPERATIONAL_DEFAULT",
            "default": {"model": "MODEL_V2_FINAL", "gateway": "GATEWAY_ARTIFACT_V2",
                        "calibration": "CAL_V2", "api": "API_SCHEMA_V1",
                        "runtime_binding": "DEFAULT_RUNTIME_BINDING_V2"},
            "rollback": {"model": "MODEL_V1", "runtime": "API_RUNTIME_V1_1",
                         "binding": "ROLLBACK_RUNTIME_BINDING_V1",
                         "role": "FROZEN_ROLLBACK_REFERENCE"},
            "quality_v1": "unchanged (known stuck-nonzero limitation carried)",
            "fl_research_lineage_ids": ["FL_INIT_V2", "FL_IID_MODEL_V2_V1", "FL_NON_IID_MODEL_V2_V1",
                                        "FEDPROX_METHOD_V2", "FEDPROX_MU_V2",
                                        "V2_FL_EVAL_PROTOCOL_V1"],
            "wearable_sim_ids": ["WEARABLE_SIM_FL_COHORT_V1", "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1",
                                 "WEARABLE_SIM_FL_SYSTEM_REPLAY_V1", "VIRTUAL_FL_CLIENT_SOURCE_V1",
                                 "WEARABLE_SIM_FL_SECAGG_COMPAT_V1"],
            "historical_model_promotion_disposition": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
            "new_system_release_disposition": "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED",
            "federated_checkpoint_deployed": False, "hardware": "OUT_OF_SCOPE (T036 not started)",
            "bound_artifacts": {p: hash_file(ROOT / p) for p in comps}}
    print("SOFTWARE_SYSTEM_V2", _w(ART / "SOFTWARE_SYSTEM_V2.lock.json", lock))


def release_manifest() -> None:
    log = _git("log", "--format=%H %s", "-12").splitlines()
    find = lambda needle: next((x.split()[0] for x in log if needle in x), None)  # noqa: E731
    manifest = {
        "manifest_id": "SYSTEM_V2_RELEASE_MANIFEST_V1", "release_level":
        "RESEARCH_SOFTWARE_OPERATIONAL_DEFAULT", "operational_default": "SOFTWARE_SYSTEM_V2 (MODEL_V2_FINAL)",
        "rollback_default": "MODEL_V1 / API_RUNTIME_V1_1 (explicit operator profile)",
        "policy_commit": find("SYSTEM_V2_RELEASE_POLICY_V1 + V2RELG0"),
        "decision_commit": find("SYSTEM_V2_RELEASE_DECISION_V1 = ACCEPT"),
        "release_commit": "recorded by reports/model_v2/v2_rel_001/final/release_commit.json "
        "(the cutover result commit cannot contain its own hash)",
        "hashes": {n: hash_file(ART / n) for n in (
            "SYSTEM_V2_RELEASE_POLICY_V1.lock.json", "SYSTEM_V2_RELEASE_DECISION_V1.lock.json",
            "SOFTWARE_SYSTEM_V2.lock.json", "DEFAULT_RUNTIME_BINDING_V2.lock.json",
            "ROLLBACK_RUNTIME_BINDING_V1.lock.json", "DASHBOARD_UI_V1_5.lock.json",
            "MODEL_V2_COMPLETE_REPRO_V1.lock.json", "SECAGG_METHOD_V2.lock.json",
            "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "CAL_V2.json")},
        "model_checkpoint_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
        "gateway_sha256": hash_file(ROOT / "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts"),
        "api_schema_sha256": hash_file(ROOT / "contracts/API_SCHEMA_V1.json"),
        "known_limitations": [x["text"] for x in __import__("yaml").safe_load(
            (ROOT / "configs/model_v2/system_v2_release_policy_v1.yaml").read_text())[
            "non_blocking_known_limitations"]],
        "unsupported_claims": ["clinical diagnosis", "hospital deployment", "hardware deployment",
                               "differential privacy", "real wearable validation",
                               "federated-trained default checkpoint", "system privacy guarantee",
                               "scientific promotion of MODEL_V2 (MODEL_V2_NOT_PROMOTED_RELEASE_CI stands)"],
        "federated_checkpoint_deployed": False, "T036": "NOT_STARTED"}
    path = ROOT / "reports/model_v2/v2_rel_001/system_v2_release_manifest.json"
    print("SYSTEM_V2_RELEASE_MANIFEST_V1", _w(path, manifest))


def main() -> None:
    dashboard_v15()
    e2e_v14()
    rollback_lock()
    default_lock()
    system_lock()
    release_manifest()


if __name__ == "__main__":
    main()
