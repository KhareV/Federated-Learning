# ruff: noqa: E501
"""CAP-007: exactly ten new routes, ownership, system info, models, concurrency, no promote/deploy."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from product.contracts import ROOT, load_contract
from tests.capstone_federation_support import (
    BASE,
    SINGLE_RUN,
    USER_A,
    USER_B,
    completed_run,
    make_fed_app,
    poll_run,
)


def _routes(app) -> set[tuple[str, str]]:
    found = set()
    for route in app.routes:
        if route.path.startswith("/product"):
            for method in sorted(getattr(route, "methods", None) or ["WS"]):
                if method != "HEAD":
                    found.add((method, route.path))
    return found


def _contract(phase: str) -> set[tuple[str, str]]:
    return {(r["method"], r["path"]) for r in load_contract("product_api")["routes"] if r["owner_phase"] == phase}


def test_the_successor_exposes_exactly_the_ten_cap_007_routes_and_no_later_phase_route(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    routes = _routes(app)
    cap007 = _contract("CAP-007")
    assert len(cap007) == 10
    assert routes == _contract("CAP-003") | _contract("CAP-004") | cap007
    for phase in ("CAP-008", "CAP-009", "CAP-010", "CAP-011"):
        assert not routes & _contract(phase)
    joined = " ".join(path for _, path in routes).lower()
    for forbidden in ("promote", "deploy", "select_model", "set_default", "switch_model", "/research",
                      "/infer", "sandbox"):
        assert forbidden not in joined
    assert app.docs_url is None and app.openapi_url is None


def test_system_reports_engineering_federation_and_the_unchanged_released_model(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        body = client.get(f"{BASE}/system").json()
    assert body["product_api_implementation"] == "CAPSTONE_PRODUCT_API_V1_2"
    assert body["federation_runtime"] == "ENABLED_ENGINEERING"
    assert body["hardware_mode"] == "SIMULATED_ONLY" and body["physical_hardware_available"] is False
    assert body["model_id"] == "MODEL_V2_FINAL" and body["software_system"] == "SOFTWARE_SYSTEM_V2"
    assert "candidate" not in json.dumps(body).lower()


def test_all_federation_routes_require_authentication(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        for method, path in (("GET", "/federation"), ("GET", "/federation/clients"),
                             ("POST", "/federation/runs"), ("GET", "/federation/runs"),
                             ("GET", "/federation/runs/X"), ("POST", "/federation/runs/X/start"),
                             ("GET", "/federation/runs/X/rounds"), ("GET", "/models"),
                             ("GET", "/models/MODEL_V2_FINAL")):
            response = client.request(method, BASE + path, json=SINGLE_RUN if method == "POST" else None)
            assert response.status_code == 401, (method, path)


def test_run_ownership_for_get_list_rounds_and_start(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        created = client.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).json()
        rid = created["run_id"]
        assert created["status"] == "CREATED" and created["candidate_ids"] == []
        assert client.get(f"{BASE}/federation/runs/{rid}", headers=USER_B).status_code == 403
        assert client.get(f"{BASE}/federation/runs/{rid}/rounds", headers=USER_B).status_code == 403
        assert client.post(f"{BASE}/federation/runs/{rid}/start", headers=USER_B).status_code == 403
        assert client.get(f"{BASE}/federation/runs/NOPE", headers=USER_A).status_code == 404
        assert [r["run_id"] for r in client.get(f"{BASE}/federation/runs", headers=USER_A).json()] == [rid]
        assert client.get(f"{BASE}/federation/runs", headers=USER_B).json() == []


def test_global_read_routes_and_the_models_namespaces(tmp_path) -> None:
    done = completed_run()
    app, _ = make_fed_app(done.root)  # same DB and artifacts: a second process reading the registry
    with TestClient(app) as client:
        overview = client.get(f"{BASE}/federation", headers=USER_B).json()
        assert overview["client_count"] == 8 and overview["candidate_count"] == 1
        assert overview["production_deployed"] is False and overview["scientific_evidence"] is False
        clients = client.get(f"{BASE}/federation/clients", headers=USER_B).json()
        assert [c["client_id"] for c in clients] == [f"SIM_FL_SITE_{i:02d}" for i in range(8)]
        assert all(c["eligible"] and c["local_example_count"] > 0 and c["client_state"] == "IDLE" for c in clients)
        assert "label" not in json.dumps(clients).lower()
        models = client.get(f"{BASE}/models", headers=USER_B).json()
        assert models["released_default_model_id"] == "MODEL_V2_FINAL"
        assert {m["model_id"] for m in models["released_scientific"]} == {"MODEL_V1", "MODEL_V2_FINAL"}
        [candidate] = models["capstone_fl_candidates"]
        assert candidate["candidate_id"] == "CAPSTONE_FL_CANDIDATE_0001"
        assert candidate["governance_status"] == "ACCEPTED_TO_SANDBOX" and candidate["sandbox_status"] == "IN_SANDBOX"
        assert candidate["production_deployed"] is False and candidate["parent_model_id"] == "FL_INIT_V2"
        assert client.get(f"{BASE}/models/MODEL_V2_FINAL", headers=USER_B).json()["role"] == "RELEASED_DEFAULT"
        assert client.get(f"{BASE}/models/CAPSTONE_FL_CANDIDATE_0001", headers=USER_B).status_code == 200
        assert client.get(f"{BASE}/models/CAPSTONE_FL_CANDIDATE_0099", headers=USER_B).status_code == 404
        for verb in ("post", "put", "delete"):
            assert getattr(client, verb)(f"{BASE}/models/CAPSTONE_FL_CANDIDATE_0001", headers=USER_A).status_code in (404, 405)


def test_start_returns_promptly_and_a_second_live_run_is_refused_while_one_is_active(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        first = client.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).json()["run_id"]
        second = client.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_B).json()["run_id"]
        t0 = time.time()
        started = client.post(f"{BASE}/federation/runs/{first}/start", headers=USER_A)
        assert time.time() - t0 < 10 and started.json()["status"] == "RUNNING"
        refused = client.post(f"{BASE}/federation/runs/{second}/start", headers=USER_B)
        assert refused.status_code == 409 and "FEDERATION_RUN_ALREADY_ACTIVE" in refused.json()["error"]["message"]
        assert client.get(f"{BASE}/federation", headers=USER_B).json()["active_live_run"] is True
        assert poll_run(client, first, USER_A)["status"] == "COMPLETED"
        assert client.get(f"{BASE}/federation", headers=USER_B).json()["active_live_run"] is False
        assert client.post(f"{BASE}/federation/runs/{first}/start", headers=USER_A).status_code == 409


def test_the_api_module_adds_no_cap_009_or_promotion_surface() -> None:
    text = (ROOT / "api/product_app_v1_2.py").read_text().lower()
    for forbidden in ("def promote", "def deploy", "set_default", "select_model", "/research"):
        assert forbidden not in text
