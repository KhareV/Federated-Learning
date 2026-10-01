#!/usr/bin/env python3
"""Verify E2E_REPLAY_SOFTWARE_V1_1 (C034 successor): tamper-detect every bound file, confirm
the predecessor E2E_REPLAY_SOFTWARE_V1 lock is preserved byte-identical, confirm the public
semantic digest is unchanged from the predecessor, and confirm G21 is still not claimed PASS."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_1.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    if lock.get("lock_id") != "E2E_REPLAY_SOFTWARE_V1_1":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_1_LOCK_ID_MISMATCH")
    if lock.get("status") != "FROZEN_ENGINEERING_INTEGRATION":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_1_STATUS_MISMATCH")
    if lock.get("is_final_g21_lock") is not False:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_1_G21_CLAIM_VIOLATION")
    if lock.get("g21_status") != "NON_PASS_PENDING_T030_REAL_WEARABLE":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_1_G21_STATUS_MISMATCH")
    if lock.get("public_semantic_digest_unchanged_from_predecessor") is not True:
        raise RuntimeError("C034_RUNTIME_SEMANTIC_DRIFT")

    predecessor_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1.lock.json"
    if not predecessor_path.exists():
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_1_PREDECESSOR_MISSING")
    if hash_file(predecessor_path) != lock["predecessor_sha256"]:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_1_PREDECESSOR_WAS_MUTATED")

    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(ROOT / relative_path) != expected:
            raise RuntimeError(f"E2E_REPLAY_SOFTWARE_V1_1_TAMPER:{relative_path}")

    if lock["dashboard_ui_lock_sha256"] != hash_file(
        ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json"
    ):
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_1_DASHBOARD_LOCK_MISMATCH")
    if lock["api_runtime_v1_lock_sha256"] != hash_file(
        ROOT / "artifacts/API_RUNTIME_V1.lock.json"
    ):
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_1_API_RUNTIME_LOCK_MISMATCH")

    return {
        "status": "PASS",
        "lock_id": "E2E_REPLAY_SOFTWARE_V1_1",
        "predecessor_id": lock["predecessor_id"],
        "predecessor_preserved": True,
        "g21_status": lock["g21_status"],
        "bound_artifacts": len(lock.get("bound_artifacts", {})),
        "lock_sha256": hash_file(lock_path),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
