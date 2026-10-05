# ruff: noqa: E501
"""CAP-004: process restart persistence and crash recovery (in-process restarts against the same
SQLite file, plus a REAL killed product process against a real released inference service)."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time

import httpx
from fastapi.testclient import TestClient

from capstone_persistence.store import CapstoneSqliteStore
from product.contracts import ROOT, load_contract
from product.devices.base import DeviceState
from product.persistence.recovery import POLICY
from scripts.run_capstone_monitoring_e2e import launch_released_inference
from tests.capstone_persistent_support import (
    BASE,
    USER_A,
    USER_B,
    SeqIds,
    StrictInferenceDouble,
    collect_ws,
    make_persistent_app,
    provisioned_session,
)

ACK = load_contract("auth_policy")["demo_provider"]["acknowledgement_value"]


def test_completed_sessions_devices_and_users_survive_a_restart(tmp_path) -> None:
    path = tmp_path / "r.sqlite3"
    app1, store1 = make_persistent_app(path, StrictInferenceDouble(), ids=SeqIds("SESS-A"))
    with TestClient(app1) as client:
        device, sid = provisioned_session(client, "CONTEXT_LOSS")
        client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        collect_ws(client, sid)
        before = client.get(f"{BASE}/sessions/{sid}", headers=USER_A).json()
        counts = store1.row_counts()
    store1.close()

    app2, store2 = make_persistent_app(path, StrictInferenceDouble(), ids=SeqIds("SESS-B"))
    with TestClient(app2) as client:
        assert client.get(f"{BASE}/me", headers=USER_A).json()["user_id"] == "demo:cap003-user-a"
        devices = client.get(f"{BASE}/devices", headers=USER_A).json()
        assert [d["device_id"] for d in devices] == [device]
        assert devices[0]["connection_state"] == "DETACHED"  # no pretend-connection after restart
        assert devices[0]["adapter_type"] == "SIMULATED" and devices[0]["simulation"] is True
        after = client.get(f"{BASE}/sessions/{sid}", headers=USER_A).json()
        assert after == before  # COMPLETED survives byte for byte, runtime identity included
        assert after["state"] == "COMPLETED" and after["runtime"]["model_id"] == "MODEL_V2_FINAL"
        assert [s["session_id"] for s in client.get(f"{BASE}/sessions", headers=USER_A).json()] == [
            sid]
        assert client.get(f"{BASE}/devices", headers=USER_B).json() == []
        assert client.get(f"{BASE}/sessions/{sid}", headers=USER_B).status_code == 403
    after_counts = store2.row_counts()
    assert after_counts.pop("users") == counts.pop("users") + 1  # only user B authenticating above
    assert after_counts == counts  # nothing re-ran, nothing was regenerated on open
    entry = app2.state.runtime_state.devices[device]
    assert entry.source.connection_state is DeviceState.DETACHED
    assert entry.scenario_id == "CONTEXT_LOSS" and entry.source.scenario.scenario_id == "CONTEXT_LOSS"
    assert app2.state.recovery_report.recovered_sessions == []
    assert app2.state.recovery_report.restored_devices[0]["historical_connection_rows"] == 6  # 4 pre-stream + STREAM_STARTED/STOPPED
    assert app2.state.recovery_report.restored_devices[0]["last_historical_state"] == "STOPPED"
    history = store2.list_device_connections(device)
    assert history[-1]["device_state"] == "STOPPED"  # history keeps the LAST real event, not a fake


def test_a_restored_device_must_be_scanned_and_connected_again_and_ids_do_not_collide(
        tmp_path) -> None:
    path = tmp_path / "d.sqlite3"
    app1, store1 = make_persistent_app(path, StrictInferenceDouble())
    with TestClient(app1) as client:
        first, _ = provisioned_session(client, "POOR_SIGNAL")
    store1.close()
    app2, _ = make_persistent_app(path, StrictInferenceDouble(), ids=SeqIds("SESS-R"))
    with TestClient(app2) as client:
        assert client.post(f"{BASE}/sessions", json={"device_id": first,
                                                     "scenario_id": "POOR_SIGNAL"},
                           headers=USER_A).status_code == 409  # DETACHED: not usable yet
        assert client.post(f"{BASE}/devices/{first}/connect", headers=USER_A).status_code == 409
        assert client.post(f"{BASE}/devices/{first}/scan", headers=USER_A).json()[
            "connection_state"] == "FOUND"
        assert client.post(f"{BASE}/devices/{first}/connect", headers=USER_A).json()[
            "connection_state"] == "CONNECTED"
        created = client.post(f"{BASE}/sessions", json={"device_id": first,
                                                        "scenario_id": "POOR_SIGNAL"},
                              headers=USER_A)
        assert created.status_code == 200 and created.json()["simulation_provenance"][
            "scenario_id"] == "POOR_SIGNAL"  # the persisted scenario survived: no default
        second = client.post(f"{BASE}/devices/simulated", json={"scenario_id": "CONTEXT_LOSS"},
                             headers=USER_A).json()["device_id"]
        assert second != first
        history = [r["device_state"] for r in app2.state.store.list_device_connections(first)]
        assert history[-3:] == ["SCANNING", "FOUND", "PAIRING"] or "CONNECTED" in history


def test_stale_nonterminal_sessions_are_failed_not_resumed(tmp_path) -> None:
    path = tmp_path / "s.sqlite3"
    app1, store1 = make_persistent_app(path, StrictInferenceDouble(), ids=SeqIds("SESS-S"))
    with TestClient(app1) as client:
        _, ready = provisioned_session(client, "NORMAL_MONITORING")  # DEVICE_READY
        _, other = provisioned_session(client, "CONTEXT_LOSS")
        # simulate persisted nonterminal states left by a dead process (the REAL kill is below)
        from product.session import SessionState
        store1.update_session_state(other, SessionState.MONITORING, started_at_us=1)
        counts_before = store1.row_counts()
    store1.close()
    app2, store2 = make_persistent_app(path, StrictInferenceDouble())
    report = app2.state.recovery_report
    assert report.policy == POLICY
    assert {(r["session_id"], r["previous_state"]) for r in report.recovered_sessions} == {
        (ready, "DEVICE_READY"), (other, "MONITORING")}
    assert all(r["new_state"] == "FAILED" and r["reason"] ==
               "RESTART_RECOVERY_STALE_NONTERMINAL_SESSION" for r in report.recovered_sessions)
    for sid in (ready, other):
        session = store2.get_session(sid)
        assert session.state.value == "FAILED" and session.ended_at_us is not None
        assert sid not in app2.state.runtime_state.sessions  # not resumed in memory
    after = store2.row_counts()
    for table in ("inference_events", "context_snapshots", "monitoring_state_events",
                  "signal_quality_events", "waveform_previews"):
        assert after[table] == counts_before[table] == 0, table  # no fake continuation rows
    with TestClient(app2) as client:
        assert client.post(f"{BASE}/sessions/{other}/start", headers=USER_A).status_code == 409
    app3, store3 = make_persistent_app(path, StrictInferenceDouble())  # idempotent
    assert app3.state.recovery_report.recovered_sessions == []
    assert store3.get_session(other).state.value == "FAILED"


def test_the_recovery_policy_never_touches_terminal_sessions(tmp_path) -> None:
    store = CapstoneSqliteStore(tmp_path / "t.sqlite3")
    assert store.recover_stale_sessions(5) == []
    from product.devices.scenarios import TimingMode
    from product.monitoring.runtime_state import RuntimeState
    from product.persistence.recovery import recover
    report = recover(store, RuntimeState(), timing_mode=TimingMode.ACCELERATED)
    assert report.recovered_sessions == [] and report.restored_devices == []


# ---- a REAL killed process ----------------------------------------------------------------------
def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _product_process(db: str, inference_url: str, port: int, user: str = "demo:faculty"):
    env = {**os.environ, "PYTHONPATH": "src:.", "NHM_PRODUCT_AUTH_MODE": "DEMO",
           "NHM_PRODUCT_DEMO_AUTH_ACK": ACK, "NHM_PRODUCT_DEMO_USER_ID": user,
           "NHM_PRODUCT_DB_PATH": db, "NHM_PRODUCT_INFERENCE_URL": inference_url,
           "NHM_PRODUCT_TIMING_MODE": "LIVE_SPEED"}
    process = subprocess.Popen([sys.executable, "-m", "scripts.run_capstone_product", "--port",
                                str(port)], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}{BASE}/system", timeout=2).status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(0.3)
        if process.poll() is not None:
            raise RuntimeError("PRODUCT_PROCESS_EXITED")
    process.kill()
    raise RuntimeError("PRODUCT_PROCESS_LAUNCH_TIMEOUT")


def test_a_killed_product_process_leaves_a_stale_session_that_is_failed_not_resumed(
        tmp_path) -> None:
    db = str(tmp_path / "crash.sqlite3")
    with launch_released_inference() as (inference_url, _):
        port = _free_port()
        process = _product_process(db, inference_url, port)
        base = f"http://127.0.0.1:{port}{BASE}"
        try:
            device = httpx.post(f"{base}/devices/simulated",
                                json={"scenario_id": "NORMAL_MONITORING"}).json()["device_id"]
            httpx.post(f"{base}/devices/{device}/scan").raise_for_status()
            httpx.post(f"{base}/devices/{device}/connect").raise_for_status()
            sid = httpx.post(f"{base}/sessions", json={"device_id": device,
                                                       "scenario_id": "NORMAL_MONITORING"}
                             ).json()["session_id"]
            assert httpx.post(f"{base}/sessions/{sid}/start").json()["state"] == "MONITORING"
            for _ in range(200):  # LIVE_SPEED: wait until real monitoring evidence exists
                store = CapstoneSqliteStore(db)
                running = store.row_counts()["inference_events"] >= 1
                store.close()
                if running:
                    break
                time.sleep(0.5)
            assert running, "the live session never produced an inference row"
            assert httpx.get(f"{base}/sessions/{sid}").json()["state"] == "MONITORING"
        finally:
            process.send_signal(signal.SIGKILL)  # a crash: no graceful shutdown, no cleanup
            process.wait(timeout=20)
        store = CapstoneSqliteStore(db)
        crashed = store.get_session(sid)
        inference_at_crash = store.row_counts()["inference_events"]
        context_at_crash = store.row_counts()["context_snapshots"]
        store.close()
        assert crashed.state.value == "MONITORING" and crashed.ended_at_us is None
        time.sleep(3)  # nothing must advance the session while the product is down
        check = CapstoneSqliteStore(db)
        assert check.row_counts()["inference_events"] == inference_at_crash
        check.close()

        port2 = _free_port()
        process2 = _product_process(db, inference_url, port2)
        try:
            base2 = f"http://127.0.0.1:{port2}{BASE}"
            recovered = httpx.get(f"{base2}/sessions/{sid}").json()
            assert recovered["state"] == "FAILED" and recovered["ended_at_us"] is not None
            assert recovered["runtime"]["model_id"] == "MODEL_V2_FINAL"
            devices = httpx.get(f"{base2}/devices").json()
            assert [d["connection_state"] for d in devices] == ["DETACHED"]
            time.sleep(3)
            final = CapstoneSqliteStore(db)
            counts = final.row_counts()
            assert counts["inference_events"] == inference_at_crash  # no fake post-crash inference
            assert counts["context_snapshots"] == context_at_crash
            assert final.integrity_check() == ["ok"] and final.foreign_key_check() == []
            assert final.get_session(sid).state.value == "FAILED"
            final.close()
            assert json.loads(json.dumps(devices))[0]["device_id"] == device
        finally:
            process2.send_signal(signal.SIGTERM)
            try:
                process2.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process2.kill()
