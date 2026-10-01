"""Shared, non-collected test support for the T032 API suite.

Named with a leading underscore so pytest never collects it as a test module itself.
Provides a deterministic fake `InferenceRuntime` (never touches MODEL_V1/torch) bound to
the REAL, frozen `AlertPolicy` loaded from `configs/alert_policy_v1.yaml` + `CAL_V1` +
`ECG_HR_CONTEXT_V2.lock.json` -- so stateful/HTTP-layer tests exercise the real
ALERT_POLICY_V1 state machine and real session wiring without the cost of loading the
TorchScript gateway artifact for every test.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.app import create_app
from fusion.episode_manager import AlertPolicy, load_alert_policy

ROOT = Path(__file__).resolve().parents[1]
ECG_WINDOW_SAMPLE_COUNT = 2500


def real_policy() -> AlertPolicy:
    return load_alert_policy(ROOT)


@dataclass(frozen=True)
class FakeOutcome:
    source_domain_calibrated_probability: float
    threshold: float
    model_id: str = "MODEL_V1"
    calibration_id: str = "CAL_V1"
    calibration_domain: str = "MIT-BIH-v1.0.0"
    raw_probability: float = 0.5


@dataclass(frozen=True)
class FakeHRResult:
    hr_ecg_bpm: float | None = None
    valid: bool = False


class FakeRuntime:
    """Satisfies `api.app.InferenceRuntime` without ever loading MODEL_V1/GATEWAY_ARTIFACT_V1."""

    preprocess_id = "PREPROC_V1"
    calibration_patient_count = 3

    def __init__(
        self,
        probability: float = 0.9,
        *,
        policy: AlertPolicy | None = None,
        hr_ecg_bpm: float | None = None,
        hr_valid: bool = False,
        raise_on_infer: Exception | None = None,
    ) -> None:
        self.policy = policy or real_policy()
        self.probability = probability
        self.hr_ecg_bpm = hr_ecg_bpm
        self.hr_valid = hr_valid
        self.raise_on_infer = raise_on_infer
        self.infer_calls: list[list[float]] = []

    def infer(self, ecg_samples: list[float]) -> FakeOutcome:
        self.infer_calls.append(ecg_samples)
        if self.raise_on_infer is not None:
            raise self.raise_on_infer
        return FakeOutcome(
            source_domain_calibrated_probability=self.probability,
            threshold=self.policy.threshold,
        )

    def estimate_ecg_hr(self, ecg_samples: list[float], *, timestamp_us: int) -> FakeHRResult:
        del ecg_samples, timestamp_us
        return FakeHRResult(hr_ecg_bpm=self.hr_ecg_bpm, valid=self.hr_valid)


def make_payload(
    session_id: str,
    timestamp_us: int,
    *,
    ecg_quality: str = "VALID",
    samples: list[float] | None = None,
    ppg_context: dict[str, Any] | None = None,
    model_id: str = "MODEL_V1",
) -> dict[str, Any]:
    if samples is None:
        samples = [0.0] * ECG_WINDOW_SAMPLE_COUNT
    return {
        "contract_version": "API_SCHEMA_V1",
        "session_id": session_id,
        "timestamp_us": timestamp_us,
        "ecg": {"samples": samples, "target_hz": 250, "window_seconds": 10},
        "ecg_quality": ecg_quality,
        "ppg_context": ppg_context,
        "model_id": model_id,
    }


def build_app(**fake_kwargs: Any):
    """Returns (app, runtime, session_store). A fresh SessionRuntimeStore every call."""
    runtime = FakeRuntime(**fake_kwargs)
    app = create_app(runtime=runtime)
    return app, runtime, app.state.session_store
