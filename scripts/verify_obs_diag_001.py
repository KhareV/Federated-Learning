# ruff: noqa: E501
"""Verify NHM_OBS_DIAG_001: chain to the byte-identical V1 lock (also at its recorded commit), bound bytes, frontend binding, scope flags and the protected surface."""

from __future__ import annotations

import json
import subprocess

from scripts.freeze_obs_diag_001 import (
    LOCK_PATH,
    ROOT,
    UI_LOCK,
    V1_COMMIT,
    V1_LOCK,
    frontend_files,
    protected_diff,
    sha,
)


def verify() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text())
    if lock["lock_id"] != "NHM_OBS_DIAG_001" or lock["predecessor_id"] != "NHM_RESEARCH_OBSERVATORY_V1":
        raise RuntimeError("OBS_DIAG_IDENTITY_DRIFT")
    if sha(V1_LOCK) != lock["predecessor_sha256"]:
        raise RuntimeError("OBS_DIAG_PREDECESSOR_LOCK_MUTATED")
    blob = subprocess.run(["git", "show", f"{V1_COMMIT}:artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"], cwd=ROOT, capture_output=True, check=True).stdout
    import hashlib

    if hashlib.sha256(blob).hexdigest() != lock["predecessor_sha256"]:
        raise RuntimeError("OBS_DIAG_PREDECESSOR_NOT_BYTE_IDENTICAL_TO_ACCEPTED_COMMIT")
    if json.loads(V1_LOCK.read_text())["status"] != "FROZEN_IMPLEMENTED_SCOPE_NOT_FULL_MASTER_PROMPT_ACCEPTANCE" or sha(UI_LOCK) != lock["ui_baseline_sha256"]:
        raise RuntimeError("OBS_DIAG_BASELINE_STATUS_DRIFT")
    for flag in ("scientific_state_semantics_changed", "model_calibration_or_fl_math_changed", "new_scientific_experiment_run", "released_model_binding_changed", "candidate_promoted_or_deployed", "hardware_work_performed", "held_out_data_accessed", "calibration_applied_to_candidate"):
        if lock[flag] is not False:
            raise RuntimeError(f"OBS_DIAG_SCOPE_DRIFT:{flag}")
    for path, digest in lock["bound_files"].items():
        if not (ROOT / path).is_file() or sha(ROOT / path) != digest:
            raise RuntimeError(f"OBS_DIAG_TAMPER:{path}")
    if set(frontend_files()) != set(lock["bound_artifacts"]) or any(sha(ROOT / p) != d for p, d in lock["bound_artifacts"].items()):
        raise RuntimeError("OBS_DIAG_FRONTEND_BINDING_DRIFT")
    if protected_diff():
        raise RuntimeError(f"OBS_DIAG_PROTECTED_SURFACE_DRIFT:{protected_diff()[:3]}")
    return {"status": "PASS", "bound_files": len(lock["bound_files"]), "changed_from_v1": len(lock["changed_from_predecessor_files"]), "lock_sha256": sha(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
