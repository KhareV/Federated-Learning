#!/usr/bin/env python3
"""Create the DASHBOARD_UI_V1 component lock (T033).

Like API_RUNTIME_V1 (T032), this is a component lock, not a new canonical Fxx freeze row --
F15 remains reserved for RELEASE_V1 / G22. Binds every frontend source file the dashboard's
state/API contract depends on, plus the upstream API_RUNTIME_V1/API_SCHEMA_V1/OpenAPI locks it
consumes read-only.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

MONITORING_STATE_VOCABULARY = [
    "NORMAL_MONITORED_PATTERN",
    "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
    "RECHECK_SENSOR",
    "CONTEXT_UNAVAILABLE",
    "SYSTEM_ERROR",
]


def main() -> None:
    api_runtime_lock_text = (ROOT / "artifacts/API_RUNTIME_V1.lock.json").read_text(
        encoding="utf-8"
    )
    api_runtime_lock = json.loads(api_runtime_lock_text)

    bound_paths = [
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/vite.config.ts",
        "frontend/vitest.config.ts",
        "frontend/src/lib/api/nhm-v1.ts",
        "frontend/src/lib/dashboard/state-presentation.ts",
        "frontend/src/lib/dashboard/session.svelte.ts",
        "frontend/src/lib/dashboard/demo-window.ts",
        "frontend/src/lib/dashboard/fixtures.ts",
        "frontend/src/routes/monitoring/+page.svelte",
        "contracts/API_SCHEMA_V1.json",
        "contracts/openapi_v1.json",
        "artifacts/API_RUNTIME_V1.lock.json",
        "reports/t033/frontend_path_mapping.json",
        "reports/t033/frontend_legacy_audit.json",
        "reports/t033/frontend_claim_reconciliation.json",
    ]

    lock = {
        "lock_id": "DASHBOARD_UI_V1",
        "status": "FROZEN_ENGINEERING_INTERFACE",
        "logical_subsystem": "dashboard",
        "repository_path": "frontend/",
        "source_plan_path": "dashboard/",
        "mapping_reason": "explicit project repository convention (see T033 task instructions)",
        "framework": "SvelteKit",
        "framework_version": "2.70.3",
        "svelte_version": "5.57.0",
        "vite_version": "6.4.3",
        "route": "/monitoring",
        "api_route_consumed": "POST /v1/infer-window",
        "contract_version": "API_SCHEMA_V1",
        "api_runtime_v1_lock_sha256": hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json"),
        "api_schema_v1_sha256": hash_file(ROOT / "contracts/API_SCHEMA_V1.json"),
        "openapi_v1_sha256": hash_file(ROOT / "contracts/openapi_v1.json"),
        "gateway_artifact_lock_sha256": api_runtime_lock["bound_artifacts"][
            "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
        ],
        "monitoring_state_vocabulary": MONITORING_STATE_VOCABULARY,
        "required_wording": {
            "NORMAL_MONITORED_PATTERN": "Normal monitored pattern",
            "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN": (
                "Potential SVF-associated ECG pattern -- Not a diagnosis."
            ),
            "RECHECK_SENSOR": "Recheck sensor / signal quality",
            "CONTEXT_UNAVAILABLE": (
                "Context unavailable (PPG/SpO2); ECG result retained when valid"
            ),
            "SYSTEM_ERROR": "Technical system error -- monitoring result unavailable",
        },
        "calibration_metadata_required": [
            "calibration_domain",
            "calibration_patient_count",
            "calibration_id",
            "alert_policy_id",
            "threshold",
        ],
        "research_only_panel_required": True,
        "persistent_panels": [
            "LIVE WAVEFORMS",
            "SIGNAL QUALITY",
            "CURRENT MONITORING STATE",
            "TECHNICAL METADATA",
        ],
        "no_new_canonical_freeze_row": True,
        "change_control": (
            "Changing the frontend API client, state-presentation mapping, or the /monitoring "
            "route's panel structure requires a controlled DASHBOARD_UI_V2 and invalidates this "
            "lock."
        ),
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/DASHBOARD_UI_V1.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(destination))


if __name__ == "__main__":
    main()
