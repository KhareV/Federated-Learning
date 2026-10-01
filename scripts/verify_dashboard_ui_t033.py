#!/usr/bin/env python3
"""Verify DASHBOARD_UI_V1: tamper-detect every bound file and cross-check against the upstream
API_RUNTIME_V1 lock it reads."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/DASHBOARD_UI_V1.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    if lock.get("lock_id") != "DASHBOARD_UI_V1":
        raise RuntimeError("DASHBOARD_UI_V1_LOCK_ID_MISMATCH")
    if lock.get("status") != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("DASHBOARD_UI_V1_STATUS_MISMATCH")
    if lock.get("repository_path") != "frontend/":
        raise RuntimeError("DASHBOARD_UI_V1_PATH_MAPPING_MISMATCH")

    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(ROOT / relative_path) != expected:
            raise RuntimeError(f"DASHBOARD_UI_V1_TAMPER:{relative_path}")

    api_runtime_lock = json.loads(
        (ROOT / "artifacts/API_RUNTIME_V1.lock.json").read_text(encoding="utf-8")
    )
    if lock["api_runtime_v1_lock_sha256"] != hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json"):
        raise RuntimeError("DASHBOARD_UI_V1_API_RUNTIME_LOCK_MISMATCH")
    if api_runtime_lock.get("status") != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("DASHBOARD_UI_V1_UPSTREAM_API_RUNTIME_STATUS_MISMATCH")

    expected_states = {
        "NORMAL_MONITORED_PATTERN",
        "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
        "RECHECK_SENSOR",
        "CONTEXT_UNAVAILABLE",
        "SYSTEM_ERROR",
    }
    if set(lock.get("monitoring_state_vocabulary", [])) != expected_states:
        raise RuntimeError("DASHBOARD_UI_V1_MONITORING_STATE_VOCABULARY_MISMATCH")

    if (ROOT / "dashboard").is_dir() or (ROOT / "ui").is_dir() or (ROOT / "client").is_dir():
        raise RuntimeError("DASHBOARD_UI_V1_PARALLEL_FRONTEND_DETECTED")

    return {
        "status": "PASS",
        "lock_id": "DASHBOARD_UI_V1",
        "bound_artifacts": len(lock.get("bound_artifacts", {})),
        "lock_sha256": hash_file(lock_path),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
