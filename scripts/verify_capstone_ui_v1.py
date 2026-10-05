#!/usr/bin/env python3
# ruff: noqa: E501
"""Verify CAPSTONE_UI_V1 (CAP-005 successor of DASHBOARD_UI_V1_5): every bound frontend/UI file is
byte-identical to the lock (amendments applied), the predecessor DASHBOARD_UI_V1_5 lock file is preserved
byte-identical, and the lock claims no backend change, no API change, no model selector and no
scientific-state change."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_UI_V1.lock.json"


def _successor_bound() -> dict[str, str]:
    lock_path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json"
    if not lock_path.exists():
        return {}
    bound = dict(json.loads(lock_path.read_text(encoding="utf-8"))["bound_artifacts"])
    for amendment in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_*.json")):
        data = json.loads(amendment.read_text(encoding="utf-8"))
        for path, change in data.get("files", {}).items():
            if path in bound:
                bound[path] = change["new_sha256"]
        bound.update(data.get("added_files", {}))
    return bound


def verify() -> dict[str, object]:
    lock_path = ROOT / LOCK
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    checks = {
        "lock_id": lock.get("lock_id") == "CAPSTONE_UI_V1",
        "status": lock.get("status") == "FROZEN_ENGINEERING_INTERFACE",
        "predecessor": lock.get("predecessor_id") == "DASHBOARD_UI_V1_5",
        "science": lock.get("scientific_state_semantics_changed") is False,
        "contract": lock.get("api_contract_changed") is False,
        "backend": lock.get("backend_modified") is False,
        "selector": lock.get("public_runtime_model_selector_added") is False,
        "framework": lock.get("second_frontend_created") is False,
    }
    for name, ok in checks.items():
        if not ok:
            raise RuntimeError(f"CAPSTONE_UI_V1_CLAIM_VIOLATION:{name}")
    if hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_5.lock.json") != lock["predecessor_sha256"]:
        raise RuntimeError("CAPSTONE_UI_V1_PREDECESSOR_WAS_MUTATED")
    expected = dict(lock["bound_artifacts"])
    for amendment in sorted((ROOT / "artifacts/capstone").glob(
            "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_*.json")):
        data = json.loads(amendment.read_text(encoding="utf-8"))
        for path, change in data.get("files", {}).items():
            if path in expected:
                if expected[path] != change["old_sha256"]:
                    raise RuntimeError(f"CAPSTONE_UI_V1_AMENDMENT_CHAIN_BROKEN:{path}")
                expected[path] = change["new_sha256"]
        expected.update(data.get("added_files", {}))
    successor = _successor_bound()  # CAP-008: a change is legal only if CAPSTONE_UI_V1_1 binds exactly the current bytes
    for relative, digest in expected.items():
        current = hash_file(ROOT / relative)
        if current != digest and successor.get(relative) != current:
            raise RuntimeError(f"CAPSTONE_UI_V1_TAMPER:{relative}")
    return {"status": "PASS", "lock_id": "CAPSTONE_UI_V1", "predecessor_id": lock["predecessor_id"],
            "predecessor_preserved": True, "bound_artifacts": len(expected),
            "lock_sha256": hash_file(lock_path)}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
