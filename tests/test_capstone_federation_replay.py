# ruff: noqa: E501
"""CAP-007: REPLAY runs (real replay of a prior completed run; zero training/aggregation/candidates)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from product.events import parse_federation_event
from product.federation import client as client_module
from product.federation.replay import semantic_projection
from tests.capstone_federation_support import (
    BASE,
    SINGLE_RUN,
    USER_A,
    USER_B,
    clone_root,
    completed_run,
    make_fed_app,
    poll_run,
)

REPLAY = {**SINGLE_RUN, "run_type": "REPLAY"}


def _forbid_training(monkeypatch) -> list[str]:
    calls: list[str] = []

    def boom(*args, **kwargs):
        calls.append("train")
        raise AssertionError("a REPLAY must never train")

    monkeypatch.setattr(client_module, "train_local_epoch_v2", boom)
    monkeypatch.setattr(client_module, "train_local_fedprox_epoch_v2", boom)
    return calls


def test_replay_without_a_completed_source_fails_clearly_and_creates_no_run(tmp_path) -> None:
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(f"{BASE}/federation/runs", json=REPLAY, headers=USER_A)
        assert response.status_code == 409 and "NO_COMPLETED_SOURCE_RUN_FOR_REPLAY" in response.text
        assert client.get(f"{BASE}/federation/runs", headers=USER_A).json() == []


def test_replay_does_not_use_another_users_run_or_a_different_configuration() -> None:
    done = completed_run()
    app, _ = make_fed_app(clone_root(done.root))
    with TestClient(app) as client:
        assert client.post(f"{BASE}/federation/runs", json=REPLAY, headers=USER_B).status_code == 409
        other = {**REPLAY, "algorithm": "FEDPROX"}
        assert client.post(f"{BASE}/federation/runs", json=other, headers=USER_A).status_code == 409


def test_replay_reproduces_the_source_stream_with_zero_training_and_zero_new_candidates(monkeypatch) -> None:
    done = completed_run()
    calls = _forbid_training(monkeypatch)
    app, _ = make_fed_app(clone_root(done.root), run_ids=lambda: "FEDRUN-REPLAY-1")
    with TestClient(app) as client:
        created = client.post(f"{BASE}/federation/runs", json=REPLAY, headers=USER_A).json()
        assert created["run_type"] == "REPLAY" and created["run_id"] == "FEDRUN-REPLAY-1"
        assert client.post(f"{BASE}/federation/runs/FEDRUN-REPLAY-1/start", headers=USER_A).status_code == 200
        run = poll_run(client, "FEDRUN-REPLAY-1", USER_A, timeout=60)
        rounds = client.get(f"{BASE}/federation/runs/FEDRUN-REPLAY-1/rounds", headers=USER_A).json()
        models = client.get(f"{BASE}/models", headers=USER_A).json()
    assert calls == []
    assert run["status"] == "COMPLETED" and run["run_type"] == "REPLAY" and run["candidate_ids"] == []
    assert [r["state"] for r in rounds] == ["COMPLETED"] * 3 and all(r["candidate_id"] is None for r in rounds)
    assert [r["base_state_digest"] for r in rounds] == [r["base_state_digest"] for r in done.rounds]
    assert len(models["capstone_fl_candidates"]) == 1  # no new candidate, no new governance decision
    service = app.state.federation_service
    events = list(service.journal_for("FEDRUN-REPLAY-1").events)
    for event in events:
        parse_federation_event(event.model_dump(mode="json"))
    source = [parse_federation_event(e) for e in done.events]
    assert semantic_projection(events) == semantic_projection(source)
    assert [e.event_type for e in events] == [e["event_type"] for e in done.events]
    assert all(e.run_id == "FEDRUN-REPLAY-1" and e.event_id.startswith("FEDRUN-REPLAY-1-FEV") for e in events)
    assert {e.payload.run_type.value for e in events if e.event_type == "federation.status"} == {"REPLAY"}
    meta = service.artifacts.read_run_meta("FEDRUN-REPLAY-1")
    assert meta["replay_source_run_id"] == done.run_id
    counts = app.state.federation_store.counts()
    assert counts["candidate_models"] == 1 and counts["governance_decisions"] == 1
    assert json.loads(json.dumps(meta))["run_type"] == "REPLAY"


def test_replay_is_visibly_replay_in_every_status_event() -> None:
    done = completed_run()
    assert {e["payload"]["run_type"] for e in done.events if e["event_type"] == "federation.status"} == {"LIVE_RUN"}
