# ruff: noqa: E501
"""CAP-007: the orchestrator end to end (public policy, canonical FEDAVG run, V2-FL-005 parity, events)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from federated.model_v2_fl import state_sha
from federated.wearable_fl_runner_v1 import new_session
from product.events import FEDERATION_EVENT_KINDS, parse_federation_event
from product.federation.client import ClientError
from product.federation.client_v2 import CapstoneFlClientAdapterV2
from product.federation.execution_binding import (
    BINDING_PATH,
    BindingViolation,
    frozen_fl_init_sha,
    verify_round_base,
)
from tests.capstone_federation_support import (
    BASE,
    SINGLE_RUN,
    USER_A,
    completed_run,
    make_fed_app,
    reference,
)

CLIENTS = [f"SIM_FL_SITE_{i:02d}" for i in range(8)]


# ---- public request policy ---------------------------------------------------------------------
@pytest.mark.parametrize("patch", [
    {"scenario_id": "FL_NEW_LOCAL_BATCH"}, {"scenario_id": "FL_MULTIRUN_CANDIDATE_HISTORY"},
    {"scenario_id": "NORMAL_MONITORING"}, {"scenario_id": "FL_RESTART_RESUME"},
    {"scenario_id": "FL_REJECT_INVALID_UPDATE"}, {"scenario_id": "FL_SECAGG_SHADOW"},
    {"planned_rounds": 2}, {"planned_rounds": 4}, {"planned_rounds": 1},
])
def test_public_create_run_rejects_every_non_frozen_scenario_and_round_count(tmp_path, patch) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(f"{BASE}/federation/runs", json={**SINGLE_RUN, **patch}, headers=USER_A)
        assert response.status_code == 400, response.text
        assert client.get(f"{BASE}/federation/runs", headers=USER_A).json() == []


@pytest.mark.parametrize("field", ["mu", "learning_rate", "optimizer", "batch_size", "model_id",
                                   "checkpoint", "calibration", "threshold", "base_model_id",
                                   "candidate_id"])
def test_a_user_can_never_submit_a_model_or_hyperparameter_field(tmp_path, field) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(f"{BASE}/federation/runs", json={**SINGLE_RUN, field: "x"}, headers=USER_A)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_request_fields_are_exactly_the_five_frozen_fields() -> None:
    from product.models.views import CreateFederationRunRequest

    assert set(CreateFederationRunRequest.model_fields) == {
        "run_type", "algorithm", "secagg_mode", "planned_rounds", "scenario_id"}
    binding = json.loads(BINDING_PATH.read_text())
    assert set(binding["public_request_fields"]) == set(CreateFederationRunRequest.model_fields)


# ---- client V2 / lineage -----------------------------------------------------------------------
def test_round_two_cannot_start_from_fl_init_and_model_v2_final_is_never_a_base() -> None:
    state, _ = new_session()
    assert verify_round_base(round_id=1, state=state, committed={}) == frozen_fl_init_sha()
    with pytest.raises(BindingViolation) as wrong:
        verify_round_base(round_id=2, state=state, committed={1: "f" * 64})
    assert wrong.value.code == "ROUND_BASE_LINEAGE_MISMATCH"
    with pytest.raises(BindingViolation) as missing:
        verify_round_base(round_id=2, state=state, committed={})
    assert missing.value.code == "PREVIOUS_ROUND_NOT_COMMITTED"
    with pytest.raises(BindingViolation) as final:
        verify_round_base(round_id=1, state=state, committed={}, base_model_id="MODEL_V2_FINAL")
    assert final.value.code == "BASE_MODEL_NOT_ALLOWED"
    with pytest.raises(BindingViolation) as cand:
        verify_round_base(round_id=1, state=state, committed={}, base_model_id="CAPSTONE_FL_CANDIDATE_0001")
    assert cand.value.code == "CANDIDATE_BASE_NOT_ENABLED_YET"


def test_client_v2_refuses_unverified_bases_and_reuses_the_v1_training_path() -> None:
    from product.federation import client as v1
    from product.federation.service import get_cohort

    cohort = get_cohort()
    c = cohort.clients[0]
    state, _ = new_session()
    ok = CapstoneFlClientAdapterV2(c.buffer, edge_node_id=c.edge_node_id, participant_id=c.participant_id,
                                   session_id=c.session_id, round_id=1, base_state=state, committed={})
    assert ok.base_state_sha == state_sha(state)
    with pytest.raises(ClientError) as error:
        CapstoneFlClientAdapterV2(c.buffer, edge_node_id=c.edge_node_id, participant_id=c.participant_id,
                                  session_id=c.session_id, round_id=2, base_state=state,
                                  committed={1: "0" * 64})
    assert error.value.code == "ROUND_BASE_LINEAGE_MISMATCH"
    assert issubclass(CapstoneFlClientAdapterV2, v1.CapstoneFlClientAdapterV1)
    assert "local_train" not in CapstoneFlClientAdapterV2.__dict__  # inherited, not re-implemented


# ---- canonical run: shape + parity -------------------------------------------------------------
def test_canonical_fedavg_run_shape() -> None:
    done = completed_run()
    run = done.run
    assert run["status"] == "COMPLETED" and run["run_type"] == "LIVE_RUN"
    assert run["base_model_id"] == "FL_INIT_V2" and run["client_ids"] == CLIENTS
    assert run["planned_rounds"] == 3 and run["current_round"] == 3 and run["engineering_only"] is True
    assert run["candidate_ids"] == ["CAPSTONE_FL_CANDIDATE_0001"]
    assert [r["state"] for r in done.rounds] == ["COMPLETED"] * 3
    assert [r["accepted_update_count"] for r in done.rounds] == [8, 8, 8]
    assert [r["candidate_id"] for r in done.rounds] == [None, None, "CAPSTONE_FL_CANDIDATE_0001"]


def test_canonical_run_has_exact_v2_fl_005_lineage_and_update_parity() -> None:
    done, ref = completed_run(), reference()
    states = {r: ref["state_progression"][str(r)]["sha256"] for r in range(4)}
    assert [r["base_state_digest"] for r in done.rounds] == [states[0], states[1], states[2]]
    assert done.meta["final_global_state_sha256"] == states[3]
    assert done.meta["committed_digests"] == {"1": states[1], "2": states[2], "3": states[3]}
    record = done.meta["training_record"]
    updates = 0
    for r in ("1", "2", "3"):
        rr = ref["round_reports"][r]
        assert sorted(record[r]) == CLIENTS
        for client in CLIENTS:
            got = record[r][client]
            assert got["examples_seen"] == rr["examples_seen"][client]
            assert got["shuffle_seed"] == rr["shuffle_seeds"][client]
            assert got["update_sha256"] == rr["update_sha256"][client]
            updates += 1
    assert updates == 24


def test_events_are_valid_contiguous_federation_only_and_deterministic() -> None:
    done = completed_run()
    kinds = {e["event_type"] for e in done.events}
    assert kinds <= set(FEDERATION_EVENT_KINDS) and len(FEDERATION_EVENT_KINDS) == 12
    assert [e["sequence_index"] for e in done.events] == list(range(len(done.events)))
    assert all(e["event_id"] == f"{done.run_id}-FEV{e['sequence_index']:06d}" for e in done.events)
    for e in done.events:
        parse_federation_event(e)
    assert done.events[0]["payload"]["run_status"] == "CREATED"
    assert done.events[-1]["event_type"] == "federation.completed"
    progress = [e for e in done.events if e["event_type"] == "client.training_progress"]
    assert len(progress) == 48 and {e["payload"]["progress_fraction"] for e in progress} == {0.0, 1.0}
    ready = [e for e in done.events if e["event_type"] == "client.update_ready"]
    assert len(ready) == 24
    assert sum(e["event_type"] == "candidate.created" for e in done.events) == 1


def test_round_state_paths_match_the_frozen_v2_contract() -> None:
    done = completed_run()
    by_round: dict[int, list[str]] = {}
    for e in done.events:
        if e["event_type"] == "round.status":
            by_round.setdefault(e["payload"]["round_id"], []).append(e["payload"]["round_state"])
    common = ["COLLECTING", "LOCAL_TRAINING", "UPDATES_READY", "AGGREGATING"]
    assert by_round[1] == by_round[2] == [*common, "COMPLETED"]
    assert by_round[3] == [*common, "CANDIDATE_CREATED", "VALIDATING", "ACCEPTED_TO_SANDBOX", "COMPLETED"]


def test_no_event_or_row_carries_data_labels_truth_or_tensors() -> None:
    done = completed_run()
    blob = json.dumps(done.events).lower()
    for forbidden in ("ecg_samples", "waveform", "label", "truth", "tensor", "delta", "state.bin"):
        assert forbidden not in blob, forbidden


def test_invalid_update_probe_uses_the_existing_rejection_logic_and_creates_nothing(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    probe = app.state.federation_service.invalid_update_probe()
    codes = {r["case"]: (r["decision"], r["code"]) for r in probe["results"]}
    assert codes["VALID"] == ("ACCEPTED", None)
    for case in ("DUPLICATE_UPDATE", "STALE_ROUND", "BASE_STATE_MISMATCH", "UNKNOWN_CLIENT"):
        assert codes[case] == ("REJECTED", case)
    assert probe["accepted_after"] == 1 and probe["round_complete"] is False
    assert probe["candidate_created"] is False
    assert app.state.federation_store.counts() == {
        "federation_runs": 0, "federation_rounds": 0, "fl_client_statuses": 0,
        "candidate_models": 0, "governance_decisions": 0}
