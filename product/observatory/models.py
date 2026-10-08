"""Strict, bounded public contracts for one synthetic pipeline reconstruction."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioInfo(StrictModel):
    scenario_id: str
    duration_s: int
    window_count: int
    source_kind: Literal["SYNTHETIC_VIRTUAL_WEARABLE"] = "SYNTHETIC_VIRTUAL_WEARABLE"
    trace_classification: Literal["DETERMINISTIC_LOCAL_RECONSTRUCTION"] = (
        "DETERMINISTIC_LOCAL_RECONSTRUCTION"
    )


class SignalPoint(StrictModel):
    timestamp_us: int
    value: float | None
    source_index: int | None = None


class SignalStage(StrictModel):
    stage_id: str
    unit: str
    sample_rate_hz: int
    actual_point_count: int
    displayed_point_count: int
    display_is_decimated: bool
    points: list[SignalPoint] = Field(max_length=1200)


class GapTrace(StrictModel):
    kind: Literal["SHORT", "LONG"]
    first_missing_index: int
    last_missing_index: int
    missing_count: int
    duration_ms: float
    fill_count: int
    previous_segment_id: int
    next_segment_id: int
    quality_requirement: str


class NormalizationTrace(StrictModel):
    status: Literal["RECONSTRUCTED_MODEL_INPUT", "NOT_APPLIED_UNUSABLE"]
    identity: str
    mean: float | None
    std: float | None
    epsilon: float
    shape: list[int] | None
    dtype: str | None
    tensor_sha256: str | None


class PersistedInference(StrictModel):
    model_id: str | None
    calibration_domain: str | None
    raw_probability: float | None
    source_domain_calibrated_probability: float | None
    threshold: float | None
    monitoring_state: str
    ecg_quality: str
    probability_role: Literal["RESEARCH_TECHNICAL_METADATA"] = "RESEARCH_TECHNICAL_METADATA"


class WindowTrace(StrictModel):
    trace_version: Literal["NHM_PIPELINE_TRACE_V1"] = "NHM_PIPELINE_TRACE_V1"
    classification: Literal["DETERMINISTIC_LOCAL_RECONSTRUCTION"] = (
        "DETERMINISTIC_LOCAL_RECONSTRUCTION"
    )
    source_kind: Literal["SYNTHETIC_VIRTUAL_WEARABLE"] = "SYNTHETIC_VIRTUAL_WEARABLE"
    scenario_id: str
    session_id: str | None
    window_index: int
    window_id: str
    left_timestamp_us: int
    right_timestamp_us: int
    source_rate_hz: int
    target_rate_hz: int
    window_sample_count: int
    cadence_us: int
    quality_state: str
    quality_reasons: list[str]
    missing_slots: int
    context_available: bool
    gaps: list[GapTrace]
    stages: list[SignalStage]
    normalization: NormalizationTrace
    persisted_inference: PersistedInference | None
    inference_evidence_status: str
    claim_boundary: str = "SYNTHETIC_ENGINEERING_RECONSTRUCTION_NOT_CAPTURED_HISTORICAL_TRACE"
    limitations: list[str]
