"""Verify CAPSTONE_UI_V1_8 and the unmodified V1_7 predecessor lock."""

from __future__ import annotations

import json

from nhm.hashing import hash_file
from scripts.freeze_capstone_ui_v1_8 import LOCK_PATH, PREDECESSOR, ROOT, frontend_files


def verify() -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if (
        lock.get("lock_id") != "CAPSTONE_UI_V1_8"
        or lock.get("status") != "FROZEN_ENGINEERING_INTERFACE"
    ):
        raise RuntimeError("CAPSTONE_UI_V1_8_IDENTITY_DRIFT")
    if (
        lock.get("predecessor_id") != "CAPSTONE_UI_V1_7"
        or lock.get("predecessor_sha256") != hash_file(PREDECESSOR)
    ):
        raise RuntimeError("CAPSTONE_UI_V1_8_PREDECESSOR_DRIFT")
    for field in ("backend_modified", "api_contract_changed", "fl_implementation_changed",
                  "auth_implementation_changed", "scientific_state_semantics_changed",
                  "new_scientific_metrics_added", "second_frontend_created"):
        if lock.get(field) is not False:
            raise RuntimeError(f"CAPSTONE_UI_V1_8_SCOPE_DRIFT:{field}")
    if (
        lock.get("npm_dependencies_added") != []
        or lock.get("claim_boundary")
        != "PRODUCT_STORY_COMPARISON_AND_RESEARCH_VISUALIZATION_ONLY"
    ):
        raise RuntimeError("CAPSTONE_UI_V1_8_SCOPE_DRIFT")
    actual = frontend_files()
    expected = lock["bound_artifacts"]
    if set(actual) != set(expected):
        raise RuntimeError("CAPSTONE_UI_V1_8_UNBOUND_OR_MISSING_FRONTEND_FILE")
    for path, digest in expected.items():
        if hash_file(ROOT / path) != digest:
            raise RuntimeError(f"CAPSTONE_UI_V1_8_TAMPER:{path}")
    predecessor = json.loads(PREDECESSOR.read_text(encoding="utf-8"))["bound_artifacts"]
    changed = sorted(path for path, digest in expected.items() if predecessor.get(path) != digest)
    if changed != lock["changed_from_predecessor"]:
        raise RuntimeError("CAPSTONE_UI_V1_8_CHANGED_FILE_ACCOUNTING_DRIFT")
    return {"status": "PASS", "bound_files": len(actual), "changed_files": len(changed),
            "lock_sha256": hash_file(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
