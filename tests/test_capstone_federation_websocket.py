# ruff: noqa: E501
"""CAP-007: WS /product/v1/federation/runs/{id}/live (auth, ownership, replay, tail, reconnect)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from product.events import FEDERATION_EVENT_KINDS, parse_federation_event
from tests.capstone_federation_support import (
    BASE,
    SINGLE_RUN,
    USER_A,
    USER_B,
    completed_run,
    make_fed_app,
    poll_run,
)


def collect(client: TestClient, run_id: str, headers: dict[str, str] | None, limit: int | None = None
            ) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with client.websocket_connect(f"{BASE}/federation/runs/{run_id}/live", headers=headers or {}) as ws:
        while limit is None or len(events) < limit:
            try:
                events.append(ws.receive_json())
            except WebSocketDisconnect:
                break
    return events


def close_code(client: TestClient, run_id: str, headers: dict[str, str] | None) -> int:
    with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(
            f"{BASE}/federation/runs/{run_id}/live", headers=headers or {}) as ws:
        ws.receive_json()
    return closed.value.code


def test_close_codes_4401_4403_4404() -> None:
    done = completed_run()
    app, _ = make_fed_app(done.root)
    with TestClient(app) as client:
        assert close_code(client, done.run_id, None) == 4401
        assert close_code(client, done.run_id, USER_B) == 4403
        assert close_code(client, "FEDRUN-DOES-NOT-EXIST", USER_A) == 4404


def test_a_finished_run_replays_from_sequence_zero_identically_to_every_subscriber() -> None:
    done = completed_run()
    app, _ = make_fed_app(done.root)
    with TestClient(app) as client:
        first = collect(client, done.run_id, USER_A)
        second = collect(client, done.run_id, USER_A)
    assert first == second == done.events
    assert [e["sequence_index"] for e in first] == list(range(len(first)))
    assert {e["event_type"] for e in first} <= set(FEDERATION_EVENT_KINDS)
    for event in first:
        parse_federation_event(event)


def test_the_channel_is_server_to_client_only() -> None:
    done = completed_run()
    app, _ = make_fed_app(done.root)
    with TestClient(app) as client:
        with client.websocket_connect(f"{BASE}/federation/runs/{done.run_id}/live", headers=USER_A) as ws:
            ws.send_text("hello")
            with pytest.raises(WebSocketDisconnect) as closed:
                while True:
                    ws.receive_json()
        assert closed.value.code == 1008


def test_live_tail_reconnect_and_multiple_concurrent_subscribers_on_a_running_run(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        run_id = client.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).json()["run_id"]
        streams: dict[str, list[dict[str, Any]]] = {}
        errors: list[BaseException] = []

        def subscribe(name: str) -> None:
            try:
                streams[name] = collect(client, run_id, USER_A)  # connected BEFORE start: replay 0 + tail
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=subscribe, args=(n,)) for n in ("one", "two")]
        for t in threads:
            t.start()
        time.sleep(1.0)
        assert client.post(f"{BASE}/federation/runs/{run_id}/start", headers=USER_A).status_code == 200
        for t in threads:
            t.join(timeout=420)
        assert not errors, errors
        assert poll_run(client, run_id, USER_A)["status"] == "COMPLETED"
        partial = collect(client, run_id, USER_A, limit=20)  # a browser dropping mid-stream ...
        reconnect = collect(client, run_id, USER_A)          # ... reconnects: replay from 0
    assert streams["one"] == streams["two"] == reconnect
    assert reconnect[:20] == partial and reconnect[0]["payload"]["run_status"] == "CREATED"
    assert reconnect[-1]["event_type"] == "federation.completed"
    assert [e["sequence_index"] for e in reconnect] == list(range(len(reconnect)))
