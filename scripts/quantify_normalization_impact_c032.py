#!/usr/bin/env python3
"""C032-NORM-RUNTIME Section 9: quantify the T032 normalization defect across all 12
PUBLIC_ECG_REPLAY_V1 windows.

For each window, computes BOTH:
  - OLD_INVALID_PATH: the defective behaviour actually shipped at T032/T034/C034 -- the raw
    filtered (but unnormalized) window handed directly to GatewayModelRuntime.infer().
  - CORRECT_LOCKED_PATH: the locked PREPROC_V1 PER_WINDOW_ZSCORE_V1 normalization applied
    before GatewayModelRuntime.infer(), exactly as T015-T031 already do.

ALERT_POLICY_V1 (fusion.episode_manager.AlertEpisodeManager) is then replayed *sequentially*,
once, over the CORRECT_LOCKED_PATH outputs only -- the old (invalid) state sequence is not
reproduced or preserved. No target labels are read or used anywhere in this script.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from deployment.runtime import GatewayModelRuntime
from fusion.episode_manager import AlertEpisodeManager, load_alert_policy
from fusion.state_machine import FusionObservation
from nhm.hashing import hash_file
from preprocessing.ecg_hr_context import estimate_hr
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/e2e"
OUT = ROOT / "reports/c032_norm_runtime"
ECG_HR_CANDIDATE_ID = "WFDB_XQRS_V1"
SESSION_ID = "C032-NORM-RUNTIME-PUBLIC-REPLAY"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def _run_gateway(runtime: GatewayModelRuntime, window: np.ndarray) -> dict:
    array = np.asarray(window, dtype=np.float32).reshape(1, 1, -1)
    result = runtime.infer(array)
    return {
        "raw_logit": result.raw_logit,
        "raw_probability": float(_sigmoid(result.raw_logit)),
        "source_domain_calibrated_probability": result.calibrated_probability,
        "threshold": result.threshold,
        "above_threshold": result.above_threshold,
    }


def main() -> None:
    manifest = json.loads(
        (FIXTURE_DIR / "PUBLIC_ECG_REPLAY_V1.manifest.json").read_text(encoding="utf-8")
    )
    samples = np.load(FIXTURE_DIR / "PUBLIC_ECG_REPLAY_V1.npz")["samples"]
    windows = sorted(manifest["selection"]["windows"], key=lambda w: w["sequence_index"])

    gateway = GatewayModelRuntime(ROOT, ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts")
    policy = load_alert_policy(ROOT)
    episode_manager = AlertEpisodeManager(policy)
    episode_manager.reset(session_id=SESSION_ID)

    rows: list[dict] = []
    for window in windows:
        index = window["sequence_index"]
        raw = np.asarray(samples[index], dtype=np.float64)

        old_invalid = _run_gateway(gateway, raw)
        normalized = normalize_window_zscore(raw, epsilon=NORMALIZATION_EPSILON)
        if not np.isfinite(normalized).all():
            raise RuntimeError(f"NORMALIZATION_OUTPUT_NONFINITE:index={index}")
        correct_locked = _run_gateway(gateway, normalized)

        hr_result = estimate_hr(
            raw, timestamp_us=window["prediction_timestamp_us"], candidate_id=ECG_HR_CANDIDATE_ID
        )

        observation = FusionObservation(
            session_id=SESSION_ID,
            timestamp_us=window["prediction_timestamp_us"],
            source_domain_calibrated_probability=correct_locked[
                "source_domain_calibrated_probability"
            ],
            ecg_quality="VALID",
            ppg_quality=None,
            spo2_pct=None,
            spo2_valid=False,
            hr_ecg_bpm=hr_result.hr_ecg_bpm,
            hr_ecg_valid=hr_result.valid,
            pr_ppg_bpm=None,
            pr_ppg_valid=False,
            model_id=policy.model_id,
            calibration_id=policy.calibration_id,
        )
        decision = episode_manager.process(observation)

        delta_raw_logit = correct_locked["raw_logit"] - old_invalid["raw_logit"]
        delta_calibrated = (
            correct_locked["source_domain_calibrated_probability"]
            - old_invalid["source_domain_calibrated_probability"]
        )
        rows.append(
            {
                "sequence_index": index,
                "window_id": window["example_id"],
                "prediction_timestamp_us": window["prediction_timestamp_us"],
                "old_invalid_raw_logit": old_invalid["raw_logit"],
                "old_invalid_raw_probability": old_invalid["raw_probability"],
                "old_invalid_calibrated_probability": old_invalid[
                    "source_domain_calibrated_probability"
                ],
                "old_invalid_above_threshold": old_invalid["above_threshold"],
                "correct_locked_raw_logit": correct_locked["raw_logit"],
                "correct_locked_raw_probability": correct_locked["raw_probability"],
                "correct_locked_calibrated_probability": correct_locked[
                    "source_domain_calibrated_probability"
                ],
                "correct_locked_above_threshold": correct_locked["above_threshold"],
                "threshold": correct_locked["threshold"],
                "delta_raw_logit": delta_raw_logit,
                "delta_calibrated_probability": delta_calibrated,
                "decision_changed": (
                    old_invalid["above_threshold"] != correct_locked["above_threshold"]
                ),
                "corrected_monitoring_state": decision.monitoring_state,
                "corrected_alert_policy_id": decision.alert_policy_id,
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "public_replay_impact.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "fixture_id": "PUBLIC_ECG_REPLAY_V1",
        "window_count": len(rows),
        "normalization_helper": "preprocessing.windowing.normalize_window_zscore",
        "epsilon": NORMALIZATION_EPSILON,
        "alert_policy_id": policy.policy_id,
        "labels_used": False,
        "old_path_description": (
            "Raw PREPROC_V1-filtered-but-unnormalized window handed directly to "
            "GatewayModelRuntime.infer() -- reproduces the defect actually shipped by "
            "api/runtime.py::ProductionRuntime.infer() at T032/T034/C034."
        ),
        "correct_path_description": (
            "preprocessing.windowing.normalize_window_zscore(window) applied before "
            "GatewayModelRuntime.infer() -- the locked PREPROC_V1 PER_WINDOW_ZSCORE_V1 "
            "contract, identical to the normalization already applied by T015-T031."
        ),
        "windows_with_decision_change": sum(1 for row in rows if row["decision_changed"]),
        "max_abs_delta_raw_logit": max(abs(row["delta_raw_logit"]) for row in rows),
        "max_abs_delta_calibrated_probability": max(
            abs(row["delta_calibrated_probability"]) for row in rows
        ),
        "corrected_monitoring_state_sequence": [
            row["corrected_monitoring_state"] for row in rows
        ],
        "old_state_sequence_preserved": False,
        "gateway_artifact_sha256": hash_file(
            ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
        ),
        "rows": rows,
        "status": "PASS",
    }
    (OUT / "public_replay_impact.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
