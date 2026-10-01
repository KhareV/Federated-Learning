#!/usr/bin/env python3
"""Verify E2E_REPLAY_SOFTWARE_V1: tamper-detect every bound file and cross-check against the
upstream API_RUNTIME_V1/GATEWAY_ARTIFACT_V1/DASHBOARD_UI_V1 locks it reads."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    if lock.get("lock_id") != "E2E_REPLAY_SOFTWARE_V1":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_LOCK_ID_MISMATCH")
    if lock.get("status") != "FROZEN_ENGINEERING_INTEGRATION":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_STATUS_MISMATCH")
    if lock.get("is_final_g21_lock") is not False:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_G21_CLAIM_VIOLATION")
    if lock.get("g21_status") != "NON_PASS_PENDING_T030_REAL_WEARABLE":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_G21_STATUS_MISMATCH")

    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(ROOT / relative_path) != expected:
            raise RuntimeError(f"E2E_REPLAY_SOFTWARE_V1_TAMPER:{relative_path}")

    if lock["api_runtime_v1_lock_sha256"] != hash_file(
        ROOT / "artifacts/API_RUNTIME_V1.lock.json"
    ):
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_API_RUNTIME_LOCK_MISMATCH")
    if lock["gateway_artifact_v1_lock_sha256"] != hash_file(
        ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
    ):
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_GATEWAY_LOCK_MISMATCH")
    if lock["dashboard_ui_v1_lock_sha256"] != hash_file(
        ROOT / "artifacts/DASHBOARD_UI_V1.lock.json"
    ):
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_DASHBOARD_LOCK_MISMATCH")

    if lock["reproducibility_status"] != "PASS":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_REPRODUCIBILITY_NOT_PASS")

    return {
        "status": "PASS",
        "lock_id": "E2E_REPLAY_SOFTWARE_V1",
        "bound_artifacts": len(lock.get("bound_artifacts", {})),
        "g21_status": lock["g21_status"],
        "lock_sha256": hash_file(lock_path),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
