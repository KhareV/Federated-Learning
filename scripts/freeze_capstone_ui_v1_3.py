# ruff: noqa: E501
"""Create the CLERK-LIVE-001 SvelteKit successor lock CAPSTONE_UI_V1_3 over every current frontend file."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json"
PREDECESSOR = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json"


def frontend_files() -> list[str]:
    paths = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "frontend"],
                           cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    return sorted(set(path for path in paths if (ROOT / path).is_file()))


def freeze() -> dict[str, object]:
    predecessor = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
    bound = {path: hash_file(ROOT / path) for path in frontend_files()}
    changed = [path for path, digest in bound.items() if predecessor["bound_artifacts"].get(path) != digest]
    lock = {
        "lock_id": "CAPSTONE_UI_V1_3", "owner_phase": "CLERK-LIVE-001", "status": "FROZEN_ENGINEERING_INTERFACE",
        "predecessor_id": "CAPSTONE_UI_V1_2", "predecessor_sha256": hash_file(PREDECESSOR),
        "bound_artifacts": bound, "changed_from_predecessor": changed, "reason": "REAL_CLERK_UI_COMPATIBILITY_SUCCESSOR",
        "api_contract_changed": False, "scientific_state_semantics_changed": False, "second_frontend_created": False,
        "npm_dependencies_added": [], "backend_modified": False,
        "claim_boundary": "CLERK_CONNECTED_AUTH_UI_LOADING_ONLY; belongs to CAPSTONE_CLERK_CONNECTED_V1, not to CAPSTONE_RELEASE_V1",
    }
    LOCK_PATH.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "FROZEN", "bound_files": len(bound), "changed_files": changed, "lock_sha256": hash_file(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
