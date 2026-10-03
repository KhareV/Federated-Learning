"""API_RUNTIME_V2: parallel RESEARCH runtime binding for POST /v1/infer-window.

Binds, and verifies at construction (fail closed): GATEWAY_ARTIFACT_V2 (FROZEN_RESEARCH_GATEWAY),
MODEL_V2_FINAL, CAL_V2 (temperature/threshold/identity read from the frozen artifact, never copied
into code), PREPROC_V1, ECG_HR_CONTEXT_V2, and ALERT_POLICY_V1 through the additive
ALERT_POLICY_V1_MODEL_V2_BINDING. It is NOT the operational default: the production runtime
(api.runtime.ProductionRuntime, MODEL_V1/GATEWAY_ARTIFACT_V1/CAL_V1) is untouched, and nothing
here is reachable from the default launch path.

The request `ecg` is the PREPROC_V1 filtered, amplitude-preserving window (NOT normalized). Like
API_RUNTIME_V1_1 (C032), this module applies the locked PER_WINDOW_ZSCORE_V1 normalization
exactly once, immediately before gateway inference, and routes the UNNORMALIZED array to
ECG_HR_CONTEXT_V2:

    filtered ECG --+--> estimate_ecg_hr  (amplitude-preserving)
                   +--> per-window z-score --> GATEWAY_ARTIFACT_V2 --> CAL_V2 wrapper
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from api.runtime import (
    ECG_HR_CANDIDATE_ID,
    InferenceOutcome,
    InputValidationError,
    RuntimeVerificationError,
    _verify_alert_policy,
    _verify_ecg_hr_context_lock,
    _verify_preproc_lock,
)
from deployment.gateway_v2 import ARTIFACT_ID, GatewayV2Runtime
from fusion.alert_policy_v2_binding import load_alert_policy_v2_binding
from fusion.episode_manager import AlertPolicy
from preprocessing.ecg_hr_context import ECGHRResult, estimate_hr
from preprocessing.windowing import (
    NORMALIZATION_EPSILON,
    WINDOW_SAMPLES,
    normalize_window_zscore,
)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ID = "API_RUNTIME_V2"
BOUND_MODEL_ID = "MODEL_V2_FINAL"
PREPROCESS_ID = "PREPROC_V1"


class ResearchRuntimeV2:
    """Satisfies `api.app.InferenceRuntime` (structurally) plus `bound_model_id`."""

    preprocess_id = PREPROCESS_ID
    runtime_id = RUNTIME_ID
    bound_model_id = BOUND_MODEL_ID

    def __init__(self, root: Path = ROOT, *, verify: str = "full") -> None:
        self.root = root
        _verify_preproc_lock(root)
        _verify_ecg_hr_context_lock(root)
        _verify_alert_policy(root)
        if verify == "full":
            from models.cal_v2_verify import verify_cal_v2
            from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2

            try:
                verify_cal_v2(root)
                verify_gateway_artifact_v2(root)
            except Exception as error:
                raise RuntimeVerificationError(f"API_RUNTIME_V2_UPSTREAM_VERIFICATION: {error}"
                                               ) from error
        elif verify != "manifest":
            raise RuntimeVerificationError("API_RUNTIME_V2_UNKNOWN_VERIFY_MODE")
        self.gateway = GatewayV2Runtime(root)  # manifest + artifact/source/CAL_V2 hash binding
        self.policy: AlertPolicy = load_alert_policy_v2_binding(root)
        calibration = json.loads((root / "artifacts/CAL_V2.json").read_text(encoding="utf-8"))
        self.calibration_patient_count: int = int(calibration["calibration_patient_count"])

    def infer(self, ecg_samples: list[float]) -> InferenceOutcome:
        window = np.asarray(ecg_samples, dtype=np.float64)
        if window.ndim != 1 or window.size != WINDOW_SAMPLES:
            raise InputValidationError(
                f"INFER_INPUT_LENGTH_MISMATCH: expected {WINDOW_SAMPLES} samples, "
                f"got shape {window.shape}")
        if not np.isfinite(window).all():
            raise InputValidationError("INFER_INPUT_NONFINITE")
        normalized = normalize_window_zscore(window, epsilon=NORMALIZATION_EPSILON)
        if not np.isfinite(normalized).all():
            raise InputValidationError("INFER_NORMALIZATION_OUTPUT_NONFINITE")
        result = self.gateway.infer(normalized.astype(np.float32).reshape(1, 1, -1))
        return InferenceOutcome(
            model_id=result.model_id,
            model_sha=self.gateway.model_sha,
            deployment_artifact_id=result.gateway_artifact_id,
            deployment_artifact_sha=self.gateway.artifact_sha,
            raw_probability=result.raw_probability,
            source_domain_calibrated_probability=result.source_domain_calibrated_probability,
            threshold=result.threshold,
            calibration_id=result.calibration_id,
            calibration_domain=result.calibration_domain,
            above_threshold=result.above_threshold,
        )

    def estimate_ecg_hr(self, ecg_samples: list[float], *, timestamp_us: int) -> ECGHRResult:
        array = np.asarray(ecg_samples, dtype=np.float64)
        return estimate_hr(array, timestamp_us=timestamp_us, candidate_id=ECG_HR_CANDIDATE_ID)


__all__ = ["ARTIFACT_ID", "BOUND_MODEL_ID", "RUNTIME_ID", "ResearchRuntimeV2"]
