#!/usr/bin/env python3
"""Create the E2E_REPLAY_SOFTWARE_V1_1 successor lock (C034-UI-E2E).

The frozen E2E_REPLAY_SOFTWARE_V1 lock (predecessor) binds frontend/src/lib/dashboard/
replay.ts and scripts/run_replay.py, both modified by this corrective checkpoint (full
2500-sample canonical replay wiring; pointing at the DASHBOARD_UI_V1_1 successor verifier).
Per Section 27, the predecessor lock is NEVER mutated in place -- this is an ADDITIVE
successor, still NOT the final real-wearable G21 closure lock.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_LOCK_PATH = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1.lock.json"
PREDECESSOR_ID = "E2E_REPLAY_SOFTWARE_V1"
PREDECESSOR_SHA_EXPECTED = "fbb76813214c926230dbdc12db218557ebc696c968025fd8c20b3de0d59f25ec"


def main() -> None:
    predecessor_sha = hash_file(PREDECESSOR_LOCK_PATH)
    if predecessor_sha != PREDECESSOR_SHA_EXPECTED:
        raise RuntimeError(
            f"E2E_REPLAY_SOFTWARE_V1_PREDECESSOR_SHA_MISMATCH: expected "
            f"{PREDECESSOR_SHA_EXPECTED}, got {predecessor_sha}"
        )
    predecessor_lock = json.loads(PREDECESSOR_LOCK_PATH.read_text(encoding="utf-8"))

    replay_run_1 = json.loads(
        (ROOT / "reports/c034_ui_e2e/replay_run_1.json").read_text(encoding="utf-8")
    )
    reproducibility = json.loads(
        (ROOT / "reports/c034_ui_e2e/reproducibility.json").read_text(encoding="utf-8")
    )
    ci_deferral = json.loads(
        (ROOT / "reports/t034/ci_deferral.json").read_text(encoding="utf-8")
    )

    bound_paths = [
        "artifacts/API_RUNTIME_V1.lock.json",
        "artifacts/DASHBOARD_UI_V1_1.lock.json",
        "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
        "frontend/src/lib/dashboard/replay.ts",
        "frontend/src/routes/monitoring/+page.svelte",
        "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json",
        "scripts/run_replay.py",
        "scripts/select_replay_windows_t034.py",
        "scripts/build_replay_fixture_t034.py",
        "scripts/build_wearable_sim_replay_t034.py",
        "scripts/build_frontend_replay_bundle_c034.py",
        "scripts/run_e2e_dashboard_demo_c034.py",
        "reports/t034/ci_deferral.json",
        "reports/c034_ui_e2e/replay_run_1.json",
        "reports/c034_ui_e2e/reproducibility.json",
        "reports/c034_ui_e2e/rendered_dashboard_test.json",
        "reports/c034_ui_e2e/one_command_demo_audit.json",
        "reports/c034_ui_e2e/screenshot_status.json",
        "reports/c034_ui_e2e/production_route_binding.json",
        "reports/c034_ui_e2e/waveform_binding.json",
        "reports/c034_ui_e2e/scope_audit.json",
        "reports/c034_ui_e2e/run_manifest.json",
        "reports/c034_ui_e2e/entry_audit.json",
        "reports/c034_ui_e2e/t002_historical_evidence_audit.json",
        "reports/c034_ui_e2e/model_input_semantics.json",
        "reports/c034_ui_e2e/replay_eligibility_audit.json",
        "reports/c034_ui_e2e/frontend_replay_bundle.json",
        "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.manifest.json",
        "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.npz",
        "tests/fixtures/e2e/WEARABLE_SIM_REPLAY_V1.manifest.json",
        "tests/fixtures/e2e/WEARABLE_SIM_REPLAY_V1.npz",
    ]

    lock = {
        "lock_id": "E2E_REPLAY_SOFTWARE_V1_1",
        "status": "FROZEN_ENGINEERING_INTEGRATION",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "reason": (
            "wire full 2500-sample canonical replay into the rendered /monitoring dashboard "
            "route (C034-UI-E2E)"
        ),
        "is_final_g21_lock": False,
        "g21_status": "NON_PASS_PENDING_T030_REAL_WEARABLE",
        "public_replay_id": predecessor_lock["public_replay_id"],
        "public_replay_manifest_sha256": predecessor_lock["public_replay_manifest_sha256"],
        "public_replay_npz_sha256": predecessor_lock["public_replay_npz_sha256"],
        "sim_replay_id": predecessor_lock["sim_replay_id"],
        "sim_replay_manifest_sha256": predecessor_lock["sim_replay_manifest_sha256"],
        "sim_replay_npz_sha256": predecessor_lock["sim_replay_npz_sha256"],
        "api_runtime_v1_lock_sha256": hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json"),
        "gateway_artifact_v1_lock_sha256": hash_file(
            ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
        ),
        "dashboard_ui_lock_id": "DASHBOARD_UI_V1_1",
        "dashboard_ui_lock_sha256": hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_1.lock.json"),
        "frontend_replay_controller_sha256": hash_file(
            ROOT / "frontend/src/lib/dashboard/replay.ts"
        ),
        "canonical_monitoring_route_sha256": hash_file(
            ROOT / "frontend/src/routes/monitoring/+page.svelte"
        ),
        "frontend_replay_bundle_sha256": hash_file(
            ROOT / "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json"
        ),
        "public_semantic_digest": replay_run_1["public_semantic_digest"],
        "public_semantic_digest_unchanged_from_predecessor": (
            replay_run_1["public_semantic_digest"] == predecessor_lock["public_semantic_digest"]
        ),
        "sim_semantic_digest": replay_run_1["sim_semantic_digest"],
        "reproducibility_report_sha256": hash_file(
            ROOT / "reports/c034_ui_e2e/reproducibility.json"
        ),
        "reproducibility_status": reproducibility["status"],
        "rendered_integration_test_evidence_sha256": hash_file(
            ROOT / "reports/c034_ui_e2e/rendered_dashboard_test.json"
        ),
        "one_command_demo_audit_sha256": hash_file(
            ROOT / "reports/c034_ui_e2e/one_command_demo_audit.json"
        ),
        "screenshot_status_sha256": hash_file(
            ROOT / "reports/c034_ui_e2e/screenshot_status.json"
        ),
        "ci_deferral_policy_sha256": hash_file(ROOT / "reports/t034/ci_deferral.json"),
        "ci_deferral_policy": ci_deferral["policy"],
        "model_id": predecessor_lock["model_id"],
        "preproc_id": predecessor_lock["preproc_id"],
        "calibration_id": predecessor_lock["calibration_id"],
        "alert_policy_id": predecessor_lock["alert_policy_id"],
        "claim_boundary": predecessor_lock["claim_boundary"],
        "no_new_canonical_freeze_registry_row": True,
        "change_control": (
            "Changing scripts/run_replay.py, the replay fixtures, the frontend replay "
            "controller, or the canonical monitoring route's replay wiring requires a further "
            "controlled successor and invalidates this lock."
        ),
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_1.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    supersedes = {
        "successor_id": "E2E_REPLAY_SOFTWARE_V1_1",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "predecessor_status_at_supersession": predecessor_lock["status"],
        "predecessor_preserved_unchanged": True,
        "reason": lock["reason"],
        "checkpoint": "C034-UI-E2E",
    }
    supersedes_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_1.supersedes.json"
    supersedes_path.write_text(
        json.dumps(supersedes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(hash_file(destination))
    print(hash_file(supersedes_path))


if __name__ == "__main__":
    main()
