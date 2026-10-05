"""LOCAL_TRAINING_BUFFER_CONTRACT_V1 -- schema/interface only (no storage is implemented).

The buffer is the ONLY bridge between an edge node's observed stream and its local FL trainer. It
holds a *reference* to the model-input representation (never raw samples shipped to the server),
a label with an explicit label_source, and quality eligibility. Simulation labels come exclusively
from the dedicated SIMULATION_LABEL_ADAPTER_V1 (the existing client-local adapter
federated/wearable_sim_local_labels.py is the reuse candidate); they never touch the live path.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.contracts import load_contract


class LabelSource(StrEnum):
    SIMULATION_TRUTH_ENGINEERING = "SIMULATION_TRUTH_ENGINEERING"
    # Future real-wearable label sources: no validated acquisition protocol exists yet.
    VERIFIED_ANNOTATION = "VERIFIED_ANNOTATION"
    CLINICIAN_REVIEW = "CLINICIAN_REVIEW"
    EXPERT_ADJUDICATION = "EXPERT_ADJUDICATION"


def forbidden_label_sources() -> tuple[str, ...]:
    return tuple(load_contract("training_buffer")["forbidden_label_sources"])


class TrainingBufferRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    window_id: str = Field(min_length=1)
    model_input_ref: str = Field(min_length=1)
    label: int = Field(ge=0, le=1)
    label_source: LabelSource
    quality_eligible: bool
    timestamp_us: int = Field(ge=0)
    simulation: bool
    provenance_id: str = Field(min_length=1)
    buffer_batch_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _label_source_matches_data_origin(self) -> TrainingBufferRecord:
        sim_label = self.label_source is LabelSource.SIMULATION_TRUTH_ENGINEERING
        if self.simulation and not sim_label:
            raise ValueError("SIMULATED_RECORD_REQUIRES_SIMULATION_TRUTH_ENGINEERING_LABEL")
        if not self.simulation and sim_label:
            raise ValueError("SIMULATION_TRUTH_ENGINEERING_FORBIDDEN_FOR_REAL_DATA")
        if not self.simulation and self.label_source.value in load_contract("training_buffer")[
            "unvalidated_real_label_sources"
        ]:
            raise ValueError("REAL_LABEL_SOURCE_VERIFICATION_REQUIRED")
        return self


@runtime_checkable
class SimulationLabelAdapter(Protocol):
    """SIMULATION_LABEL_ADAPTER_V1: the only consumer of SimulationTruth, sandbox-only."""

    def labels_for_windows(self, right_edges_us: Sequence[int]) -> Sequence[int]: ...


@runtime_checkable
class LocalTrainingBuffer(Protocol):
    @property
    def client_id(self) -> str: ...

    def append_batch(self, records: Sequence[TrainingBufferRecord]) -> str: ...

    def batch_ids(self) -> Sequence[str]: ...

    def eligible_count(self) -> int: ...
