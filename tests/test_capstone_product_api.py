"""CAP-003: product API route ownership, auth boundary, ownership, device manager, sessions."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api.product_app import create_product_app
from product.api.errors import ProductError, ProductErrorCode
from product.api.models import CreateSimulatedDeviceRequest
from product.contracts import ROOT, load_contract
from product.devices.base import DeviceState
from product.inference.client import CapstoneInferenceClient
from product.monitoring.runtime_state import RuntimeState, seed_engineering_session
from tests.capstone_product_support import (
    BASE,
    USER_A,
    USER_B,
    StrictInferenceDouble,
    collect_ws,
    make_app,
    ready_session,
)

CAP003_FILES = (
    "api/product_app.py", "product/api/errors.py", "product/api/models.py",
    "product/devices/manager.py", "product/inference/client.py",
    "product/monitoring/coordinator.py",
    "product/monitoring/event_adapter.py", "product/monitoring/event_journal.py",
    "product/monitoring/mux.py", "product/monitoring/runtime_state.py",
    "product/monitoring/waveform.py",
)


def _contract_routes(phase: str) -> set[tuple[str, str]]:
    return {(r["method"], r["path"]) for r in load_contract("product_api")["routes"]
            if r["owner_phase"] == phase}


def _app_routes(app) -> set[tuple[str, str]]:
    found = set()
    for route in app.routes:
        if not route.path.startswith("/product"):
            continue
        methods = getattr(route, "methods", None)
        for method in (sorted(methods) if methods else ["WS"]):
            found.add((method, route.path))
    return found


# ---- routes ---------------------------------------------------------------------------------
def test_product_app_implements_exactly_the_cap_003_route_subset() -> None:
    app = make_app()
    assert _app_routes(app) == _contract_routes("CAP-003")
    assert len(_contract_routes("CAP-003")) == 9
    paths = [r.path for r in app.routes if r.path.startswith("/product")]
    assert len(paths) == len(set(zip(paths, [str(getattr(r, "methods", "WS")) for r in app.routes
                                              if r.path.startswith("/product")], strict=True)))


def test_no_later_phase_route_is_implemented_early() -> None:
    implemented = _app_routes(make_app())
    for phase in ("CAP-004", "CAP-006", "CAP-007", "CAP-008", "CAP-009"):
        assert not implemented & _contract_routes(phase), phase
    joined = " ".join(path for _, path in implemented)
    for forbidden in ("/me", "/federation", "/models", "/research", "/summary", "/timeline"):
        assert forbidden not in joined
    assert ("POST", f"{BASE}/sessions") not in implemented  # public session creation is CAP-004
    assert ("GET", f"{BASE}/sessions") not in implemented


def test_product_api_is_separate_from_the_frozen_inference_api() -> None:
    for path in ("api/app_default.py", "api/app_v2.py"):
        text = (ROOT / path).read_text()
        assert "/product/v1" not in text and "product_app" not in text, path
    app = make_app()
    assert not any(r.path.startswith("/v1/") for r in app.routes)
    assert app.docs_url is None and app.openapi_url is None


def test_system_route_is_public_and_truthful() -> None:
    with TestClient(make_app()) as client:
        body = client.get(f"{BASE}/system").json()
    assert body["hardware_mode"] == "SIMULATED_ONLY"
    assert body["physical_hardware_available"] is False
    assert body["persistence_mode"] == "EPHEMERAL_CAP003"
    assert body["federation_runtime"] == "NOT_IMPLEMENTED_IN_CAP003"
    assert body["model_id"] == "MODEL_V2_FINAL" and body["calibration_id"] == "CAL_V2"
    assert body["software_system"] == "SOFTWARE_SYSTEM_V2" and body["auth_status"] == "INJECTED"
    assert "candidate" not in json.dumps(body).lower().replace("no clinical", "")
    with TestClient(make_app(resolver=None)) as client:
        assert client.get(f"{BASE}/system").json()["auth_status"] == "NOT_CONFIGURED"


# ---- auth boundary --------------------------------------------------------------------------
AUTHENTICATED = [("GET", "/devices"), ("POST", "/devices/simulated"), ("POST", "/devices/D/scan"),
                 ("POST", "/devices/D/connect"), ("POST", "/devices/D/disconnect"),
                 ("POST", "/sessions/S/start"), ("POST", "/sessions/S/stop")]


@pytest.mark.parametrize(("method", "path"), AUTHENTICATED)
def test_authenticated_routes_fail_closed_without_an_injected_resolver(method: str,
                                                                       path: str) -> None:
    with TestClient(make_app(resolver=None)) as client:
        response = client.request(method, BASE + path, headers=USER_A,
                                  json={} if method == "POST" else None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize(("method", "path"), AUTHENTICATED)
def test_authenticated_routes_reject_requests_without_an_identity(method: str, path: str) -> None:
    with TestClient(make_app()) as client:  # resolver present but no identity header
        response = client.request(method, BASE + path, json={} if method == "POST" else None)
    assert response.status_code == 401


def test_the_contract_marks_exactly_the_system_route_public() -> None:
    public = {r["path"] for r in load_contract("product_api")["routes"]
              if r["owner_phase"] == "CAP-003" and r["auth"] == "PUBLIC"}
    assert public == {f"{BASE}/system"}


def test_no_production_auth_provider_or_bypass_exists() -> None:
    source = "".join((ROOT / p).read_text() for p in CAP003_FILES)
    for forbidden in ("ClerkAuthProvider", "DemoAuthProvider", "DEBUG", "allow_anonymous",
                      "CAP003_TEST_IDENTITY_ONLY", "import clerk", "clerk_backend_api"):
        assert forbidden not in source, forbidden
    for path in Path(ROOT / "product").rglob("*.py"):
        assert "x-cap003-test-user" not in path.read_text().lower(), path
    assert (ROOT / "scripts/capstone_cap003_test_identity.py").is_file()
    from scripts.capstone_cap003_test_identity import CLASSIFICATION
    assert CLASSIFICATION == "CAP003_TEST_IDENTITY_ONLY"
    assert not [p for p in (ROOT / "product/auth").rglob("*.py")
                if "cap003" in p.read_text().lower()]


# ---- no model selector ----------------------------------------------------------------------
def test_no_client_controlled_model_selector_exists_anywhere_on_the_product_api() -> None:
    forbidden = set(load_contract("product_api")["forbidden_request_field_names"])
    assert not forbidden & set(CreateSimulatedDeviceRequest.model_fields)
    for route in make_app().routes:
        for dependant in (getattr(route, "dependant", None),):
            if dependant is None:
                continue
            names = {p.name for p in (*dependant.query_params, *dependant.header_params,
                                      *dependant.cookie_params)}
            assert not names & forbidden, route.path
    with TestClient(make_app()) as client:
        for body in ({"model_id": "MODEL_V1"}, {"checkpoint": "x"}, {"threshold": 0.1},
                     {"calibration_id": "CAL_V1"}, {"scenario_id": "NORMAL_MONITORING",
                                                    "alert_policy_id": "P"}):
            response = client.post(f"{BASE}/devices/simulated", json=body, headers=USER_A)
            assert response.status_code == 400, body
            assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_session_runtime_identity_is_pinned_and_not_overridable() -> None:
    from product.session import default_runtime_identity
    lock = json.loads((ROOT / "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json").read_text())
    runtime = default_runtime_identity().model_dump()
    assert runtime["model_id"] == lock["identity"]["model_id"] == "MODEL_V2_FINAL"
    assert runtime["calibration_id"] == lock["identity"]["calibration_id"] == "CAL_V2"
    assert runtime["gateway_artifact_id"] == lock["identity"]["gateway_artifact_id"]
    app = make_app(StrictInferenceDouble())
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "S_ID")
        session = client.post(f"{BASE}/sessions/S_ID/start", headers=USER_A).json()
        assert session["runtime"] == runtime
        collect_ws(client, "S_ID")


# ---- device manager -------------------------------------------------------------------------
def test_device_manager_full_flow_and_owner_scoping() -> None:
    with TestClient(make_app()) as client:
        created = client.post(f"{BASE}/devices/simulated", headers=USER_A,
                              json={"display_name": "Bench", "scenario_id": "CONTEXT_LOSS"})
        assert created.status_code == 200
        device = created.json()
        assert device["adapter_type"] == "SIMULATED" and device["simulation"] is True
        assert device["connection_state"] == "DETACHED" and device["display_name"] == "Bench"
        device_id = device["device_id"]
        assert [d["device_id"] for d in client.get(f"{BASE}/devices", headers=USER_A).json()] == [
            device_id]
        assert client.get(f"{BASE}/devices", headers=USER_B).json() == []
        scanned = client.post(f"{BASE}/devices/{device_id}/scan", headers=USER_A).json()
        assert scanned["connection_state"] == "FOUND"
        connected = client.post(f"{BASE}/devices/{device_id}/connect", headers=USER_A).json()
        assert connected["connection_state"] == "CONNECTED"
        detached = client.post(f"{BASE}/devices/{device_id}/disconnect", headers=USER_A).json()
        assert detached["connection_state"] == "DETACHED"
        state: RuntimeState = client.app.state.runtime_state
        assert state.devices[device_id].source.connection_state is DeviceState.DETACHED
        assert [e.event_type.value for e in state.devices[device_id].event_log] == [
            "SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED",
            "DEVICE_DETACHED"]


@pytest.mark.parametrize("action", ["scan", "connect", "disconnect"])
def test_device_commands_reject_other_users_and_unknown_devices(action: str) -> None:
    with TestClient(make_app()) as client:
        device_id = client.post(f"{BASE}/devices/simulated", json={}, headers=USER_A).json()[
            "device_id"]
        forbidden = client.post(f"{BASE}/devices/{device_id}/{action}", headers=USER_B)
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "FORBIDDEN"
        unknown = client.post(f"{BASE}/devices/NOPE/{action}", headers=USER_A)
        assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "NOT_FOUND"


def test_illegal_lifecycle_commands_map_to_a_deterministic_product_error() -> None:
    with TestClient(make_app()) as client:
        device_id = client.post(f"{BASE}/devices/simulated", json={}, headers=USER_A).json()[
            "device_id"]
        for action in ("connect", "disconnect"):  # DETACHED: neither is legal
            response = client.post(f"{BASE}/devices/{device_id}/{action}", headers=USER_A)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "INVALID_STATE"
            assert "ILLEGAL_DEVICE_TRANSITION" in response.json()["error"]["message"]
        client.post(f"{BASE}/devices/{device_id}/scan", headers=USER_A)
        again = client.post(f"{BASE}/devices/{device_id}/scan", headers=USER_A)
        assert again.status_code == 409
        state = client.app.state.runtime_state.devices[device_id].source.connection_state
        assert state is DeviceState.FOUND  # the CAP-002 source stayed authoritative


def test_unimplemented_scenarios_are_rejected_for_new_devices() -> None:
    with TestClient(make_app()) as client:
        for scenario in ("FL_SINGLE_RUN", "ALERT_POLICY_ENGINEERING_FIXTURE", "NOPE"):
            response = client.post(f"{BASE}/devices/simulated", headers=USER_A,
                                   json={"scenario_id": scenario})
            assert response.status_code == 400


def test_device_manager_reuses_the_cap_002_source_unchanged() -> None:
    from product.devices.simulated import SimulatedWearableSource
    with TestClient(make_app()) as client:
        device_id = client.post(f"{BASE}/devices/simulated", json={}, headers=USER_A).json()[
            "device_id"]
        entry = client.app.state.runtime_state.devices[device_id]
        assert type(entry.source) is SimulatedWearableSource
        assert entry.node.device_source is entry.source and entry.owner_user_id.startswith("demo:")
    text = (ROOT / "product/devices/manager.py").read_text()
    assert "SimulatedWearableSource(" in text and "class SimulatedWearable" not in text


# ---- sessions -------------------------------------------------------------------------------
def test_session_start_runs_to_natural_completion_and_rejects_a_second_start() -> None:
    double = StrictInferenceDouble()
    app = make_app(double)
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "S1")
        started = client.post(f"{BASE}/sessions/S1/start", headers=USER_A)
        assert started.status_code == 200 and started.json()["state"] == "MONITORING"
        events = collect_ws(client, "S1")  # blocks until the journal closes (session terminal)
        entry = app.state.runtime_state.sessions["S1"]
        assert entry.session.state.value == "COMPLETED"
        assert entry.session.ended_at_us is not None and entry.session.started_at_us == 0
        assert entry.coordinator.telemetry["session_states"] == [
            "MONITORING", "STOPPING", "COMPLETED"]
        statuses = [e["payload"]["session_state"] for e in events
                    if e["event_type"] == "session.status"]
        assert statuses == ["MONITORING", "STOPPING", "COMPLETED"]
        again = client.post(f"{BASE}/sessions/S1/start", headers=USER_A)
        assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_STATE"
        late_stop = client.post(f"{BASE}/sessions/S1/stop", headers=USER_A)
        assert late_stop.status_code == 409
        assert entry.task is not None and entry.task.done()
        assert entry.device_id in app.state.runtime_state.devices
        assert app.state.runtime_state.devices[entry.device_id].active_session_id is None


def test_session_routes_enforce_ownership_and_unknown_sessions() -> None:
    with TestClient(make_app(StrictInferenceDouble())) as client:
        ready_session(client, "NORMAL_MONITORING", "S2")
        assert client.post(f"{BASE}/sessions/S2/start", headers=USER_B).status_code == 403
        assert client.post(f"{BASE}/sessions/S2/stop", headers=USER_B).status_code == 403
        assert client.post(f"{BASE}/sessions/NOPE/start", headers=USER_A).status_code == 404
        assert client.post(f"{BASE}/sessions/NOPE/stop", headers=USER_A).status_code == 404
        stop_early = client.post(f"{BASE}/sessions/S2/stop", headers=USER_A)
        assert stop_early.status_code == 409  # DEVICE_READY, not MONITORING


def test_manual_stop_goes_monitoring_stopping_completed_and_halts_the_device() -> None:
    release = threading.Event()
    seen: list[int] = []
    double = StrictInferenceDouble()

    async def gated(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        while len(seen) >= 3 and not release.is_set():
            await asyncio.sleep(0.01)
        return double.handler(request)

    def factory() -> CapstoneInferenceClient:
        return CapstoneInferenceClient("http://inference.test",
                                       transport=httpx.MockTransport(gated))

    app = make_app(factory=factory)
    with TestClient(app) as client:
        ready_session(client, "MIXED_MONITORING_SESSION", "S3")
        client.post(f"{BASE}/sessions/S3/start", headers=USER_A)
        for _ in range(500):  # wait until the coordinator is blocked inside inference call #3
            if len(seen) >= 3:
                break
            threading.Event().wait(0.01)
        assert len(seen) >= 3
        threading.Timer(0.3, release.set).start()
        stopped = client.post(f"{BASE}/sessions/S3/stop", headers=USER_A)
        assert stopped.status_code == 200 and stopped.json()["state"] == "COMPLETED"
        entry = app.state.runtime_state.sessions["S3"]
        assert entry.coordinator.telemetry["session_states"] == [
            "MONITORING", "STOPPING", "COMPLETED"]
        device = app.state.runtime_state.devices[entry.device_id]
        assert device.active_session_id is None
        # the source timeline may have run ahead (ACCELERATED); the owner can release the device
        released = client.post(f"{BASE}/devices/{entry.device_id}/disconnect", headers=USER_A)
        assert released.status_code == 200
        assert released.json()["connection_state"] == "DETACHED"
        assert entry.coordinator.telemetry["scientific_record_count"] < 167400  # really stopped
        events = collect_ws(client, "S3")
        assert events[-1]["payload"]["session_state"] == "COMPLETED"
        assert events[-2]["payload"]["reason_code"] == "USER_STOP" or any(
            e["payload"].get("reason_code") == "USER_STOP" for e in events[-4:])
        assert client.post(f"{BASE}/sessions/S3/stop", headers=USER_A).status_code == 409


def test_recoverable_device_disconnect_does_not_change_the_session_state() -> None:
    app = make_app(StrictInferenceDouble())
    with TestClient(app) as client:
        ready_session(client, "DISCONNECT_RECONNECT", "S4")
        client.post(f"{BASE}/sessions/S4/start", headers=USER_A)
        events = collect_ws(client, "S4")
    device_states = [e["payload"]["device_state"] for e in events
                     if e["event_type"] == "device.status"]
    assert device_states == ["STREAMING", "DISCONNECTED", "RECONNECTING", "CONNECTED",
                             "STREAMING", "STOPPED"]
    session_states = [e["payload"]["session_state"] for e in events
                      if e["event_type"] == "session.status"]
    assert session_states == ["MONITORING", "STOPPING", "COMPLETED"]  # outage never touched it
    entry = app.state.runtime_state.sessions["S4"]
    assert entry.session.state.value == "COMPLETED"


def test_unrecoverable_inference_failure_fails_the_session_without_retry() -> None:
    double = StrictInferenceDouble(fail_with=500, fail_after=2)
    app = make_app(double)
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "S5")
        client.post(f"{BASE}/sessions/S5/start", headers=USER_A)
        events = collect_ws(client, "S5")
    entry = app.state.runtime_state.sessions["S5"]
    assert entry.session.state.value == "FAILED"
    assert len(double.requests) == 3  # two good windows, one failure, NO automatic retry
    errors = [e for e in events if e["event_type"] == "system.error"]
    assert len(errors) == 1 and errors[0]["payload"]["origin"] == "INFERENCE"
    assert errors[0]["payload"]["recoverable"] is False
    assert events[-1]["event_type"] == "session.status"
    assert events[-1]["payload"]["session_state"] == "FAILED"
    assert app.state.runtime_state.devices[entry.device_id].active_session_id is None


def test_a_400_from_a_product_generated_request_is_an_integration_failure() -> None:
    double = StrictInferenceDouble(fail_with=400)
    app = make_app(double)
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "S6")
        client.post(f"{BASE}/sessions/S6/start", headers=USER_A)
        collect_ws(client, "S6")
    assert app.state.runtime_state.sessions["S6"].session.state.value == "FAILED"


def test_seeding_a_session_is_python_only_and_validates_ownership() -> None:
    state = RuntimeState()
    app = make_app(state=state)
    with TestClient(app) as client:
        device_id = client.post(f"{BASE}/devices/simulated", json={}, headers=USER_A).json()[
            "device_id"]
        owner = state.devices[device_id].owner_user_id
        with pytest.raises(ValueError, match="NOT_CONNECTED"):
            seed_engineering_session(state, owner_user_id=owner, device_id=device_id,
                                     session_id="X")
        client.post(f"{BASE}/devices/{device_id}/scan", headers=USER_A)
        client.post(f"{BASE}/devices/{device_id}/connect", headers=USER_A)
        with pytest.raises(ValueError, match="NOT_OWNED"):
            seed_engineering_session(state, owner_user_id="demo:cap003-other", device_id=device_id,
                                     session_id="X")
        session = seed_engineering_session(state, owner_user_id=owner, device_id=device_id,
                                           session_id="X")
        assert session.state.value == "DEVICE_READY"
        assert client.post(f"{BASE}/sessions", json={}, headers=USER_A).status_code in (404, 405)


def test_product_error_models_cover_the_required_codes() -> None:
    assert {c.value for c in ProductErrorCode} >= {
        "UNAUTHENTICATED", "FORBIDDEN", "NOT_FOUND", "INVALID_STATE",
        "INFERENCE_INTEGRATION_ERROR", "INTERNAL_PRODUCT_ERROR"}
    error = ProductError(ProductErrorCode.INVALID_STATE, "x")
    assert error.status_code == 409


# ---- ephemeral state / no database ----------------------------------------------------------
def test_state_is_ephemeral_in_memory_only_and_no_database_exists() -> None:
    before = {p for p in ROOT.rglob("*") if p.suffix in (".db", ".sqlite", ".sqlite3")
              and "node_modules" not in p.parts and ".venv" not in p.parts}
    with TestClient(make_app(StrictInferenceDouble())) as client:
        ready_session(client, "NORMAL_MONITORING", "S7")
        client.post(f"{BASE}/sessions/S7/start", headers=USER_A)
        collect_ws(client, "S7")
    after = {p for p in ROOT.rglob("*") if p.suffix in (".db", ".sqlite", ".sqlite3")
             and "node_modules" not in p.parts and ".venv" not in p.parts}
    assert before == after
    source = "".join((ROOT / p).read_text() for p in CAP003_FILES)
    for forbidden in ("sqlite3", "sqlalchemy", "aiosqlite", "open(", "write_text", "pickle"):
        assert forbidden not in source, forbidden
    state_text = (ROOT / "product/monitoring/runtime_state.py").read_text()
    assert "EPHEMERAL ENGINEERING STATE" in state_text
    assert not Path(ROOT / "migrations").exists()


def test_product_app_import_does_not_load_a_model_or_the_inference_runtime() -> None:
    code = ("import api.product_app, sys, json;"
            "print(json.dumps(sorted(m for m in sys.modules "
            "if m.split('.')[0] in ('torch','federated','privacy','flwr','training','models') "
            "or m in ('api.runtime_v2','api.runtime','api.app_v2','api.app_default',"
            "'deployment.gateway_v2'))))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True,
                         text=True, env={"PYTHONPATH": "src:.", "PATH": ""}).stdout
    assert json.loads(out.strip().splitlines()[-1]) == []


def test_factory_exposes_the_same_app_type_for_every_construction() -> None:
    assert type(create_product_app()).__name__ == "FastAPI"
