# ruff: noqa: E501
"""Typed, strict evaluation record (backend validation; the frontend parser mirrors these fields)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studio.constants import CLAIM_BOUNDARY, COHORT_USE_LABEL, EVAL_PROTOCOL_ID, OBSERVER_ID, RECORD_SCHEMA

Status = Literal["QUEUED", "EVALUATING", "COMPLETED", "FAILED"]


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Failure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str = Field(max_length=300)


class EvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["STUDIO_ROUND_EVALUATION_V1"] = RECORD_SCHEMA
    run_id: str = Field(min_length=1)
    run_length: Literal[3, 10]
    round_id: int = Field(ge=0)
    global_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str | None = None
    cohort_id: str
    cohort_use: str = COHORT_USE_LABEL
    evaluation_protocol_id: str = EVAL_PROTOCOL_ID
    observer_id: str = OBSERVER_ID
    evaluation_status: Status
    evaluation_queued_at: str
    evaluation_started_at: str | None = None
    evaluation_completed_at: str | None = None
    failure: Failure | None = None
    threshold: float = 0.5
    calibration: Literal["NONE"] = "NONE"
    windows: int | None = None
    metric_result: dict[str, Any] | None = None              # pooled metrics (full precision, None = UNDEFINED with reason in ``undefined``)
    participant_metrics: dict[str, Any] | None = None
    participant_summary: dict[str, Any] | None = None
    confusion_counts: dict[str, int] | None = None
    curve_artifact_reference: ArtifactRef | None = None
    prediction_artifact_reference: ArtifactRef | None = None
    source_digest: str | None = None
    claim_boundary: str = CLAIM_BOUNDARY

    @model_validator(mode="after")
    def _consistent(self) -> EvaluationRecord:
        done = self.evaluation_status == "COMPLETED"
        if done != (self.metric_result is not None) or done != (self.confusion_counts is not None):
            raise ValueError("METRICS_REQUIRED_IFF_COMPLETED")
        if done and (self.prediction_artifact_reference is None or self.source_digest is None or self.evaluation_completed_at is None):
            raise ValueError("COMPLETED_REQUIRES_PREDICTION_EVIDENCE")
        if (self.evaluation_status == "FAILED") != (self.failure is not None):
            raise ValueError("FAILURE_REQUIRED_IFF_FAILED")
        return self

    def light(self) -> dict[str, Any]:
        """Summary for polling: no curves, no per-participant detail, no histogram."""
        data = self.model_dump(mode="json", exclude={"participant_metrics", "metric_result"})
        if self.metric_result is not None:
            data["metric_result"] = {k: v for k, v in self.metric_result.items() if k not in ("histogram",)}
        return data
