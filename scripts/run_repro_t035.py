#!/usr/bin/env python3
"""T035-REPRO CPU smoke: proves the clean-environment software stack actually runs, without
retraining, tuning, held-out re-evaluation, a developer-local data path, or any manual edit.

Exercises, in order: environment import, MODEL_V1 frozen-checkpoint load, PREPROC_V1 contract
verification, GATEWAY_ARTIFACT_V1 load + frozen test-vector inference, CAL_V1/ALERT_POLICY_V1/
ECG_HR_CONTEXT_V2 load (via ProductionRuntime construction, which fails closed on any mismatch),
one deterministic PUBLIC_ECG_REPLAY_V1 replay run through the corrected production app, and a
structural reachability check of the committed frontend replay bundle/build output. No target
labels are read anywhere in this script.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from api.runtime import ProductionRuntime
from deployment.runtime import GatewayModelRuntime
from models.model_freeze import verify_frozen_model_v1
from nhm.hashing import hash_file
from nhm.reproducibility import capture_execution_identity
from preprocessing.freeze import verify_preproc_freeze
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore
from scripts.run_replay_corrected_t035 import run_once as run_corrected_replay

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/t035"


def _model_fixed_vector_check() -> dict[str, object]:
    gateway = GatewayModelRuntime(ROOT, ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts")
    fixture = np.load(ROOT / "tests/fixtures/model_v1_test_vector.npz")
    deltas = []
    for index in range(fixture["raw_windows_float64"].shape[0]):
        raw = fixture["raw_windows_float64"][index]
        normalized = normalize_window_zscore(raw, epsilon=NORMALIZATION_EPSILON)
        result = gateway.infer(normalized.astype(np.float32).reshape(1, 1, -1))
        expected = float(fixture["expected_logits_float32"][index][0])
        deltas.append(abs(result.raw_logit - expected))
    return {
        "vectors_checked": int(fixture["raw_windows_float64"].shape[0]),
        "max_abs_logit_delta": max(deltas),
        "status": "PASS" if max(deltas) < 1e-3 else "FAIL",
    }


def _frontend_reachability_check() -> dict[str, object]:
    bundle_path = ROOT / "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    checks = {
        "bundle_exists": bundle_path.exists(),
        "bundle_is_valid_json": isinstance(bundle, dict),
        "bundle_has_events": len(bundle.get("events", [])) == 12,
        "monitoring_route_exists": (
            ROOT / "frontend/src/routes/monitoring/+page.svelte"
        ).exists(),
        "replay_controller_exists": (
            ROOT / "frontend/src/lib/dashboard/replay.ts"
        ).exists(),
    }
    return {"checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"}


def main() -> None:
    start = time.monotonic()
    identity = capture_execution_identity(ROOT, config_path=None, dependency_snapshot_path=None)

    report: dict[str, object] = {
        "report_version": "1.0",
        "task_id": "T035",
        "gate": "G20",
        "git_commit": identity["git_commit"],
        "git_dirty": identity["git_dirty"],
        "python_version": identity["python_version"],
        "steps": {},
    }

    report["steps"]["environment_import"] = {"status": "PASS"}

    model_result = verify_frozen_model_v1(ROOT)
    report["steps"]["model_v1_load"] = {
        "status": model_result["status"],
        "maximum_absolute_error": model_result["maximum_absolute_error"],
    }

    preproc_result = verify_preproc_freeze(ROOT)
    report["steps"]["preproc_v1_contract"] = {
        "status": preproc_result["status"],
        "bound_artifact_count": preproc_result["bound_artifact_count"],
    }

    report["steps"]["gateway_and_model_fixed_vector"] = _model_fixed_vector_check()

    runtime = ProductionRuntime(ROOT)
    report["steps"]["production_runtime_construction"] = {
        "status": "PASS",
        "note": (
            "ProductionRuntime() fails closed at construction if PREPROC_V1, "
            "ECG_HR_CONTEXT_V2, ALERT_POLICY_V1, or GATEWAY_ARTIFACT_V1 mismatch -- "
            "successful construction is itself the pass condition."
        ),
        "calibration_patient_count": runtime.calibration_patient_count,
    }

    replay_result = run_corrected_replay("t035_smoke_replay", speed=0.0)
    report["steps"]["deterministic_replay_fixture"] = {
        "status": replay_result["status"],
        "public_semantic_digest": replay_result["public_semantic_digest"],
        "public_200": replay_result["public_200"],
    }

    report["steps"]["frontend_replay_reachability"] = _frontend_reachability_check()

    report["labels_used"] = False
    report["retraining_performed"] = False
    report["tuning_performed"] = False
    report["held_out_reevaluation_performed"] = False
    report["developer_local_data_path_required"] = False
    report["manual_edit_required"] = False
    report["duration_seconds"] = round(time.monotonic() - start, 3)
    report["status"] = (
        "PASS"
        if all(step["status"] == "PASS" for step in report["steps"].values())
        else "FAIL"
    )

    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "cpu_smoke_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["artifact_sha256"] = hash_file(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
