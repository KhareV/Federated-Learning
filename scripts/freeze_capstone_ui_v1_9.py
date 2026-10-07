"""Freeze the final UI-only successor, CAPSTONE_UI_V1_9."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.freeze_capstone_ui_v1_8 import frontend_files

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_8.lock.json"
LOCK_PATH = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_9.lock.json"


def freeze() -> dict[str, object]:
    previous = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
    bound = {path: hash_file(ROOT / path) for path in frontend_files()}
    changed = sorted(
        path for path, digest in bound.items()
        if previous["bound_artifacts"].get(path) != digest
    )
    if not changed or not all(path.startswith("frontend/") for path in changed):
        raise RuntimeError("CAPSTONE_UI_V1_9_INVALID_SCOPE")
    lock = {
        "lock_id": "CAPSTONE_UI_V1_9",
        "owner_phase": "UI-ENH-003",
        "status": "FROZEN_ENGINEERING_INTERFACE",
        "predecessor_id": "CAPSTONE_UI_V1_8",
        "predecessor_sha256": hash_file(PREDECESSOR),
        "bound_artifacts": bound,
        "changed_from_predecessor": changed,
        "claim_boundary": "FINAL_UI_POLISH_AND_BUG_FIX_ONLY",
        "backend_modified": False,
        "api_contract_changed": False,
        "fl_implementation_changed": False,
        "auth_implementation_changed": False,
        "model_changed": False,
        "calibration_changed": False,
        "scientific_state_semantics_changed": False,
        "new_scientific_metrics_added": False,
        "npm_dependencies_added": [],
        "second_frontend_created": False,
    }
    LOCK_PATH.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "FROZEN", "bound_files": len(bound), "changed_files": changed,
            "lock_sha256": hash_file(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
