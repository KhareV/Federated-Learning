"""Read-only trace parity, ownership and raw-context exclusion controls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

import product.observatory.federation as federation
import product.observatory.research_record as research_record
from api.product_app_observatory_v1 import create_product_app_observatory_v1
from api.product_app_v1_3 import create_product_app_v1_3
from capstone_persistence.store import CapstoneSqliteStore
from federated.virtual_client_source_v1 import is_trainable, stream_windows
from federated.wearable_sim_local_labels import SyntheticEventLabelProvider, SyntheticObservedSource
from preprocessing.windowing import normalize_window_zscore
from product.devices.scenarios import ScenarioSegment, ScenarioSpec, load_scenarios
from product.federation.artifact_store import FederationArtifactStore
from product.federation.base import AggregationMode, Algorithm, FederationRun, RunState, RunType
from product.federation.execution_binding import PROTOCOL_ID
from product.federation.service import RunContext
from product.observatory.acceptance_capture import capture_file, read_verified, snapshot
from product.observatory.federation import (
    _attested_final_updates,
    fl_client_window,
    frozen_cohort,
    run_contributions,
)
from product.observatory.live_capture import LiveWindowCapture
from product.observatory.pipeline import reconstruct_window
from product.observatory.research_record import inspect_train_window, list_train_records
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver
from simulation.fl_cohort_v1 import client_profile
from simulation.profile_v2013 import iter_observed_records
from simulation.stream_runtime_v2013 import CHUNK_RECORDS, WearableStreamRuntime
from tests.capstone_federation_support import DESCRIPTION, SINGLE_RUN, USER_A, USER_B
from tests.capstone_persistent_support import StrictInferenceDouble, collect_ws, provisioned_session
from tests.test_capstone_history_evidence import seed


def _unobserved_window(scenario: ScenarioSpec, index: int):
    runtime = WearableStreamRuntime(session_id="PARITY", model_id="MODEL_V2_FINAL",
                                    replay_id="PARITY")
    batch = []
    for record in iter_observed_records(scenario.profile()):
        batch.append(record)
        if len(batch) == CHUNK_RECORDS:
            emitted = runtime.ingest(batch)
            batch = []
            selected = next((w for w in emitted if w["sequence_index"] == index), None)
            if selected is not None:
                return selected
    raise AssertionError("canonical window not emitted")


def test_observer_delegates_to_canonical_pipeline_without_output_drift() -> None:
    for scenario, index in ((load_scenarios()["NORMAL_MONITORING"], 0),
                            (load_scenarios()["DISCONNECT_RECONNECT"], 12)):
        trace = reconstruct_window(scenario, index)
        original = _unobserved_window(scenario, index)
        assert trace.quality_state == original["ecg_quality"]
        assert trace.quality_reasons == original["diagnostics"]["quality_reasons"]
        assert trace.right_timestamp_us == original["timestamp_us"]
        assert trace.window_sample_count == len(original["ecg"]["samples"]) == 2500
        filtered = next(stage for stage in trace.stages
                        if stage.stage_id == "PREPROC_V1_ECG_FILTER_V1")
        assert filtered.actual_point_count >= 2400 or trace.quality_state == "UNUSABLE"
        assert all(trace.left_timestamp_us <= p.timestamp_us < trace.right_timestamp_us
                   for p in filtered.points)
        if trace.quality_state == "UNUSABLE":
            assert trace.normalization.status == "NOT_APPLIED_UNUSABLE"
        else:
            normalized = normalize_window_zscore(np.asarray(original["ecg"]["samples"]))
            tensor = np.ascontiguousarray(normalized.astype(np.float32).reshape(1, 2500))
            assert trace.normalization.tensor_sha256 == hashlib.sha256(tensor.tobytes()).hexdigest()
        assert trace.persisted_inference is None
        assert trace.classification == "DETERMINISTIC_LOCAL_RECONSTRUCTION"
        assert all(stage.displayed_point_count <= 1200 for stage in trace.stages)


@pytest.mark.parametrize("scenario_id,window_index", [
    ("NORMAL_MONITORING", 0), ("DISCONNECT_RECONNECT", 12),
])
def test_opt_in_live_capture_parity_with_unobserved_runtime(scenario_id: str,
                                                             window_index: int) -> None:
    scenario = load_scenarios()[scenario_id]
    observed = WearableStreamRuntime(session_id="LIVE_CAPTURE_TEST", model_id="MODEL_V2_FINAL",
                                     replay_id="PARITY")
    plain = WearableStreamRuntime(session_id="LIVE_CAPTURE_TEST", model_id="MODEL_V2_FINAL",
                                  replay_id="PARITY")
    capture = LiveWindowCapture(observed, scenario_id=scenario.scenario_id,
                                session_id="LIVE_CAPTURE_TEST", window_index=window_index)
    batch = []
    for record in iter_observed_records(scenario.profile()):
        batch.append(record)
        if len(batch) < CHUNK_RECORDS:
            continue
        observed_windows = observed.ingest(batch)
        plain_windows = plain.ingest(batch)
        assert observed_windows == plain_windows
        batch = []
        if capture.trace is not None:
            break
    assert capture.error is None and capture.trace is not None
    assert capture.trace.classification == "CAPTURED_LIVE_PREPROCESSING"
    reconstruction = reconstruct_window(scenario, window_index, session_id="LIVE_CAPTURE_TEST")
    assert capture.trace.quality_state == reconstruction.quality_state
    assert capture.trace.quality_reasons == reconstruction.quality_reasons
    assert capture.trace.gaps == reconstruction.gaps
    assert capture.trace.stages == reconstruction.stages
    assert capture.trace.normalization == reconstruction.normalization


def test_short_gap_trace_shows_causal_fill_without_future_value() -> None:
    scenario = ScenarioSpec(
        scenario_id="TEST_SHORT_GAP", seed=20260927, duration_s=45,
        segments=(ScenarioSegment("short", 20.0, 20.08, "ECG_SHORT_GAP", "VALID"),),
    )
    trace = reconstruct_window(scenario, 2)  # [15 s, 25 s)
    assert trace.gaps and trace.gaps[0].kind == "SHORT"
    gap = trace.gaps[0]
    assert gap.fill_count == gap.missing_count
    assert gap.duration_ms <= 100
    assert gap.previous_segment_id == gap.next_segment_id


def test_authenticated_session_trace_owner_and_projected_context_only(tmp_path: Path) -> None:
    store = CapstoneSqliteStore(tmp_path / "product.sqlite3", clock=lambda: 12_000_000)
    app = create_product_app_observatory_v1(
        store=store, identity_resolver=cap003_test_identity_resolver,
        auth_description=DESCRIPTION, federation_artifact_root=tmp_path / "federation",
        candidate_root=tmp_path / "candidates", auto_resume=False,
    )
    with TestClient(app) as client:
        scenario_path = "/product/v1/observatory/scenarios/NORMAL_MONITORING/windows/0"
        assert client.get(scenario_path).status_code == 401
        scenario = client.get(scenario_path, headers=USER_A)
        assert scenario.status_code == 200, scenario.text
        assert scenario.json()["persisted_inference"] is None
        sid = seed(client, store)
        owned_path = f"/product/v1/observatory/sessions/{sid}/windows/7"  # 50 s edge
        assert client.get(owned_path).status_code == 401
        assert client.get(owned_path, headers=USER_B).status_code == 403
        owned = client.get(owned_path, headers=USER_A)
        assert owned.status_code == 200, owned.text
        body = owned.json()
        assert body["persisted_inference"]["model_id"] == "MODEL_V2_FINAL"
        assert body["context_available"] is False  # projected snapshot, not raw context_json
        assert "WITHHELD_SENTINEL" not in owned.text
        assert "666.0" not in owned.text
        assert client.get(f"/product/v1/observatory/sessions/{sid}/windows/6",
                          headers=USER_A).status_code == 404


def test_live_capture_arm_requires_owner_and_prestart_state(tmp_path: Path) -> None:
    store = CapstoneSqliteStore(tmp_path / "product.sqlite3")
    app = create_product_app_observatory_v1(
        store=store, identity_resolver=cap003_test_identity_resolver,
        auth_description=DESCRIPTION, federation_artifact_root=tmp_path / "federation",
        candidate_root=tmp_path / "candidates", auto_resume=False,
    )
    base = "/product/v1"
    with TestClient(app) as client:
        device = client.post(f"{base}/devices/simulated",
                             json={"scenario_id": "NORMAL_MONITORING"},
                             headers=USER_A).json()
        device_id = device["device_id"]
        assert client.post(f"{base}/devices/{device_id}/scan", headers=USER_A).status_code == 200
        assert client.post(f"{base}/devices/{device_id}/connect", headers=USER_A).status_code == 200
        session = client.post(f"{base}/sessions",
                              json={"device_id": device_id,
                                    "scenario_id": "NORMAL_MONITORING"},
                              headers=USER_A).json()
        path = f"{base}/observatory/sessions/{session['session_id']}/capture/0"
        assert client.post(path).status_code == 401
        assert client.post(path, headers=USER_B).status_code == 403
        assert client.post(path.replace("/capture/0", "/capture/9999"),
                           headers=USER_A).status_code == 400
        response = client.post(path, headers=USER_A)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ARMED_BEFORE_START"
        assert client.get(path.rsplit("/", 1)[0], headers=USER_B).status_code == 403


def test_opt_in_capture_of_real_session_preserves_inference_and_source_parity(tmp_path: Path
                                                                             ) -> None:
    double = StrictInferenceDouble()
    store = CapstoneSqliteStore(tmp_path / "product.sqlite3")
    app = create_product_app_observatory_v1(
        store=store, identity_resolver=cap003_test_identity_resolver,
        auth_description=DESCRIPTION, inference_client_factory=double.client,
        federation_artifact_root=tmp_path / "federation", candidate_root=tmp_path / "candidates",
        auto_resume=False,
    )
    with TestClient(app) as client:
        _, sid = provisioned_session(client, "NORMAL_MONITORING")
        capture_url = f"/product/v1/observatory/sessions/{sid}/capture"
        assert client.post(f"{capture_url}/0", headers=USER_A).status_code == 200
        assert client.post(f"/product/v1/sessions/{sid}/start", headers=USER_A).status_code == 200
        collect_ws(client, sid)
        captured = client.get(capture_url, headers=USER_A)
        assert captured.status_code == 200, captured.text
        body = captured.json()
        assert body["classification"] == "CAPTURED_LIVE_PREPROCESSING"
        assert body["persisted_inference"]["model_id"] == "MODEL_V2_FINAL"
        rebuilt = client.get(f"/product/v1/observatory/sessions/{sid}/windows/0",
                             headers=USER_A).json()
        for field in ("stages", "gaps", "quality_state", "quality_reasons", "normalization",
                      "persisted_inference"):
            assert body[field] == rebuilt[field]
        assert client.get(capture_url, headers=USER_B).status_code == 403
        assert len(double.requests) == len(store.rows("inference_events")) == 21
    restarted = create_product_app_observatory_v1(
        store=store, identity_resolver=cap003_test_identity_resolver,
        auth_description=DESCRIPTION, inference_client_factory=double.client,
        federation_artifact_root=tmp_path / "federation", candidate_root=tmp_path / "candidates",
        auto_resume=False,
    )
    with TestClient(restarted) as client:
        assert client.get(capture_url, headers=USER_A).status_code == 404
        assert client.get(f"/product/v1/observatory/sessions/{sid}/windows/0",
                          headers=USER_A).status_code == 200
        assert len(double.requests) == 21


def test_frozen_cohort_counts_and_direct_acceptance_only(tmp_path: Path) -> None:
    cohort = frozen_cohort()
    assert len(cohort.clients) == 8
    assert sum(c.windows_emitted for c in cohort.clients) == 744
    assert sum(c.trainable for c in cohort.clients) == 723
    assert sum(c.synthetic_positive for c in cohort.clients) == 150
    assert sum(c.unusable for c in cohort.clients) == 17
    artifacts = FederationArtifactStore(tmp_path / "federation")
    run = FederationRun(
        run_id="RUN_OBSERVATORY_TEST", run_type=RunType.LIVE_RUN, base_model_id="FL_INIT_V2",
        federation_protocol_id=PROTOCOL_ID, algorithm=Algorithm.FEDAVG,
        client_ids=tuple(c.client_id for c in cohort.clients), planned_rounds=3, current_round=3,
        started_at_us=1, completed_at_us=2, status=RunState.COMPLETED,
        secagg_mode=AggregationMode.PLAIN,
    )
    artifacts.write_run_meta(run.run_id, {
        "training_record": {
            "1": {"SIM_FL_SITE_00": {"examples_seen": 93, "shuffle_seed": 42,
                                        "update_sha256": "digest0"},
                  "SIM_FL_SITE_07": {"examples_seen": 83, "shuffle_seed": 43,
                                        "update_sha256": "digest7"}},
            "3": {"SIM_FL_SITE_00": {"examples_seen": 93, "shuffle_seed": 44,
                                        "update_sha256": "digest-last"}},
        },
        "coordinator_digests": {"1": {"SIM_FL_SITE_00": "digest0",
                                       "SIM_FL_SITE_07": "digest7"}},
        "round_base_digests": {"1": "base-1", "3": "base-3"},
        "committed_digests": {"1": "global-1", "3": "global-3"},
    })
    view = run_contributions(run, artifacts)
    first = view.rounds[0]
    assert first.accepted_update_count == 2
    assert first.accepted_example_total == 176
    assert sum(c.weight or 0 for c in first.clients) == 1
    last = view.rounds[-1]
    assert last.round_id == 3 and last.accepted_update_count is None
    assert last.clients[0].evidence_state == "TRAINED_ACCEPTANCE_NOT_RECORDED"
    assert last.clients[0].weight is None
    artifacts.write_run_meta(run.run_id, {"training_record": {"1": {
        "SIM_FL_SITE_00": {"examples_seen": 93, "shuffle_seed": 42,
                           "update_sha256": "digest0"}}},
        "coordinator_digests": {"1": {"SIM_FL_SITE_00": "tampered"}}})
    with pytest.raises(ValueError, match="ACCEPTED_UPDATE_TRAINING_DIGEST_MISMATCH"):
        run_contributions(run, artifacts)


def test_post_run_observer_preserves_direct_final_round_acceptance(tmp_path: Path) -> None:
    artifacts = FederationArtifactStore(tmp_path / "federation")
    client_id = "SIM_FL_SITE_00"
    run = FederationRun(
        run_id="RUN_OBSERVED_FINAL", run_type=RunType.LIVE_RUN,
        base_model_id="FL_INIT_V2", federation_protocol_id=PROTOCOL_ID,
        algorithm=Algorithm.FEDAVG, client_ids=(client_id,), planned_rounds=1,
        current_round=1, started_at_us=1, completed_at_us=2, status=RunState.COMPLETED,
        secagg_mode=AggregationMode.PLAIN, candidate_ids=("CANDIDATE_FINAL",),
    )
    training = {"examples_seen": 93, "shuffle_seed": 42, "update_sha256": "digest0"}
    artifacts.write_run_meta(run.run_id, {
        "training_record": {"1": {client_id: training}},
        "round_base_digests": {"1": "base-1"},
        "committed_digests": {"1": "global-1"},
    })
    context = RunContext(
        run_id=run.run_id, user_id="owner", run_type=RunType.LIVE_RUN,
        algorithm=Algorithm.FEDAVG, secagg_mode=AggregationMode.PLAIN, planned_rounds=1,
        journal=SimpleNamespace(), emitter=SimpleNamespace(), candidate_id="CANDIDATE_FINAL",
        round_bases={1: "base-1"}, committed={1: "global-1"},
        coordinator_digests={1: {client_id: "digest0"}},
        training_record={1: {client_id: training}},
    )
    diagnostic = {"examples_seen": 93, "batch_count": 2, "shuffle_seed": "42", "update_bytes": 10,
                  "mean_loss_diagnostic_only": 0.5, "update_norm_diagnostic_only": 1.5}
    snapshot(context, artifacts, {"1": {client_id: diagnostic}})
    observed = read_verified(artifacts, run.run_id)
    assert observed is not None
    assert observed["rounds"]["1"]["accepted_updates"] == {client_id: "digest0"}
    round_one = run_contributions(run, artifacts).rounds[0]
    assert round_one.acceptance_basis == "DIRECT_OBSERVED_COORDINATOR_MAP"
    assert round_one.clients[0].accepted_examples == 93
    assert round_one.clients[0].weight == 1.0
    recorded = round_one.clients[0].training_diagnostic
    assert recorded is not None and recorded.batch_count == 2
    assert recorded.mean_loss_diagnostic_only == 0.5
    path = capture_file(artifacts, run.run_id)
    path.write_text(path.read_text().replace("digest0", "tampered"))
    with pytest.raises(ValueError, match="OBSERVATORY_ACCEPTANCE_CAPTURE_HASH_MISMATCH"):
        run_contributions(run, artifacts)


def test_research_train_cache_access_firewall_and_actual_window(tmp_path: Path,
                                                                 monkeypatch) -> None:
    records = list_train_records()
    assert len(records) == 27
    assert all(record.partition == "TRAIN" for record in records)
    actual = inspect_train_window("101", 0)
    assert actual.record.participant_group_id == "MITDB_P101"
    assert actual.stage.actual_point_count == 2500
    assert actual.mapped_n_count == 11 and actual.label == 0
    assert actual.annotation_positions_status == "UNAVAILABLE_RAW_WFDB_NOT_PRESENT"
    with pytest.raises(ValueError, match="TRAIN_WINDOW_NOT_AVAILABLE"):
        inspect_train_window("107", 0)  # INTERNAL_TEST record cannot be opened.
    with pytest.raises(ValueError, match="TRAIN_WINDOW_NOT_AVAILABLE"):
        inspect_train_window("101", 356)
    store = CapstoneSqliteStore(tmp_path / "product.sqlite3")
    app = create_product_app_observatory_v1(
        store=store, identity_resolver=cap003_test_identity_resolver,
        auth_description=DESCRIPTION, federation_artifact_root=tmp_path / "federation",
        candidate_root=tmp_path / "candidates", auto_resume=False,
    )
    with TestClient(app) as client:
        listing = "/product/v1/observatory/research/records"
        window = f"{listing}/101/windows/0"
        assert client.get(listing).status_code == 401
        assert client.get(window).status_code == 401
        assert client.get(listing, headers=USER_A).status_code == 200
        response = client.get(window, headers=USER_A)
        assert response.status_code == 200, response.text
        assert response.json()["stage"]["actual_point_count"] == 2500
        assert client.get(f"{listing}/107/windows/0", headers=USER_A).status_code == 404
    monkeypatch.setattr(research_record, "CACHE_SHA", "0" * 64)
    with pytest.raises(ValueError, match="FROZEN_RESEARCH_MANIFEST_HASH_MISMATCH"):
        list_train_records()


def test_final_round_attestation_requires_governance_not_submitted_alone() -> None:
    cohort_ids = {item.client_id for item in frozen_cohort().clients}
    digests = {client_id: f"{index:064x}" for index, client_id in
               enumerate(sorted(cohort_ids), start=1)}
    training = {"3": {client_id: {"update_sha256": digest, "examples_seen": 90}
                      for client_id, digest in digests.items()}}
    checks = [{"check_id": check_id, "passed": True} for check_id in (
        "STATE_FINITE", "STATE_SPEC_MATCHES_BASE", "UPDATE_DIGESTS_RECONCILE",
        "ROUND_ACCEPTED_UPDATE_COUNT_COMPLETE", "BASE_STATE_LINEAGE_VERIFIED")]
    candidate = {"federation_run_id": "RUN_ATTEST", "state_digest": "global-3",
                 "governance_status": "ACCEPTED_TO_SANDBOX", "validation_status": "PASSED",
                 "sandbox_status": "IN_SANDBOX", "production_deployed": 0}
    decision = {"decision": "ACCEPTED_TO_SANDBOX", "scientific_promotion": 0,
                "production_deployed": 0, "checks_json": json.dumps(checks)}
    store = SimpleNamespace(get_candidate=lambda _: candidate,
                            list_decisions=lambda _: [decision])
    payloads = []
    for client_id, digest in digests.items():
        payloads.extend([
            ("client.update_ready", {"round_id": 3, "client_id": client_id,
                                     "update_digest": digest, "examples_seen": 90}),
            ("client.status", {"client_id": client_id, "client_state": "SUBMITTED"}),
        ])
    payloads.append(("aggregation.status", {"round_id": 3, "accepted_updates": 8,
                                                     "state_digest": "global-3",
                                                     "aggregation_mode": "PLAIN"}))

    def events(items):
        return [SimpleNamespace(sequence_index=index, run_id="RUN_ATTEST",
                                model_dump=lambda mode, kind=kind, payload=payload: {
                                    "event_type": kind, "payload": payload})
                for index, (kind, payload) in enumerate(items)]

    artifacts = SimpleNamespace(read_events=lambda _: events(payloads))
    run = FederationRun(
        run_id="RUN_ATTEST", run_type=RunType.LIVE_RUN, base_model_id="FL_INIT_V2",
        federation_protocol_id=PROTOCOL_ID, algorithm=Algorithm.FEDAVG,
        client_ids=tuple(sorted(cohort_ids)), planned_rounds=3, current_round=3,
        started_at_us=1, completed_at_us=2, status=RunState.COMPLETED,
        secagg_mode=AggregationMode.PLAIN, candidate_ids=("CANDIDATE_1",),
    )
    reports = {3: SimpleNamespace(accepted_update_count=8)}

    def attest():
        return _attested_final_updates(run, artifacts, store, training, {"3": "global-3"},
                                       cohort_ids, reports)

    assert attest() == digests
    decision["checks_json"] = json.dumps(checks[:-1])
    assert attest() is None  # SUBMITTED journal entries alone are not accepted evidence.
    decision["checks_json"] = json.dumps(checks)
    payloads[1] = ("client.status", {"client_id": sorted(cohort_ids)[0],
                                     "client_state": "UPDATE_READY"})
    assert attest() is None
    payloads[1] = ("client.status", {"client_id": sorted(cohort_ids)[0],
                                     "client_state": "SUBMITTED"})
    payloads[-1][1]["accepted_updates"] = 7
    assert attest() is None


def test_fl_client_window_uses_actual_source_and_client_local_label_rule() -> None:
    clean = fl_client_window("SIM_FL_SITE_00", 18)
    assert clean.signal.right_timestamp_us == 105_000_000
    assert clean.training_eligible and clean.engineering_label == 1
    assert clean.signal.quality_state == "VALID"
    mixed = fl_client_window("SIM_FL_SITE_07", 48)
    assert mixed.signal.quality_state == "UNUSABLE"
    assert "LONG_GAP_SPAN" in mixed.signal.quality_reasons
    assert not mixed.training_eligible and mixed.engineering_label is None
    assert mixed.signal.missing_slots > 0
    for client_index, window_index, observed in ((0, 18, clean), (7, 48, mixed)):
        profile = client_profile(client_index)
        actual = stream_windows(SyntheticObservedSource(profile))[window_index]
        assert observed.signal.quality_state == actual["ecg_quality"]
        assert observed.signal.quality_reasons == actual["diagnostics"]["quality_reasons"]
        assert observed.signal.missing_slots == actual["diagnostics"]["missing_slots"]
        assert observed.training_eligible == is_trainable(actual)
        if observed.training_eligible:
            expected = SyntheticEventLabelProvider(profile).labels_for_windows(
                [actual["timestamp_us"]])[0]
            assert observed.engineering_label == int(expected)


def test_federation_observatory_auth_and_owner_scope(tmp_path: Path) -> None:
    store = CapstoneSqliteStore(tmp_path / "product.sqlite3")
    app = create_product_app_observatory_v1(
        store=store, identity_resolver=cap003_test_identity_resolver,
        auth_description=DESCRIPTION, federation_artifact_root=tmp_path / "federation",
        candidate_root=tmp_path / "candidates", auto_resume=False,
    )
    base = "/product/v1/observatory/federation"
    with TestClient(app) as client:
        assert client.get(f"{base}/cohort").status_code == 401
        cohort = client.get(f"{base}/cohort", headers=USER_A)
        assert cohort.status_code == 200 and len(cohort.json()["clients"]) == 8
        fl_window = f"{base}/clients/SIM_FL_SITE_00/windows/0"
        assert client.get(fl_window).status_code == 401
        observed = client.get(fl_window, headers=USER_A)
        assert observed.status_code == 200 and observed.json()["training_eligible"] is True
        assert observed.json()["engineering_label"] == 0
        assert client.get(f"{base}/clients/UNKNOWN/windows/0", headers=USER_A).status_code == 404
        created = client.post("/product/v1/federation/runs", json=SINGLE_RUN, headers=USER_A)
        assert created.status_code == 200, created.text
        run_id = created.json()["run_id"]
        route = f"{base}/runs/{run_id}/contributions"
        assert client.get(route).status_code == 401
        assert client.get(route, headers=USER_B).status_code == 403
        own = client.get(route, headers=USER_A)
        assert own.status_code == 200 and own.json()["evidence_status"] == "NOT_RECORDED"
        assert client.get(f"{base}/runs/unknown/contributions", headers=USER_A).status_code == 404


def test_frozen_cohort_hash_fails_closed_on_tamper(tmp_path: Path, monkeypatch) -> None:
    tampered = tmp_path / "cohort.json"
    tampered.write_text('{"clients":[]}')
    monkeypatch.setattr(federation, "MANIFEST", tampered)
    with pytest.raises(ValueError, match="FROZEN_COHORT_MANIFEST_HASH_MISMATCH"):
        federation.frozen_cohort()


def test_api_extension_adds_only_the_documented_observatory_routes(tmp_path: Path) -> None:
    shared = dict(
        store=CapstoneSqliteStore(tmp_path / "product.sqlite3"),
        identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
        federation_artifact_root=tmp_path / "federation",
        candidate_root=tmp_path / "candidates", auto_resume=False,
    )
    predecessor = create_product_app_v1_3(**shared)
    successor = create_product_app_observatory_v1(**shared)
    def routes(app):
        return {(path.path, tuple(sorted(getattr(path, "methods", ()) or ())))
                for path in app.routes}
    added = routes(successor) - routes(predecessor)
    assert added == {
        ("/product/v1/observatory/scenarios", ("GET",)),
        ("/product/v1/observatory/scenarios/{scenario_id}/windows/{window_index}", ("GET",)),
        ("/product/v1/observatory/sessions/{session_id}/windows/{window_index}", ("GET",)),
        ("/product/v1/observatory/federation/cohort", ("GET",)),
        ("/product/v1/observatory/federation/clients/{client_id}/windows/{window_index}",
         ("GET",)),
        ("/product/v1/observatory/federation/runs/{run_id}/contributions", ("GET",)),
        ("/product/v1/observatory/research/records", ("GET",)),
        ("/product/v1/observatory/research/records/{record_id}/windows/{window_index}",
         ("GET",)),
        ("/product/v1/observatory/sessions/{session_id}/capture/{window_index}", ("POST",)),
        ("/product/v1/observatory/sessions/{session_id}/capture", ("GET",)),
        ("/product/v1/observatory/scenarios/{scenario_id}/timeline", ("GET",)),
        ("/product/v1/observatory/evidence/fl-eval", ("GET",)),
        ("/product/v1/observatory/evidence/fl-eval/curves/{dataset}/{model_id}", ("GET",)),
        ("/product/v1/observatory/evidence/boundaries", ("GET",)),
        ("/product/v1/observatory/research/preprocessing", ("GET",)),
        ("/product/v1/observatory/evidence/explainability", ("GET",)),
        ("/product/v1/observatory/evidence/explainability/{case_type}", ("GET",)),
        ("/product/v1/observatory/model/architecture", ("GET",)),
        ("/product/v1/observatory/model/activations/{scenario_id}/{window_index}", ("GET",)),
        ("/product/v1/observatory/model/calibration", ("GET",)),
        ("/product/v1/observatory/reproducibility", ("GET",)),
    }


def test_frozen_evidence_is_verified_recomputable_and_not_about_the_candidate(monkeypatch) -> None:
    from product.observatory import evidence

    index = evidence.fl_eval_index()
    assert {name: len(item["models"]) for name, item in index["datasets"].items()} == {
        "INTERNAL_TEST": 20, "INCART": 20}
    internal = index["datasets"]["INTERNAL_TEST"]
    assert internal["clusters"] == 6 and internal["bootstrap"]["p_values"] == "NOT_COMPUTED"
    assert all(not model["model_id"].startswith("CAPSTONE_FL_CANDIDATE")
               for model in internal["models"])
    curves = evidence.fl_eval_curves("INTERNAL_TEST", "V2_FEDAVG_IID")
    assert curves["recomputed_matches_frozen_point_metrics"] is True
    assert sum(curves["confusion_at_0_5"].values()) == curves["windows"]
    with pytest.raises(evidence.EvidenceError, match="UNKNOWN_EVIDENCE_MODEL"):
        evidence.fl_eval_curves("INTERNAL_TEST", "CAPSTONE_FL_CANDIDATE_0001")
    from api.observatory_model_inspect import architecture as inspect_architecture

    architecture = inspect_architecture()
    assert architecture["parameter_count"] == 57_553 and architecture["output_shape"] == [1, 1]
    calibration = evidence.calibration()
    assert calibration["constants"]["temperature"] == 52.88261929727761
    assert calibration["constants"]["threshold"] == 0.5101937262006424
    gallery = evidence.boundaries()
    assert all(item["exists"] and item["sha256"]
               for item in (*gallery["boundaries"], *gallery["chronology"]))
    zeroed = {key: "0" * 64 for key in evidence._hash_manifest()}
    monkeypatch.setattr(evidence, "_hash_manifest", lambda: zeroed)
    evidence._statistics.cache_clear()
    with pytest.raises(evidence.EvidenceError, match="EVIDENCE_HASH_MISMATCH"):
        evidence.fl_eval_index()
    evidence._statistics.cache_clear()


def test_scenario_timeline_is_the_frozen_definition_in_source_time(tmp_path: Path) -> None:
    app = create_product_app_observatory_v1(
        store=CapstoneSqliteStore(tmp_path / "product.sqlite3"),
        identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
        federation_artifact_root=tmp_path / "federation", candidate_root=tmp_path / "candidates",
        auto_resume=False)
    with TestClient(app) as client:
        url = "/product/v1/observatory/scenarios/MIXED_MONITORING_SESSION/timeline"
        assert client.get(url).status_code == 401
        body = client.get(url, headers=USER_A).json()
        assert body["time_basis"] == "SIMULATED_SOURCE_TIME_NOT_WALL_CLOCK"
        names = [seg["name"] for seg in body["segments"]]
        assert names[:3] == ["clean", "ppg_missing", "invalid_spo2"]
        assert body["window_right_edges_s"][0] == 15.0 and body["window_cadence_s"] == 5.0
        assert body["window_right_edges_s"][-1] <= body["duration_s"]
        missing = "/product/v1/observatory/scenarios/NOT_A_SCENARIO/timeline"
        assert client.get(missing, headers=USER_A).status_code == 404


def test_explainability_cases_are_hash_verified_and_labeled_non_causal() -> None:
    from product.observatory import evidence

    index = evidence.explainability_index()
    assert {case["case_type"] for case in index["cases"]} == {"TP", "TN", "FP", "FN"}
    assert "not a causal" in " ".join(index["limitations"])
    case = evidence.explainability_case("TP")
    assert len(case["model_input"]) == 2500 and case["classification"] == "FROZEN_RESEARCH_EVIDENCE"
    with pytest.raises(evidence.EvidenceError, match="UNKNOWN_EVIDENCE_CASE"):
        evidence.explainability_case("../../etc/passwd")


def test_each_dataset_has_its_own_locked_resampler_and_causality_holds() -> None:
    from product.observatory import evidence

    body = evidence.dataset_preprocessing()
    by_name = {item["dataset"]: item for item in body["datasets"]}
    assert (by_name["MITDB"]["native_rate_hz"], by_name["INCART"]["native_rate_hz"]) == (360, 257)
    assert by_name["MITDB"]["resampler_id"] != by_name["INCART"]["resampler_id"]
    assert by_name["INCART"]["allowed_for_training"] == "false"
    for item in body["datasets"]:
        assert item["causality"]["outputs_before_alteration_identical"] is True
        assert item["causality"]["first_output_index_that_changed"] is not None
    contract = body["contract"]
    assert contract["signal_interval"] == "[t-10s,t)"
    assert contract["annotation_interval"] == "[t-10s,t]"
    assert body["raw_recordings"].startswith("NOT_PRESENT")


def test_observatory_lock_verifies_and_detects_tamper(tmp_path: Path, monkeypatch) -> None:
    import json as _json

    from scripts import verify_observatory_v1 as verifier

    assert verifier.verify()["status"] == "PASS"
    lock = _json.loads(verifier.LOCK_PATH.read_text())
    first = sorted(lock["bound_files"])[0]
    lock["bound_files"][first] = "0" * 64
    tampered = tmp_path / "lock.json"
    tampered.write_text(_json.dumps(lock))
    monkeypatch.setattr(verifier, "LOCK_PATH", tampered)
    # Judge the tampered V1 copy on its own, without the chained successor.
    monkeypatch.setattr(verifier, "SUCCESSOR_PATH", tmp_path / "none.json")
    with pytest.raises(RuntimeError, match="OBSERVATORY_TAMPER"):
        verifier.verify()
