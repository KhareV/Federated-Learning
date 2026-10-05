# ruff: noqa: E501
"""CAP-004 canonical persistent end-to-end run (separate processes, real inference, real SQLite).

    PYTHONPATH=src:. python scripts/run_capstone_persistent_e2e.py run   <N>   # canonical + restart + ownership
    PYTHONPATH=src:. python scripts/run_capstone_persistent_e2e.py crash       # killed-process recovery

Processes: (1) a FRESH released SOFTWARE_SYSTEM_V2 inference service (`scripts.run_nhm_default`);
(2) the CAP-004 product API (`scripts.run_capstone_product`) in explicit DEMO mode against a temporary
SQLite file; (3) after it is stopped, a SECOND product process on the SAME database (restart), and a
THIRD with a different demo user (ownership). The harness talks to the product ONLY over HTTP and
WebSocket. No mock, no scripted probabilities, no SimulationTruth, no FL, no frontend.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from capstone_persistence.store import CapstoneSqliteStore
from product.contracts import load_contract
from product.devices.replay import canonical_json
from product.persistence import preview as preview_module
from scripts.run_capstone_monitoring_e2e import launch_released_inference

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_004"
BASE = "/product/v1"
ACK = load_contract("auth_policy")["demo_provider"]["acknowledgement_value"]
CAP003_STREAM = ROOT / "reports/capstone/cap_003/canonical_event_stream_run_1.jsonl"
CAP003_RUN = ROOT / "reports/capstone/cap_003/canonical_e2e_run_1.json"
SCENARIO = "MIXED_MONITORING_SESSION"
PREDECLARED = {"windows": 93, "valid": 86, "unusable": 7, "attempts": 93, "http_200": 86,
               "http_422": 7, "model_id": "MODEL_V2_FINAL", "calibration_id": "CAL_V2",
               "terminal": "COMPLETED"}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def product_process(db: str, inference_url: str, *, user: str = "demo:faculty",
                    timing: str = "ACCELERATED"):
    port = free_port()
    env = {**os.environ, "PYTHONPATH": "src:.", "NHM_PRODUCT_AUTH_MODE": "DEMO",
           "NHM_PRODUCT_DEMO_AUTH_ACK": ACK, "NHM_PRODUCT_DEMO_USER_ID": user,
           "NHM_PRODUCT_DB_PATH": db, "NHM_PRODUCT_INFERENCE_URL": inference_url,
           "NHM_PRODUCT_TIMING_MODE": timing}
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_capstone_product", "--port", str(port)], cwd=ROOT,
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.monotonic() + 120
    try:
        while True:
            if process.poll() is not None:
                raise RuntimeError("PRODUCT_PROCESS_EXITED")
            try:
                if httpx.get(f"http://127.0.0.1:{port}{BASE}/system", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise RuntimeError("PRODUCT_PROCESS_LAUNCH_TIMEOUT") from None
                time.sleep(0.3)
        yield f"http://127.0.0.1:{port}{BASE}", f"ws://127.0.0.1:{port}{BASE}", process.pid, port
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def ws_close_code(url: str) -> int | None:
    with connect(url, open_timeout=10, close_timeout=5) as ws:
        try:
            ws.recv(timeout=15)
        except ConnectionClosed as closed:
            return closed.rcvd.code if closed.rcvd else None
    return None


def project(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PROJECTION_V1 (frozen before execution): drop ONLY the session identity (session_id, the
    session-derived event_id) and the wall-clock latency_ms. Every scientific value is kept."""
    projected = []
    for event in events:
        clean = json.loads(json.dumps(event))
        clean["session_id"] = "S"
        clean["event_id"] = f"S-PEV{clean['sequence_index']:06d}"
        if clean["event_type"] == "inference.result":
            clean["payload"]["latency_ms"] = None
        projected.append(clean)
    return projected


def db_evidence(db: str) -> dict[str, Any]:
    store = CapstoneSqliteStore(db)
    try:
        counts = store.row_counts()
        sessions = store.rows("monitoring_sessions")
        inference = store.rows("inference_events")
        snapshots = {r["timestamp_us"]: r for r in store.rows("context_snapshots")}
        raw = {r["timestamp_us"]: json.loads(r["context_json"]) for r in inference}
        withheld = [t for t, c in raw.items() if not c["context_available"] and any(
            c.get(k) not in (None, False) for k in ("pr_ppg_bpm", "spo2_pct", "spo2_valid"))]
        preview = store.rows("waveform_previews")
        points = preview_module.decode(preview[0]["data"]) if preview else []
        quality = store.rows("signal_quality_events")
        dump = [line for line in store._connection.iterdump()]
        result = {
            "pragmas": {"foreign_keys": store.pragma("foreign_keys"),
                        "journal_mode": store.pragma("journal_mode"),
                        "user_version": store.pragma("user_version")},
            "integrity_check": store.integrity_check(), "foreign_key_check": store.foreign_key_check(),
            "tables": store.table_names(), "row_counts": counts,
            "inference_models": sorted({r["model_id"] for r in inference}),
            "raw_context_rows": len(raw), "product_context_rows": len(snapshots),
            "withheld_context_cases": len(withheld), "withheld_timestamps": withheld,
            "withheld_raw_has_ppg_values": all(
                raw[t]["pr_ppg_bpm"] is not None or raw[t]["spo2_pct"] is not None for t in withheld),
            "withheld_product_values_null": all(
                snapshots[t]["pr_ppg_bpm"] is None and snapshots[t]["spo2_pct"] is None
                and snapshots[t]["context_available"] == 0 for t in withheld),
            "quality_rows": len(quality),
            "quality_change_sequence": [(r["ecg_quality"], r["ppg_quality"]) for r in quality],
            "waveform_preview": ({k: v for k, v in preview[0].items() if k != "data"} | {
                "blob_bytes": len(preview[0]["data"]), "null_points": sum(
                    1 for p in points if p is None), "decoded_points": len(points)}
                                 if preview else None),
            "sessions": [{k: s[k] for k in ("session_id", "user_id", "device_id", "state",
                                            "scenario_id", "model_id", "calibration_id",
                                            "preprocess_id", "alert_policy_id",
                                            "alert_policy_binding_id", "gateway_artifact_id",
                                            "api_contract_version", "software_system_id")}
                         for s in sessions],
            "users": [{k: u[k] for k in ("user_id", "auth_provider", "display_name", "demo_mode")}
                      for u in store.rows("users")],
            "devices": [{k: d[k] for k in ("device_id", "user_id", "scenario_id", "adapter_type")}
                        for d in store.rows("devices")],
            "schema_sql": store.schema_dump(),
            "schema_sha256": hashlib.sha256("\n".join(store.schema_dump()).encode()).hexdigest(),
            "credential_strings_in_database": [w for w in ("Bearer", "token", "secret", "password")
                                               if any(w.lower() in line.lower()
                                                      for line in dump if line.startswith("INSERT"))],
        }
        return result
    finally:
        store.close()


def run_canonical(run_number: int) -> dict[str, Any]:
    cap003_stream = [json.loads(line) for line in CAP003_STREAM.read_text().splitlines()]
    cap003_run = json.loads(CAP003_RUN.read_text())["summary"]
    with tempfile.TemporaryDirectory(prefix="cap004-e2e-") as tmp, launch_released_inference() as (
            inference_url, inference_info):
        db = os.path.join(tmp, "product.sqlite3")
        proc1: dict[str, Any] = {"process": 1}
        with product_process(db, inference_url) as (base, ws_base, pid1, _):
            system = httpx.get(f"{base}/system").json()
            me = httpx.get(f"{base}/me").json()
            device = httpx.post(f"{base}/devices/simulated", json={"scenario_id": SCENARIO}).json()
            device_id = device["device_id"]
            scan = httpx.post(f"{base}/devices/{device_id}/scan").json()
            connect_ = httpx.post(f"{base}/devices/{device_id}/connect").json()
            created = httpx.post(f"{base}/sessions", json={"device_id": device_id,
                                                           "scenario_id": SCENARIO})
            created.raise_for_status()
            session_id = created.json()["session_id"]
            listed = httpx.get(f"{base}/sessions").json()
            fetched = httpx.get(f"{base}/sessions/{session_id}").json()
            events: list[dict[str, Any]] = []
            with connect(f"{ws_base}/sessions/{session_id}/live", open_timeout=10,
                         close_timeout=5) as ws:
                started = httpx.post(f"{base}/sessions/{session_id}/start")
                started.raise_for_status()
                while True:
                    try:
                        events.append(json.loads(ws.recv(timeout=300)))
                    except ConnectionClosed:
                        break
            final = httpx.get(f"{base}/sessions/{session_id}").json()
            late_start = httpx.post(f"{base}/sessions/{session_id}/start").status_code
            proc1.update(system=system, me=me, device_created=device, scan_state=scan[
                "connection_state"], connect_state=connect_["connection_state"],
                         session_created=created.json(), session_list_ids=[
                             s["session_id"] for s in listed], session_get_state=fetched["state"],
                         start_response_state=started.json()["state"], final_session=final,
                         late_start_status=late_start, pid_excluded=pid1)
        db1 = db_evidence(db)
        with product_process(db, inference_url) as (base2, ws_base2, pid2, _):
            proc2 = {
                "process": 2, "me": httpx.get(f"{base2}/me").json(),
                "system": httpx.get(f"{base2}/system").json(),
                "devices": httpx.get(f"{base2}/devices").json(),
                "sessions": httpx.get(f"{base2}/sessions").json(),
                "session": httpx.get(f"{base2}/sessions/{session_id}").json(),
                "late_start_status": httpx.post(f"{base2}/sessions/{session_id}/start").status_code,
                "websocket_close_code_for_past_process_session": ws_close_code(
                    f"{ws_base2}/sessions/{session_id}/live"), "pid_excluded": pid2}
        db2 = db_evidence(db)
        with product_process(db, inference_url, user="demo:other") as (base3, ws_base3, pid3, _):
            ownership = {
                "other_user": httpx.get(f"{base3}/me").json()["user_id"],
                "devices_listed": httpx.get(f"{base3}/devices").json(),
                "sessions_listed": httpx.get(f"{base3}/sessions").json(),
                "get_session_status": httpx.get(f"{base3}/sessions/{session_id}").status_code,
                "start_status": httpx.post(f"{base3}/sessions/{session_id}/start").status_code,
                "scan_other_users_device_status": httpx.post(
                    f"{base3}/devices/{device_id}/scan").status_code,
                "websocket_close_code": ws_close_code(f"{ws_base3}/sessions/{session_id}/live"),
                "unknown_session_status": httpx.get(f"{base3}/sessions/NOPE").status_code,
                "pid_excluded": pid3}
    projected = project(events)
    reference = project(cap003_stream)
    quality = [e["payload"]["ecg_quality"] for e in events if e["event_type"] == "quality.status"]
    inference = [e for e in events if e["event_type"] == "inference.result"]
    statuses = [e["payload"]["session_state"] for e in events if e["event_type"] == "session.status"]
    devices = [e["payload"]["device_state"] for e in events if e["event_type"] == "device.status"]
    changes = [e["payload"]["monitoring_state"] for e in events if e["event_type"] == "monitoring.state"]
    stream = hashlib.sha256()
    for event in projected:
        stream.update(canonical_json(event) + b"\n")
    comparison = {
        "event_count_equal": len(projected) == len(reference),
        "full_projected_stream_identical_to_cap003_canonical_run_1": projected == reference,
        "kind_order_equal": [e["event_type"] for e in projected] == [
            e["event_type"] for e in reference],
        "device_states_equal": devices == cap003_run["device_state_sequence"],
        "session_states_equal": statuses == cap003_run["session_state_sequence"],
        "quality_sequence_equal": quality == [w["ecg_quality"] for w in cap003_run["windows"]],
        "monitoring_state_changes_equal": changes == cap003_run["monitoring_state_change_events"],
        "window_timestamps_equal": [e["source_timestamp_us"] for e in events
                                    if e["event_type"] == "quality.status"] == [
            w["timestamp_us"] for w in cap003_run["windows"]],
        "waveform_null_interval_equal": cap003_run["waveform"]["null_intervals"] == [
            [118800, 124199]],
        "model_calibration_equal": sorted({e["payload"]["model_id"] for e in inference}) == [
            "MODEL_V2_FINAL"] and sorted({e["payload"]["calibration_id"] for e in inference}) == [
            "CAL_V2"],
        "raw_and_calibrated_probabilities_equal": [
            (e["payload"]["raw_probability"], e["payload"]["source_domain_calibrated_probability"])
            for e in inference] == [
            (w["raw_probability"], w["calibrated_probability"]) for w in cap003_run["windows"]
            if w["http_status"] == 200],
        "cap003_context_values_withheld": cap003_run["context_values_withheld"],
        "cap004_withheld_cases_in_database": db1["withheld_context_cases"],
    }
    return {
        "run": run_number, "auth_mode": "DEMO (explicit, acknowledged)", "database": "temporary real SQLite file",
        "inference_service": {k: v for k, v in inference_info.items() if k not in ("pid", "port")},
        "product_process_separate": True, "inference_process_separate": True,
        "predeclared_invariants": PREDECLARED, "projection": "PROJECTION_V1",
        "process_1": proc1, "process_2": proc2, "ownership_process_3": ownership,
        "database_after_process_1": db1, "database_after_restart": db2,
        "observed": {"windows": len(quality), "valid": quality.count("VALID"),
                     "unusable": quality.count("UNUSABLE"), "inference_results": len(inference),
                     "http_200_equiv": len(inference), "http_422_equiv": len(quality) - len(inference),
                     "attempts_equiv": len(quality), "terminal_session_state": proc1[
                         "final_session"]["state"], "session_state_sequence": statuses,
                     "device_state_sequence": devices, "event_count": len(events),
                     "sequence_contiguous": [e["sequence_index"] for e in events] == list(
                         range(len(events)))},
        "noninterference": comparison, "projected_event_stream_sha256": stream.hexdigest(),
        "_events": events,
    }


def run_crash() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cap004-crash-") as tmp, launch_released_inference() as (
            inference_url, _):
        db = os.path.join(tmp, "crash.sqlite3")
        before: dict[str, Any] = {}
        process = None
        with contextlib.ExitStack() as stack:
            base, _ws, _pid, _ = stack.enter_context(
                product_process(db, inference_url, timing="LIVE_SPEED"))
            device_id = httpx.post(f"{base}/devices/simulated",
                                   json={"scenario_id": "NORMAL_MONITORING"}).json()["device_id"]
            httpx.post(f"{base}/devices/{device_id}/scan").raise_for_status()
            httpx.post(f"{base}/devices/{device_id}/connect").raise_for_status()
            session_id = httpx.post(f"{base}/sessions", json={
                "device_id": device_id, "scenario_id": "NORMAL_MONITORING"}).json()["session_id"]
            httpx.post(f"{base}/sessions/{session_id}/start").raise_for_status()
            for _ in range(240):
                store = CapstoneSqliteStore(db)
                inference_rows = store.row_counts()["inference_events"]
                store.close()
                if inference_rows >= 1:
                    break
                time.sleep(0.5)
            before = {"session_state_via_api": httpx.get(f"{base}/sessions/{session_id}").json()[
                "state"], "inference_rows": inference_rows}
            # CRASH: hard-kill the product process (the context manager then finds it dead)
            for proc in subprocess.run(["pgrep", "-f", "scripts.run_capstone_product"],
                                       capture_output=True, text=True).stdout.split():
                with contextlib.suppress(ProcessLookupError):
                    os.kill(int(proc), signal.SIGKILL)
            time.sleep(1)
        store = CapstoneSqliteStore(db)
        at_crash = {"session_state": store.get_session(session_id).state.value,
                    "counts": store.row_counts()}
        store.close()
        time.sleep(4)  # the dead product must not advance anything
        store = CapstoneSqliteStore(db)
        still = store.row_counts()
        store.close()
        with product_process(db, inference_url) as (base2, _ws2, _pid2, _):
            recovered = httpx.get(f"{base2}/sessions/{session_id}").json()
            devices = httpx.get(f"{base2}/devices").json()
            time.sleep(4)
        final = db_evidence(db)
        del process
        return {
            "auth_mode": "DEMO", "database": "temporary real SQLite file",
            "timing_mode": "LIVE_SPEED (engineering: keeps a session in flight long enough to crash)",
            "before_crash": before, "at_crash_database": at_crash,
            "database_unchanged_while_product_down": still == at_crash["counts"],
            "recovered_session": recovered, "devices_after_restart": [
                {k: d[k] for k in ("device_id", "connection_state")} for d in devices],
            "database_after_recovery": {k: final[k] for k in (
                "row_counts", "integrity_check", "foreign_key_check", "sessions")},
            "stale_session_failed_not_resumed": recovered["state"] == "FAILED",
            "no_fake_post_crash_inference": final["row_counts"]["inference_events"] == at_crash[
                "counts"]["inference_events"],
            "no_fake_post_crash_context": final["row_counts"]["context_snapshots"] == at_crash[
                "counts"]["context_snapshots"],
            "devices_detached": all(d["connection_state"] == "DETACHED" for d in devices),
            "engineering_evidence_only": True,
        }


def main() -> None:
    mode = sys.argv[1]
    if mode == "run":
        number = int(sys.argv[2])
        result = run_canonical(number)
        events = result.pop("_events")
        (OUT / f"canonical_persistent_e2e_run_{number}.json").write_text(
            json.dumps(result, indent=1, sort_keys=True, default=str) + "\n")
        with (OUT / f"canonical_event_stream_run_{number}.jsonl").open("w") as handle:
            for event in project(events):
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        print(json.dumps({"run": number, "observed": result["observed"],
                          "noninterference_identical": result["noninterference"][
                              "full_projected_stream_identical_to_cap003_canonical_run_1"]}))
    elif mode == "crash":
        result = run_crash()
        (OUT / "crash_recovery.json").write_text(
            json.dumps(result, indent=1, sort_keys=True, default=str) + "\n")
        print(json.dumps({k: result[k] for k in ("stale_session_failed_not_resumed",
                                                 "no_fake_post_crash_inference",
                                                 "devices_detached")}))
    else:
        raise SystemExit("usage: run <N> | crash")


if __name__ == "__main__":
    main()
