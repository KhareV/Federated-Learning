#!/usr/bin/env python3
"""Create the E2E_REPLAY_SOFTWARE_V1 component lock (T034).

This is a component lock (like API_RUNTIME_V1/DASHBOARD_UI_V1), not the final real-wearable
G21 closure lock. Status FROZEN_ENGINEERING_INTEGRATION -- an explicit, lesser status than
FROZEN_ENGINEERING_INTERFACE, signaling this is integration-demo evidence, not a production
interface contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    api_runtime_lock = json.loads(
        (ROOT / "artifacts/API_RUNTIME_V1.lock.json").read_text(encoding="utf-8")
    )
    public_manifest = json.loads(
        (ROOT / "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    sim_manifest = json.loads(
        (ROOT / "tests/fixtures/e2e/WEARABLE_SIM_REPLAY_V1.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    replay_run_1 = json.loads(
        (ROOT / "reports/t034/replay_run_1.json").read_text(encoding="utf-8")
    )
    reproducibility = json.loads(
        (ROOT / "reports/t034/reproducibility.json").read_text(encoding="utf-8")
    )
    ci_deferral = json.loads(
        (ROOT / "reports/t034/ci_deferral.json").read_text(encoding="utf-8")
    )

    bound_paths = [
        "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.npz",
        "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.manifest.json",
        "tests/fixtures/e2e/WEARABLE_SIM_REPLAY_V1.npz",
        "tests/fixtures/e2e/WEARABLE_SIM_REPLAY_V1.manifest.json",
        "scripts/run_replay.py",
        "scripts/select_replay_windows_t034.py",
        "scripts/build_replay_fixture_t034.py",
        "scripts/build_wearable_sim_replay_t034.py",
        "scripts/compare_replay_runs_t034.py",
        "artifacts/API_RUNTIME_V1.lock.json",
        "artifacts/GATEWAY_ARTIFACT_V1.lock.json",
        "artifacts/DASHBOARD_UI_V1.lock.json",
        "frontend/src/lib/dashboard/replay.ts",
        "reports/t034/replay_selection.json",
        "reports/t034/reproducibility.json",
        "reports/t034/ci_deferral.json",
    ]

    lock = {
        "lock_id": "E2E_REPLAY_SOFTWARE_V1",
        "status": "FROZEN_ENGINEERING_INTEGRATION",
        "is_final_g21_lock": False,
        "public_replay_id": "PUBLIC_ECG_REPLAY_V1",
        "public_replay_manifest_sha256": hash_file(
            ROOT / "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.manifest.json"
        ),
        "public_replay_npz_sha256": public_manifest["npz_sha256"],
        "sim_replay_id": "WEARABLE_SIM_REPLAY_V1",
        "sim_replay_manifest_sha256": hash_file(
            ROOT / "tests/fixtures/e2e/WEARABLE_SIM_REPLAY_V1.manifest.json"
        ),
        "sim_replay_npz_sha256": sim_manifest["npz_sha256"],
        "api_runtime_v1_lock_sha256": hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json"),
        "gateway_artifact_v1_lock_sha256": hash_file(
            ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
        ),
        "dashboard_ui_v1_lock_sha256": hash_file(ROOT / "artifacts/DASHBOARD_UI_V1.lock.json"),
        "dashboard_ui_v1_status": "COMPATIBLE_UNCHANGED",
        "frontend_replay_adapter_sha256": hash_file(
            ROOT / "frontend/src/lib/dashboard/replay.ts"
        ),
        "public_semantic_digest": replay_run_1["public_semantic_digest"],
        "sim_semantic_digest": replay_run_1["sim_semantic_digest"],
        "dashboard_projection_semantic_digest_source": (
            "reports/t034/public_dashboard_projection.jsonl"
        ),
        "reproducibility_report_sha256": hash_file(ROOT / "reports/t034/reproducibility.json"),
        "reproducibility_status": reproducibility["status"],
        "ci_deferral_policy_sha256": hash_file(ROOT / "reports/t034/ci_deferral.json"),
        "ci_deferral_policy": ci_deferral["policy"],
        "model_id": api_runtime_lock["model_id"],
        "preproc_id": api_runtime_lock["preproc_id"],
        "calibration_id": api_runtime_lock["calibration_id"],
        "alert_policy_id": api_runtime_lock["alert_policy_id"],
        "claim_boundary": (
            "A deterministic recorded public-ECG/software replay traversed the frozen "
            "MODEL_V1 gateway, typed API, and dashboard integration path, and repeated with "
            "the same semantic outputs. The same software interfaces accept deterministic "
            "simulated wearable-format engineering replay (WEARABLE_SIM_REPLAY_V1). NOT real "
            "wearable integration, NOT G16 PASS, NOT G21 PASS, NOT live hardware, NOT "
            "wearable-domain calibrated, NOT a clinical or diagnostic claim."
        ),
        "g21_status": "NON_PASS_PENDING_T030_REAL_WEARABLE",
        "change_control": (
            "Changing scripts/run_replay.py, the replay fixtures, or the frontend replay "
            "adapter requires a controlled E2E_REPLAY_SOFTWARE_V2 and invalidates this lock."
        ),
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(destination))


if __name__ == "__main__":
    main()
