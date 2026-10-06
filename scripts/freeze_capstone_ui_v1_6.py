# ruff: noqa: E501
"""Create the FINAL-EVAL-REPAIR-002 SvelteKit successor lock CAPSTONE_UI_V1_6 over every current frontend file."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json"
PREDECESSOR = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json"


def frontend_files() -> list[str]:
    paths = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "frontend"],
                           cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    return sorted(set(path for path in paths if (ROOT / path).is_file()))


def freeze() -> dict[str, object]:
    predecessor = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
    bound = {path: hash_file(ROOT / path) for path in frontend_files()}
    changed = [path for path, digest in bound.items() if predecessor["bound_artifacts"].get(path) != digest]
    lock = {
        "lock_id": "CAPSTONE_UI_V1_6", "owner_phase": "FINAL-EVAL-REPAIR-002", "status": "FROZEN_ENGINEERING_INTERFACE",
        "predecessor_id": "CAPSTONE_UI_V1_5", "predecessor_sha256": hash_file(PREDECESSOR),
        "bound_artifacts": bound, "changed_from_predecessor": changed, "reason": "FINAL_PUBLIC_PRESENTATION_REPAIR_SUCCESSOR",
        "api_contract_changed": False, "scientific_state_semantics_changed": False, "second_frontend_created": False,
        "npm_dependencies_added": [], "backend_modified": False,
        "claim_boundary": "FINAL_PUBLIC_PRESENTATION_REPAIR_ONLY (FINAL-EVAL-REPAIR-002); no backend, API, DB, FL or auth change",
    }
    LOCK_PATH.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "FROZEN", "bound_files": len(bound), "changed_files": changed, "lock_sha256": hash_file(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
