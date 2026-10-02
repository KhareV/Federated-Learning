"""Production runtime bindings for POST /v1/infer-window.

Binds, and verifies at construction time, every frozen artifact the production route
consumes: GATEWAY_ARTIFACT_V1 (F14), MODEL_V1/CAL_V1 (via GatewayModelRuntime), PREPROC_V1
(F06), ECG_HR_CONTEXT_V2, and ALERT_POLICY_V1. Fails closed -- raises RuntimeVerificationError
rather than serving a partially-verified app. Imports no dataset loader, training code,
calibration-fitting code, or SimulationTruth; the only rational-resampling/filtering
implementation this module is aware of is the frozen one consumed upstream of the request.

The request's `ecg` field (see api/schemas.py::ECGWindow) is PREPROC_V1-resampled/filtered but
NOT normalized -- it is in the same FILTERED_UNNORMALIZED_CANONICAL_CACHE representation T013
caches. This module owns applying the locked PREPROC_V1 PER_WINDOW_ZSCORE_V1 normalization,
exactly once, immediately before MODEL_V1/gateway inference (API_RUNTIME_V1_1, C032-NORM-
RUNTIME). `estimate_ecg_hr` deliberately continues to receive the amplitude-preserving
filtered representation -- ECG_HR_CONTEXT_V2 (xqrs beat detection) was validated against that
representation and must never see the z-scored MODEL branch array.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from deployment.runtime import GatewayModelRuntime
from fusion.episode_manager import AlertPolicy, load_alert_policy, verify_alert_policy_lock
from nhm.hashing import hash_file
from preprocessing.ecg_hr_context import ECGHRResult, estimate_hr
from preprocessing.freeze import verify_preproc_freeze
from preprocessing.windowing import (
    NORMALIZATION_EPSILON,
    WINDOW_SAMPLES,
    normalize_window_zscore,
)

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ARTIFACT_RELATIVE_PATH = "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
ECG_HR_CANDIDATE_ID = "WFDB_XQRS_V1"
PREPROCESS_ID = "PREPROC_V1"


class InputValidationError(ValueError):
    """The caller handed `ProductionRuntime.infer` a window that cannot be normalized under
    the locked PREPROC_V1 PER_WINDOW_ZSCORE_V1 contract (wrong length, non-finite samples, or
    a non-finite normalization result). Callers (api/app.py) must route UNUSABLE/incomplete
    windows to the 422 path *before* ever calling `infer` -- this is a defense-in-depth check,
    not the primary completeness gate."""


class RuntimeVerificationError(RuntimeError):
    """A required frozen production artifact failed identity verification at startup."""


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _verify_ecg_hr_context_lock(root: Path) -> dict:
    lock_path = root / "artifacts/ECG_HR_CONTEXT_V2.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("status") != "FROZEN_ENGINEERING_COMPONENT":
        raise RuntimeVerificationError("ECG_HR_CONTEXT_V2_LOCK_STATUS_MISMATCH")
    if hash_file(root / "configs/ecg_hr_context_v2.yaml") != lock["config_sha256"]:
        raise RuntimeVerificationError("ECG_HR_CONTEXT_V2_CONFIG_HASH_MISMATCH")
    if hash_file(root / "preprocessing/ecg_hr_context.py") != lock["implementation_sha256"]:
        raise RuntimeVerificationError("ECG_HR_CONTEXT_V2_IMPLEMENTATION_HASH_MISMATCH")
    if lock["selected_candidate"] != ECG_HR_CANDIDATE_ID:
        raise RuntimeVerificationError("ECG_HR_CONTEXT_V2_SELECTION_MISMATCH")
    return lock


def _verify_gateway_artifact_lock(root: Path) -> dict:
    lock_path = root / "artifacts/GATEWAY_ARTIFACT_V1.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("freeze_id") != "F14" or lock.get("status") != "FROZEN":
        raise RuntimeVerificationError("GATEWAY_ARTIFACT_V1_LOCK_STATUS_MISMATCH")
    for relative_path, expected in lock.get("bound_artifacts", {}).items():
        if hash_file(root / relative_path) != expected:
            raise RuntimeVerificationError(f"GATEWAY_ARTIFACT_V1_TAMPER:{relative_path}")
    return lock


def _verify_preproc_lock(root: Path) -> None:
    try:
        verify_preproc_freeze(root)
    except Exception as error:
        raise RuntimeVerificationError(f"PREPROC_V1_LOCK_MISMATCH: {error}") from error


def _verify_alert_policy(root: Path) -> None:
    try:
        verify_alert_policy_lock(root)
    except Exception as error:
        raise RuntimeVerificationError(f"ALERT_POLICY_V1_LOCK_MISMATCH: {error}") from error


@dataclass(frozen=True)
class InferenceOutcome:
    model_id: str
    model_sha: str
    deployment_artifact_id: str
    deployment_artifact_sha: str
    raw_probability: float
    source_domain_calibrated_probability: float
    threshold: float
    calibration_id: str
    calibration_domain: str
    above_threshold: bool


class ProductionRuntime:
    """The single production dependency bundle `api.app.create_app()` binds by default.
    Tests that need to exercise HTTP-layer state policy without a real model may construct
    `create_app()` with an injected fake runtime instead -- see tests/test_api_stateful_t032.py.
    Production app construction (`api.app.app`) always uses this class.
    """

    preprocess_id = PREPROCESS_ID

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        _verify_preproc_lock(root)
        _verify_ecg_hr_context_lock(root)
        _verify_alert_policy(root)
        _verify_gateway_artifact_lock(root)
        self.gateway = GatewayModelRuntime(root, root / GATEWAY_ARTIFACT_RELATIVE_PATH)
        self.policy: AlertPolicy = load_alert_policy(root)
        calibration = json.loads((root / "artifacts/CAL_V1.json").read_text(encoding="utf-8"))
        self.calibration_patient_count: int = int(calibration["calibration_patient_count"])

    def infer(self, ecg_samples: list[float]) -> InferenceOutcome:
        """Applies the locked PREPROC_V1 PER_WINDOW_ZSCORE_V1 normalization to the incoming
        filtered-but-unnormalized window before MODEL_V1/gateway inference. Never call this
        with an UNUSABLE/incomplete window -- api/app.py routes those to HTTP 422 first."""
        window = np.asarray(ecg_samples, dtype=np.float64)
        if window.ndim != 1 or window.size != WINDOW_SAMPLES:
            raise InputValidationError(
                f"INFER_INPUT_LENGTH_MISMATCH: expected {WINDOW_SAMPLES} samples, "
                f"got shape {window.shape}"
            )
        if not np.isfinite(window).all():
            raise InputValidationError("INFER_INPUT_NONFINITE")
        normalized = normalize_window_zscore(window, epsilon=NORMALIZATION_EPSILON)
        if not np.isfinite(normalized).all():
            raise InputValidationError("INFER_NORMALIZATION_OUTPUT_NONFINITE")
        array = normalized.astype(np.float32).reshape(1, 1, -1)
        result = self.gateway.infer(array)
        return InferenceOutcome(
            model_id=result.model_id,
            model_sha=result.model_sha,
            deployment_artifact_id=result.deployment_artifact_id,
            deployment_artifact_sha=result.deployment_artifact_sha,
            raw_probability=_sigmoid(result.raw_logit),
            source_domain_calibrated_probability=result.calibrated_probability,
            threshold=result.threshold,
            calibration_id=result.calibration_id,
            calibration_domain=result.calibration_domain,
            above_threshold=result.above_threshold,
        )

    def estimate_ecg_hr(self, ecg_samples: list[float], *, timestamp_us: int) -> ECGHRResult:
        array = np.asarray(ecg_samples, dtype=np.float64)
        return estimate_hr(array, timestamp_us=timestamp_us, candidate_id=ECG_HR_CANDIDATE_ID)
