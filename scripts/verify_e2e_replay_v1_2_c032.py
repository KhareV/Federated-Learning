#!/usr/bin/env python3
"""Verify E2E_REPLAY_SOFTWARE_V1_2 (C032-NORM-RUNTIME successor): tamper-detect every bound
file, cross-check the predecessor E2E_REPLAY_SOFTWARE_V1_1 lock is preserved byte-identical,
confirm reproducibility (run1==run2), and confirm G21 is never claimed PASS."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_2.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    if lock.get("lock_id") != "E2E_REPLAY_SOFTWARE_V1_2":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_LOCK_ID_MISMATCH")
    if lock.get("status") != "FROZEN_ENGINEERING_INTEGRATION":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_STATUS_MISMATCH")
    if lock.get("is_final_g21_lock") is not False:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_G21_CLAIM_VIOLATION")
    if lock.get("g21_status") != "NON_PASS_PENDING_T030_REAL_WEARABLE":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_G21_STATUS_MISMATCH")
    if lock.get("run_1_equals_run_2") is not True:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_NOT_REPRODUCIBLE")

    predecessor_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_1.lock.json"
    if not predecessor_path.exists():
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_PREDECESSOR_MISSING")
    if hash_file(predecessor_path) != lock["predecessor_sha256"]:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_PREDECESSOR_WAS_MUTATED")

    predecessor_lock = json.loads(predecessor_path.read_text(encoding="utf-8"))
    if lock["superseded_unnormalized_runtime_digest"] != predecessor_lock["public_semantic_digest"]:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_SUPERSEDED_DIGEST_MISMATCH")

    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(ROOT / relative_path) != expected:
            raise RuntimeError(f"E2E_REPLAY_SOFTWARE_V1_2_TAMPER:{relative_path}")

    api_runtime_v1_1 = json.loads(
        (ROOT / "artifacts/API_RUNTIME_V1_1.lock.json").read_text(encoding="utf-8")
    )
    if api_runtime_v1_1.get("status") != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_UPSTREAM_API_RUNTIME_STATUS_MISMATCH")

    return {
        "status": "PASS",
        "lock_id": "E2E_REPLAY_SOFTWARE_V1_2",
        "predecessor_id": lock["predecessor_id"],
        "predecessor_preserved": True,
        "g21_status": lock["g21_status"],
        "public_semantic_digest": lock["public_semantic_digest"],
        "superseded_unnormalized_runtime_digest": lock["superseded_unnormalized_runtime_digest"],
        "bound_artifacts": len(lock.get("bound_artifacts", {})),
        "lock_sha256": hash_file(lock_path),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
