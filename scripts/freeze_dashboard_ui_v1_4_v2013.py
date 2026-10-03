#!/usr/bin/env python3
"""Create the DASHBOARD_UI_V1_4 successor lock (V2-013).

Genuine frontend defect closed (see reports/model_v2/v2_013/frontend_compatibility.json): the
single dashboard route hard-coded `model_id: 'MODEL_V1'` in the manual research-window request
and rendered MODEL_V1-specific copy (waveform note, 422 text, replay caption). Against a runtime
bound to another model the control could only ever return HTTP 400. The route now sends a
build-time deployment value (VITE_NHM_REQUEST_MODEL_ID, default MODEL_V1 -- NOT a runtime
selector) and the copy is model-neutral. Only two frontend source files change. Scientific
state semantics (the five states, their meaning, thresholds), the API contract and every other
bound file are unchanged. The predecessor DASHBOARD_UI_V1_3 lock is never mutated.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_PATH = ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json"
PREDECESSOR_ID = "DASHBOARD_UI_V1_3"
CHANGED_SOURCES = (
    "frontend/src/lib/dashboard/state-presentation.ts",
    "frontend/src/routes/monitoring/+page.svelte",
)


def main() -> None:
    predecessor_sha = hash_file(PREDECESSOR_PATH)
    predecessor = json.loads(PREDECESSOR_PATH.read_text(encoding="utf-8"))
    carried = {k: v for k, v in predecessor.items()
               if k not in {"lock_id", "predecessor_id", "predecessor_sha256", "checkpoint",
                            "reason", "bound_artifacts", "types_node_added",
                            "clean_checkout_svelte_check_errors_before_fix",
                            "clean_checkout_svelte_check_errors_after_fix",
                            "frontend_dependency_declaration_changed", "state_wording_changed",
                            "frontend_application_source_changed"}}
    lock = {
        **carried,
        "lock_id": "DASHBOARD_UI_V1_4",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "checkpoint": "V2-013",
        "status": "FROZEN_ENGINEERING_INTERFACE",
        "reason": (
            "remove hard-coded MODEL_V1 identity from the dashboard route's manual request and "
            "from model-specific user-facing copy so the same frontend works against the "
            "parallel API_RUNTIME_V2 research runtime; request model_id is a build-time "
            "deployment value (default MODEL_V1), not a runtime selector"
        ),
        "scientific_state_semantics_changed": False,
        "state_wording_changed": True,
        "state_wording_change_scope": (
            "model-identity wording only (waveform note, 422 text, replay caption, meta "
            "description); the five state titles/texts and their meaning are unchanged"
        ),
        "api_contract_changed": False,
        "frontend_application_source_changed": True,
        "frontend_application_sources_changed": list(CHANGED_SOURCES),
        "frontend_dependency_declaration_changed": False,
        "build_time_request_model_id_env": "VITE_NHM_REQUEST_MODEL_ID",
        "default_request_model_id": "MODEL_V1",
        "public_runtime_model_selector_added": False,
        "types_node_added": predecessor["types_node_added"],
        "no_new_canonical_freeze_registry_row": True,
        "bound_artifacts": {p: hash_file(ROOT / p) for p in predecessor["bound_artifacts"]},
    }
    dest = ROOT / "artifacts/DASHBOARD_UI_V1_4.lock.json"
    dest.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    supersedes = {
        "successor_id": "DASHBOARD_UI_V1_4", "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "predecessor_status_at_supersession": predecessor["status"],
        "predecessor_preserved_unchanged": True, "reason": lock["reason"],
        "checkpoint": "V2-013",
    }
    sup = ROOT / "artifacts/DASHBOARD_UI_V1_4.supersedes.json"
    sup.write_text(json.dumps(supersedes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(dest))
    print(hash_file(sup))


if __name__ == "__main__":
    main()
