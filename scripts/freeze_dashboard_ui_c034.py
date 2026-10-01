#!/usr/bin/env python3
"""Create the DASHBOARD_UI_V1_1 successor lock (C034-UI-E2E).

The frozen DASHBOARD_UI_V1 lock (predecessor) binds several files this corrective checkpoint
modifies (frontend/src/lib/api/nhm-v1.ts, frontend/src/routes/monitoring/+page.svelte,
frontend/vite.config.ts) to wire the recorded-replay orchestration into the canonical
dashboard. Per Section 26, the predecessor lock is NEVER mutated in place -- this is an
ADDITIVE successor. Scientific state semantics, state wording, and the API contract are
unchanged (verified explicitly below); only replay orchestration plumbing was added.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_LOCK_PATH = ROOT / "artifacts/DASHBOARD_UI_V1.lock.json"
PREDECESSOR_ID = "DASHBOARD_UI_V1"
PREDECESSOR_SHA_EXPECTED = "a8f7c557001503017a392f8703260ee589f4453e413e09498482b018ca8ef1b6"


def main() -> None:
    predecessor_sha = hash_file(PREDECESSOR_LOCK_PATH)
    if predecessor_sha != PREDECESSOR_SHA_EXPECTED:
        raise RuntimeError(
            f"DASHBOARD_UI_V1_PREDECESSOR_SHA_MISMATCH: expected {PREDECESSOR_SHA_EXPECTED}, "
            f"got {predecessor_sha}"
        )
    predecessor_lock = json.loads(PREDECESSOR_LOCK_PATH.read_text(encoding="utf-8"))

    api_runtime_lock = json.loads(
        (ROOT / "artifacts/API_RUNTIME_V1.lock.json").read_text(encoding="utf-8")
    )

    bound_paths = [
        # Carried over from DASHBOARD_UI_V1 (unchanged content unless noted):
        "artifacts/API_RUNTIME_V1.lock.json",
        "contracts/API_SCHEMA_V1.json",
        "contracts/openapi_v1.json",
        "frontend/package-lock.json",
        "frontend/package.json",
        "frontend/src/lib/api/nhm-v1.ts",  # MODIFIED: + NhmApiClient type export
        "frontend/src/lib/dashboard/demo-window.ts",
        "frontend/src/lib/dashboard/fixtures.ts",
        "frontend/src/lib/dashboard/session.svelte.ts",
        "frontend/src/lib/dashboard/state-presentation.ts",  # UNCHANGED -- wording frozen
        "frontend/src/routes/monitoring/+page.svelte",  # MODIFIED: + recorded-replay mode
        "frontend/vite.config.ts",  # MODIFIED: + preview proxy, NHM_API_PORT
        "frontend/vitest.config.ts",
        "reports/t033/frontend_claim_reconciliation.json",
        "reports/t033/frontend_legacy_audit.json",
        "reports/t033/frontend_path_mapping.json",
        # New in C034:
        "frontend/src/lib/dashboard/replay.ts",
        "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json",
        "scripts/build_frontend_replay_bundle_c034.py",
        "scripts/run_e2e_dashboard_demo_c034.py",
        "reports/c034_ui_e2e/model_input_semantics.json",
        "reports/c034_ui_e2e/replay_eligibility_audit.json",
        "reports/c034_ui_e2e/frontend_replay_bundle.json",
    ]

    lock = {
        "lock_id": "DASHBOARD_UI_V1_1",
        "status": "FROZEN_ENGINEERING_INTERFACE",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "reason": "add recorded-replay orchestration only (C034-UI-E2E)",
        "scientific_state_semantics_changed": False,
        "state_wording_changed": False,
        "api_contract_changed": False,
        "new_canonical_freeze_registry_row_created": False,
        "logical_subsystem": predecessor_lock["logical_subsystem"],
        "repository_path": predecessor_lock["repository_path"],
        "source_plan_path": predecessor_lock["source_plan_path"],
        "framework": predecessor_lock["framework"],
        "framework_version": predecessor_lock["framework_version"],
        "svelte_version": predecessor_lock["svelte_version"],
        "vite_version": predecessor_lock["vite_version"],
        "route": predecessor_lock["route"],
        "api_route_consumed": predecessor_lock["api_route_consumed"],
        "contract_version": predecessor_lock["contract_version"],
        "api_runtime_v1_lock_sha256": hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json"),
        "api_schema_v1_sha256": hash_file(ROOT / "contracts/API_SCHEMA_V1.json"),
        "openapi_v1_sha256": hash_file(ROOT / "contracts/openapi_v1.json"),
        "gateway_artifact_lock_sha256": api_runtime_lock["bound_artifacts"][
            "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
        ],
        "monitoring_state_vocabulary": predecessor_lock["monitoring_state_vocabulary"],
        "required_wording": predecessor_lock["required_wording"],
        "calibration_metadata_required": predecessor_lock["calibration_metadata_required"],
        "research_only_panel_required": predecessor_lock["research_only_panel_required"],
        "persistent_panels": predecessor_lock["persistent_panels"],
        "recorded_replay_entry_convention": "/monitoring?mode=replay&replay=<replay_id>&speed=0|1",
        "recorded_replay_controller": (
            "frontend/src/lib/dashboard/replay.ts::runCanonicalRecordedReplay"
        ),
        "recorded_replay_bundle_generator": "scripts/build_frontend_replay_bundle_c034.py",
        "no_new_canonical_freeze_row": True,
        "change_control": (
            "Changing the frontend API client, state-presentation mapping, the /monitoring "
            "route's panel structure, or the recorded-replay controller requires a further "
            "controlled successor and invalidates this lock."
        ),
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    supersedes = {
        "successor_id": "DASHBOARD_UI_V1_1",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "predecessor_status_at_supersession": predecessor_lock["status"],
        "predecessor_preserved_unchanged": True,
        "reason": lock["reason"],
        "checkpoint": "C034-UI-E2E",
    }
    supersedes_path = ROOT / "artifacts/DASHBOARD_UI_V1_1.supersedes.json"
    supersedes_path.write_text(
        json.dumps(supersedes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(hash_file(destination))
    print(hash_file(supersedes_path))


if __name__ == "__main__":
    main()
