"""Strict CAP-009 persisted-evidence response contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionSummary(EvidenceModel):
    session_id: str
    summary_version: Literal["SESSION_SUMMARY_V1_INFERRED_WINDOWS"]
    duration_ms: int = Field(ge=0)
    duration_basis: Literal["PRODUCT_LIFECYCLE_CLOCK"] = "PRODUCT_LIFECYCLE_CLOCK"
    windows_inferred: int = Field(ge=0)
    windows_inferred_basis: Literal["PERSISTED_INFERENCE_EVENTS"] = "PERSISTED_INFERENCE_EVENTS"
    state_counts: dict[str, int]
    state_counts_basis: Literal["PERSISTED_INFERENCE_EVENTS"] = "PERSISTED_INFERENCE_EVENTS"
    quality_counts: dict[str, int]
    quality_counts_basis: Literal["PERSISTED_INFERENCE_EVENTS"] = "PERSISTED_INFERENCE_EVENTS"
    hr_min: float | None
    hr_mean: float | None
    hr_max: float | None
    spo2_min: float | None
    spo2_mean: float | None
    spo2_max: float | None
    reconnect_count: int = Field(ge=0)
    disconnect_count: int = Field(ge=0)
    generated_at_us: int = Field(ge=0)
    claim_boundary: Literal["PERSISTED_RESEARCH_ENGINEERING_SESSION_SUMMARY_NOT_CLINICAL"] = (
        "PERSISTED_RESEARCH_ENGINEERING_SESSION_SUMMARY_NOT_CLINICAL"
    )


class InferencePayload(EvidenceModel):
    model_id: str | None
    calibration_domain: str | None
    ecg_quality: str
    monitoring_state: str
    raw_probability: float | None
    source_domain_calibrated_probability: float | None
    threshold: float | None
    latency_ms: float | None
    probability_role: Literal["RESEARCH_TECHNICAL_METADATA"] = "RESEARCH_TECHNICAL_METADATA"


class StateChangePayload(EvidenceModel):
    monitoring_state: str
    previous_state: str | None
    reason_code: str | None


class QualityChangePayload(EvidenceModel):
    ecg_quality: str
    ppg_quality: str | None
    storage_basis: Literal["CHANGE_ONLY"] = "CHANGE_ONLY"


class ContextSnapshotPayload(EvidenceModel):
    hr_ecg_bpm: float | None
    pr_ppg_bpm: float | None
    spo2_pct: float | None
    spo2_valid: bool
    context_available: bool
    ppg_quality: str | None


class SourceTimelineItem(EvidenceModel):
    kind: Literal["INFERENCE", "MONITORING_STATE_CHANGE", "QUALITY_CHANGE", "CONTEXT_SNAPSHOT"]
    sequence_index: int
    source_timestamp_us: int
    payload: InferencePayload | StateChangePayload | QualityChangePayload | ContextSnapshotPayload


class DeviceLifecycleItem(EvidenceModel):
    event_type: str
    device_state: str
    reason_code: str | None
    recoverable: bool | None
    at_us: int
    time_domain: Literal["PRODUCT_CLOCK"] = "PRODUCT_CLOCK"


class TimeDomains(EvidenceModel):
    source_timeline: Literal["SOURCE_TIMELINE"] = "SOURCE_TIMELINE"
    device_lifecycle: Literal["PRODUCT_CLOCK"] = "PRODUCT_CLOCK"


class WaveformPreview(EvidenceModel):
    channel: str
    source_rate_hz: int
    decimation_factor: int
    point_count: int = Field(ge=0, le=4000)
    start_timestamp_us: int
    points: list[int | None] = Field(max_length=4000)
    claim_boundary: Literal["BOUNDED_DECIMATED_PREVIEW_NOT_RAW_STREAM_STORAGE"] = (
        "BOUNDED_DECIMATED_PREVIEW_NOT_RAW_STREAM_STORAGE"
    )


class SessionTimeline(EvidenceModel):
    session_id: str
    timeline_version: Literal["CAPSTONE_SESSION_TIMELINE_V1"] = "CAPSTONE_SESSION_TIMELINE_V1"
    source_timeline: list[SourceTimelineItem]
    device_lifecycle: list[DeviceLifecycleItem]
    waveform_previews: list[WaveformPreview]
    time_domains: TimeDomains = TimeDomains()
    time_domain_explanation: str = (
        "Source timestamps and product lifecycle clock have different origins and are not merged."
    )
    claim_boundary: Literal["PERSISTED_RESEARCH_ENGINEERING_EVIDENCE_NOT_WEBSOCKET_REPLAY"] = (
        "PERSISTED_RESEARCH_ENGINEERING_EVIDENCE_NOT_WEBSOCKET_REPLAY"
    )
