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


def verify() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text())
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
    for path, digest in lock["bound_files"].items():
        if not (ROOT / path).is_file() or sha(ROOT / path) != digest:
            raise RuntimeError(f"OBSERVATORY_TAMPER:{path}")
    actual_frontend = frontend_files()
    if set(actual_frontend) != set(lock["bound_artifacts"]):
        raise RuntimeError("OBSERVATORY_UNBOUND_OR_MISSING_FRONTEND_FILE")
    for path, digest in lock["bound_artifacts"].items():
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
