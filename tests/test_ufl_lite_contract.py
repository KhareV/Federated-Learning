# ruff: noqa: E501
"""UFL-LITE-001: contract + CURRENT-behaviour invariants (no runtime change). These are the Phase-2 non-interference assertions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from product.edge.local_training_buffer import LocalTrainingBufferV1
from product.federation.service import CLIENT_COUNT, get_cohort
from scripts import ufl_lite_lib as lib
from tests.capstone_federation_support import BASE, USER_A, USER_B, completed_run, make_fed_app

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / lib.CONTRACT).read_text())
BASELINE = lib.load_baseline(ROOT)


def test_contract_freezes_the_binding_without_any_computation_change() -> None:
    c = CONTRACT
    assert c["status"] == "FROZEN_ARCHITECTURE_CONTRACT" and c["owner_bound_client_id"] == "SIM_FL_SITE_00"
    assert c["synthetic_peer_client_ids"] == [f"SIM_FL_SITE_0{i}" for i in range(1, 8)] and c["client_count"] == 8 and c["synthetic_peer_count"] == 7
    assert c["planned_rounds"] == 3 and c["expected_updates"] == 24 and c["no_ninth_client"] is True
    assert c["qualifying_auth_mode"] == "CLERK" and c["qualifying_run_type"] == "LIVE_RUN" and "GLOBAL" in c["non_qualifying"]["global_clients_view"]
    for key in ("underlying_client_identity_unchanged", "underlying_dataset_unchanged", "training_algorithm_unchanged", "aggregation_unchanged", "secagg_unchanged", "fl_init_unchanged"):
        assert c[key] is True, key
    for key in ("monitoring_data_used_for_training", "monitoring_session_feeds_local_buffer", "real_user_physiology_claimed_as_training_data", "personal_model", "personalized_fl_claim", "prediction_as_label", "candidate_deployed"):
        assert c[key] is False, key
    assert c["canonical_candidate_digest"] == lib.CANONICAL_CANDIDATE_DIGEST and c["binding_decision"].startswith("DERIVED_AT_PRESENTATION_TIME")
    assert c["reuse"] == {**c["reuse"], "new_client_class": False, "new_training_buffer": False, "new_fl_pipeline": False, "db_migration": False}
    assert set(c["presentation_vocabulary"]["participation_role"]) == {"AUTHENTICATED_OWNER", "SYNTHETIC_PEER"} and c["site_00"]["dataset_represents_user_physiology"] is False


def test_current_cohort_has_exactly_eight_clients_with_the_frozen_ids_and_datasets() -> None:
    cohort = get_cohort()
    assert CLIENT_COUNT == 8 and lib.cohort_ok(list(cohort.client_ids))["ok"] and cohort.client_ids == lib.CLIENT_IDS
    assert cohort.identity == BASELINE["cohort_identity_digest"]
    for c in cohort.clients:
        frozen = BASELINE["datasets"][c.client_id]
        assert (str(c.buffer.dataset_sha256), c.buffer.eligible_count(), c.participant_id, c.edge_node_id) == (frozen["dataset_sha256"], frozen["local_example_count"], frozen["participant_id"], frozen["edge_node_id"])
        assert frozen["equals_frozen_v2_fl_005_reference"] is True


def test_site_00_uses_the_existing_buffer_and_synthetic_engineering_data() -> None:
    site = get_cohort().clients[0]
    assert site.client_id == "SIM_FL_SITE_00" and type(site.buffer) is LocalTrainingBufferV1
    assert lib.site00_ok(str(site.buffer.dataset_sha256), site.buffer.eligible_count(), BASELINE)["ok"] and site.buffer.eligible_count() == 93
    assert all(type(c.buffer) is LocalTrainingBufferV1 for c in get_cohort().clients)           # the SAME implementation for owner and peers
    assert CONTRACT["site_00"]["data_origin"] == "SYNTHETIC_ENGINEERING" and "SIMULATION_TRUTH" in CONTRACT["site_00"]["label_source"]


def test_local_training_buffers_are_client_local() -> None:
    cohort = get_cohort()
    site, other = cohort.clients[0], cohort.clients[1]
    for requester in (other.client_id, "SIM_USER_X"):
        try:
            site.buffer.training_arrays(requester_client_id=requester)
        except Exception as error:
            assert "CROSS_CLIENT" in str(error) or "OWNER" in str(error).upper() or "ACCESS" in str(error).upper(), error
        else:
            raise AssertionError("cross-client training access must be refused")


def test_no_monitoring_or_identity_source_feeds_federation_training_and_no_new_class_or_buffer() -> None:
    assert lib.monitoring_isolation_audit(ROOT)["ok"], lib.monitoring_isolation_audit(ROOT)
    assert lib.class_audit(ROOT)["ok"], lib.class_audit(ROOT)


def test_reused_modules_scientific_artifacts_and_auth_are_byte_identical_to_the_frozen_baseline() -> None:
    for group in ("reused_unchanged", "scientific", "auth"):
        assert lib.hash_drift(ROOT, BASELINE, group) == [], group
    assert lib.global_view_binding_audit(ROOT)["ok"]


def test_current_run_is_owned_by_its_user_and_the_clients_endpoint_is_global(tmp_path) -> None:
    from fastapi.testclient import TestClient

    app, _store = make_fed_app(tmp_path)
    body = {"run_type": "LIVE_RUN", "algorithm": "FEDAVG", "secagg_mode": "PLAIN", "planned_rounds": 3, "scenario_id": "FL_SINGLE_RUN"}
    with TestClient(app) as client:
        rid = client.post(f"{BASE}/federation/runs", json=body, headers=USER_A).json()["run_id"]
        owner = app.state.federation_service.owner_of(rid)
        assert owner and owner == app.state.federation_service.store.get_run(rid)["user_id"]      # the stored owner is the authenticated caller
        assert client.get(f"{BASE}/federation/runs/{rid}", headers=USER_B).status_code == 403
        assert [r["run_id"] for r in client.get(f"{BASE}/federation/runs", headers=USER_B).json()] == []
        assert [r["run_id"] for r in client.get(f"{BASE}/federation/runs", headers=USER_A).json()] == [rid]
        mine = client.get(f"{BASE}/federation/runs/{rid}", headers=USER_A).json()
        a, b = client.get(f"{BASE}/federation/clients", headers=USER_A).json(), client.get(f"{BASE}/federation/clients", headers=USER_B).json()
        assert a == b and [c["client_id"] for c in a] == list(lib.CLIENT_IDS)       # GLOBAL: identical for every user, run-independent
        assert tuple(mine["client_ids"]) == lib.CLIENT_IDS
        assert not any(k in c for c in a for k in ("participation_role", "owner", "user_id", "is_mine"))
        assert not any(k in mine for k in ("participation_role", "owner", "user_id"))


def test_completed_canonical_run_reproduces_the_frozen_digest_updates_and_sandbox_only_candidate() -> None:
    run = completed_run("FEDAVG", "SECAGG_SHADOW")
    assert run.run["status"] == "COMPLETED" and run.run["algorithm"] == "FEDAVG" and run.run["secagg_mode"] == "SECAGG_SHADOW" and len(run.run["client_ids"]) == 8
    assert [r["accepted_update_count"] for r in run.rounds] == [8, 8, 8] and sum(r["accepted_update_count"] for r in run.rounds) == 24
    assert sum(1 for e in run.events if e["event_type"] == "client.update_ready") == 24
    with sqlite3.connect(run.root / "product.sqlite3") as db:
        rows = db.execute("select candidate_id, state_digest, parent_model_id, validation_status, governance_status, sandbox_status, production_deployed, client_count from candidate_models").fetchall()
    assert len(rows) == 1
    _cid, digest, parent, validation, governance, sandbox, deployed, clients = rows[0]
    assert lib.candidate_digest_ok(digest) and parent == "FL_INIT_V2" and clients == 8
    assert (validation, governance, sandbox, deployed) == ("PASSED", "ACCEPTED_TO_SANDBOX", "IN_SANDBOX", 0)
    assert sorted(BASELINE["committed_round_state_digests"]) == ["1", "2", "3"] and run.meta is not None      # frozen per-round digests are available for Phase 2 comparisons
    assert lib.identity_in_payload(run.meta) == [] and lib.identity_in_payload([e["payload"] for e in run.events if e["event_type"].startswith("client.")]) == []


def test_released_monitoring_model_and_calibration_are_unchanged() -> None:
    from product.session import default_runtime_identity

    runtime = default_runtime_identity()
    assert runtime.model_id == "MODEL_V2_FINAL" and runtime.software_system_id == "SOFTWARE_SYSTEM_V2"
    assert BASELINE["released_monitoring_model"] == "MODEL_V2_FINAL" and BASELINE["calibration"] == "CAL_V2"


def test_identity_leak_scanner_catches_clerk_identity_in_a_payload() -> None:
    assert lib.identity_in_payload({"client_id": "SIM_FL_SITE_00", "examples_seen": 93}) == []
    assert lib.identity_in_payload({"payload": {"user_id": "user_2abcDEFghi"}})
    assert lib.identity_in_payload({"note": "owner@example.com"})
