#!/usr/bin/env python3
"""Verify E2E_REPLAY_SOFTWARE_V1_4 (V2-REL-001 successor): tamper-detect every bound file, confirm
the predecessor V1_3 lock is preserved byte-identical and G21 is never claimed PASS."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_4.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("lock_id") != "E2E_REPLAY_SOFTWARE_V1_4":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_4_LOCK_ID_MISMATCH")
    if lock.get("is_final_g21_lock") is not False:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_4_G21_CLAIM_VIOLATION")
    if hash_file(ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json") != lock[
            "predecessor_sha256"]:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_4_PREDECESSOR_WAS_MUTATED")
    if lock["dashboard_ui_lock_id"] != "DASHBOARD_UI_V1_5":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_4_DASHBOARD_BINDING_MISMATCH")
    for relative, expected in lock["bound_artifacts"].items():
        if hash_file(ROOT / relative) != expected:
            raise RuntimeError(f"E2E_REPLAY_SOFTWARE_V1_4_TAMPER:{relative}")
    return {"status": "PASS", "lock_id": "E2E_REPLAY_SOFTWARE_V1_4",
            "predecessor_id": lock["predecessor_id"], "predecessor_preserved": True,
            "g21_status": lock["g21_status"], "bound_artifacts": len(lock["bound_artifacts"]),
            "lock_sha256": hash_file(lock_path)}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
