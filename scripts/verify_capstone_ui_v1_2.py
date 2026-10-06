"""Verify CAPSTONE_UI_V1_2, both predecessor lock bytes, and all frontend file bytes."""

from __future__ import annotations

import json

from nhm.hashing import hash_file
from scripts.freeze_capstone_ui_v1_2 import LOCK_PATH, PREDECESSOR, ROOT, frontend_files


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


def _v14_bound() -> dict[str, str] | None:
    """UFL-LITE-002 successor: a V1_4 lock chained to V1_3 governs the current frontend bytes."""
    path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    v13 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json"
    chained = lock.get("predecessor_id") == "CAPSTONE_UI_V1_3"
    if not chained or lock.get("predecessor_sha256") != hash_file(v13):
        raise RuntimeError("CAPSTONE_UI_V1_4_SUCCESSOR_CHAIN_BROKEN")
    return dict(lock["bound_artifacts"])


def _v13_bound() -> dict[str, str] | None:
    """CLERK-LIVE-001 successor: a V1_3 lock chained to V1_2 governs the current frontend bytes."""
    path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    chained = lock.get("predecessor_id") == "CAPSTONE_UI_V1_2"
    if not chained or lock.get("predecessor_sha256") != hash_file(LOCK_PATH):
        raise RuntimeError("CAPSTONE_UI_V1_3_SUCCESSOR_CHAIN_BROKEN")
    return dict(lock["bound_artifacts"])


def verify() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock["lock_id"] != "CAPSTONE_UI_V1_2" or lock["status"] != "FROZEN_ENGINEERING_INTERFACE":
        raise RuntimeError("CAPSTONE_UI_V1_2_IDENTITY_DRIFT")
    if (
        lock["predecessor_id"] != "CAPSTONE_UI_V1_1"
        or hash_file(PREDECESSOR) != lock["predecessor_sha256"]
    ):
        raise RuntimeError("CAPSTONE_UI_V1_2_PREDECESSOR_DRIFT")
    if lock["npm_dependencies_added"] or lock["api_contract_changed"]:
        raise RuntimeError("CAPSTONE_UI_V1_2_SCOPE_DRIFT")
    expected = _v15_bound() or _v14_bound() or _v13_bound() or lock["bound_artifacts"]
    actual = frontend_files()
    if set(actual) != set(expected):
        raise RuntimeError("CAPSTONE_UI_V1_2_UNBOUND_OR_MISSING_FRONTEND_FILE")
    for path, digest in expected.items():
        if hash_file(ROOT / path) != digest:
            raise RuntimeError(f"CAPSTONE_UI_V1_2_TAMPER:{path}")
    return {
        "status": "PASS",
        "bound_files": len(actual),
        "changed_files": len(lock["changed_from_predecessor"]),
        "lock_sha256": hash_file(LOCK_PATH),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
