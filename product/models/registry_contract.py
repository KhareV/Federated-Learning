"""CAPSTONE_MODEL_REGISTRY_CONTRACT_V1 + CAPSTONE_MODEL_GOVERNANCE_V1 (types only).

Two namespaces never mix: RELEASED scientific models (MODEL_V1, MODEL_V2_FINAL; frozen) and
CAPSTONE_FL_CANDIDATE_#### engineering sandbox candidates. A candidate is never a scientific
release and can never be production-deployed: ``production_deployed`` is the literal ``False`` and
no PRODUCTION_DEPLOYED lifecycle state exists.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.contracts import assert_transition, load_contract, transition_table
from product.federation.base import Algorithm

RELEASED_DEFAULT_MODEL_ID = "MODEL_V2_FINAL"
CANDIDATE_ID_PATTERN = re.compile(r"^CAPSTONE_FL_CANDIDATE_\d{4}$")
CLAIM_BOUNDARY = "CAPSTONE_ENGINEERING_SANDBOX_CANDIDATE_NOT_SCIENTIFIC_RELEASE"


class CandidateState(StrEnum):
    CREATED = "CREATED"
    VALIDATION_PENDING = "VALIDATION_PENDING"
    VALIDATING = "VALIDATING"
    ACCEPTED_TO_SANDBOX = "ACCEPTED_TO_SANDBOX"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class ValidationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class SandboxStatus(StrEnum):
    NOT_IN_SANDBOX = "NOT_IN_SANDBOX"
    IN_SANDBOX = "IN_SANDBOX"
    ARCHIVED = "ARCHIVED"


def candidate_transitions() -> dict[str, tuple[str, ...]]:
    return transition_table("model_governance", "candidate_transitions")


def validate_candidate_transition(current: CandidateState, new: CandidateState) -> None:
    assert_transition(candidate_transitions(), current.value, new.value, "CANDIDATE")


class ReleasedModelRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    namespace: Literal["RELEASED_SCIENTIFIC"] = "RELEASED_SCIENTIFIC"
    role: Literal["RELEASED_DEFAULT", "ROLLBACK_REFERENCE"]

    @model_validator(mode="after")
    def _known(self) -> ReleasedModelRef:
        known = load_contract("model_registry")["released_models"]
        if self.model_id not in known or known[self.model_id]["role"] != self.role:
            raise ValueError("NOT_A_FROZEN_RELEASED_MODEL")
        return self


class CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    parent_model_id: str
    federation_run_id: str = Field(min_length=1)
    round: int = Field(ge=1)
    algorithm: Algorithm
    client_count: int = Field(ge=1)
    created_at_us: int = Field(ge=0)
    state_digest: str = Field(min_length=1)
    validation_status: ValidationStatus
    governance_status: CandidateState
    sandbox_status: SandboxStatus
    production_deployed: Literal[False] = False
    claim_boundary: Literal["CAPSTONE_ENGINEERING_SANDBOX_CANDIDATE_NOT_SCIENTIFIC_RELEASE"] = (
        CLAIM_BOUNDARY
    )

    @model_validator(mode="after")
    def _consistent(self) -> CandidateModel:
        if not CANDIDATE_ID_PATTERN.match(self.candidate_id):
            raise ValueError("CANDIDATE_ID_MUST_USE_THE_CAPSTONE_FL_CANDIDATE_NAMESPACE")
        if self.candidate_id == self.parent_model_id:
            raise ValueError("CANDIDATE_CANNOT_BE_ITS_OWN_PARENT")
        if self.governance_status is CandidateState.ACCEPTED_TO_SANDBOX and (
            self.validation_status is not ValidationStatus.PASSED
            or self.sandbox_status is not SandboxStatus.IN_SANDBOX
        ):
            raise ValueError("SANDBOX_ACCEPTANCE_REQUIRES_PASSED_VALIDATION")
        if self.governance_status is CandidateState.REJECTED and (
            self.sandbox_status is SandboxStatus.IN_SANDBOX
        ):
            raise ValueError("REJECTED_CANDIDATE_CANNOT_BE_IN_SANDBOX")
        return self


class GovernanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    decision: Literal["ACCEPTED_TO_SANDBOX", "REJECTED"]
    checks: tuple[str, ...]
    decided_at_us: int = Field(ge=0)
    scientific_promotion: Literal[False] = False
    production_deployed: Literal[False] = False
