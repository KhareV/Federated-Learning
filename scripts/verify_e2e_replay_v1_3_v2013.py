#!/usr/bin/env python3
"""Verify E2E_REPLAY_SOFTWARE_V1_3 (V2-013 successor): tamper-detect every bound file, confirm
the predecessor V1_2 lock is preserved byte-identical, and confirm G21 is never claimed PASS."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("lock_id") != "E2E_REPLAY_SOFTWARE_V1_3":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_3_LOCK_ID_MISMATCH")
    if lock.get("is_final_g21_lock") is not False:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_3_G21_CLAIM_VIOLATION")
    if lock.get("run_1_equals_run_2") is not True:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_3_NOT_REPRODUCIBLE")
    predecessor = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_2.lock.json"
    if hash_file(predecessor) != lock["predecessor_sha256"]:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_3_PREDECESSOR_WAS_MUTATED")
    if lock["dashboard_ui_lock_id"] != "DASHBOARD_UI_V1_4":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_3_DASHBOARD_BINDING_MISMATCH")
    for relative, expected in lock["bound_artifacts"].items():
        if hash_file(ROOT / relative) != expected:
            raise RuntimeError(f"E2E_REPLAY_SOFTWARE_V1_3_TAMPER:{relative}")
    return {"status": "PASS", "lock_id": "E2E_REPLAY_SOFTWARE_V1_3",
            "predecessor_id": lock["predecessor_id"], "predecessor_preserved": True,
            "g21_status": lock["g21_status"],
            "bound_artifacts": len(lock["bound_artifacts"]), "lock_sha256": hash_file(lock_path)}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
