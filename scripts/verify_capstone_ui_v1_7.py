# ruff: noqa: E501
"""Verify CAPSTONE_UI_V1_7, the V1_6 predecessor lock bytes, and every frontend file (no unaccounted drift)."""

from __future__ import annotations

import json

from nhm.hashing import hash_file
from scripts.freeze_capstone_ui_v1_7 import LOCK_PATH, PREDECESSOR, ROOT, frontend_files


def verify() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock["lock_id"] != "CAPSTONE_UI_V1_7" or lock["status"] != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("CAPSTONE_UI_V1_7_IDENTITY_DRIFT")
    if lock["predecessor_id"] != "CAPSTONE_UI_V1_6" or hash_file(PREDECESSOR) != lock["predecessor_sha256"]:
        raise RuntimeError("CAPSTONE_UI_V1_7_PREDECESSOR_DRIFT")
    if lock["npm_dependencies_added"] or lock["api_contract_changed"] or lock["scientific_state_semantics_changed"] or lock["backend_modified"]:
        raise RuntimeError("CAPSTONE_UI_V1_7_SCOPE_DRIFT")
    expected, actual = lock["bound_artifacts"], frontend_files()
    if set(actual) != set(expected):
        raise RuntimeError("CAPSTONE_UI_V1_7_UNBOUND_OR_MISSING_FRONTEND_FILE")
    for path, digest in expected.items():
        if hash_file(ROOT / path) != digest:
            raise RuntimeError(f"CAPSTONE_UI_V1_7_TAMPER:{path}")
    return {"status": "PASS", "bound_files": len(actual), "changed_files": len(lock["changed_from_predecessor"]), "lock_sha256": hash_file(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
