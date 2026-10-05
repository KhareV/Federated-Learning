# ruff: noqa: E501
"""CAPSTONE_MODEL_REGISTRY_V1 -- two namespaces that never mix.

RELEASED_SCIENTIFIC: MODEL_V1 (ROLLBACK_REFERENCE) and MODEL_V2_FINAL (RELEASED_DEFAULT), read from the
frozen model-registry contract. CAPSTONE_FL_CANDIDATE: ``CAPSTONE_FL_CANDIDATE_####`` engineering sandbox
candidates, allocated atomically; the first in an empty registry is 0001 and the parent is FL_INIT_V2.
The registry is READ-ONLY toward the released runtime: there is no promote, deploy or set-default."""

from __future__ import annotations

import threading
from typing import Any

from capstone_persistence.federation_store import FederationStore
from product.contracts import load_contract
from product.federation.base import Algorithm
from product.models.candidate_artifacts import (
    CandidateArtifactError,
    CandidateArtifactStore,
    candidate_id_for,
)
from product.models.registry_contract import (
    CLAIM_BOUNDARY,
    CandidateModel,
    CandidateState,
    ReleasedModelRef,
    SandboxStatus,
    ValidationStatus,
)

REGISTRY_ID = "CAPSTONE_MODEL_REGISTRY_V1"


class RegistryError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def candidate_from_row(row: dict[str, Any]) -> CandidateModel:
    return CandidateModel(
        candidate_id=row["candidate_id"], parent_model_id=row["parent_model_id"],
        federation_run_id=row["federation_run_id"], round=row["round"],
        algorithm=Algorithm(row["algorithm"]), client_count=row["client_count"],
        created_at_us=row["created_at_us"], state_digest=row["state_digest"],
        validation_status=ValidationStatus(row["validation_status"]),
        governance_status=CandidateState(row["governance_status"]),
        sandbox_status=SandboxStatus(row["sandbox_status"]),
        production_deployed=bool(row["production_deployed"]), claim_boundary=row["claim_boundary"])


class ModelRegistry:
    def __init__(self, store: FederationStore, artifacts: CandidateArtifactStore) -> None:
        self.store, self.artifacts = store, artifacts
        self._lock = threading.Lock()

    # ---- released namespace (frozen, read-only) --------------------------------------------------
    @staticmethod
    def released() -> list[ReleasedModelRef]:
        models = load_contract("model_registry")["released_models"]
        return [ReleasedModelRef(model_id=mid, role=spec["role"]) for mid, spec in models.items()]

    # ---- candidate namespace ---------------------------------------------------------------------
    def create_candidate(self, *, federation_run_id: str, parent_model_id: str, round_id: int,
                         algorithm: Algorithm, client_count: int, state: dict[str, Any],
                         extra_metadata: dict[str, Any]) -> CandidateModel:
        """Allocate the next ID, write the artifact (serialise -> verify -> atomic rename), THEN the row."""
        with self._lock:
            number = max(self.store.max_candidate_number(), self.artifacts.max_number()) + 1
            while True:
                candidate_id = candidate_id_for(number)
                try:
                    digests = self.artifacts.write(candidate_id, state, {
                        "federation_run_id": federation_run_id, "parent_model_id": parent_model_id,
                        "round": round_id, "algorithm": algorithm.value, "client_count": client_count,
                        "claim_boundary": CLAIM_BOUNDARY, "production_deployed": False,
                        **extra_metadata})
                    break
                except OSError:  # directory exists (another allocator won the rename): next number
                    number += 1
                except CandidateArtifactError:
                    raise
            self.store.insert_candidate(
                candidate_id=candidate_id, parent_model_id=parent_model_id,
                federation_run_id=federation_run_id, round_id=round_id, algorithm=algorithm.value,
                client_count=client_count, state_digest=digests["state_digest"],
                validation_status=ValidationStatus.PENDING.value,
                governance_status=CandidateState.CREATED.value,
                sandbox_status=SandboxStatus.NOT_IN_SANDBOX.value, claim_boundary=CLAIM_BOUNDARY)
        return self.get_candidate(candidate_id)

    def get_candidate(self, candidate_id: str) -> CandidateModel:
        row = self.store.get_candidate(candidate_id)
        if row is None:
            raise RegistryError("CANDIDATE_NOT_FOUND")
        return candidate_from_row(row)

    def list_candidates(self) -> list[CandidateModel]:
        return [candidate_from_row(r) for r in self.store.list_candidates()]

    def get_model(self, model_id: str) -> ReleasedModelRef | CandidateModel:
        for ref in self.released():
            if ref.model_id == model_id:
                return ref
        return self.get_candidate(model_id)

    def view(self) -> dict[str, Any]:
        return {"registry_id": REGISTRY_ID, "released_scientific": self.released(),
                "capstone_fl_candidates": self.list_candidates(),
                "released_default_model_id": "MODEL_V2_FINAL"}
