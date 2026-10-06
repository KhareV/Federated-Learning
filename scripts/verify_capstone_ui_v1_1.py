#!/usr/bin/env python3
# ruff: noqa: E501
"""Verify CAPSTONE_UI_V1_1 (CAP-008 successor of CAPSTONE_UI_V1): the predecessor lock file is preserved
byte-identical, the successor claims no backend/API/scientific change, EVERY frontend file is bound by the
successor (no unaccounted drift, no unbound file) and byte-identical to it (CAPSTONE_FEDERATION_UX_PROTOCOL_V1
amendments, if any, are applied link by link)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json"
PREDECESSOR = "artifacts/capstone/CAPSTONE_UI_V1.lock.json"


def frontend_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "frontend"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split()
    return sorted(set(p for p in out if (ROOT / p).is_file()))


def _v14_bound() -> dict[str, str] | None:
    """UFL-LITE-002 successor: when CAPSTONE_UI_V1_4 exists and chains to V1_3 it governs the current frontend bytes."""
    path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("predecessor_id") != "CAPSTONE_UI_V1_3" or lock.get("predecessor_sha256") != hash_file(ROOT / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json"):
        raise RuntimeError("CAPSTONE_UI_V1_4_SUCCESSOR_CHAIN_BROKEN")
    return dict(lock["bound_artifacts"])


def _v13_bound() -> dict[str, str] | None:
    """CLERK-LIVE-001 successor: when CAPSTONE_UI_V1_3 exists and chains to V1_2 it governs the current frontend bytes."""
    path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("predecessor_id") != "CAPSTONE_UI_V1_2" or lock.get("predecessor_sha256") != hash_file(ROOT / "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json"):
        raise RuntimeError("CAPSTONE_UI_V1_3_SUCCESSOR_CHAIN_BROKEN")
    return dict(lock["bound_artifacts"])


def bound_map(lock: dict) -> dict[str, str]:
    v14 = _v14_bound()
    if v14 is not None:
        return v14
    v13 = _v13_bound()
    if v13 is not None:
        return v13
    # CAP-009 successor: current frontend bytes are governed by UI_V1_2, while
    # the historical UI_V1_1 lock remains byte-identical and its claims remain scoped.
    successor_path = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json"
    if successor_path.exists():
        successor = json.loads(successor_path.read_text(encoding="utf-8"))
        if successor.get("predecessor_id") != "CAPSTONE_UI_V1_1" or successor.get(
                "predecessor_sha256") != hash_file(ROOT / LOCK):
            raise RuntimeError("CAPSTONE_UI_V1_1_SUCCESSOR_CHAIN_BROKEN")
        return dict(successor["bound_artifacts"])
    expected = dict(lock["bound_artifacts"])
    for amendment in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_*.json")):
        data = json.loads(amendment.read_text(encoding="utf-8"))
        for path, change in data.get("files", {}).items():
            if path in expected:
                if expected[path] != change["old_sha256"]:
                    raise RuntimeError(f"CAPSTONE_UI_V1_1_AMENDMENT_CHAIN_BROKEN:{path}")
                expected[path] = change["new_sha256"]
        expected.update(data.get("added_files", {}))
    return expected


def verify() -> dict[str, object]:
    lock_path = ROOT / LOCK
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    checks = {
        "lock_id": lock.get("lock_id") == "CAPSTONE_UI_V1_1", "status": lock.get("status") == "FROZEN_ENGINEERING_INTERFACE",
        "predecessor": lock.get("predecessor_id") == "CAPSTONE_UI_V1", "owner": lock.get("owner_phase") == "CAP-008",
        "science": lock.get("scientific_state_semantics_changed") is False, "contract": lock.get("api_contract_changed") is False,
        "backend": lock.get("backend_modified") is False, "selector": lock.get("public_runtime_model_selector_added") is False,
        "framework": lock.get("second_frontend_created") is False, "dependencies": lock.get("npm_dependencies_added") == [],
    }
    for name, ok in checks.items():
        if not ok:
            raise RuntimeError(f"CAPSTONE_UI_V1_1_CLAIM_VIOLATION:{name}")
    if hash_file(ROOT / PREDECESSOR) != lock["predecessor_sha256"]:
        raise RuntimeError("CAPSTONE_UI_V1_1_PREDECESSOR_WAS_MUTATED")
    expected = bound_map(lock)
    actual = frontend_files()
    unbound = [p for p in actual if p not in expected]
    missing = [p for p in expected if p not in set(actual)]
    if unbound:
        raise RuntimeError(f"CAPSTONE_UI_V1_1_UNACCOUNTED_FRONTEND_FILE:{unbound[0]}")
    if missing:
        raise RuntimeError(f"CAPSTONE_UI_V1_1_BOUND_FILE_MISSING:{missing[0]}")
    for relative, digest in expected.items():
        if hash_file(ROOT / relative) != digest:
            raise RuntimeError(f"CAPSTONE_UI_V1_1_TAMPER:{relative}")
    return {"status": "PASS", "lock_id": "CAPSTONE_UI_V1_1", "predecessor_id": lock["predecessor_id"], "predecessor_preserved": True,
            "bound_artifacts": len(expected), "changed_from_predecessor": len(lock["changed_from_predecessor"]), "lock_sha256": hash_file(lock_path)}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
