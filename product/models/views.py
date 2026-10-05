# ruff: noqa: E501
"""CAP-007 API view/request models. The create-run request carries EXACTLY the five frozen request
fields (``extra='forbid'``): a model, checkpoint, mu, learning rate, optimizer, batch size, calibration,
threshold, base model or candidate id can never be submitted by a user."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.federation.base import AggregationMode, Algorithm, RunType
from product.models.registry_contract import CandidateModel, ReleasedModelRef


class CreateFederationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_type: RunType
    algorithm: Algorithm
    secagg_mode: AggregationMode
    planned_rounds: int = Field(ge=1, le=100)
    scenario_id: str = Field(min_length=1, max_length=80)


class FederationOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    federation_runtime: Literal["ENABLED_ENGINEERING"] = "ENABLED_ENGINEERING"
    engineering_only: Literal[True] = True
    scientific_evidence: Literal[False] = False
    production_deployed: Literal[False] = False
    banner: str
    client_count: int
    cohort_id: str
    active_live_run: bool
    candidate_count: int
    released_model_id: str
    secagg_claim_scope: Literal["PROTECTED_AGGREGATION_INTERFACE_ONLY"] = (
        "PROTECTED_AGGREGATION_INTERFACE_ONLY")


class ModelRegistryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_id: str
    released_default_model_id: str
    released_scientific: list[ReleasedModelRef]
    capstone_fl_candidates: list[CandidateModel]
