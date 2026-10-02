#!/usr/bin/env python3
"""Create the DASHBOARD_UI_V1_2 successor lock (C032-NORM-RUNTIME).

The frozen DASHBOARD_UI_V1_1 lock (predecessor) directly binds contracts/openapi_v1.json,
which this checkpoint legitimately regenerated (api/schemas.py::ECGWindow docstring
correction -- no frontend code, no API contract, no rendering change). Per the C032-NORM-
RUNTIME directive, the predecessor lock is NEVER mutated in place -- this is an ADDITIVE
successor. No frontend file changes; this lock exists purely to re-pin the updated
openapi_v1.json and the new API_RUNTIME_V1_1 it now documents.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_LOCK_PATH = ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json"
PREDECESSOR_ID = "DASHBOARD_UI_V1_1"
PREDECESSOR_SHA_EXPECTED = "39066bdaa7b54a11b1895ae659991ba441c7511d19822ad492fb744d7a903e19"


def main() -> None:
    predecessor_sha = hash_file(PREDECESSOR_LOCK_PATH)
    if predecessor_sha != PREDECESSOR_SHA_EXPECTED:
        raise RuntimeError(
            f"DASHBOARD_UI_V1_1_PREDECESSOR_SHA_MISMATCH: expected "
            f"{PREDECESSOR_SHA_EXPECTED}, got {predecessor_sha}"
        )
    predecessor_lock = json.loads(PREDECESSOR_LOCK_PATH.read_text(encoding="utf-8"))

    api_runtime_v1_1 = json.loads(
        (ROOT / "artifacts/API_RUNTIME_V1_1.lock.json").read_text(encoding="utf-8")
    )

    bound_paths = [
        path
        for path in predecessor_lock["bound_artifacts"]
        if path not in ("artifacts/API_RUNTIME_V1.lock.json",)
    ] + ["artifacts/API_RUNTIME_V1_1.lock.json"]

    lock = {
        "lock_id": "DASHBOARD_UI_V1_2",
        "status": "FROZEN_ENGINEERING_INTERFACE",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "checkpoint": "C032-NORM-RUNTIME",
        "reason": (
            "re-pin contracts/openapi_v1.json (regenerated after the api/schemas.py::"
            "ECGWindow docstring correction) and the new API_RUNTIME_V1_1 it documents -- "
            "no frontend source file changed"
        ),
        "scientific_state_semantics_changed": False,
        "state_wording_changed": False,
        "api_contract_changed": False,
        "frontend_source_changed": False,
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
        "api_runtime_lock_id": "API_RUNTIME_V1_1",
        "api_runtime_v1_1_lock_sha256": hash_file(ROOT / "artifacts/API_RUNTIME_V1_1.lock.json"),
        "api_schema_v1_sha256": hash_file(ROOT / "contracts/API_SCHEMA_V1.json"),
        "openapi_v1_sha256": hash_file(ROOT / "contracts/openapi_v1.json"),
        "gateway_artifact_lock_sha256": api_runtime_v1_1["gateway_artifact_lock_sha256"],
        "monitoring_state_vocabulary": predecessor_lock["monitoring_state_vocabulary"],
        "required_wording": predecessor_lock["required_wording"],
        "calibration_metadata_required": predecessor_lock["calibration_metadata_required"],
        "research_only_panel_required": predecessor_lock["research_only_panel_required"],
        "persistent_panels": predecessor_lock["persistent_panels"],
        "recorded_replay_entry_convention": predecessor_lock["recorded_replay_entry_convention"],
        "recorded_replay_controller": predecessor_lock["recorded_replay_controller"],
        "recorded_replay_bundle_generator": predecessor_lock["recorded_replay_bundle_generator"],
        "no_new_canonical_freeze_row": True,
        "change_control": predecessor_lock["change_control"],
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    supersedes = {
        "successor_id": "DASHBOARD_UI_V1_2",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "predecessor_status_at_supersession": predecessor_lock["status"],
        "predecessor_preserved_unchanged": True,
        "reason": lock["reason"],
        "checkpoint": "C032-NORM-RUNTIME",
    }
    supersedes_path = ROOT / "artifacts/DASHBOARD_UI_V1_2.supersedes.json"
    supersedes_path.write_text(
        json.dumps(supersedes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(hash_file(destination))
    print(hash_file(supersedes_path))


if __name__ == "__main__":
    main()
