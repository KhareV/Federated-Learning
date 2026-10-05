"""CAPSTONE_SESSION_CONTRACT_V1 -- monitoring-session identity and lifecycle.

A session's runtime identity (model / calibration / preprocess / alert policy / software system)
is fixed at creation and can never change mid-session: ``advance_session`` returns a copy in
which only ``state`` and the lifecycle timestamps differ.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.contracts import assert_transition, load_contract, transition_table
from product.devices.base import AdapterType


class SessionState(StrEnum):
    CREATED = "CREATED"
    DEVICE_READY = "DEVICE_READY"
    MONITORING = "MONITORING"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def session_transitions() -> dict[str, tuple[str, ...]]:
    return transition_table("session", "session_transitions")


def validate_session_transition(current: SessionState, new: SessionState) -> None:
    assert_transition(session_transitions(), current.value, new.value, "SESSION")


class RuntimeIdentity(BaseModel):
    """The frozen SOFTWARE_SYSTEM_V2 default identity a session is bound to. Not selectable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    calibration_id: str
    preprocess_id: str
    alert_policy_id: str
    alert_policy_binding_id: str
    gateway_artifact_id: str
    api_contract_version: str
    software_system_id: str

    @model_validator(mode="after")
    def _pinned_to_default_runtime(self) -> RuntimeIdentity:
        pinned = load_contract("session")["required_runtime_identity"]
        if self.model_dump() != pinned:
            raise ValueError("RUNTIME_IDENTITY_NOT_THE_FROZEN_DEFAULT")
        return self


def default_runtime_identity() -> RuntimeIdentity:
    return RuntimeIdentity(**load_contract("session")["required_runtime_identity"])


class SimulationProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    seed: int
    simulation_version: str


class MonitoringSession(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    device_adapter_type: AdapterType
    source_dataset_id: str | None = None
    source_mode: str | None = None
    created_at_us: int = Field(ge=0)
    started_at_us: int | None = Field(default=None, ge=0)
    ended_at_us: int | None = Field(default=None, ge=0)
    state: SessionState
    runtime: RuntimeIdentity
    simulation_provenance: SimulationProvenance | None = None

    @model_validator(mode="after")
    def _consistent(self) -> MonitoringSession:
        if self.device_adapter_type is AdapterType.SIMULATED and self.simulation_provenance is None:
            raise ValueError("SIMULATED_SESSION_REQUIRES_SIMULATION_PROVENANCE")
        if self.device_adapter_type is AdapterType.FUTURE_REAL and self.simulation_provenance:
            raise ValueError("REAL_SESSION_MUST_NOT_CARRY_SIMULATION_PROVENANCE")
        if self.state in (SessionState.CREATED, SessionState.DEVICE_READY) and (
            self.started_at_us is not None or self.ended_at_us is not None
        ):
            raise ValueError("PRE_MONITORING_SESSION_HAS_NO_START_OR_END")
        if self.state is SessionState.MONITORING and (
            self.started_at_us is None or self.ended_at_us is not None
        ):
            raise ValueError("MONITORING_SESSION_REQUIRES_START_WITHOUT_END")
        if self.state is SessionState.COMPLETED and (
            self.started_at_us is None or self.ended_at_us is None
        ):
            raise ValueError("COMPLETED_SESSION_REQUIRES_START_AND_END")
        if (
            self.started_at_us is not None and self.ended_at_us is not None
            and self.ended_at_us < self.started_at_us
        ):
            raise ValueError("SESSION_ENDS_BEFORE_IT_STARTS")
        return self


def advance_session(
    session: MonitoringSession, new_state: SessionState, at_us: int
) -> MonitoringSession:
    """Legal lifecycle step. Only state and lifecycle timestamps may change."""
    validate_session_transition(session.state, new_state)
    update: dict[str, object] = {"state": new_state}
    if new_state is SessionState.MONITORING:
        update["started_at_us"] = at_us
    if new_state in (SessionState.COMPLETED, SessionState.FAILED):
        update["ended_at_us"] = at_us
    candidate = session.model_copy(update=update)
    return MonitoringSession.model_validate(candidate.model_dump())
