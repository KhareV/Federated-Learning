"""Strict read-only CAP-009 research evidence response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str
    value: str | bool | int | float | list[str]
    unit: str | None
    role: str
    phase: str
    source_relative_path: str
    source_sha256: str
    source_locator: list[str | int]
    interpretation: str
    limitations: str


class SourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: str
    source_relative_path: str
    source_sha256: str


class ResearchEvidenceBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: Literal["CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1"]
    evidence_version: Literal["FROZEN_SUMMARY_PROJECTION_V1"]
    generated_from_frozen_sources: Literal[True]
    facts: list[EvidenceFact]
    source_provenance: list[SourceProvenance]
    claim_boundary: Literal["READ_ONLY_NON_DIAGNOSTIC_RESEARCH_EVIDENCE"]


class MlResearchEvidence(ResearchEvidenceBase):
    evidence_domain: Literal["ML"] = "ML"


class FlResearchEvidence(ResearchEvidenceBase):
    evidence_domain: Literal["FL"] = "FL"
    scientific_fl_phases: tuple[
        Literal["V2-FL-001"], Literal["V2-FL-002"], Literal["V2-FL-003"],
        Literal["V2-FL-EVAL-001"], Literal["V2-FL-004"]
    ]
    v2_fl_005_role: Literal["FL_ENGINEERING_DEMO_NOT_SCIENTIFIC_EFFICACY"]
