# ruff: noqa: E501
"""Verify CAPSTONE_UI_V1_4, the V1_3 predecessor lock bytes, and every frontend file (no unaccounted drift)."""

from __future__ import annotations

import json

from nhm.hashing import hash_file
from scripts.freeze_capstone_ui_v1_4 import LOCK_PATH, PREDECESSOR, ROOT, frontend_files


def _v17_bound() -> dict[str, str] | None:
    """UI-ENH-001 successor: a V1_7 lock chained to V1_6 governs the current bytes."""
    path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_7.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    v16 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json"
    chained = lock.get("predecessor_id") == "CAPSTONE_UI_V1_6"
    if not chained or lock.get("predecessor_sha256") != hash_file(v16):
        raise RuntimeError("CAPSTONE_UI_V1_7_SUCCESSOR_CHAIN_BROKEN")
    return dict(lock["bound_artifacts"])


def _v16_bound() -> dict[str, str] | None:
    """FINAL-EVAL-REPAIR-002 successor: a V1_6 lock chained to V1_5 governs the current bytes."""
    path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    v15 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json"
    chained = lock.get("predecessor_id") == "CAPSTONE_UI_V1_5"
    if not chained or lock.get("predecessor_sha256") != hash_file(v15):
        raise RuntimeError("CAPSTONE_UI_V1_6_SUCCESSOR_CHAIN_BROKEN")
    return dict(lock["bound_artifacts"])


def _v15_bound() -> dict[str, str] | None:
    """FINAL-EVAL-REPAIR-001 successor: a V1_5 lock chained to V1_4 governs the current bytes."""
    path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    v14 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json"
    chained = lock.get("predecessor_id") == "CAPSTONE_UI_V1_4"
    if not chained or lock.get("predecessor_sha256") != hash_file(v14):
        raise RuntimeError("CAPSTONE_UI_V1_5_SUCCESSOR_CHAIN_BROKEN")
    return dict(lock["bound_artifacts"])


def verify() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock["lock_id"] != "CAPSTONE_UI_V1_4" or lock["status"] != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("CAPSTONE_UI_V1_4_IDENTITY_DRIFT")
    if lock["predecessor_id"] != "CAPSTONE_UI_V1_3" or hash_file(PREDECESSOR) != lock["predecessor_sha256"]:
        raise RuntimeError("CAPSTONE_UI_V1_4_PREDECESSOR_DRIFT")
    if lock["npm_dependencies_added"] or lock["api_contract_changed"] or lock["scientific_state_semantics_changed"] or lock["backend_modified"]:
        raise RuntimeError("CAPSTONE_UI_V1_4_SCOPE_DRIFT")
    expected, actual = _v17_bound() or _v16_bound() or _v15_bound() or lock["bound_artifacts"], frontend_files()
    if set(actual) != set(expected):
        raise RuntimeError("CAPSTONE_UI_V1_4_UNBOUND_OR_MISSING_FRONTEND_FILE")
    for path, digest in expected.items():
        if hash_file(ROOT / path) != digest:
            raise RuntimeError(f"CAPSTONE_UI_V1_4_TAMPER:{path}")
    return {"status": "PASS", "bound_files": len(actual), "changed_files": len(lock["changed_from_predecessor"]), "lock_sha256": hash_file(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
