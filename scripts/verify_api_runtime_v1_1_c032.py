#!/usr/bin/env python3
"""Verify API_RUNTIME_V1_1 (C032-NORM-RUNTIME successor): tamper-detect every bound file,
cross-check the predecessor API_RUNTIME_V1 lock is preserved byte-identical, and confirm the
restored PREPROC_V1 PER_WINDOW_ZSCORE_V1 normalization ownership/epsilon are as locked."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/API_RUNTIME_V1_1.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    if lock.get("lock_id") != "API_RUNTIME_V1_1":
        raise RuntimeError("API_RUNTIME_V1_1_LOCK_ID_MISMATCH")
    if lock.get("status") != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("API_RUNTIME_V1_1_STATUS_MISMATCH")
    if lock.get("normalization_id") != "PER_WINDOW_ZSCORE_V1":
        raise RuntimeError("API_RUNTIME_V1_1_NORMALIZATION_ID_MISMATCH")
    if lock.get("normalization_epsilon") != 1e-8:
        raise RuntimeError("API_RUNTIME_V1_1_NORMALIZATION_EPSILON_MISMATCH")
    if lock.get("hr_branch_receives_normalized_input") is not False:
        raise RuntimeError("API_RUNTIME_V1_1_HR_BRANCH_SEPARATION_VIOLATION")
    if lock.get("api_contract_byte_identical_to_predecessor") is not True:
        raise RuntimeError("API_RUNTIME_V1_1_CONTRACT_CLAIM_VIOLATION")
    if lock.get("runtime_equivalence_decision_agreement_fraction") != 1.0:
        raise RuntimeError("API_RUNTIME_V1_1_EQUIVALENCE_NOT_EXACT")

    predecessor_path = ROOT / "artifacts/API_RUNTIME_V1.lock.json"
    if not predecessor_path.exists():
        raise RuntimeError("API_RUNTIME_V1_1_PREDECESSOR_MISSING")
    if hash_file(predecessor_path) != lock["predecessor_sha256"]:
        raise RuntimeError("API_RUNTIME_V1_1_PREDECESSOR_WAS_MUTATED")

    if hash_file(ROOT / "contracts/API_SCHEMA_V1.json") != lock["api_schema_v1_sha256"]:
        raise RuntimeError("API_RUNTIME_V1_1_CONTRACT_TAMPER")

    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(ROOT / relative_path) != expected:
            raise RuntimeError(f"API_RUNTIME_V1_1_TAMPER:{relative_path}")

    gateway_lock = json.loads(
        (ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json").read_text(encoding="utf-8")
    )
    if gateway_lock.get("freeze_id") != "F14" or gateway_lock.get("status") != "FROZEN":
        raise RuntimeError("API_RUNTIME_V1_1_UPSTREAM_F14_MISMATCH")

    return {
        "status": "PASS",
        "lock_id": "API_RUNTIME_V1_1",
        "predecessor_id": lock["predecessor_id"],
        "predecessor_preserved": True,
        "bound_artifacts": len(lock.get("bound_artifacts", {})),
        "lock_sha256": hash_file(lock_path),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
