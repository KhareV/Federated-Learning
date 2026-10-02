#!/usr/bin/env python3
"""Create the E2E_REPLAY_SOFTWARE_V1_2 successor lock (C032-NORM-RUNTIME).

The frozen E2E_REPLAY_SOFTWARE_V1_1 lock (predecessor) recorded the public replay semantic
digest produced by the DEFECTIVE (unnormalized) api/runtime.py. This checkpoint corrects that
defect (API_RUNTIME_V1_1) and re-runs the identical replay mechanics twice through the
corrected production app (scripts/run_replay_corrected_c032.py), confirming run1==run2
(determinism) and recording the new digest here. The predecessor lock is NEVER mutated in
place; its old digest is preserved historically as the superseded_unnormalized_runtime_digest
field and is explicitly NOT required to match the new one.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_LOCK_PATH = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_1.lock.json"
PREDECESSOR_ID = "E2E_REPLAY_SOFTWARE_V1_1"
PREDECESSOR_SHA_EXPECTED = "ff97c4d9b60d9695f1bc9bfc7a11a1629110a4274353f6071c468a565f3eee8d"


def main() -> None:
    predecessor_sha = hash_file(PREDECESSOR_LOCK_PATH)
    if predecessor_sha != PREDECESSOR_SHA_EXPECTED:
        raise RuntimeError(
            f"E2E_REPLAY_SOFTWARE_V1_1_PREDECESSOR_SHA_MISMATCH: expected "
            f"{PREDECESSOR_SHA_EXPECTED}, got {predecessor_sha}"
        )
    predecessor_lock = json.loads(PREDECESSOR_LOCK_PATH.read_text(encoding="utf-8"))

    reproducibility = json.loads(
        (ROOT / "reports/c032_norm_runtime/corrected_replay_reproducibility.json").read_text(
            encoding="utf-8"
        )
    )
    run_1 = json.loads(
        (ROOT / "reports/c032_norm_runtime/corrected_replay_run_1.json").read_text(
            encoding="utf-8"
        )
    )
    if not reproducibility["run_1_equals_run_2"]:
        raise RuntimeError("E2E_REPLAY_SOFTWARE_V1_2_NOT_REPRODUCIBLE")

    bound_paths = [
        path
        for path in predecessor_lock["bound_artifacts"]
        if path
        not in (
            "artifacts/API_RUNTIME_V1.lock.json",
            "artifacts/DASHBOARD_UI_V1_1.lock.json",
            "scripts/run_replay.py",
        )
    ] + [
        "artifacts/API_RUNTIME_V1_1.lock.json",
        "artifacts/DASHBOARD_UI_V1_2.lock.json",
        "scripts/run_replay.py",
        "scripts/run_replay_corrected_c032.py",
        "reports/c032_norm_runtime/corrected_replay_run_1.json",
        "reports/c032_norm_runtime/corrected_replay_run_2.json",
        "reports/c032_norm_runtime/corrected_replay_reproducibility.json",
        "reports/c032_norm_runtime/public_replay_impact.json",
        "reports/c032_norm_runtime/public_replay_impact.csv",
        "reports/c032_norm_runtime/downstream_impact_analysis.json",
    ]

    lock = {
        "lock_id": "E2E_REPLAY_SOFTWARE_V1_2",
        "status": "FROZEN_ENGINEERING_INTEGRATION",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "checkpoint": "C032-NORM-RUNTIME",
        "reason": (
            "re-run the deterministic public/sim software replay through the corrected "
            "API_RUNTIME_V1_1 (restores PREPROC_V1 PER_WINDOW_ZSCORE_V1 normalization before "
            "MODEL_V1/gateway inference); the predecessor's recorded digest reflected the "
            "defective unnormalized runtime and is preserved historically, not reproduced"
        ),
        "is_final_g21_lock": False,
        "g21_status": "NON_PASS_PENDING_T030_REAL_WEARABLE",
        "public_replay_id": predecessor_lock["public_replay_id"],
        "public_replay_manifest_sha256": predecessor_lock["public_replay_manifest_sha256"],
        "public_replay_npz_sha256": predecessor_lock["public_replay_npz_sha256"],
        "sim_replay_id": predecessor_lock["sim_replay_id"],
        "sim_replay_manifest_sha256": predecessor_lock["sim_replay_manifest_sha256"],
        "sim_replay_npz_sha256": predecessor_lock["sim_replay_npz_sha256"],
        "api_runtime_lock_id": "API_RUNTIME_V1_1",
        "api_runtime_v1_1_lock_sha256": hash_file(ROOT / "artifacts/API_RUNTIME_V1_1.lock.json"),
        "gateway_artifact_v1_lock_sha256": hash_file(
            ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
        ),
        "dashboard_ui_lock_id": "DASHBOARD_UI_V1_2",
        "dashboard_ui_lock_sha256": hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_2.lock.json"),
        "frontend_replay_controller_sha256": predecessor_lock["frontend_replay_controller_sha256"],
        "canonical_monitoring_route_sha256": predecessor_lock["canonical_monitoring_route_sha256"],
        "frontend_replay_bundle_sha256": predecessor_lock["frontend_replay_bundle_sha256"],
        "public_semantic_digest": run_1["public_semantic_digest"],
        "public_semantic_digest_unchanged_from_predecessor": (
            run_1["public_semantic_digest"] == predecessor_lock["public_semantic_digest"]
        ),
        "superseded_unnormalized_runtime_digest": predecessor_lock["public_semantic_digest"],
        "sim_semantic_digest": run_1["sim_semantic_digest"],
        "sim_semantic_digest_unchanged_from_predecessor": (
            run_1["sim_semantic_digest"] == predecessor_lock["sim_semantic_digest"]
        ),
        "sim_digest_unchanged_reason": (
            "WEARABLE_SIM_REPLAY_V1 windows are synthetically engineered already at "
            "population mean=0/std=1 (or all-zero -> UNUSABLE/422); PER_WINDOW_ZSCORE_V1 is "
            "near-identity on such input, so the sim digest is coincidentally unaffected by "
            "this defect class -- the public (real MITDB-derived) replay digest is the "
            "scientifically meaningful comparison and DOES change."
        ),
        "reproducibility_report_sha256": hash_file(
            ROOT / "reports/c032_norm_runtime/corrected_replay_reproducibility.json"
        ),
        "reproducibility_status": reproducibility["status"],
        "run_1_equals_run_2": reproducibility["run_1_equals_run_2"],
        "public_replay_impact_sha256": hash_file(
            ROOT / "reports/c032_norm_runtime/public_replay_impact.json"
        ),
        "model_id": predecessor_lock["model_id"],
        "preproc_id": predecessor_lock["preproc_id"],
        "calibration_id": predecessor_lock["calibration_id"],
        "alert_policy_id": predecessor_lock["alert_policy_id"],
        "claim_boundary": predecessor_lock["claim_boundary"],
        "no_new_canonical_freeze_registry_row": True,
        "change_control": predecessor_lock["change_control"],
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound_paths},
    }

    destination = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_2.lock.json"
    destination.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    supersedes = {
        "successor_id": "E2E_REPLAY_SOFTWARE_V1_2",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "predecessor_status_at_supersession": predecessor_lock["status"],
        "predecessor_preserved_unchanged": True,
        "predecessor_public_semantic_digest_preserved_historically": predecessor_lock[
            "public_semantic_digest"
        ],
        "reason": lock["reason"],
        "checkpoint": "C032-NORM-RUNTIME",
    }
    supersedes_path = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_2.supersedes.json"
    supersedes_path.write_text(
        json.dumps(supersedes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(hash_file(destination))
    print(hash_file(supersedes_path))


if __name__ == "__main__":
    main()
