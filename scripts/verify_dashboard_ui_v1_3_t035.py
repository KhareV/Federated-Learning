#!/usr/bin/env python3
"""Verify DASHBOARD_UI_V1_3 (T035-REPRO successor): tamper-detect every bound file,
cross-check the predecessor DASHBOARD_UI_V1_2 lock is preserved byte-identical, and confirm no
frontend application source or scientific/state/contract change is claimed -- only the
dependency declaration."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    if lock.get("lock_id") != "DASHBOARD_UI_V1_3":
        raise RuntimeError("DASHBOARD_UI_V1_3_LOCK_ID_MISMATCH")
    if lock.get("status") != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("DASHBOARD_UI_V1_3_STATUS_MISMATCH")
    if lock.get("scientific_state_semantics_changed") is not False:
        raise RuntimeError("DASHBOARD_UI_V1_3_SCIENCE_CLAIM_VIOLATION")
    if lock.get("state_wording_changed") is not False:
        raise RuntimeError("DASHBOARD_UI_V1_3_WORDING_CLAIM_VIOLATION")
    if lock.get("api_contract_changed") is not False:
        raise RuntimeError("DASHBOARD_UI_V1_3_CONTRACT_CLAIM_VIOLATION")
    if lock.get("frontend_application_source_changed") is not False:
        raise RuntimeError("DASHBOARD_UI_V1_3_FRONTEND_SOURCE_CLAIM_VIOLATION")

    predecessor_path = ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json"
    if not predecessor_path.exists():
        raise RuntimeError("DASHBOARD_UI_V1_3_PREDECESSOR_MISSING")
    if hash_file(predecessor_path) != lock["predecessor_sha256"]:
        raise RuntimeError("DASHBOARD_UI_V1_3_PREDECESSOR_WAS_MUTATED")

    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(ROOT / relative_path) != expected:
            raise RuntimeError(f"DASHBOARD_UI_V1_3_TAMPER:{relative_path}")

    package_json = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    if package_json.get("devDependencies", {}).get("@types/node") != "26.6.4":
        raise RuntimeError("DASHBOARD_UI_V1_3_TYPES_NODE_DECLARATION_MISSING")

    if (ROOT / "dashboard").is_dir() or (ROOT / "ui").is_dir() or (ROOT / "client").is_dir():
        raise RuntimeError("DASHBOARD_UI_V1_3_PARALLEL_FRONTEND_DETECTED")

    return {
        "status": "PASS",
        "lock_id": "DASHBOARD_UI_V1_3",
        "predecessor_id": lock["predecessor_id"],
        "predecessor_preserved": True,
        "bound_artifacts": len(lock.get("bound_artifacts", {})),
        "lock_sha256": hash_file(lock_path),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
