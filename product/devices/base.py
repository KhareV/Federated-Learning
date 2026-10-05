"""DEVICE_SOURCE_CONTRACT_V1 -- the typed source boundary of the capstone product.

``DeviceSource`` is what BOTH the simulated wearable (CAP-002) and any future physical wearable
must implement. Whatever the source, it emits the repository's existing canonical
``simulation.types.ObservedRecord`` (contracts/sample_schema_v1.json) -- no replacement record
type exists or may be introduced -- so the existing ``WearableStreamRuntime`` and the frozen
POST /v1/infer-window path are reused unchanged. Hardware-specific fields that are not yet known
are marked VERIFICATION_REQUIRED and are never invented.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.contracts import (
    IllegalTransitionError,
    assert_transition,
    load_contract,
    transition_table,
)
from simulation.types import ObservedRecord

DEVICE_EVENT_VERSION = "DEVICE_EVENT_V1"
VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"


class AdapterType(StrEnum):
    SIMULATED = "SIMULATED"
    FUTURE_REAL = "FUTURE_REAL"


class DeviceState(StrEnum):
    DETACHED = "DETACHED"
    SCANNING = "SCANNING"
    FOUND = "FOUND"
    PAIRING = "PAIRING"
    CONNECTED = "CONNECTED"
    STREAMING = "STREAMING"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class DeviceEventType(StrEnum):
    SCAN_STARTED = "SCAN_STARTED"
    DEVICE_DISCOVERED = "DEVICE_DISCOVERED"
    PAIRING_STARTED = "PAIRING_STARTED"
    DEVICE_CONNECTED = "DEVICE_CONNECTED"
    STREAM_STARTED = "STREAM_STARTED"
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"
    RECONNECT_STARTED = "RECONNECT_STARTED"
    DEVICE_RECONNECTED = "DEVICE_RECONNECTED"
    STREAM_STOPPED = "STREAM_STOPPED"
    DEVICE_DETACHED = "DEVICE_DETACHED"
    DEVICE_ERROR = "DEVICE_ERROR"


def device_transitions() -> dict[str, tuple[str, ...]]:
    return transition_table("device_source", "device_transitions")


def validate_device_transition(current: DeviceState, new: DeviceState) -> None:
    """Raise IllegalTransitionError unless the frozen contract allows current -> new."""
    assert_transition(device_transitions(), current.value, new.value, "DEVICE")


def event_state_effect(event_type: DeviceEventType) -> DeviceState:
    return DeviceState(load_contract("device_source")["event_type_state_effects"][event_type.value])


class DeviceCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supports_ecg: bool
    supports_ppg: bool
    supports_spo2_context: bool
    supports_device_events: bool
    nominal_source_rates_hz: dict[str, int] | None = None


class DeviceDescriptor(BaseModel):
    """Identity + capabilities of one device. Carries no clinical-certification field and does
    not imply that physical hardware exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    adapter_type: AdapterType
    source_dataset_id: str | None = None
    source_mode: str | None = None
    connection_state: DeviceState
    capabilities: DeviceCapabilities
    simulation: bool
    simulation_version: str | None = None
    hardware_specific_fields_status: Literal["VERIFICATION_REQUIRED", "NOT_APPLICABLE"]

    @model_validator(mode="after")
    def _adapter_consistency(self) -> DeviceDescriptor:
        if self.adapter_type is AdapterType.SIMULATED:
            if not self.simulation or not self.simulation_version:
                raise ValueError("SIMULATED_REQUIRES_SIMULATION_FLAG_AND_VERSION")
            if self.hardware_specific_fields_status != "NOT_APPLICABLE":
                raise ValueError("SIMULATED_HAS_NO_HARDWARE_FIELDS")
        else:
            if self.simulation or self.simulation_version is not None:
                raise ValueError("FUTURE_REAL_MUST_NOT_CLAIM_SIMULATION")
            if self.hardware_specific_fields_status != VERIFICATION_REQUIRED:
                raise ValueError("FUTURE_REAL_HARDWARE_FIELDS_ARE_VERIFICATION_REQUIRED")
        return self


class DeviceEventMetadata(BaseModel):
    """Restricted, versioned metadata. Deliberately cannot carry model/physiological output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str | None = None
    attempt: int | None = Field(default=None, ge=0)
    detail: str | None = Field(default=None, max_length=200)


class DeviceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_version: Literal["DEVICE_EVENT_V1"] = DEVICE_EVENT_VERSION
    event_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    session_id: str | None = None
    sequence_index: int = Field(ge=0)
    event_type: DeviceEventType
    device_state: DeviceState
    source: AdapterType
    source_timestamp_us: int | None = Field(default=None, ge=0)
    product_timestamp_us: int = Field(ge=0)
    reason_code: str | None = None
    recoverable: bool
    metadata: DeviceEventMetadata = DeviceEventMetadata()

    @model_validator(mode="after")
    def _state_matches_event(self) -> DeviceEvent:
        if self.device_state is not event_state_effect(self.event_type):
            raise ValueError(f"EVENT_STATE_MISMATCH:{self.event_type}->{self.device_state}")
        return self


@runtime_checkable
class DeviceSource(Protocol):
    """Semantic source contract (see contracts/capstone/device_source_v1.json ``methods``)."""

    @property
    def descriptor(self) -> DeviceDescriptor: ...

    @property
    def connection_state(self) -> DeviceState: ...

    async def scan(self, timeout_s: float) -> Sequence[DeviceDescriptor]: ...

    async def connect(self, device_id: str) -> None: ...

    async def disconnect(self) -> None: ...

    async def start_stream(self, session_id: str) -> None: ...

    async def stop_stream(self) -> None: ...

    def records(self) -> AsyncIterator[ObservedRecord]: ...

    def events(self) -> AsyncIterator[DeviceEvent]: ...


__all__ = [
    "AdapterType", "DeviceCapabilities", "DeviceDescriptor", "DeviceEvent",
    "DeviceEventMetadata", "DeviceEventType", "DeviceSource", "DeviceState",
    "IllegalTransitionError", "device_transitions", "event_state_effect",
    "validate_device_transition",
]
