# ruff: noqa: E501
"""Unified Studio routes: authentication, two-user isolation (HTTP + WebSocket), unchanged 3-round contract, REAL 3-round and 10-round runs evaluated checkpoint by
checkpoint (reproducing the recorded digests/metrics without being preloaded with them), live event integrity and run-specific exports."""

from __future__ import annotations

import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.capstone_federation_support import DESCRIPTION, SINGLE_RUN
from tests.capstone_product_support import BASE, USER_A, USER_B

S = f"{BASE}/studio"
RECORDED_EVAL = "reports/fl10/eval/modeA/evaluation_results.json"


def _app(tmp_path):
    from api.product_app_observatory_v1 import create_product_app_observatory_v1
    from capstone_persistence.store import CapstoneSqliteStore
    from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver

    return create_product_app_observatory_v1(store=CapstoneSqliteStore(tmp_path / "p.sqlite3"), identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
                                             federation_artifact_root=tmp_path / "f", candidate_root=tmp_path / "c", inference_base_url="http://127.0.0.1:8001", auto_resume=False)


def _recorded():
    return json.load(open(RECORDED_EVAL))


def _poll(c, run_id, headers, until, timeout=900):
    end = time.time() + timeout
    while time.time() < end:
        d = c.get(f"{S}/runs/{run_id}", headers=headers).json()
        if until(d):
            return d
        time.sleep(1.0)
    raise AssertionError(f"timeout waiting for {run_id}: {d}")


def _check_against_recorded(records, rounds):
    rec = _recorded()
    assert [r["round_id"] for r in records] == list(range(rounds + 1))
    for r in records:
        key = f"R{r['round_id']:02d}"
        ref = rec["states"][key]["pooled"]
        assert r["evaluation_status"] == "COMPLETED" and r["global_state_digest"] == rec["state_digests"][key]
        assert all(r["metric_result"][m] == ref[m] for m in ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "BCE", "Brier", "TP", "FP", "TN", "FN", "windows"))
        assert r["threshold"] == 0.5 and r["calibration"] == "NONE" and r["cohort_use"].startswith("REUSED SYNTHETIC DIAGNOSTIC EVALUATION")


def test_studio_requires_identity_and_serves_recorded_runs_through_the_same_routes(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        for path in ("/capabilities", "/runs", "/runs/recorded-A", "/runs/recorded-A/evaluation", "/runs/recorded-A/figures", "/runs/recorded-A/tables", "/runs/recorded-A/exports"):
            assert c.get(f"{S}{path}").status_code == 401, path
        caps = c.get(f"{S}/capabilities", headers=USER_A).json()
        assert caps["run_lengths"] == [3, 10] and caps["default_run_length"] == 3 and "FEDPROX" in caps["ten_round"]["unsupported"] and caps["ten_round"]["expected_updates"] == 80
        runs = c.get(f"{S}/runs", headers=USER_A).json()
        assert {r["run_id"] for r in runs} == {"recorded-A", "recorded-B"} and all(r["origin"] == "RECORDED" and r["source_label"].startswith("RECORDED") for r in runs)
        summary = c.get(f"{S}/runs/recorded-A/evaluation", headers=USER_B).json()          # recorded evidence is global read-only reference
        assert len(summary["records"]) == 11 and all(r["evaluation_status"] == "COMPLETED" for r in summary["records"]) and summary["comparison"]["paired_available"]
        r6 = c.get(f"{S}/runs/recorded-A/evaluation/6", headers=USER_A).json()
        assert r6["round_id"] == 6 and r6["curves"]["roc"] and r6["metric_result"]["AUPRC"] == _recorded()["states"]["R06"]["pooled"]["AUPRC"]
        assert c.get(f"{S}/runs/recorded-A/evaluation/11", headers=USER_A).status_code == 404
        figs = c.get(f"{S}/runs/recorded-A/figures?round=6", headers=USER_A).json()
        assert len(figs["specs"]) == 20 and figs["selected_round"] == 6 and {s["availability"] for s in figs["specs"].values()} == {"AVAILABLE"}
        assert len(c.get(f"{S}/runs/recorded-A/tables", headers=USER_A).json()["tables"]) == 12
        png = c.get(f"{S}/runs/recorded-A/exports/FL10_FIG09/png", headers=USER_A)
        assert png.status_code == 200 and hashlib.sha256(png.content).hexdigest() == png.headers["x-content-sha256"]
        prov = c.get(f"{S}/runs/recorded-A/exports/FL10_FIG09/provenance", headers=USER_A)
        assert prov.status_code == 200 and json.loads(prov.content)["figure_id"] == "FL10_FIG09"
        assert c.get(f"{S}/runs/recorded-A/exports/FL10_FIG09/exe", headers=USER_A).status_code == 404
        assert c.get(f"{S}/runs/FEDRUN-NOPE", headers=USER_A).status_code == 404


def test_three_round_contract_is_unchanged_and_the_studio_does_not_widen_it(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        assert c.post(f"{BASE}/federation/runs", json={**SINGLE_RUN, "planned_rounds": 10}, headers=USER_A).status_code in (400, 422)
        assert c.post(f"{S}/runs", json={"run_length": 3}, headers=USER_A).status_code == 400                      # 3 rounds use the frozen product route
        for body in ({"run_length": 5}, {"run_length": 10, "source_mode": "NOPE"}, {"run_length": 10, "algorithm": "FEDPROX"}, {"run_length": 10, "secagg_mode": "SECAGG_SHADOW"},
                     {"run_length": 10, "run_type": "REPLAY"}, {"run_length": 10, "rounds": 3}):
            assert c.post(f"{S}/runs", json=body, headers=USER_A).status_code == 400, body            # unsupported combinations are refused, never reinterpreted as FedAvg/plain
        assert c.post(f"{S}/runs", json={"run_length": 10}).status_code == 401
        assert c.get(f"{BASE}/federation/runs", headers=USER_A).json() == []                          # nothing was created by the refused requests


def test_real_three_round_run_is_evaluated_per_checkpoint_and_isolated_between_users(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        created = c.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A)
        assert created.status_code == 200
        run_id = created.json()["run_id"]
        assert c.post(f"{BASE}/federation/runs/{run_id}/start", headers=USER_A).status_code == 200
        done = _poll(c, run_id, USER_A, lambda d: d["status"] == "COMPLETED" and d["export_status"] in ("READY", "FAILED"))
        assert done["run_length"] == 3 and done["engine"] == "PRODUCT_3R" and done["export_status"] == "READY" and done["candidate"]["promoted"] is False
        # isolation: another user cannot see or touch ANY run-scoped surface
        for path in ("", "/evaluation", "/evaluation/1", "/rounds/1", "/figures", "/tables", "/exports", "/exports/FL10_FIG04/svg"):
            assert c.get(f"{S}/runs/{run_id}{path}", headers=USER_B).status_code == 403, path
        assert run_id not in {r["run_id"] for r in c.get(f"{S}/runs", headers=USER_B).json()}
        with pytest.raises(WebSocketDisconnect) as closed, c.websocket_connect(f"{S}/runs/{run_id}/live", headers=USER_B) as ws:
            ws.receive_json()
        assert closed.value.code == 4403
        # genuine per-checkpoint evaluation of THIS run
        summary = c.get(f"{S}/runs/{run_id}/evaluation", headers=USER_A).json()
        assert summary["run_id"] == run_id and summary["evaluation"]["source"] == "LIVE"
        _check_against_recorded(summary["records"], 3)
        assert all(r["run_id"] == run_id for r in summary["records"]) and summary["comparison"] == {"comparator_round": 0, "endpoint_round": 3, "paired_available": True}
        figs = c.get(f"{S}/runs/{run_id}/figures", headers=USER_A).json()["specs"]
        auprc = next(s for s in figs["FL10_FIG04"]["views"][0]["series"] if s["name"] == "AUPRC")
        assert auprc["x"] == [0, 1, 2, 3] and all(isinstance(v, float) for v in auprc["y"])
        assert figs["FL10_FIG16"]["title"] == "Paired R3 minus R0 effects" and figs["FL10_FIG16"]["availability"] == "AVAILABLE"
        assert figs["FL10_FIG01"]["title"].startswith("Three-round")
        rows = c.get(f"{S}/runs/{run_id}/tables", headers=USER_A).json()["tables"]
        assert len(rows["FL10_TAB03"]["rows"]) == 24 and len(rows["FL10_TAB01"]["rows"]) == 4 and all(r[1] == "PASS" for r in rows["FL10_TAB12"]["rows"])
        detail = c.get(f"{S}/runs/{run_id}/rounds/2", headers=USER_A).json()
        assert detail["committed"] and len(detail["client_rounds"]) == 8 and sum(r["aggregation_weight"] for r in detail["client_rounds"]) == pytest.approx(1.0, abs=1e-12)
        assert detail["round"]["accepted_updates"] == 8 and detail["round"]["parity"]["equals_frozen_reference"] is True
        # run-specific exports carry THIS run's id and verify by hash
        manifest = c.get(f"{S}/runs/{run_id}/exports", headers=USER_A).json()
        assert manifest["status"] == "READY" and manifest["run_id"] == run_id and len(manifest["figures"]) == 20 and len(manifest["tables"]) == 12
        for item, fmt in (("FL10_FIG04", "svg"), ("FL10_FIG07", "png"), ("FL10_FIG04", "csv"), ("FL10_FIG04", "provenance"), ("FL10_TAB01", "csv"), ("FL10_TAB01", "json"), ("evaluation_records", "json"), ("predictions_R03", "csv")):
            r = c.get(f"{S}/runs/{run_id}/exports/{item}/{fmt}", headers=USER_A)
            assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == r.headers["x-content-sha256"] and r.headers["x-export-run-id"] == run_id, (item, fmt)
        prov = json.loads(c.get(f"{S}/runs/{run_id}/exports/FL10_FIG04/provenance", headers=USER_A).content)
        assert prov["run_id"] == run_id and prov["source_label"] == "LIVE RUN (this session)" and "recorded" not in prov["source_label"].lower()
        # historical replay: no training, evaluation is the SOURCE run's recorded evaluation, clearly labelled, and still owner-scoped
        replay = c.post(f"{BASE}/federation/runs", json={**SINGLE_RUN, "run_type": "REPLAY"}, headers=USER_A)
        assert replay.status_code == 200, replay.text
        replay_id = replay.json()["run_id"]
        assert c.post(f"{BASE}/federation/runs/{replay_id}/start", headers=USER_A).status_code == 200
        replayed = _poll(c, replay_id, USER_A, lambda d: d["status"] == "COMPLETED")
        assert replayed["origin"] == "REPLAY" and replayed["replay_of"] == run_id and replayed["evaluation"]["source"] == "RECORDED_FROM_SOURCE_RUN" and replayed["evaluation"]["evaluation_run_id"] == run_id
        replay_summary = c.get(f"{S}/runs/{replay_id}/evaluation", headers=USER_A).json()
        assert [r["global_state_digest"] for r in replay_summary["records"]] == [r["global_state_digest"] for r in summary["records"]] and "REPLAY" in replay_summary["source_label"]
        assert "REPLAY" in c.get(f"{S}/runs/{replay_id}/figures", headers=USER_A).json()["source_label"]
        assert c.get(f"{S}/runs/{replay_id}/evaluation", headers=USER_B).status_code == 403
        assert len(c.get(f"{S}/runs/{run_id}/evaluation", headers=USER_A).json()["records"]) == 4        # replaying created no new evaluation of the source
        # the live journal is the unchanged product journal, replayed from sequence 0
        with c.websocket_connect(f"{S}/runs/{run_id}/live", headers=USER_A) as ws:
            events = []
            while True:
                try:
                    events.append(ws.receive_json())
                except WebSocketDisconnect:
                    break
        assert [e["sequence_index"] for e in events] == list(range(len(events))) and sum(e["event_type"] == "client.update_ready" for e in events) == 24


def test_real_ten_round_run_streams_genuine_events_and_reproduces_the_recorded_evidence(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        assert c.post(f"{S}/runs", json={"run_length": 10, "source_mode": "CANONICAL_SYNTHETIC"}, headers=USER_B).status_code == 200
        first = c.get(f"{S}/runs", headers=USER_B).json()
        run_id = next(r["run_id"] for r in first if r["origin"] == "LIVE")
        # one federation run at a time, across engines and routes
        assert c.post(f"{S}/runs", json={"run_length": 10}, headers=USER_A).status_code == 409
        assert c.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).status_code == 409
        assert c.post(f"{BASE}/observatory/fl10/runs", json={"mode": "A"}, headers=USER_A).status_code == 409
        # another user cannot reach it
        assert c.get(f"{S}/runs/{run_id}", headers=USER_A).status_code == 403 and c.get(f"{S}/runs/{run_id}/evaluation", headers=USER_A).status_code == 403
        with pytest.raises(WebSocketDisconnect) as closed, c.websocket_connect(f"{S}/runs/{run_id}/live", headers=USER_A) as ws:
            ws.receive_json()
        assert closed.value.code == 4403
        # while it runs: committed rounds are only ever shown with their own state; queued rounds carry NO numbers
        seen_pending = False
        done = None
        end = time.time() + 900
        while time.time() < end:
            d = c.get(f"{S}/runs/{run_id}", headers=USER_B).json()
            for rec in c.get(f"{S}/runs/{run_id}/evaluation", headers=USER_B).json()["records"]:
                if rec["evaluation_status"] != "COMPLETED":
                    seen_pending = seen_pending or rec["evaluation_status"] in ("QUEUED", "EVALUATING")
                    assert rec["metric_result"] is None and rec["confusion_counts"] is None
            if d["phase"] == "DONE":
                done = d
                break
            assert d["phase"] != "FAILED", d
            time.sleep(1.0)
        assert done and done["status"] == "COMPLETED" and done["export_status"] == "READY" and done["candidate"]["promoted"] is False and done["candidate"]["deployed"] is False
        assert seen_pending, "evaluation never lagged training in this run (expected QUEUED/EVALUATING rounds while training advanced)"
        records = c.get(f"{S}/runs/{run_id}/evaluation", headers=USER_B).json()["records"]
        _check_against_recorded(records, 10)
        # genuine event stream: 80 actual updates, 80 coordinator acceptances, 10 aggregations, strict sequence
        with c.websocket_connect(f"{S}/runs/{run_id}/live", headers=USER_B) as ws:
            events = []
            while True:
                try:
                    events.append(ws.receive_json())
                except WebSocketDisconnect:
                    break
        kinds: dict[str, int] = {}
        for e in events:
            kinds[e["event_type"]] = kinds.get(e["event_type"], 0) + 1
        submitted = [e for e in events if e["event_type"] == "client.status" and e["payload"]["client_state"] == "SUBMITTED"]
        assert [e["sequence_index"] for e in events] == list(range(len(events))) and all(e["run_id"] == run_id for e in events)
        assert kinds["client.update_ready"] == 80 and len(submitted) == 80 and kinds["aggregation.status"] == 10 and kinds.get("federation.error", 0) == 0
        assert events[-1]["event_type"] == "federation.completed" and events[-1]["payload"]["rounds_completed"] == 10 and events[-1]["payload"]["production_deployed"] is False
        last_update = max(i for i, e in enumerate(events) if e["event_type"] == "client.update_ready")
        assert all(i > min(j for j, x in enumerate(events) if x["event_type"] == "client.update_ready") for i, e in enumerate(events) if e["event_type"] == "aggregation.status")
        assert last_update < len(events) - 1
        # the paired comparison, figures, tables and exports are run-specific
        summary = c.get(f"{S}/runs/{run_id}/evaluation", headers=USER_B).json()
        assert summary["comparison"] == {"comparator_round": 3, "endpoint_round": 10, "paired_available": True}
        paired = _recorded()["paired"]["metrics"]
        figs = c.get(f"{S}/runs/{run_id}/figures?round=6", headers=USER_B).json()["specs"]
        assert {s["availability"] for s in figs.values()} == {"AVAILABLE"}
        rows16 = {r["label"]: r for r in figs["FL10_FIG16"]["views"][0]["rows"]}
        assert rows16["AUPRC"]["point"] == paired["AUPRC"]["difference_point"]
        tables = c.get(f"{S}/runs/{run_id}/tables", headers=USER_B).json()["tables"]
        assert len(tables["FL10_TAB03"]["rows"]) == 80 and len(tables["FL10_TAB01"]["rows"]) == 11 and all(r[1] == "PASS" for r in tables["FL10_TAB12"]["rows"])
        for item, fmt in (("FL10_FIG16", "svg"), ("FL10_FIG09", "png"), ("FL10_TAB02", "csv"), ("evaluation_records", "json"), ("predictions_R10", "csv"), ("run_report", "json")):
            r = c.get(f"{S}/runs/{run_id}/exports/{item}/{fmt}", headers=USER_B)
            assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == r.headers["x-content-sha256"], (item, fmt)
        assert c.get(f"{S}/runs/{run_id}/exports/FL10_FIG09/png", headers=USER_A).status_code == 403


def test_stopping_the_application_stops_a_running_ten_round_job_and_it_is_never_a_candidate(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as c:
        assert c.post(f"{S}/runs", json={"run_length": 10}, headers=USER_A).status_code == 200
        run_id = next(r["run_id"] for r in c.get(f"{S}/runs", headers=USER_A).json() if r["origin"] == "LIVE")
        _poll(c, run_id, USER_A, lambda d: d["phase"] == "TRAINING" and d["current_round"] >= 1, timeout=300)
    job = app.state.studio_service.runner10.jobs[run_id]          # the lifespan shutdown stopped the job at its next progress event
    assert job.status == "FAILED" and job.failure["code"] == "CANCELLED" and job.candidate is None
    report = json.loads((tmp_path / "f" / "studio_runs" / run_id / "run" / "run_report.json").read_text())
    assert report["status"] == "INCOMPLETE_NOT_A_CANDIDATE" and report["rounds_committed"] < 10 and "candidate" not in report
