#!/usr/bin/env python3
"""Verify API_RUNTIME_V1: tamper-detect every bound file and cross-check identifiers against
the upstream frozen artifacts (CAL_V1, ALERT_POLICY_V1, GATEWAY_ARTIFACT_V1) it reads."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/API_RUNTIME_V1.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    if lock.get("lock_id") != "API_RUNTIME_V1":
        raise RuntimeError("API_RUNTIME_V1_LOCK_ID_MISMATCH")
    if lock.get("status") != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("API_RUNTIME_V1_STATUS_MISMATCH")

    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(ROOT / relative_path) != expected:
            raise RuntimeError(f"API_RUNTIME_V1_TAMPER:{relative_path}")

    cal = json.loads((ROOT / "artifacts/CAL_V1.json").read_text(encoding="utf-8"))
    if lock["model_id"] != cal["model_id"] or lock["calibration_id"] != cal["calibration_id"]:
        raise RuntimeError("API_RUNTIME_V1_CALIBRATION_IDENTITY_MISMATCH")
    if lock["calibration_patient_count"] != cal["calibration_patient_count"]:
        raise RuntimeError("API_RUNTIME_V1_CALIBRATION_PATIENT_COUNT_MISMATCH")

    alert_policy_lock = json.loads(
        (ROOT / "artifacts/ALERT_POLICY_V1.lock.json").read_text(encoding="utf-8")
    )
    if lock["alert_policy_id"] != alert_policy_lock["policy_id"]:
        raise RuntimeError("API_RUNTIME_V1_ALERT_POLICY_IDENTITY_MISMATCH")
    if lock["monitoring_state_vocabulary"] != alert_policy_lock["monitoring_state_vocabulary"]:
        raise RuntimeError("API_RUNTIME_V1_MONITORING_STATE_VOCABULARY_MISMATCH")

    gateway_lock = json.loads(
        (ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json").read_text(encoding="utf-8")
    )
    if gateway_lock.get("freeze_id") != "F14" or gateway_lock.get("status") != "FROZEN":
        raise RuntimeError("API_RUNTIME_V1_UPSTREAM_F14_MISMATCH")

    return {
        "status": "PASS",
        "lock_id": "API_RUNTIME_V1",
        "bound_artifacts": len(lock.get("bound_artifacts", {})),
        "lock_sha256": hash_file(lock_path),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
