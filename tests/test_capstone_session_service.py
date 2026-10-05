# ruff: noqa: E501
"""CAP-004: public session create/list/get, ownership, successor route parity, CORS, launcher."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.product_app_v1_1 import create_product_app_v1_1
from product.contracts import ROOT, load_contract
from product.devices.base import DeviceState
from product.inference.client import CapstoneInferenceClient
from product.monitoring.coordinator import MonitoringService
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver
from tests.capstone_persistent_support import (
    BASE,
    TEST_DESCRIPTION,
    USER_A,
    USER_B,
    SeqIds,
    StrictInferenceDouble,
    collect_ws,
    make_persistent_app,
    provisioned_session,
)

API_V2 = json.loads((ROOT / "contracts/capstone/product_api_v2.json").read_text())


def _routes(app) -> set[tuple[str, str]]:
    found = set()
    for route in app.routes:
        if route.path.startswith("/product"):
            for method in sorted(getattr(route, "methods", None) or ["WS"]):
                found.add((method, route.path))
    return found


def _contract(phase: str) -> set[tuple[str, str]]:
    return {(r["method"], r["path"]) for r in load_contract("product_api")["routes"]
            if r["owner_phase"] == phase}


# ---- route surface -----------------------------------------------------------------------------
def test_the_successor_exposes_the_nine_cap_003_routes_plus_exactly_the_four_cap_004_routes(
        tmp_path) -> None:
    app, _ = make_persistent_app(tmp_path / "r.sqlite3")
    routes = _routes(app)
    assert routes == _contract("CAP-003") | _contract("CAP-004")
    assert len(_contract("CAP-003")) == 9 and _contract("CAP-004") == {
        ("GET", f"{BASE}/me"), ("POST", f"{BASE}/sessions"), ("GET", f"{BASE}/sessions"),
        ("GET", f"{BASE}/sessions/{{id}}")}
    for phase in ("CAP-006", "CAP-007", "CAP-008", "CAP-009"):
        assert not routes & _contract(phase), phase
    joined = " ".join(path for _, path in routes)
    for forbidden in ("/federation", "/models", "/research", "/summary", "/timeline", "promote",
                      "deploy"):
        assert forbidden not in joined
    assert API_V2["implemented_by_phase"]["CAP-004"] == [
        "GET /product/v1/me", "POST /product/v1/sessions", "GET /product/v1/sessions",
        "GET /product/v1/sessions/{id}"]
    assert app.docs_url is None and app.openapi_url is None


def test_the_frozen_cap_003_app_file_is_untouched_and_not_imported_by_the_successor() -> None:
    lock = json.loads((ROOT / "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json"
                       ).read_text())
    path = "api/product_app.py"
    expected = lock["components"]["CAPSTONE_PRODUCT_API_V1"]["sha256"]
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    tree = ast.parse((ROOT / "api/product_app_v1_1.py").read_text())
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "api.product_app" not in imported


def test_the_successor_reuses_the_frozen_cap_003_services_instead_of_copying_them(tmp_path) -> None:
    app, _ = make_persistent_app(tmp_path / "u.sqlite3")
    assert type(app.state.session_service._monitoring) is MonitoringService
    text = (ROOT / "api/product_app_v1_1.py").read_text() + (
        ROOT / "product/sessions/service.py").read_text()
    for token in ("WearableStreamRuntime", "infer_window(", "merge_source_streams",
                  "ProductEventAdapter(", ".live_records(", ".live_events("):
        assert text.count(token) <= 1, token  # at most the one construction in the service
    assert "WearableStreamRuntime" not in text and "merge_source_streams" not in text
    for forbidden in ("torch", "api.runtime_v2", "federated", "privacy", "flwr"):
        assert forbidden not in text


def test_no_model_selector_exists_on_any_successor_route_or_body(tmp_path) -> None:
    forbidden = set(load_contract("product_api")["forbidden_request_field_names"])
    app, _ = make_persistent_app(tmp_path / "m.sqlite3")
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            names = {p.name for p in (*dependant.query_params, *dependant.header_params,
                                      *dependant.cookie_params)}
            assert not names & forbidden, route.path
    with TestClient(app) as client:
        device = client.post(f"{BASE}/devices/simulated", json={}, headers=USER_A).json()["device_id"]
        for body in ({"device_id": device, "scenario_id": "NORMAL_MONITORING",
                      "model_id": "MODEL_V1"}, {"device_id": device, "scenario_id": "X",
                                                "threshold": 0.1},
                     {"device_id": device, "scenario_id": "X", "checkpoint": "c"}):
            response = client.post(f"{BASE}/sessions", json=body, headers=USER_A)
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "INVALID_REQUEST"


# ---- system + me -------------------------------------------------------------------------------
def test_system_info_v2_reports_auth_demo_and_sqlite_truthfully(tmp_path) -> None:
    app, _ = make_persistent_app(tmp_path / "s.sqlite3")
    with TestClient(app) as client:
        body = client.get(f"{BASE}/system").json()
    delta = API_V2["system_info_v2"]
    assert set(delta["added_fields"]) <= set(body)
    assert body["auth_provider"] == "DEMO" and body["demo_mode"] is True
    assert body["persistence_mode"] == "SQLITE" and body["auth_status"] == "CONFIGURED"
    assert body["product_api_implementation"] == "CAPSTONE_PRODUCT_API_V1_1"
    assert body["product_api_version"] == "PRODUCT_API_V2"
    assert body["model_id"] == "MODEL_V2_FINAL" and body["calibration_id"] == "CAL_V2"
    assert body["software_system"] == "SOFTWARE_SYSTEM_V2"
    assert body["hardware_mode"] == "SIMULATED_ONLY" and body["physical_hardware_available"] is False
    assert body["federation_runtime"] == "NOT_IMPLEMENTED"
    assert not {"threshold", "checkpoint", "candidate", "scenario_id"} & set(body)


def test_me_returns_the_verified_identity_and_requires_authentication(tmp_path) -> None:
    app, store = make_persistent_app(tmp_path / "me.sqlite3")
    with TestClient(app) as client:
        assert client.get(f"{BASE}/me").status_code == 401
        me = client.get(f"{BASE}/me", headers=USER_A).json()
    assert me["user_id"] == "demo:cap003-user-a" and me["demo_mode"] is True
    assert me["auth_provider"] == "DEMO" and "model_id" not in me
    assert store.get_user("demo:cap003-user-a")["demo_mode"] == 1


# ---- sessions ----------------------------------------------------------------------------------
def test_session_creation_persists_a_device_ready_session_with_the_frozen_runtime(tmp_path) -> None:
    app, store = make_persistent_app(tmp_path / "c.sqlite3", ids=SeqIds("SESS-X"))
    with TestClient(app) as client:
        device, sid = provisioned_session(client, "CONTEXT_LOSS")
        body = client.get(f"{BASE}/sessions/{sid}", headers=USER_A).json()
    assert sid == "SESS-X0001" and body["state"] == "DEVICE_READY"
    assert body["device_id"] == device and body["started_at_us"] is None
    assert body["runtime"]["model_id"] == "MODEL_V2_FINAL" and body["runtime"][
        "software_system_id"] == "SOFTWARE_SYSTEM_V2"
    assert body["simulation_provenance"]["scenario_id"] == "CONTEXT_LOSS"
    assert body["simulation_provenance"]["seed"] == 20261002
    assert store.get_session(sid).state.value == "DEVICE_READY"
    assert app.state.runtime_state.sessions[sid].task is None  # creation never starts monitoring


def test_session_creation_validates_ownership_connection_and_scenario(tmp_path) -> None:
    app, store = make_persistent_app(tmp_path / "v.sqlite3")
    with TestClient(app) as client:
        device = client.post(f"{BASE}/devices/simulated", json={"scenario_id": "POOR_SIGNAL"},
                             headers=USER_A).json()["device_id"]
        post = lambda body, h=USER_A: client.post(f"{BASE}/sessions", json=body, headers=h)  # noqa: E731
        assert post({"device_id": device, "scenario_id": "POOR_SIGNAL"}).status_code == 409
        client.post(f"{BASE}/devices/{device}/scan", headers=USER_A)
        client.post(f"{BASE}/devices/{device}/connect", headers=USER_A)
        mismatch = post({"device_id": device, "scenario_id": "NORMAL_MONITORING"})
        assert mismatch.status_code == 400 and mismatch.json()["error"]["code"] == "INVALID_REQUEST"
        assert post({"device_id": device, "scenario_id": "POOR_SIGNAL"}, USER_B).status_code == 403
        assert post({"device_id": "NOPE", "scenario_id": "POOR_SIGNAL"}).status_code == 404
        assert post({"device_id": device}).status_code == 400  # scenario_id is required
        assert client.post(f"{BASE}/sessions", json={}, headers=USER_A).status_code == 400
        assert post({"device_id": device, "scenario_id": "POOR_SIGNAL"}).status_code == 200
    assert len(store.rows("monitoring_sessions")) == 1  # rejected attempts persisted nothing


def test_session_list_is_caller_scoped_and_ordered_newest_first_with_a_stable_tiebreak(
        tmp_path) -> None:
    ticks = iter(range(1_700_000_000_000_000, 1_700_000_000_000_000 + 10_000, 1))
    clock_values = {"fixed": None}

    def clock() -> int:
        return clock_values["fixed"] if clock_values["fixed"] is not None else next(ticks)

    app, _ = make_persistent_app(tmp_path / "l.sqlite3", ids=SeqIds("SESS-L"), clock=clock)
    with TestClient(app) as client:
        created = []
        for scenario in ("NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL"):
            created.append(provisioned_session(client, scenario)[1])
        other = provisioned_session(client, "NORMAL_MONITORING", USER_B)[1]
        listed = [s["session_id"] for s in client.get(f"{BASE}/sessions", headers=USER_A).json()]
        assert listed == created[::-1]  # newest created first
        assert other not in listed and [
            s["session_id"] for s in client.get(f"{BASE}/sessions", headers=USER_B).json()] == [other]
        clock_values["fixed"] = 1_800_000_000_000_000  # identical created_at_us -> id tiebreak
        a = provisioned_session(client, "NORMAL_MONITORING")[1]
        b = provisioned_session(client, "NORMAL_MONITORING")[1]
        ordered = [s["session_id"] for s in client.get(f"{BASE}/sessions", headers=USER_A).json()]
        assert ordered[:2] == sorted([a, b], reverse=True)


def test_session_get_and_start_stop_enforce_ownership_and_hide_nothing_by_listing(tmp_path) -> None:
    app, _ = make_persistent_app(tmp_path / "o.sqlite3", StrictInferenceDouble())
    with TestClient(app) as client:
        device, sid = provisioned_session(client, "NORMAL_MONITORING")
        for method, path in (("GET", f"/sessions/{sid}"), ("POST", f"/sessions/{sid}/start"),
                             ("POST", f"/sessions/{sid}/stop")):
            denied = client.request(method, BASE + path, headers=USER_B)
            assert denied.status_code == 403 and denied.json()["error"]["code"] == "FORBIDDEN"
            assert client.request(method, BASE + path.replace(sid, "NOPE"),
                                  headers=USER_A).status_code == 404
        assert client.get(f"{BASE}/devices", headers=USER_B).json() == []
        assert client.post(f"{BASE}/devices/{device}/scan", headers=USER_B).status_code == 403
        assert client.get(f"{BASE}/sessions", headers=USER_B).json() == []
        for headers, expected in ((None, 4401), (USER_B, 4403), (USER_A, None)):
            if expected is None:
                continue
            with client.websocket_connect(f"{BASE}/sessions/{sid}/live",
                                          headers=headers or {}) as ws, pytest.raises(
                    WebSocketDisconnect) as excinfo:
                ws.receive_json()
            assert excinfo.value.code == expected
        with client.websocket_connect(f"{BASE}/sessions/NOPE/live", headers=USER_A) as ws, \
                pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 4404


def test_start_and_natural_completion_persist_through_the_frozen_monitoring_service(tmp_path) -> None:
    double = StrictInferenceDouble()
    app, store = make_persistent_app(tmp_path / "n.sqlite3", double)
    with TestClient(app) as client:
        device, sid = provisioned_session(client, "NORMAL_MONITORING")
        started = client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        assert started.status_code == 200 and started.json()["state"] == "MONITORING"
        assert started.json()["started_at_us"] is not None
        again = client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        assert again.status_code == 409
        events = collect_ws(client, sid)
        final = client.get(f"{BASE}/sessions/{sid}", headers=USER_A).json()
    assert final["state"] == "COMPLETED" and final["ended_at_us"] >= final["started_at_us"]
    statuses = [e["payload"]["session_state"] for e in events if e["event_type"] == "session.status"]
    assert statuses == ["MONITORING", "STOPPING", "COMPLETED"]
    assert len(double.requests) == 21 and len(store.rows("inference_events")) == 21
    assert app.state.runtime_state.devices[device].active_session_id is None
    assert app.state.bridge.unmatched_raw_responses == []


def test_manual_stop_goes_through_the_frozen_stop_and_is_persisted(tmp_path) -> None:
    import asyncio
    import threading
    import time
    release, seen = threading.Event(), []
    double = StrictInferenceDouble()

    async def gated(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        while len(seen) >= 3 and not release.is_set():
            await asyncio.sleep(0.01)
        return double.handler(request)

    def factory() -> CapstoneInferenceClient:
        return CapstoneInferenceClient("http://inference.test", transport=httpx.MockTransport(gated))

    from api.product_app_v1_1 import create_product_app_v1_1 as build
    from capstone_persistence.store import CapstoneSqliteStore
    store = CapstoneSqliteStore(tmp_path / "ms.sqlite3")
    app = build(store=store, identity_resolver=cap003_test_identity_resolver,
                auth_description=TEST_DESCRIPTION, inference_client_factory=factory,
                id_generator=SeqIds("SESS-M"))
    with TestClient(app) as client:
        _, sid = provisioned_session(client, "MIXED_MONITORING_SESSION")
        client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        for _ in range(1000):
            if len(seen) >= 3:
                break
            time.sleep(0.01)
        threading.Timer(0.3, release.set).start()
        stopped = client.post(f"{BASE}/sessions/{sid}/stop", headers=USER_A)
        assert stopped.status_code == 200 and stopped.json()["state"] == "COMPLETED"
        assert client.post(f"{BASE}/sessions/{sid}/stop", headers=USER_A).status_code == 409
        assert client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A).status_code == 409
    assert store.get_session(sid).state.value == "COMPLETED"
    assert len(store.rows("inference_events")) < 93  # really stopped early


def test_unrecoverable_storage_failure_fails_the_session_without_altering_inference(
        tmp_path) -> None:
    double = StrictInferenceDouble()
    app, store = make_persistent_app(tmp_path / "f.sqlite3", double)
    original = store.insert_context_snapshot
    calls = {"n": 0}

    def failing(**kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("disk full")
        return original(**kwargs)

    store.insert_context_snapshot = failing  # type: ignore[method-assign]
    with TestClient(app) as client:
        _, sid = provisioned_session(client, "NORMAL_MONITORING")
        client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        events = collect_ws(client, sid)
        final = client.get(f"{BASE}/sessions/{sid}", headers=USER_A).json()
    assert final["state"] == "FAILED"  # storage failure => session FAILED, never silent loss
    errors = [e for e in events if e["event_type"] == "system.error"]
    assert len(errors) == 1 and "StoragePersistenceError" in errors[0]["payload"]["message"]
    assert len(double.requests) == 3  # the inference path itself was not altered or retried
    assert events[-1]["payload"]["session_state"] == "FAILED"


def test_persisted_session_websocket_for_an_earlier_process_closes_cleanly_without_events(
        tmp_path) -> None:
    path = tmp_path / "w.sqlite3"
    app, store = make_persistent_app(path, StrictInferenceDouble(), ids=SeqIds("SESS-P"))
    with TestClient(app) as client:
        _, sid = provisioned_session(client, "NORMAL_MONITORING")
        client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        collect_ws(client, sid)
    store.close()
    app2, _ = make_persistent_app(path, StrictInferenceDouble(), ids=SeqIds("SESS-Q"))
    with TestClient(app2) as client2:
        assert client2.get(f"{BASE}/sessions/{sid}", headers=USER_A).json()["state"] == "COMPLETED"
        assert collect_ws(client2, sid) == []  # the live journal is ephemeral; history is CAP-009


# ---- CORS --------------------------------------------------------------------------------------
def test_cors_uses_an_explicit_allow_list_and_never_a_wildcard_with_credentials(tmp_path) -> None:
    from capstone_persistence.store import CapstoneSqliteStore
    store = CapstoneSqliteStore(tmp_path / "cors.sqlite3")
    with pytest.raises(ValueError, match="WILDCARD"):
        create_product_app_v1_1(store=store, identity_resolver=cap003_test_identity_resolver,
                                auth_description=TEST_DESCRIPTION, allowed_origins=("*",))
    app = create_product_app_v1_1(store=store, identity_resolver=cap003_test_identity_resolver,
                                  auth_description=TEST_DESCRIPTION,
                                  allowed_origins=("http://localhost:5173",))
    with TestClient(app) as client:
        good = client.options(f"{BASE}/me", headers={"Origin": "http://localhost:5173",
                                                    "Access-Control-Request-Method": "GET"})
        assert good.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert good.headers["access-control-allow-credentials"] == "true"
        bad = client.options(f"{BASE}/me", headers={"Origin": "https://evil.example",
                                                   "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in bad.headers
        assert client.get(f"{BASE}/me", headers={"Origin": "http://localhost:5173"}
                          ).status_code == 401  # CORS does not replace authentication


# ---- launcher: refuses to start without explicit auth -----------------------------------------
def _launch(env: dict[str, str]) -> subprocess.CompletedProcess:
    base = {"PYTHONPATH": "src:.", "PATH": ""}
    return subprocess.run([sys.executable, "-m", "scripts.run_capstone_product", "--port", "1"],
                          cwd=ROOT, capture_output=True, text=True, env={**base, **env}, timeout=60)


@pytest.mark.parametrize("env", [
    {}, {"NHM_PRODUCT_AUTH_MODE": "DEMO"},
    {"NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": "wrong"},
    {"NHM_PRODUCT_AUTH_MODE": "CLERK"}, {"NHM_PRODUCT_AUTH_MODE": "NOPE"}])
def test_the_launcher_refuses_to_start_without_a_valid_explicit_auth_configuration(env) -> None:
    result = _launch(env)
    assert result.returncode == 2 and "REFUSING TO START" in result.stderr
    assert "Uvicorn running" not in result.stderr and "NHM capstone" not in result.stdout


def test_the_launcher_builds_a_demo_app_when_explicitly_configured(tmp_path) -> None:
    from scripts.run_capstone_product import build_app_from_env
    ack = load_contract("auth_policy")["demo_provider"]["acknowledgement_value"]
    app = build_app_from_env({"NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": ack,
                              "NHM_PRODUCT_DB_PATH": str(tmp_path / "e.sqlite3"),
                              "NHM_PRODUCT_DEMO_USER_ID": "demo:alice"})
    with TestClient(app) as client:
        system = client.get(f"{BASE}/system").json()
        me = client.get(f"{BASE}/me").json()  # demo identity needs no credential
    assert system["auth_provider"] == "DEMO" and system["demo_mode"] is True
    assert me["user_id"] == "demo:alice" and me["demo_mode"] is True
    assert (tmp_path / "e.sqlite3").exists()
    assert DeviceState.DETACHED.value == "DETACHED"


def _project(events: list[dict]) -> list[dict]:
    projected = []
    for event in events:
        clean = json.loads(json.dumps(event))
        clean["session_id"] = "S"
        clean["event_id"] = f"S-PEV{clean['sequence_index']:06d}"
        projected.append(clean)
    return projected


def test_persistence_does_not_alter_or_reorder_the_live_monitoring_stream(tmp_path) -> None:
    from tests.capstone_product_support import make_app, ready_session
    app3 = make_app(StrictInferenceDouble())
    with TestClient(app3) as client:
        ready_session(client, "MIXED_MONITORING_SESSION", "SX")
        client.post(f"{BASE}/sessions/SX/start", headers=USER_A)
        reference = collect_ws(client, "SX")  # the frozen CAP-003 path, no persistence
    app4, store = make_persistent_app(tmp_path / "ni.sqlite3", StrictInferenceDouble())
    with TestClient(app4) as client:
        _, sid = provisioned_session(client, "MIXED_MONITORING_SESSION")
        client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        persisted = collect_ws(client, sid)
    assert _project(persisted) == _project(reference)  # identical, scientific values included
    assert [e["sequence_index"] for e in persisted] == list(range(len(persisted)))
    assert store.row_counts()["inference_events"] == 86


def test_cap_004_imports_no_fl_runtime_and_never_writes_fl_or_candidate_tables(tmp_path) -> None:
    new_code = [p for d in ("product/auth", "product/persistence", "product/sessions",
                                "capstone_persistence")
                for p in (ROOT / d).rglob("*.py")
                if p.name != "federation_store.py"] + [
        ROOT / "api/product_app_v1_1.py", ROOT / "scripts/run_capstone_product.py"]
    for path in new_code:
        for node in ast.walk(ast.parse(path.read_text())):
            names = set()
            if isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            elif isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
            assert not names & {"federated", "privacy", "flwr", "torch"}, (path, names)
        text = path.read_text().lower()
        for token in ("fedavg", "fedprox", "secagg", "local_train", "capstone_fl_candidate"):
            assert token not in text, (path, token)
    app, store = make_persistent_app(tmp_path / "fl.sqlite3", StrictInferenceDouble())
    with TestClient(app) as client:
        _, sid = provisioned_session(client, "NORMAL_MONITORING")
        client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        collect_ws(client, sid)
    counts = store.row_counts()
    for table in ("federation_runs", "federation_rounds", "fl_client_statuses",
                  "candidate_models", "governance_decisions", "session_summaries"):
        assert counts[table] == 0, table
    assert not store.rows("devices", "adapter_type <> 'SIMULATED'")  # no physical adapter exists
