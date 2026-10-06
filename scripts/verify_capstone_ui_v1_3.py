# ruff: noqa: E501
"""Verify CAPSTONE_UI_V1_3, the V1_2 predecessor lock bytes, and every frontend file (no unaccounted drift)."""

from __future__ import annotations

import json

from nhm.hashing import hash_file
from scripts.freeze_capstone_ui_v1_3 import LOCK_PATH, PREDECESSOR, ROOT, frontend_files


def _v14_bound() -> dict[str, str] | None:
    """UFL-LITE-002 successor: a V1_4 lock chained to this lock governs the current frontend bytes (this lock stays historical)."""
    path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("predecessor_id") != "CAPSTONE_UI_V1_3" or lock.get("predecessor_sha256") != hash_file(LOCK_PATH):
        raise RuntimeError("CAPSTONE_UI_V1_4_SUCCESSOR_CHAIN_BROKEN")
    return dict(lock["bound_artifacts"])


def verify() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock["lock_id"] != "CAPSTONE_UI_V1_3" or lock["status"] != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("CAPSTONE_UI_V1_3_IDENTITY_DRIFT")
    if lock["predecessor_id"] != "CAPSTONE_UI_V1_2" or hash_file(PREDECESSOR) != lock["predecessor_sha256"]:
        raise RuntimeError("CAPSTONE_UI_V1_3_PREDECESSOR_DRIFT")
    if lock["npm_dependencies_added"] or lock["api_contract_changed"] or lock["scientific_state_semantics_changed"] or lock["backend_modified"]:
        raise RuntimeError("CAPSTONE_UI_V1_3_SCOPE_DRIFT")
    expected, actual = _v14_bound() or lock["bound_artifacts"], frontend_files()
    if set(actual) != set(expected):
        raise RuntimeError("CAPSTONE_UI_V1_3_UNBOUND_OR_MISSING_FRONTEND_FILE")
    for path, digest in expected.items():
        if hash_file(ROOT / path) != digest:
            raise RuntimeError(f"CAPSTONE_UI_V1_3_TAMPER:{path}")
    return {"status": "PASS", "bound_files": len(actual), "changed_files": len(lock["changed_from_predecessor"]), "lock_sha256": hash_file(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
