#!/usr/bin/env python3
"""Create the DASHBOARD_UI_V1_3 successor lock (T035-REPRO).

The frozen DASHBOARD_UI_V1_2 lock (predecessor) directly binds frontend/package.json and
frontend/package-lock.json, both legitimately changed by this checkpoint: a clean `npm ci`
from the committed lockfile (run from a genuinely fresh clone, outside the developer's home
directory tree) surfaced 13 real svelte-check TypeScript errors ("Cannot find module
'node:fs'"/'__dirname' undefined) that the developer's working tree had been silently hiding
by accidentally resolving an UNRELATED, undeclared, machine-local @types/node package from a
stray node_modules directory several levels up the developer's home directory (a hidden,
non-portable dependency -- see reports/t035/hidden_dependency_audit.json finding F9). Fixed by
declaring @types/node as an explicit, exact-pinned devDependency. No frontend application
source file changed; this is a dependency-declaration reproducibility fix only.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_LOCK_PATH = ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json"
PREDECESSOR_ID = "DASHBOARD_UI_V1_2"
PREDECESSOR_SHA_EXPECTED = "62341027cf4723e221ea58facc66bf2dca65b34fe1e513209bf887c407393382"


def main() -> None:
    predecessor_sha = hash_file(PREDECESSOR_LOCK_PATH)
    if predecessor_sha != PREDECESSOR_SHA_EXPECTED:
        raise RuntimeError(
            f"DASHBOARD_UI_V1_2_PREDECESSOR_SHA_MISMATCH: expected "
            f"{PREDECESSOR_SHA_EXPECTED}, got {predecessor_sha}"
        )
    predecessor_lock = json.loads(PREDECESSOR_LOCK_PATH.read_text(encoding="utf-8"))

    bound_paths = list(predecessor_lock["bound_artifacts"])

    lock = {
        "lock_id": "DASHBOARD_UI_V1_3",
        "status": "FROZEN_ENGINEERING_INTERFACE",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "checkpoint": "T035-REPRO",
        "reason": (
            "declare @types/node as an explicit devDependency (frontend/package.json, "
            "frontend/package-lock.json) so `npm ci` + svelte-check is reproducible from a "
            "genuinely clean checkout, without relying on an accidental ambient @types/node "
            "resolved from a stray unrelated node_modules directory on the developer machine"
        ),
        "scientific_state_semantics_changed": False,
        "state_wording_changed": False,
        "api_contract_changed": False,
        "frontend_application_source_changed": False,
        "frontend_dependency_declaration_changed": True,
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
        "api_runtime_lock_id": predecessor_lock["api_runtime_lock_id"],
        "api_runtime_v1_1_lock_sha256": predecessor_lock["api_runtime_v1_1_lock_sha256"],
        "api_schema_v1_sha256": predecessor_lock["api_schema_v1_sha256"],
        "openapi_v1_sha256": predecessor_lock["openapi_v1_sha256"],
        "gateway_artifact_lock_sha256": predecessor_lock["gateway_artifact_lock_sha256"],
        "monitoring_state_vocabulary": predecessor_lock["monitoring_state_vocabulary"],
        "required_wording": predecessor_lock["required_wording"],
        "calibration_metadata_required": predecessor_lock["calibration_metadata_required"],
        "research_only_panel_required": predecessor_lock["research_only_panel_required"],
        "persistent_panels": predecessor_lock["persistent_panels"],
        "recorded_replay_entry_convention": predecessor_lock["recorded_replay_entry_convention"],
        "recorded_replay_controller": predecessor_lock["recorded_replay_controller"],
        "recorded_replay_bundle_generator": predecessor_lock["recorded_replay_bundle_generator"],
        "types_node_added": {
            "package": "@types/node",
            "version": "26.6.4",
            "pinned_exact": True,
        },
        "clean_checkout_svelte_check_errors_before_fix": 13,
        "clean_checkout_svelte_check_errors_after_fix": 0,
        "no_new_canonical_freeze_row": True,
        "change_control": predecessor_lock["change_control"],
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/DASHBOARD_UI_V1_3.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    supersedes = {
        "successor_id": "DASHBOARD_UI_V1_3",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "predecessor_status_at_supersession": predecessor_lock["status"],
        "predecessor_preserved_unchanged": True,
        "reason": lock["reason"],
        "checkpoint": "T035-REPRO",
    }
    supersedes_path = ROOT / "artifacts/DASHBOARD_UI_V1_3.supersedes.json"
    supersedes_path.write_text(
        json.dumps(supersedes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(hash_file(destination))
    print(hash_file(supersedes_path))


if __name__ == "__main__":
    main()
