# ruff: noqa: E501
"""Verify NHM_RESEARCH_OBSERVATORY_V1: bound bytes, the accepted CAPSTONE_UI_V1_9 lock bytes at the entry commit, the exact predecessor delta, and the protected surface."""

from __future__ import annotations

import hashlib
import json
import subprocess

from scripts.freeze_observatory_v1 import (
    ENTRY,
    INTEGRATION,
    LOCK_PATH,
    ROOT,
    UI_LOCK,
    frontend_files,
    protected_diff,
    sha,
    v19_delta,
)

SUCCESSOR_PATH = ROOT / "artifacts/observatory/NHM_OBS_DIAG_001.lock.json"


def _successor() -> dict | None:
    """The accepted successor NHM_OBS_DIAG_001 may re-pin V1-bound files; it must chain to this lock's exact bytes."""
    if not SUCCESSOR_PATH.exists():
        return None
    successor = json.loads(SUCCESSOR_PATH.read_text())
    if successor.get("lock_id") != "NHM_OBS_DIAG_001" or successor.get("predecessor_sha256") != sha(LOCK_PATH):
        raise RuntimeError("OBSERVATORY_SUCCESSOR_CHAIN_BROKEN")
    return successor


FINAL_PATH = ROOT / "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"


def _final(diag: dict | None) -> dict | None:
    """NHM_FINAL_SHOWCASE_001 (chained to the exact NHM_OBS_DIAG_001 bytes) may re-pin files further; it never edits this lock."""
    if not FINAL_PATH.exists():
        return None
    final = json.loads(FINAL_PATH.read_text())
    if final.get("lock_id") != "NHM_FINAL_SHOWCASE_001" or diag is None or final.get("predecessor_sha256") != sha(SUCCESSOR_PATH):
        raise RuntimeError("OBSERVATORY_FINAL_CHAIN_BROKEN")
    return final


def verify() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text())
    successor = _successor()
    final = _final(successor)
    if lock["lock_id"] != "NHM_RESEARCH_OBSERVATORY_V1" or lock["full_master_prompt_acceptance"] is not False:
        raise RuntimeError("OBSERVATORY_LOCK_IDENTITY_DRIFT")
    if lock["predecessor_id"] != "CAPSTONE_UI_V1_9" or sha(UI_LOCK) != lock["predecessor_sha256"]:
        raise RuntimeError("OBSERVATORY_PREDECESSOR_LOCK_DRIFT")
    entry_blob = subprocess.run(["git", "show", f"{ENTRY}:artifacts/capstone/CAPSTONE_UI_V1_9.lock.json"], cwd=ROOT, capture_output=True, check=True).stdout
    if hashlib.sha256(entry_blob).hexdigest() != lock["predecessor_sha256"]:
        raise RuntimeError("OBSERVATORY_PREDECESSOR_LOCK_NOT_BYTE_IDENTICAL_TO_ENTRY")
    for flag in ("scientific_state_semantics_changed", "model_calibration_or_fl_math_changed", "new_scientific_experiment_run", "released_model_binding_changed", "candidate_promoted_or_deployed", "hardware_work_performed"):
        if lock[flag] is not False:
            raise RuntimeError(f"OBSERVATORY_SCOPE_DRIFT:{flag}")
    repinned = successor["changed_from_predecessor_files"] if successor else []
    for path, digest in lock["bound_files"].items():
        if not (ROOT / path).is_file():
            raise RuntimeError(f"OBSERVATORY_TAMPER:{path}")
        accepted = {digest} | ({successor["bound_files"].get(path)} if successor and path in repinned else set())
        if final and path in final["repins_predecessor_files"]:
            accepted |= {final["bound_files"][path]}
        if sha(ROOT / path) not in accepted:
            raise RuntimeError(f"OBSERVATORY_TAMPER:{path}")
    actual_frontend = frontend_files()
    expected_frontend = final["bound_artifacts"] if final else successor["bound_artifacts"] if successor else lock["bound_artifacts"]
    if set(actual_frontend) != set(expected_frontend):
        raise RuntimeError("OBSERVATORY_UNBOUND_OR_MISSING_FRONTEND_FILE")
    for path, digest in expected_frontend.items():
        if sha(ROOT / path) != digest:
            raise RuntimeError(f"OBSERVATORY_FRONTEND_TAMPER:{path}")
    delta = v19_delta()
    unexpected = sorted(set(delta) - set(INTEGRATION))
    if delta != lock["predecessor_frontend_files_changed"] or unexpected:
        raise RuntimeError(f"OBSERVATORY_PREDECESSOR_DELTA_DRIFT:{unexpected}")
    if protected_diff():
        raise RuntimeError(f"OBSERVATORY_PROTECTED_SURFACE_DRIFT:{protected_diff()[:3]}")
    return {"status": "PASS", "bound_files": len(lock["bound_files"]), "predecessor_files_changed": delta, "lock_sha256": sha(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
