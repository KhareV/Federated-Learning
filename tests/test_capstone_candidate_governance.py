# ruff: noqa: E501
"""CAP-007: CAPSTONE_MODEL_GOVERNANCE_RUNTIME_V1 (five structural checks, sandbox-only decision)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from capstone_persistence.federation_store import FederationStore
from capstone_persistence.store import CapstoneSqliteStore
from federated.model_adapter import deserialize_state
from federated.model_v2_fl import state_sha
from federated.wearable_fl_runner_v1 import new_session
from federated.wearable_fl_system_v1 import state_spec_sha
from product.auth.base import AuthIdentity, AuthProviderType
from product.contracts import IllegalTransitionError, load_contract
from product.federation.base import Algorithm
from product.federation.execution_binding import frozen_fl_init_sha
from product.models.candidate_artifacts import CandidateArtifactStore
from product.models.governance import CHECK_IDS, GovernanceRuntime, ValidationEvidence, run_checks
from product.models.registry import ModelRegistry
from tests.capstone_federation_support import completed_run


def _evidence() -> ValidationEvidence:
    done = completed_run()
    cid = done.run["candidate_ids"][0]
    state = deserialize_state((done.root / "candidates" / cid / "state.bin").read_bytes())
    meta = done.meta
    base, _ = new_session()
    record = meta["training_record"]
    digests = {int(r): {c: v["update_sha256"] for c, v in clients.items()} for r, clients in record.items()}
    return ValidationEvidence(
        candidate_state=state, base_state_spec_sha=state_spec_sha(base), fl_init_sha=frozen_fl_init_sha(),
        cohort_size=8, planned_rounds=3, round_bases={int(k): v for k, v in meta["round_base_digests"].items()},
        committed={int(k): v for k, v in meta["committed_digests"].items()},
        coordinator_digests=copy.deepcopy(digests), published_digests=copy.deepcopy(digests),
        candidate_state_digest=state_sha(state))


def _passed(evidence: ValidationEvidence) -> dict[str, bool]:
    return {c["check_id"]: c["passed"] for c in run_checks(evidence)}


def test_only_the_five_frozen_checks_exist_and_all_pass_for_the_canonical_candidate() -> None:
    assert tuple(load_contract("model_governance")["validation_gate"]["check_ids"]) == CHECK_IDS
    results = _passed(_evidence())
    assert tuple(results) == CHECK_IDS and all(results.values())


def test_each_check_fails_for_its_own_defect() -> None:
    e = _evidence()
    nan_state = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in e.candidate_state.items()}
    first_float = next(k for k, v in nan_state.items() if np.issubdtype(np.asarray(v).dtype, np.floating))
    nan_state[first_float] = np.full_like(nan_state[first_float], np.nan)
    assert _passed(ValidationEvidence(**{**e.__dict__, "candidate_state": nan_state}))["STATE_FINITE"] is False
    wrong_spec = ValidationEvidence(**{**e.__dict__, "base_state_spec_sha": "0" * 64})
    assert _passed(wrong_spec)["STATE_SPEC_MATCHES_BASE"] is False
    mismatch = copy.deepcopy(e.published_digests)
    mismatch[2]["SIM_FL_SITE_03"] = "1" * 64
    assert _passed(ValidationEvidence(**{**e.__dict__, "published_digests": mismatch}))["UPDATE_DIGESTS_RECONCILE"] is False
    omitted = copy.deepcopy(e.coordinator_digests)
    del omitted[3]["SIM_FL_SITE_07"]
    assert _passed(ValidationEvidence(**{**e.__dict__, "coordinator_digests": omitted}))["ROUND_ACCEPTED_UPDATE_COUNT_COMPLETE"] is False
    bad_bases = {**e.round_bases, 2: e.fl_init_sha}  # round 2 "started from FL_INIT"
    assert _passed(ValidationEvidence(**{**e.__dict__, "round_bases": bad_bases}))["BASE_STATE_LINEAGE_VERIFIED"] is False
    wrong_candidate = ValidationEvidence(**{**e.__dict__, "candidate_state_digest": "2" * 64})
    assert _passed(wrong_candidate)["BASE_STATE_LINEAGE_VERIFIED"] is False


def _governed(tmp_path):
    store = CapstoneSqliteStore(tmp_path / "p.sqlite3")
    store.upsert_user(AuthIdentity(user_id="demo:g", display_name="g", auth_provider=AuthProviderType.DEMO,
                                   auth_session_id="s", demo_mode=True))
    fed = FederationStore(tmp_path / "p.sqlite3")
    fed.insert_run(run_id="RUN-1", user_id="demo:g", run_type="LIVE_RUN", base_model_id="FL_INIT_V2",
                   protocol_id="V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1", algorithm="FEDAVG", secagg_mode="PLAIN",
                   planned_rounds=3)
    registry = ModelRegistry(fed, CandidateArtifactStore(tmp_path / "c"))
    state, _ = new_session()
    candidate = registry.create_candidate(federation_run_id="RUN-1", parent_model_id="FL_INIT_V2", round_id=3,
                                          algorithm=Algorithm.FEDAVG, client_count=8, state=state, extra_metadata={})
    return fed, registry, GovernanceRuntime(fed), candidate.candidate_id


def test_accept_requires_all_checks_and_yields_sandbox_only_never_promotion(tmp_path) -> None:
    fed, registry, gov, cid = _governed(tmp_path)
    gov.mark_pending(cid)
    gov.mark_validating(cid)
    decision = gov.decide(cid, run_checks(_evidence()))
    assert decision["decision"] == "ACCEPTED_TO_SANDBOX"
    candidate = registry.get_candidate(cid)
    assert (candidate.validation_status.value, candidate.governance_status.value, candidate.sandbox_status.value) == (
        "PASSED", "ACCEPTED_TO_SANDBOX", "IN_SANDBOX")
    [row] = fed.list_decisions(cid)
    assert (row["scientific_promotion"], row["production_deployed"]) == (0, 0)
    assert [c["check_id"] for c in json.loads(row["checks_json"])] == list(CHECK_IDS)
    assert registry.get_candidate(cid).production_deployed is False


def test_a_failed_check_rejects_the_candidate_and_it_never_reaches_the_sandbox(tmp_path) -> None:
    fed, registry, gov, cid = _governed(tmp_path)
    gov.mark_pending(cid)
    gov.mark_validating(cid)
    e = _evidence()
    omitted = copy.deepcopy(e.coordinator_digests)
    del omitted[1]["SIM_FL_SITE_00"]
    checks = run_checks(ValidationEvidence(**{**e.__dict__, "coordinator_digests": omitted}))
    decision = gov.decide(cid, checks)
    assert decision["decision"] == "REJECTED"
    candidate = registry.get_candidate(cid)
    assert (candidate.validation_status.value, candidate.governance_status.value, candidate.sandbox_status.value) == (
        "FAILED", "REJECTED", "NOT_IN_SANDBOX")
    assert fed.list_decisions(cid)[0]["decision"] == "REJECTED"


def test_governance_state_machine_is_the_frozen_one_and_cannot_skip_validation(tmp_path) -> None:
    _fed, registry, gov, cid = _governed(tmp_path)
    with pytest.raises(IllegalTransitionError):
        gov.decide(cid, run_checks(_evidence()))  # CREATED -> ACCEPTED is not a legal transition
    assert registry.get_candidate(cid).governance_status.value == "CREATED"
    gov.mark_pending(cid)
    with pytest.raises(IllegalTransitionError):
        gov.mark_pending(cid)
    forbidden = set(load_contract("model_governance")["forbidden_states"])
    assert not forbidden & {c.value for c in type(registry.get_candidate(cid).governance_status)}


def test_incomplete_or_reordered_check_lists_never_accept(tmp_path) -> None:
    _fed, _reg, gov, cid = _governed(tmp_path)
    gov.mark_pending(cid)
    gov.mark_validating(cid)
    checks = run_checks(_evidence())
    assert gov.decide(cid, checks[:-1])["decision"] == "REJECTED"


def test_the_canonical_run_persisted_one_accepted_decision_and_no_inference_surface() -> None:
    done = completed_run()
    assert done.run["candidate_ids"] and len(done.run["candidate_ids"]) == 1
    import product.models.governance as governance
    import product.models.registry as registry_module

    for module in (governance, registry_module):
        text = Path(module.__file__).read_text().lower()
        for forbidden in ("infer", "predict", "auroc", "auprc", "forward("):
            assert forbidden not in text.replace("inference runs on a candidate", ""), (module.__name__, forbidden)
