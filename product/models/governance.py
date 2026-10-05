# ruff: noqa: E501
"""CAPSTONE_MODEL_GOVERNANCE_RUNTIME_V1 -- the five frozen STRUCTURAL validation checks and the
sandbox-only governance decision.

Governance: CREATED -> VALIDATION_PENDING -> VALIDATING -> ACCEPTED_TO_SANDBOX | REJECTED. ACCEPTED means
"accepted as a capstone engineering sandbox candidate" and nothing more: scientific_promotion and
production_deployed are False. No inference runs on a candidate and no metric is computed; only the five
check ids of CAPSTONE_MODEL_GOVERNANCE_V1 exist."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from capstone_persistence.federation_store import FederationStore
from federated.model_v2_fl import state_sha
from federated.wearable_fl_system_v1 import state_spec_sha
from product.contracts import load_contract
from product.models.registry_contract import (
    CandidateState,
    SandboxStatus,
    ValidationStatus,
    validate_candidate_transition,
)

GOVERNANCE_RUNTIME_ID = "CAPSTONE_MODEL_GOVERNANCE_RUNTIME_V1"
CHECK_IDS = ("STATE_FINITE", "STATE_SPEC_MATCHES_BASE", "UPDATE_DIGESTS_RECONCILE",
             "ROUND_ACCEPTED_UPDATE_COUNT_COMPLETE", "BASE_STATE_LINEAGE_VERIFIED")
assert tuple(load_contract("model_governance")["validation_gate"]["check_ids"]) == CHECK_IDS


@dataclass
class ValidationEvidence:
    candidate_state: dict[str, np.ndarray]          # loaded from the stored artifact, not memory
    base_state_spec_sha: str                         # FL_INIT_V2 state spec
    fl_init_sha: str
    cohort_size: int
    planned_rounds: int
    round_bases: dict[int, str]                      # round -> base digest the round was opened with
    committed: dict[int, str]                        # round -> committed global state digest
    coordinator_digests: dict[int, dict[str, str]]   # round -> client -> accepted update digest
    published_digests: dict[int, dict[str, str]]     # round -> client -> digest the client produced
    candidate_state_digest: str                      # registry row digest
    extra: dict[str, Any] = field(default_factory=dict)


def run_checks(e: ValidationEvidence) -> list[dict[str, Any]]:
    floating = [v for v in e.candidate_state.values() if np.issubdtype(np.asarray(v).dtype, np.floating)]
    final = max(e.committed) if e.committed else 0
    lineage = (
        bool(e.round_bases) and e.round_bases.get(1) == e.fl_init_sha
        and all(e.round_bases.get(r) == e.committed.get(r - 1) for r in range(2, e.planned_rounds + 1))
        and final == e.planned_rounds and e.committed.get(final) == e.candidate_state_digest
        and state_sha(e.candidate_state) == e.candidate_state_digest)
    reconcile = bool(e.coordinator_digests) and all(
        e.coordinator_digests[r] == e.published_digests.get(r)
        and all(len(d) == 64 for d in e.coordinator_digests[r].values())
        for r in e.coordinator_digests)
    complete = (sorted(e.coordinator_digests) == list(range(1, e.planned_rounds + 1))
                and all(len(e.coordinator_digests[r]) == e.cohort_size for r in e.coordinator_digests))
    results = {
        "STATE_FINITE": bool(floating) and all(bool(np.isfinite(v).all()) for v in floating),
        "STATE_SPEC_MATCHES_BASE": state_spec_sha(e.candidate_state) == e.base_state_spec_sha,
        "UPDATE_DIGESTS_RECONCILE": reconcile,
        "ROUND_ACCEPTED_UPDATE_COUNT_COMPLETE": complete,
        "BASE_STATE_LINEAGE_VERIFIED": lineage}
    return [{"check_id": c, "passed": results[c]} for c in CHECK_IDS]


class GovernanceRuntime:
    def __init__(self, store: FederationStore) -> None:
        self.store = store

    def _move(self, candidate_id: str, new: CandidateState, validation: ValidationStatus,
              sandbox: SandboxStatus) -> None:
        row = self.store.get_candidate(candidate_id)
        validate_candidate_transition(CandidateState(row["governance_status"]), new)
        self.store.update_candidate(candidate_id, validation_status=validation.value,
                                   governance_status=new.value, sandbox_status=sandbox.value)

    def mark_pending(self, candidate_id: str) -> None:
        self._move(candidate_id, CandidateState.VALIDATION_PENDING, ValidationStatus.PENDING,
                   SandboxStatus.NOT_IN_SANDBOX)

    def mark_validating(self, candidate_id: str) -> None:
        self._move(candidate_id, CandidateState.VALIDATING, ValidationStatus.RUNNING,
                   SandboxStatus.NOT_IN_SANDBOX)

    def decide(self, candidate_id: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
        """Accept to SANDBOX only if every frozen check passed; otherwise REJECTED."""
        passed = len(checks) == len(CHECK_IDS) and all(c["passed"] for c in checks) and (
            tuple(c["check_id"] for c in checks) == CHECK_IDS)
        if passed:
            self._move(candidate_id, CandidateState.ACCEPTED_TO_SANDBOX, ValidationStatus.PASSED,
                       SandboxStatus.IN_SANDBOX)
        else:
            self._move(candidate_id, CandidateState.REJECTED, ValidationStatus.FAILED,
                       SandboxStatus.NOT_IN_SANDBOX)
        decision = "ACCEPTED_TO_SANDBOX" if passed else "REJECTED"
        self.store.insert_decision(decision_id=f"{candidate_id}-GOV01", candidate_id=candidate_id,
                                   decision=decision, checks=checks)
        return {"decision": decision, "checks": checks, "scientific_promotion": False,
                "production_deployed": False}
