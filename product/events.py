"""PRODUCT_LIVE_EVENT_V1 -- versioned WebSocket/frontend event envelopes (monitoring + federation).

An explicit discriminated union (``event_type``); no untyped free-form payload exists. Quality and
monitoring-state vocabularies are the frozen ``api.schemas`` enums (reused, not redefined), so the
product cannot invent a diagnostic state. All values originate from real pipeline output -- the
frontend never fabricates them. The authoritative JSON Schema is generated from this module into
``contracts/capstone/live_event_v1.schema.json`` (parity is tested).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from api.schemas import MonitoringState, QualityState
from product.devices.base import AdapterType, DeviceState
from product.federation.base import (
    AggregationMode,
    Algorithm,
    ClientState,
    RoundState,
    RunState,
    RunType,
    SecAggStatus,
)
from product.models.registry_contract import CandidateState, SandboxStatus, ValidationStatus
from product.session import SessionState

PRODUCT_LIVE_EVENT_VERSION = "PRODUCT_LIVE_EVENT_V1"

# Waveform UI transport policy (UI transport only; independent of the 360->250 model path).
WAVEFORM_SOURCE_RATE_HZ = 360
WAVEFORM_UI_UPDATES_PER_SECOND_MIN = 5
WAVEFORM_UI_UPDATES_PER_SECOND_MAX = 10
WAVEFORM_MAX_SAMPLES_PER_CHUNK = 144

QUALITY_UI_LABELS = {
    QualityState.VALID: "Signal Good",
    QualityState.DEGRADED: "Signal Degraded",
    QualityState.UNUSABLE: "Recheck Sensor",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionStatusPayload(_Strict):
    session_state: SessionState
    elapsed_ms: int = Field(ge=0)
    reason_code: str | None = None


class DeviceStatusPayload(_Strict):
    device_id: str = Field(min_length=1)
    device_state: DeviceState
    adapter_type: AdapterType
    reason_code: str | None = None
    recoverable: bool


class WaveformChunkPayload(_Strict):
    channel: Literal["ECG", "PPG_RED", "PPG_IR"]
    unit: Literal["ADC_COUNTS"] = "ADC_COUNTS"
    source_rate_hz: Literal[360] = WAVEFORM_SOURCE_RATE_HZ
    first_sample_index: int = Field(ge=0)
    first_sample_timestamp_us: int = Field(ge=0)
    sample_count: int = Field(ge=1, le=WAVEFORM_MAX_SAMPLES_PER_CHUNK)
    samples: list[int | None]

    @model_validator(mode="after")
    def _length_matches(self) -> WaveformChunkPayload:
        if len(self.samples) != self.sample_count:
            raise ValueError("WAVEFORM_SAMPLE_COUNT_MISMATCH")
        return self


class ContextSnapshotPayload(_Strict):
    hr_ecg_bpm: float | None = None
    pr_ppg_bpm: float | None = None
    spo2_pct: float | None = None
    spo2_valid: bool
    context_available: bool
    ppg_quality: QualityState | None = None

    @model_validator(mode="after")
    def _unavailable_is_explicit(self) -> ContextSnapshotPayload:
        if not self.context_available and (
            self.pr_ppg_bpm is not None or self.spo2_pct is not None or self.spo2_valid
        ):
            raise ValueError("UNAVAILABLE_CONTEXT_MUST_NOT_CARRY_PPG_VALUES")
        if self.spo2_valid and self.spo2_pct is None:
            raise ValueError("SPO2_VALID_REQUIRES_SPO2_PCT")
        return self


class QualityStatusPayload(_Strict):
    ecg_quality: QualityState
    ppg_quality: QualityState | None = None
    ui_label: str

    @model_validator(mode="after")
    def _label_is_the_frozen_mapping(self) -> QualityStatusPayload:
        if self.ui_label != QUALITY_UI_LABELS[self.ecg_quality]:
            raise ValueError("QUALITY_UI_LABEL_MISMATCH")
        return self


class InferenceResultPayload(_Strict):
    timestamp_us: int = Field(ge=0)
    model_id: str | None
    calibration_id: str | None
    calibration_domain: str | None
    preprocess_version: str | None
    alert_policy_id: str | None
    ecg_quality: QualityState
    monitoring_state: MonitoringState
    context: ContextSnapshotPayload | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    raw_probability: float | None = Field(default=None, ge=0, le=1)
    source_domain_calibrated_probability: float | None = Field(default=None, ge=0, le=1)
    threshold: float | None = Field(default=None, ge=0, le=1)
    probability_role: Literal["RESEARCH_TECHNICAL_METADATA"] = "RESEARCH_TECHNICAL_METADATA"


class MonitoringStatePayload(_Strict):
    monitoring_state: MonitoringState
    previous_state: MonitoringState | None = None
    reason_code: str | None = None


class SystemErrorPayload(_Strict):
    error_code: str = Field(min_length=1)
    message: str = Field(max_length=300)
    recoverable: bool
    origin: Literal["DEVICE", "STREAM", "INFERENCE", "PRODUCT_API", "STORAGE"]


class _Envelope(_Strict):
    contract_version: Literal["PRODUCT_LIVE_EVENT_V1"] = PRODUCT_LIVE_EVENT_VERSION
    event_id: str = Field(min_length=1)
    sequence_index: int = Field(ge=0)
    emitted_at_us: int = Field(ge=0)


class _SessionEnvelope(_Envelope):
    session_id: str = Field(min_length=1)
    source_timestamp_us: int | None = Field(default=None, ge=0)


class _RunEnvelope(_Envelope):
    run_id: str = Field(min_length=1)


class SessionStatusEvent(_SessionEnvelope):
    event_type: Literal["session.status"]
    payload: SessionStatusPayload


class DeviceStatusEvent(_SessionEnvelope):
    event_type: Literal["device.status"]
    payload: DeviceStatusPayload


class WaveformChunkEvent(_SessionEnvelope):
    event_type: Literal["waveform.chunk"]
    payload: WaveformChunkPayload


class ContextSnapshotEvent(_SessionEnvelope):
    event_type: Literal["context.snapshot"]
    payload: ContextSnapshotPayload


class QualityStatusEvent(_SessionEnvelope):
    event_type: Literal["quality.status"]
    payload: QualityStatusPayload


class InferenceResultEvent(_SessionEnvelope):
    event_type: Literal["inference.result"]
    payload: InferenceResultPayload


class MonitoringStateEvent(_SessionEnvelope):
    event_type: Literal["monitoring.state"]
    payload: MonitoringStatePayload


class SystemErrorEvent(_SessionEnvelope):
    event_type: Literal["system.error"]
    payload: SystemErrorPayload


class FederationStatusPayload(_Strict):
    run_type: RunType
    run_status: RunState
    algorithm: Algorithm
    current_round: int = Field(ge=0)
    planned_rounds: int = Field(ge=1)
    client_count: int = Field(ge=1)
    engineering_only: Literal[True] = True


class RoundStatusPayload(_Strict):
    round_id: int = Field(ge=1)
    round_state: RoundState
    accepted_updates: int = Field(ge=0)
    expected_updates: int = Field(ge=1)


class ClientStatusPayload(_Strict):
    client_id: str = Field(min_length=1)
    client_state: ClientState
    local_example_count: int = Field(ge=0)
    reason_code: str | None = None


class ClientTrainingProgressPayload(_Strict):
    client_id: str = Field(min_length=1)
    round_id: int = Field(ge=1)
    progress_fraction: float = Field(ge=0, le=1)
    examples_seen: int = Field(ge=0)


class ClientUpdateReadyPayload(_Strict):
    client_id: str = Field(min_length=1)
    round_id: int = Field(ge=1)
    update_digest: str = Field(min_length=1)
    examples_seen: int = Field(ge=1)


class AggregationStatusPayload(_Strict):
    round_id: int = Field(ge=1)
    algorithm: Algorithm
    aggregation_mode: AggregationMode
    accepted_updates: int = Field(ge=0)
    state_digest: str | None = None


class SecAggStatusPayload(_Strict):
    round_id: int = Field(ge=1)
    mode: AggregationMode
    status: SecAggStatus
    claim_scope: Literal["PROTECTED_AGGREGATION_INTERFACE_ONLY"] = (
        "PROTECTED_AGGREGATION_INTERFACE_ONLY"
    )

    @model_validator(mode="after")
    def _mode_matches_status(self) -> SecAggStatusPayload:
        if (self.mode is AggregationMode.PLAIN) != (self.status is SecAggStatus.NOT_USED):
            raise ValueError("SECAGG_STATUS_MUST_MATCH_MODE")
        return self


class CandidateCreatedPayload(_Strict):
    candidate_id: str = Field(pattern=r"^CAPSTONE_FL_CANDIDATE_\d{4}$")
    parent_model_id: str
    round_id: int = Field(ge=1)
    state_digest: str = Field(min_length=1)
    production_deployed: Literal[False] = False


class CandidateValidationPayload(_Strict):
    candidate_id: str = Field(pattern=r"^CAPSTONE_FL_CANDIDATE_\d{4}$")
    validation_status: ValidationStatus
    checks: tuple[str, ...] = ()


class CandidateGovernancePayload(_Strict):
    candidate_id: str = Field(pattern=r"^CAPSTONE_FL_CANDIDATE_\d{4}$")
    governance_status: CandidateState
    sandbox_status: SandboxStatus
    production_deployed: Literal[False] = False


class FederationCompletedPayload(_Strict):
    rounds_completed: int = Field(ge=0)
    candidate_ids: tuple[str, ...] = ()
    production_deployed: Literal[False] = False


class FederationErrorPayload(_Strict):
    error_code: str = Field(min_length=1)
    message: str = Field(max_length=300)
    recoverable: bool
    round_id: int | None = Field(default=None, ge=1)


class FederationStatusEvent(_RunEnvelope):
    event_type: Literal["federation.status"]
    payload: FederationStatusPayload


class RoundStatusEvent(_RunEnvelope):
    event_type: Literal["round.status"]
    payload: RoundStatusPayload


class ClientStatusEvent(_RunEnvelope):
    event_type: Literal["client.status"]
    payload: ClientStatusPayload


class ClientTrainingProgressEvent(_RunEnvelope):
    event_type: Literal["client.training_progress"]
    payload: ClientTrainingProgressPayload


class ClientUpdateReadyEvent(_RunEnvelope):
    event_type: Literal["client.update_ready"]
    payload: ClientUpdateReadyPayload


class AggregationStatusEvent(_RunEnvelope):
    event_type: Literal["aggregation.status"]
    payload: AggregationStatusPayload


class SecAggStatusEvent(_RunEnvelope):
    event_type: Literal["secagg.status"]
    payload: SecAggStatusPayload


class CandidateCreatedEvent(_RunEnvelope):
    event_type: Literal["candidate.created"]
    payload: CandidateCreatedPayload


class CandidateValidationEvent(_RunEnvelope):
    event_type: Literal["candidate.validation"]
    payload: CandidateValidationPayload


class CandidateGovernanceEvent(_RunEnvelope):
    event_type: Literal["candidate.governance"]
    payload: CandidateGovernancePayload


class FederationCompletedEvent(_RunEnvelope):
    event_type: Literal["federation.completed"]
    payload: FederationCompletedPayload


class FederationErrorEvent(_RunEnvelope):
    event_type: Literal["federation.error"]
    payload: FederationErrorPayload


MonitoringLiveEvent = (
    SessionStatusEvent | DeviceStatusEvent | WaveformChunkEvent | ContextSnapshotEvent
    | QualityStatusEvent | InferenceResultEvent | MonitoringStateEvent | SystemErrorEvent
)
FederationLiveEvent = (
    FederationStatusEvent | RoundStatusEvent | ClientStatusEvent | ClientTrainingProgressEvent
    | ClientUpdateReadyEvent | AggregationStatusEvent | SecAggStatusEvent | CandidateCreatedEvent
    | CandidateValidationEvent | CandidateGovernanceEvent | FederationCompletedEvent
    | FederationErrorEvent
)
LiveEvent = Annotated[MonitoringLiveEvent | FederationLiveEvent, Field(discriminator="event_type")]
MONITORING_ADAPTER: TypeAdapter[MonitoringLiveEvent] = TypeAdapter(
    Annotated[MonitoringLiveEvent, Field(discriminator="event_type")])
FEDERATION_ADAPTER: TypeAdapter[FederationLiveEvent] = TypeAdapter(
    Annotated[FederationLiveEvent, Field(discriminator="event_type")])

LIVE_EVENT_ADAPTER: TypeAdapter[LiveEvent] = TypeAdapter(LiveEvent)

MONITORING_EVENT_KINDS = (
    "device.status", "session.status", "waveform.chunk", "context.snapshot", "quality.status",
    "inference.result", "monitoring.state", "system.error",
)
FEDERATION_EVENT_KINDS = (
    "federation.status", "round.status", "client.status", "client.training_progress",
    "client.update_ready", "aggregation.status", "secagg.status", "candidate.created",
    "candidate.validation", "candidate.governance", "federation.completed", "federation.error",
)
EVENT_KINDS = MONITORING_EVENT_KINDS + FEDERATION_EVENT_KINDS


def parse_live_event(data: object) -> LiveEvent:
    """Validate an arbitrary object against the discriminated union (raises on invalid)."""
    return LIVE_EVENT_ADAPTER.validate_python(data)


def parse_monitoring_event(data: object) -> MonitoringLiveEvent:
    """Monitoring WebSocket stream: only monitoring event kinds are legal."""
    return MONITORING_ADAPTER.validate_python(data)


def parse_federation_event(data: object) -> FederationLiveEvent:
    """Federation WebSocket stream: only federation event kinds are legal."""
    return FEDERATION_ADAPTER.validate_python(data)


def live_event_json_schema() -> dict:
    return LIVE_EVENT_ADAPTER.json_schema()
