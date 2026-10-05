"""Federation plane contracts: FL client, federation run/round lifecycle, update submission.

Pure types and interfaces. The FL client contract ADAPTS the existing V2 federated
infrastructure (federated/wearable_fl_system_v1.py coordinator + update envelope,
federated/virtual_client_source_v1.py local datasets, federated/model_v2_fl.py local training,
federated/model_v2_fedprox.py FedProx objective, privacy/secagg_app.py SecAgg+); it defines no
independent FL implementation, optimizer, aggregator or privacy mechanism.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.contracts import assert_transition, load_contract, transition_table


class Algorithm(StrEnum):
    FEDAVG = "FEDAVG"
    FEDPROX = "FEDPROX"


class AggregationMode(StrEnum):
    PLAIN = "PLAIN"
    SECAGG_SHADOW = "SECAGG_SHADOW"


class RunType(StrEnum):
    LIVE_RUN = "LIVE_RUN"
    REPLAY = "REPLAY"


class RunState(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RoundState(StrEnum):
    CREATED = "CREATED"
    COLLECTING = "COLLECTING"
    LOCAL_TRAINING = "LOCAL_TRAINING"
    UPDATES_READY = "UPDATES_READY"
    AGGREGATING = "AGGREGATING"
    CANDIDATE_CREATED = "CANDIDATE_CREATED"
    VALIDATING = "VALIDATING"
    ACCEPTED_TO_SANDBOX = "ACCEPTED_TO_SANDBOX"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ClientState(StrEnum):
    IDLE = "IDLE"
    DATA_READY = "DATA_READY"
    TRAINING = "TRAINING"
    UPDATE_READY = "UPDATE_READY"
    SUBMITTED = "SUBMITTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class SecAggStatus(StrEnum):
    NOT_USED = "NOT_USED"
    SHADOW_RUNNING = "SHADOW_RUNNING"
    SHADOW_VERIFIED = "SHADOW_VERIFIED"
    SHADOW_FAILED = "SHADOW_FAILED"


def round_transitions() -> dict[str, tuple[str, ...]]:
    return transition_table("federation", "round_transitions")


def run_transitions() -> dict[str, tuple[str, ...]]:
    return transition_table("fl_run", "run_transitions")


def client_transitions() -> dict[str, tuple[str, ...]]:
    return transition_table("fl_client", "client_transitions")


def validate_round_transition(current: RoundState, new: RoundState) -> None:
    assert_transition(round_transitions(), current.value, new.value, "ROUND")


def validate_run_transition(current: RunState, new: RunState) -> None:
    assert_transition(run_transitions(), current.value, new.value, "RUN")


def validate_client_transition(current: ClientState, new: ClientState) -> None:
    assert_transition(client_transitions(), current.value, new.value, "CLIENT")


class FLClientIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str = Field(min_length=1)
    edge_node_id: str = Field(min_length=1)
    base_model_id: str = Field(min_length=1)
    global_round: int = Field(ge=0)
    local_example_count: int = Field(ge=0)
    client_state: ClientState
    update_digest: str | None = None
    eligible: bool
    ineligible_reason: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> FLClientIdentity:
        if self.eligible == (self.ineligible_reason is not None):
            raise ValueError("INELIGIBLE_REASON_REQUIRED_IFF_NOT_ELIGIBLE")
        if self.client_state in (ClientState.UPDATE_READY, ClientState.SUBMITTED) and (
            not self.update_digest
        ):
            raise ValueError("UPDATE_STATES_REQUIRE_UPDATE_DIGEST")
        return self


class UpdateSubmission(BaseModel):
    """Server-visible submission: model-update metadata only. The extra=forbid schema cannot
    carry raw ECG/PPG/SpO2, SimulationTruth, labels or minibatches (data-locality policy)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str = Field(min_length=1)
    round_id: int = Field(ge=1)
    base_state_digest: str = Field(min_length=1)
    update_digest: str = Field(min_length=1)
    examples_seen: int = Field(ge=1)


class FederationRound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    round_id: int = Field(ge=1)
    state: RoundState
    participating_client_ids: tuple[str, ...]
    base_state_digest: str
    algorithm: Algorithm
    accepted_update_count: int = Field(ge=0)
    candidate_id: str | None = None


class FederationRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    run_type: RunType
    base_model_id: str
    federation_protocol_id: str
    algorithm: Algorithm
    client_ids: tuple[str, ...]
    planned_rounds: int = Field(ge=1)
    current_round: int = Field(ge=0)
    started_at_us: int | None = Field(default=None, ge=0)
    completed_at_us: int | None = Field(default=None, ge=0)
    status: RunState
    secagg_mode: AggregationMode
    candidate_ids: tuple[str, ...] = ()
    engineering_only: Literal[True] = True

    @model_validator(mode="after")
    def _consistent(self) -> FederationRun:
        if not self.client_ids or len(set(self.client_ids)) != len(self.client_ids):
            raise ValueError("CLIENT_IDS_MUST_BE_NON_EMPTY_AND_UNIQUE")
        if self.current_round > self.planned_rounds:
            raise ValueError("CURRENT_ROUND_EXCEEDS_PLANNED")
        contract = load_contract("fl_run")
        if self.federation_protocol_id not in contract["allowed_protocol_ids"]:
            raise ValueError("UNKNOWN_FEDERATION_PROTOCOL")
        if not (
            self.base_model_id in contract["allowed_base_model_ids"]
            or self.base_model_id.startswith(contract["candidate_base_prefix"])
        ):
            raise ValueError("BASE_MODEL_NOT_AN_ALLOWED_FEDERATION_START")
        if self.status is RunState.COMPLETED and self.completed_at_us is None:
            raise ValueError("COMPLETED_RUN_REQUIRES_COMPLETION_TIME")
        if self.status is RunState.CREATED and self.started_at_us is not None:
            raise ValueError("CREATED_RUN_HAS_NOT_STARTED")
        return self


@runtime_checkable
class FLClient(Protocol):
    """Product adapter over the existing V2 FL local-training path (reuse, not reimplementation)."""

    @property
    def identity(self) -> FLClientIdentity: ...

    async def local_train(self, round_id: int, base_state_digest: str) -> None: ...

    async def produce_update(self) -> UpdateSubmission: ...


@runtime_checkable
class FederationCoordinator(Protocol):
    """Thin orchestration adapter over federated.wearable_fl_system_v1.Coordinator."""

    async def create_run(self, run: FederationRun) -> FederationRun: ...

    async def start_run(self, run_id: str) -> FederationRun: ...

    def events(self, run_id: str) -> AsyncIterator[object]: ...
