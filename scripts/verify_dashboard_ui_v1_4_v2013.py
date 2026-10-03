#!/usr/bin/env python3
"""Verify DASHBOARD_UI_V1_4 (V2-013 successor): tamper-detect every bound file, confirm the
predecessor DASHBOARD_UI_V1_3 lock is preserved byte-identical, and confirm the lock claims only
model-identity wording/source changes."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/DASHBOARD_UI_V1_4.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    checks = {
        "lock_id": lock.get("lock_id") == "DASHBOARD_UI_V1_4",
        "status": lock.get("status") == "FROZEN_ENGINEERING_INTERFACE",
        "science": lock.get("scientific_state_semantics_changed") is False,
        "contract": lock.get("api_contract_changed") is False,
        "selector": lock.get("public_runtime_model_selector_added") is False,
        "source_claim": lock.get("frontend_application_source_changed") is True,
    }
    for name, ok in checks.items():
        if not ok:
            raise RuntimeError(f"DASHBOARD_UI_V1_4_CLAIM_VIOLATION:{name}")
    predecessor = ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json"
    if hash_file(predecessor) != lock["predecessor_sha256"]:
        raise RuntimeError("DASHBOARD_UI_V1_4_PREDECESSOR_WAS_MUTATED")
    for relative, expected in lock["bound_artifacts"].items():
        if hash_file(ROOT / relative) != expected:
            raise RuntimeError(f"DASHBOARD_UI_V1_4_TAMPER:{relative}")
    for forbidden in ("dashboard", "ui", "client", "web", "frontend-v2"):
        if (ROOT / forbidden).is_dir():
            raise RuntimeError("DASHBOARD_UI_V1_4_PARALLEL_FRONTEND_DETECTED")
    return {"status": "PASS", "lock_id": "DASHBOARD_UI_V1_4",
            "predecessor_id": lock["predecessor_id"], "predecessor_preserved": True,
            "bound_artifacts": len(lock["bound_artifacts"]), "lock_sha256": hash_file(lock_path)}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
