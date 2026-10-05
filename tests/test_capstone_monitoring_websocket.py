"""CAP-003: monitoring WebSocket semantics (auth close codes, journal replay, no control)."""

from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from product.events import parse_monitoring_event
from product.inference.client import CapstoneInferenceClient
from tests.capstone_product_support import (
    BASE,
    USER_A,
    USER_B,
    StrictInferenceDouble,
    collect_ws,
    make_app,
    ready_session,
)


def _live(session_id: str) -> str:
    return f"{BASE}/sessions/{session_id}/live"


def _close_code(client: TestClient, path: str, headers: dict[str, str] | None) -> int:
    with client.websocket_connect(path, headers=headers or {}) as ws, pytest.raises(
            WebSocketDisconnect) as excinfo:
        ws.receive_json()
    return excinfo.value.code


class Gate:
    """A double whose HTTP answers are held back until released (a controllable slow session)."""

    def __init__(self, hold_after: int = 1) -> None:
        self.double = StrictInferenceDouble()
        self.release = threading.Event()
        self.hold_after = hold_after
        self.calls = 0

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        while self.calls > self.hold_after and not self.release.is_set():
            await asyncio.sleep(0.01)
        return self.double.handler(request)

    def factory(self) -> CapstoneInferenceClient:
        return CapstoneInferenceClient("http://inference.test",
                                       transport=httpx.MockTransport(self.handler))

    def wait_until_held(self) -> None:
        for _ in range(1000):
            if self.calls > self.hold_after:
                return
            time.sleep(0.01)
        raise AssertionError("session never reached the hold point")


def test_close_codes_for_unauthenticated_unknown_and_wrong_owner() -> None:
    app = make_app(StrictInferenceDouble())
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "W1")
        assert _close_code(client, _live("W1"), None) == 4401  # no identity
        assert _close_code(client, _live("NOPE"), USER_A) == 4404  # unknown session
        assert _close_code(client, _live("W1"), USER_B) == 4403  # not the owner
    with TestClient(make_app(resolver=None)) as client:  # no resolver: fail closed
        assert _close_code(client, _live("W1"), USER_A) == 4401


def test_a_subscriber_receives_a_valid_monitoring_only_stream() -> None:
    app = make_app(StrictInferenceDouble())
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "W2")
        client.post(f"{BASE}/sessions/W2/start", headers=USER_A)
        events = collect_ws(client, "W2")
    assert events and [e["sequence_index"] for e in events] == list(range(len(events)))
    for event in events:
        assert parse_monitoring_event(event).session_id == "W2"
    assert not {e["event_type"] for e in events} & {
        "federation.status", "round.status", "client.status", "candidate.created"}


def test_reconnect_replays_the_journal_from_sequence_zero() -> None:
    app = make_app(StrictInferenceDouble())
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "W3")
        client.post(f"{BASE}/sessions/W3/start", headers=USER_A)
        first = collect_ws(client, "W3")
        second = collect_ws(client, "W3")  # a browser reconnect after completion
    assert first == second and first[0]["sequence_index"] == 0


def test_multiple_concurrent_subscribers_receive_identical_semantic_events() -> None:
    gate = Gate()
    app = make_app(factory=gate.factory)
    results: dict[str, list] = {}
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "W4")
        client.post(f"{BASE}/sessions/W4/start", headers=USER_A)
        gate.wait_until_held()

        def reader(name: str) -> None:
            results[name] = collect_ws(client, "W4")

        threads = [threading.Thread(target=reader, args=(n,)) for n in ("a", "b")]
        for thread in threads:
            thread.start()
        time.sleep(0.3)  # both are connected and replaying the live journal
        gate.release.set()
        for thread in threads:
            thread.join(timeout=60)
    assert results["a"] == results["b"] and len(results["a"]) > 50


def test_client_messages_are_rejected_and_cannot_control_monitoring() -> None:
    gate = Gate()
    app = make_app(factory=gate.factory)
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "W5")
        client.post(f"{BASE}/sessions/W5/start", headers=USER_A)
        gate.wait_until_held()
        with client.websocket_connect(_live("W5"), headers=USER_A) as ws:
            ws.receive_json()
            ws.send_json({"action": "stop"})
            ws.send_json({"model_id": "MODEL_V1", "threshold": 0.01, "scenario_id": "POOR_SIGNAL"})
            code = None
            for _ in range(5000):
                try:
                    ws.receive_json()
                except WebSocketDisconnect as error:
                    code = error.code
                    break
            assert code == 1008  # policy violation: the socket is server -> client only
        entry = app.state.runtime_state.sessions["W5"]
        assert entry.session.state.value == "MONITORING"  # the "stop" was not honoured
        gate.release.set()
        events = collect_ws(client, "W5")
        assert entry.session.state.value == "COMPLETED"
        assert entry.coordinator.telemetry["scientific_record_count"] == 43200
        models = {e["payload"]["model_id"] for e in events if e["event_type"] == "inference.result"}
        assert models == {"MODEL_V2_FINAL"}  # nothing the client sent selected a model
        assert app.state.runtime_state.devices[entry.device_id].scenario_id == "NORMAL_MONITORING"


def test_query_parameters_cannot_select_a_model_on_the_socket() -> None:
    app = make_app(StrictInferenceDouble())
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "W6")
        client.post(f"{BASE}/sessions/W6/start", headers=USER_A)
        events = collect_ws(client, "W6")
        with client.websocket_connect(_live("W6") + "?model_id=MODEL_V1&threshold=0.1",
                                      headers=USER_A) as ws:
            replay = []
            while True:
                try:
                    replay.append(ws.receive_json())
                except WebSocketDisconnect:
                    break
    assert replay == events
    assert {e["payload"]["model_id"] for e in replay if e["event_type"] == "inference.result"} == {
        "MODEL_V2_FINAL"}


def test_monitoring_completes_with_zero_subscribers() -> None:
    app = make_app(StrictInferenceDouble())
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "W7")
        client.post(f"{BASE}/sessions/W7/start", headers=USER_A)
        entry = app.state.runtime_state.sessions["W7"]
        for _ in range(3000):
            if entry.session.state.value == "COMPLETED":
                break
            time.sleep(0.01)
        assert entry.session.state.value == "COMPLETED"
        assert len(entry.journal) > 100 and entry.journal.closed
        assert len(collect_ws(client, "W7")) == len(entry.journal)  # replay after the fact


def test_a_subscriber_disconnecting_does_not_stop_monitoring() -> None:
    gate = Gate()
    app = make_app(factory=gate.factory)
    with TestClient(app) as client:
        ready_session(client, "NORMAL_MONITORING", "W8")
        client.post(f"{BASE}/sessions/W8/start", headers=USER_A)
        gate.wait_until_held()
        with client.websocket_connect(_live("W8"), headers=USER_A) as ws:
            for _ in range(3):
                ws.receive_json()
        entry = app.state.runtime_state.sessions["W8"]
        assert entry.session.state.value == "MONITORING"  # still running after the drop
        gate.release.set()
        for _ in range(3000):
            if entry.session.state.value == "COMPLETED":
                break
            time.sleep(0.01)
        assert entry.session.state.value == "COMPLETED"
        assert entry.coordinator.telemetry["scientific_record_count"] == 43200
