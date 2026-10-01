#!/usr/bin/env python3
"""Verify DASHBOARD_UI_V1_1 (C034 successor): tamper-detect every bound file, cross-check the
predecessor DASHBOARD_UI_V1 lock is preserved byte-identical, and confirm no scientific
state/wording/contract change is claimed."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    if lock.get("lock_id") != "DASHBOARD_UI_V1_1":
        raise RuntimeError("DASHBOARD_UI_V1_1_LOCK_ID_MISMATCH")
    if lock.get("status") != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("DASHBOARD_UI_V1_1_STATUS_MISMATCH")
    if lock.get("repository_path") != "frontend/":
        raise RuntimeError("DASHBOARD_UI_V1_1_PATH_MAPPING_MISMATCH")
    if lock.get("scientific_state_semantics_changed") is not False:
        raise RuntimeError("DASHBOARD_UI_V1_1_SCIENCE_CLAIM_VIOLATION")
    if lock.get("state_wording_changed") is not False:
        raise RuntimeError("DASHBOARD_UI_V1_1_WORDING_CLAIM_VIOLATION")
    if lock.get("api_contract_changed") is not False:
        raise RuntimeError("DASHBOARD_UI_V1_1_CONTRACT_CLAIM_VIOLATION")

    predecessor_path = ROOT / "artifacts/DASHBOARD_UI_V1.lock.json"
    if not predecessor_path.exists():
        raise RuntimeError("DASHBOARD_UI_V1_1_PREDECESSOR_MISSING")
    if hash_file(predecessor_path) != lock["predecessor_sha256"]:
        raise RuntimeError("DASHBOARD_UI_V1_1_PREDECESSOR_WAS_MUTATED")

    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(ROOT / relative_path) != expected:
            raise RuntimeError(f"DASHBOARD_UI_V1_1_TAMPER:{relative_path}")

    api_runtime_lock = json.loads(
        (ROOT / "artifacts/API_RUNTIME_V1.lock.json").read_text(encoding="utf-8")
    )
    if lock["api_runtime_v1_lock_sha256"] != hash_file(
        ROOT / "artifacts/API_RUNTIME_V1.lock.json"
    ):
        raise RuntimeError("DASHBOARD_UI_V1_1_API_RUNTIME_LOCK_MISMATCH")
    if api_runtime_lock.get("status") != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("DASHBOARD_UI_V1_1_UPSTREAM_API_RUNTIME_STATUS_MISMATCH")

    expected_states = {
        "NORMAL_MONITORED_PATTERN",
        "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
        "RECHECK_SENSOR",
        "CONTEXT_UNAVAILABLE",
        "SYSTEM_ERROR",
    }
    if set(lock.get("monitoring_state_vocabulary", [])) != expected_states:
        raise RuntimeError("DASHBOARD_UI_V1_1_MONITORING_STATE_VOCABULARY_MISMATCH")

    if (ROOT / "dashboard").is_dir() or (ROOT / "ui").is_dir() or (ROOT / "client").is_dir():
        raise RuntimeError("DASHBOARD_UI_V1_1_PARALLEL_FRONTEND_DETECTED")

    return {
        "status": "PASS",
        "lock_id": "DASHBOARD_UI_V1_1",
        "predecessor_id": lock["predecessor_id"],
        "predecessor_preserved": True,
        "bound_artifacts": len(lock.get("bound_artifacts", {})),
        "lock_sha256": hash_file(lock_path),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
