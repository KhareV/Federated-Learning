"""Typed request/response/error models for POST /v1/infer-window.

Implements `contracts/API_SCHEMA_V1.json` exactly (v2.2 Section 27) -- this module is the
single source of truth for what that frozen JSON Schema already requires; it does not widen
or relax it. `tests/test_api_schema_v1.py` (T003) and `tests/test_api_openapi_t032.py`
(T032) both validate real payloads produced from these models against that same schema file,
so schema/runtime/OpenAPI drift is caught, not assumed away.

`target` is always `AAMI_SVF_WINDOW_V1`: a descriptive statement about the observed ECG
window, never a disease diagnosis, beat classification, future forecast, or clinical
decision. No field here may express or imply one.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "API_SCHEMA_V1"
TARGET_ID = "AAMI_SVF_WINDOW_V1"
ECG_WINDOW_TARGET_HZ = 250
ECG_WINDOW_SECONDS = 10
ECG_WINDOW_SAMPLE_COUNT = ECG_WINDOW_TARGET_HZ * ECG_WINDOW_SECONDS

INT64_MAX = 2**63 - 1


class QualityState(StrEnum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    UNUSABLE = "UNUSABLE"


class MonitoringState(StrEnum):
    NORMAL_MONITORED_PATTERN = "NORMAL_MONITORED_PATTERN"
    POTENTIAL_ECTOPY_ASSOCIATED_PATTERN = "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"
    RECHECK_SENSOR = "RECHECK_SENSOR"
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    SYSTEM_ERROR = "SYSTEM_ERROR"


def _require_finite(value: float | None, field_name: str) -> float | None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"NONFINITE_VALUE:{field_name}")
    return value


class ECGWindow(BaseModel):
    """A PREPROC_V1-resampled (250 Hz) and causally-filtered window, in the FILTERED_
    UNNORMALIZED_CANONICAL_CACHE representation -- NOT yet GATEWAY_MODEL_INPUT_V1-ready.
    Never raw ADC counts, an arbitrary-rate signal, or a hardware serial packet. The caller
    must NOT apply PER_WINDOW_ZSCORE_V1 normalization itself: the API server applies it,
    once, immediately before MODEL_V1/gateway inference -- see api/runtime.py docstring.

    `samples` is intentionally NOT length-constrained here: a non-2500-length array is a
    *signal-completeness* condition (HTTP 422, matching this schema file's own documented
    "422 = unusable or incomplete signal window"), not a request-schema error (HTTP 400).
    Enforcing the length as a Pydantic constraint would conflate the two and make ordinary
    incomplete-window requests indistinguishable from malformed ones.
    """

    model_config = ConfigDict(extra="forbid")

    samples: list[float]
    target_hz: Literal[250]
    window_seconds: Literal[10]

    @field_validator("samples")
    @classmethod
    def _samples_finite(cls, value: list[float]) -> list[float]:
        for item in value:
            if not math.isfinite(item):
                raise ValueError("NONFINITE_VALUE:ecg.samples")
        return value


class PPGContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quality: QualityState | None
    pr_bpm: float | None
    spo2_pct: float | None
    spo2_valid: bool | None

    @field_validator("pr_bpm")
    @classmethod
    def _pr_bpm_finite(cls, value: float | None) -> float | None:
        return _require_finite(value, "ppg_context.pr_bpm")

    @field_validator("spo2_pct")
    @classmethod
    def _spo2_pct_finite(cls, value: float | None) -> float | None:
        return _require_finite(value, "ppg_context.spo2_pct")

    @model_validator(mode="after")
    def _spo2_valid_requires_finite_pct(self) -> PPGContext:
        if self.spo2_valid and self.spo2_pct is None:
            raise ValueError("SPO2_VALID_REQUIRES_SPO2_PCT")
        return self


class InferWindowRequest(BaseModel):
    """Session-oriented request for one 10-second ECG window (v2.2 Section 27). The session
    ID is opaque -- no participant_id, demographics, or diagnosis field exists here because
    the frozen contract does not require one."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["API_SCHEMA_V1"]
    session_id: str = Field(min_length=1)
    timestamp_us: int = Field(ge=0, le=INT64_MAX, strict=True)
    ecg: ECGWindow
    ecg_quality: QualityState
    ppg_context: PPGContext | None
    model_id: str = Field(min_length=1)


class InferWindowResponse(BaseModel):
    """Every successful inference response carries the full set of version identifiers
    required by API_SCHEMA_V1 (model/target/preprocess/alert-policy/calibration), the
    explicit calibration domain/patient-count, and both probability fields distinctly."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["API_SCHEMA_V1"] = CONTRACT_VERSION
    timestamp_us: int
    model_id: str | None
    target: Literal["AAMI_SVF_WINDOW_V1"] = TARGET_ID
    raw_probability: float | None = Field(default=None, ge=0, le=1)
    source_domain_calibrated_probability: float | None = Field(default=None, ge=0, le=1)
    calibration_domain: str | None
    calibration_patient_count: int | None = Field(default=None, ge=0)
    calibration_id: str | None
    threshold: float | None = Field(default=None, ge=0, le=1)
    ecg_quality: QualityState
    monitoring_state: MonitoringState
    context: dict | None
    latency_ms: float | None = Field(default=None, ge=0)
    preprocess_version: str | None
    alert_policy_id: str | None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["API_SCHEMA_V1"] = CONTRACT_VERSION
    status_code: Literal[400, 422, 500]
    error_type: str
    message: str
