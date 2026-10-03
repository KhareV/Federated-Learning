#!/usr/bin/env python3
"""Verify the V2-013 locks: ALERT_POLICY_V1_MODEL_V2_BINDING and API_RUNTIME_V2. Tamper-detects
every bound file, re-verifies the frozen V2 upstreams, and confirms the V1 default and the API
contract are claimed unchanged."""

from __future__ import annotations

import json

from nhm.hashing import hash_file
from scripts._v2_013_lib import ROOT


def _check_bound(lock: dict, tag: str) -> None:
    for relative, expected in lock["bound_artifacts"].items():
        if hash_file(ROOT / relative) != expected:
            raise RuntimeError(f"{tag}_TAMPER:{relative}")


def verify_alert_binding() -> dict[str, object]:
    path = ROOT / "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json"
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock["lock_id"] != "ALERT_POLICY_V1_MODEL_V2_BINDING":
        raise RuntimeError("ALERT_BINDING_LOCK_ID_MISMATCH")
    if lock["policy_changed"] is not False or lock["new_clinical_policy"] is not False:
        raise RuntimeError("ALERT_BINDING_POLICY_CLAIM_VIOLATION")
    _check_bound(lock, "ALERT_BINDING")
    from fusion.alert_policy_v2_binding import binding_payload

    if binding_payload(ROOT) != lock["binding"]:
        raise RuntimeError("ALERT_BINDING_PAYLOAD_DRIFT")
    return {"status": "PASS", "lock_sha256": hash_file(path),
            "bound_artifacts": len(lock["bound_artifacts"])}


def verify() -> dict[str, object]:
    path = ROOT / "artifacts/API_RUNTIME_V2.lock.json"
    lock = json.loads(path.read_text(encoding="utf-8"))
    expected = {"lock_id": "API_RUNTIME_V2", "status": "FROZEN_RESEARCH_RUNTIME",
                "bound_model_id": "MODEL_V2_FINAL", "calibration_id": "CAL_V2",
                "operational_default": "MODEL_V1", "api_contract_version": "API_SCHEMA_V1"}
    for key, value in expected.items():
        if lock.get(key) != value:
            raise RuntimeError(f"API_RUNTIME_V2_FIELD_MISMATCH:{key}")
    for flag in ("operational_default_changed", "public_runtime_model_selector",
                 "api_contract_changed"):
        if lock[flag] is not False:
            raise RuntimeError(f"API_RUNTIME_V2_CLAIM_VIOLATION:{flag}")
    if lock["neural_fits_in_this_phase"] != 0 or lock["protected_partitions_accessed"]:
        raise RuntimeError("API_RUNTIME_V2_SCIENTIFIC_FIREWALL_VIOLATION")
    if hash_file(ROOT / "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json") != lock[
            "alert_policy_binding_lock_sha256"]:
        raise RuntimeError("API_RUNTIME_V2_BINDING_LOCK_DRIFT")
    _check_bound(lock, "API_RUNTIME_V2")
    from models.cal_v2_verify import verify_cal_v2
    from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2

    verify_cal_v2(ROOT)
    verify_gateway_artifact_v2(ROOT)
    for forbidden in ("dashboard", "ui", "web", "frontend-v2"):
        if (ROOT / forbidden).is_dir():
            raise RuntimeError("API_RUNTIME_V2_PARALLEL_FRONTEND_DETECTED")
    return {"status": "PASS", "lock_id": "API_RUNTIME_V2", "lock_sha256": hash_file(path),
            "bound_artifacts": len(lock["bound_artifacts"]),
            "alert_binding": verify_alert_binding()}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
