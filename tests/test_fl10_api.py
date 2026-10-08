# ruff: noqa: E501
"""NHM-FL10-001 routes: authentication, ownership, concurrency, a real opt-in run reproducing the recorded digests, and the unchanged 3-round contract."""

from __future__ import annotations

import hashlib
import time

from fastapi.testclient import TestClient

from fl10 import service
from tests.capstone_federation_support import DESCRIPTION, SINGLE_RUN
from tests.capstone_product_support import BASE, USER_A, USER_B


def _app(tmp_path, inference_base_url=None):
    from api.product_app_observatory_v1 import create_product_app_observatory_v1
    from capstone_persistence.store import CapstoneSqliteStore
    from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver

    return create_product_app_observatory_v1(store=CapstoneSqliteStore(tmp_path / "p.sqlite3"), identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
                                             federation_artifact_root=tmp_path / "f", candidate_root=tmp_path / "c",
                                             inference_base_url=inference_base_url or "http://127.0.0.1:8001",
                                             auto_resume=False)


def test_recorded_routes_require_identity_and_serve_the_recorded_runs(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        assert c.get(f"{BASE}/observatory/fl10/recorded").status_code == 401
        listing = c.get(f"{BASE}/observatory/fl10/recorded", headers=USER_A).json()
        assert [r["mode"] for r in listing] == ["A", "B"] and all(r["status"] == "COMPLETED" for r in listing)
        body = c.get(f"{BASE}/observatory/fl10/recorded/recorded-A", headers=USER_A).json()
        assert body["overview"]["source_label"] == "RECORDED VERIFIED RUN" and body["overview"]["run"]["accepted_updates_total"] == 80 and len(body["specs"]) == 20 and len(body["tables"]) == 12
        assert c.get(f"{BASE}/observatory/fl10/recorded/nope", headers=USER_A).status_code == 404
        png = c.get(f"{BASE}/observatory/fl10/recorded/recorded-A/exports/FL10_FIG09/png", headers=USER_A)
        assert png.status_code == 200 and hashlib.sha256(png.content).hexdigest() == png.headers["x-content-sha256"]
        csv = c.get(f"{BASE}/observatory/fl10/recorded/recorded-A/exports/FL10_TAB01/csv", headers=USER_A)
        assert csv.status_code == 200 and hashlib.sha256(csv.content).hexdigest() == csv.headers["x-content-sha256"]
        assert c.get(f"{BASE}/observatory/fl10/recorded/recorded-A/exports/FL10_FIG09/exe", headers=USER_A).status_code == 404
        assert c.get(f"{BASE}/observatory/fl10/recorded/recorded-A/exports/../x/csv", headers=USER_A).status_code == 404


def test_three_round_default_is_not_replaced_by_the_ten_round_experiment(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        bad = c.post(f"{BASE}/federation/runs", json={**SINGLE_RUN, "planned_rounds": 10}, headers=USER_A)
        assert bad.status_code in (400, 422)
        ok = c.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A)
        assert ok.status_code == 200 and ok.json()["planned_rounds"] == 3
        assert c.post(f"{BASE}/observatory/fl10/runs", json={"mode": "C"}, headers=USER_A).status_code in (400, 422)
        assert c.post(f"{BASE}/observatory/fl10/runs", json={"mode": "A", "rounds": 3}, headers=USER_A).status_code in (400, 422)
        assert c.post(f"{BASE}/observatory/fl10/runs", json={"mode": "A"}).status_code == 401


def test_opt_in_run_is_owner_scoped_exclusive_and_reproduces_the_recorded_states(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        started = c.post(f"{BASE}/observatory/fl10/runs", json={"mode": "A"}, headers=USER_A)
        assert started.status_code == 200, started.text
        job = started.json()["job_id"]
        assert started.json()["candidate_promoted"] is False
        assert c.post(f"{BASE}/observatory/fl10/runs", json={"mode": "A"}, headers=USER_A).status_code == 409          # concurrent conflicting run
        assert c.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).status_code in (200, 409)
        assert c.get(f"{BASE}/observatory/fl10/runs/{job}", headers=USER_B).status_code == 404                           # cross-user access
        assert c.get(f"{BASE}/observatory/fl10/runs/{job}/bundle", headers=USER_B).status_code == 404
        early = c.get(f"{BASE}/observatory/fl10/runs/{job}/bundle", headers=USER_A)
        assert early.status_code in (409, 400, 422)                                                                       # never served before completion
        deadline = time.time() + 900
        while time.time() < deadline:
            st = c.get(f"{BASE}/observatory/fl10/runs/{job}", headers=USER_A).json()
            if st["phase"] in ("COMPLETED", "FAILED_NOT_A_CANDIDATE"):
                break
            time.sleep(1.0)
        assert st["phase"] == "COMPLETED", st
        live = c.get(f"{BASE}/observatory/fl10/runs/{job}/bundle", headers=USER_A).json()
        export_url = f"{BASE}/observatory/fl10/runs/{job}/exports/FL10_FIG09/png"
        assert c.get(export_url, headers=USER_B).status_code == 404
        live_export = c.get(export_url, headers=USER_A)
        assert live_export.status_code == 200
        assert hashlib.sha256(live_export.content).hexdigest() == live_export.headers["x-content-sha256"]
        rec = service.recorded("recorded-A")
        assert live["overview"]["source_label"] == "LIVE RUN (this session)"
        assert live["overview"]["evaluation"]["state_digests"] == rec["overview"]["evaluation"]["state_digests"]                 # deterministic: same digests as the recorded run
        assert live["overview"]["run"]["candidate"]["state_sha256"] == rec["overview"]["run"]["candidate"]["state_sha256"]
        assert live["tables"]["FL10_TAB01"]["rows"] == rec["tables"]["FL10_TAB01"]["rows"]


def test_live_monitored_mode_b_uses_one_verified_session_and_owner_scoped_result(tmp_path):
    from scripts.run_capstone_monitoring_e2e import launch_released_inference

    with launch_released_inference() as (inference_url, _), TestClient(
        _app(tmp_path, inference_base_url=inference_url)
    ) as client:
        start = client.post(f"{BASE}/observatory/fl10/runs", json={"mode": "B"}, headers=USER_A)
        assert start.status_code == 200, start.text
        job_id = start.json()["job_id"]
        deadline = time.time() + 900
        while time.time() < deadline:
            status = client.get(f"{BASE}/observatory/fl10/runs/{job_id}", headers=USER_A).json()
            if status["phase"] in ("COMPLETED", "FAILED_NOT_A_CANDIDATE"):
                break
            time.sleep(1)
        assert status["phase"] == "COMPLETED", status
        assert client.get(f"{BASE}/observatory/fl10/runs/{job_id}/bundle", headers=USER_B).status_code == 404
        bundle = client.get(f"{BASE}/observatory/fl10/runs/{job_id}/bundle", headers=USER_A).json()
        overview = bundle["overview"]
        assert overview["mode"] == "B"
        assert overview["run"]["rounds_committed"] == 10
        assert overview["run"]["accepted_updates_total"] == 80
        assert overview["monitoring_link"]["monitoring_sessions_executed"] == 1
        assert overview["monitoring_link"]["buffer_reused_for_rounds"] == 10
        assert overview["monitoring_link"]["site00_source"] == "LIVE_MONITORED_WINDOWS"
        assert overview["monitoring_link"]["trace"]["verified"] is True
