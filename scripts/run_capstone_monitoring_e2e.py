"""CAP-003 canonical end-to-end monitoring run against a FRESH, REAL released inference process.

    PYTHONPATH=src:. python scripts/run_capstone_monitoring_e2e.py run <N>

Path: actual CAP-002 virtual device -> VirtualEdgeNode -> CAP-003 coordinator -> unchanged
WearableStreamRuntime -> HTTP -> fresh `python -m scripts.run_nhm_default` (SOFTWARE_SYSTEM_V2,
MODEL_V2_FINAL) -> product events -> monitoring WebSocket. No mock model, no scripted probabilities.

The product FastAPI app runs IN-PROCESS (TestClient): CAP-003 has no production auth provider, so
the CAP003_TEST_IDENTITY_ONLY resolver and the Python-only session seeding live in this process.
Inference is ALWAYS a fresh real localhost process. Wall-clock, latency_ms, pid and port are never
part of the semantic digest.
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
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.product_app import create_product_app
from product.devices.replay import canonical_json
from product.inference.client import CapstoneInferenceClient
from product.monitoring.runtime_state import RuntimeState, seed_engineering_session
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver, headers_for

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_003"
BASE = "/product/v1"
USER = headers_for("e2e-user")
CANONICAL_SCENARIO = "MIXED_MONITORING_SESSION"
PREDECLARED = {"windows": 93, "valid": 86, "unusable": 7, "attempts": 93, "http_200": 86,
               "http_422": 7, "terminal_session_state": "COMPLETED",
               "successful_model_ids": ["MODEL_V2_FINAL"], "successful_calibration_ids": ["CAL_V2"]}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def launch_released_inference(timeout: float = 300.0):
    """Start a fresh `scripts.run_nhm_default` (SOFTWARE_SYSTEM_V2) process; yield (url, info)."""
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_nhm_default", "--port", str(port)], cwd=ROOT,
        env={**os.environ, "PYTHONPATH": "src:."}, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + timeout
        spec = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("RELEASED_INFERENCE_PROCESS_EXITED")
            try:
                spec = httpx.get(f"{base}/openapi.json", timeout=2.0).json()
                break
            except (httpx.HTTPError, ValueError):
                time.sleep(0.5)
        if spec is None:
            raise RuntimeError("RELEASED_INFERENCE_LAUNCH_TIMEOUT")
        title = spec["info"]["title"]
        if "SOFTWARE_SYSTEM_V2 default binding" not in title:
            raise RuntimeError(f"NOT_THE_RELEASED_DEFAULT_SERVICE:{title}")
        yield base, {"launcher": "python -m scripts.run_nhm_default", "profile": "default",
                     "service_title": title, "paths": sorted(spec["paths"]), "pid": process.pid,
                     "port": port, "fresh_process": True}
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def run_session(scenario_id: str, base_url: str, session_id: str) -> dict[str, Any]:
    """Drive one full monitoring session through the real REST + WebSocket surface."""
    state = RuntimeState()
    holder: dict[str, CapstoneInferenceClient] = {}

    def factory() -> CapstoneInferenceClient:
        holder["client"] = CapstoneInferenceClient(base_url)
        return holder["client"]

    app = create_product_app(identity_resolver=cap003_test_identity_resolver, state=state,
                             inference_client_factory=factory)
    events: list[dict[str, Any]] = []
    with TestClient(app) as client:
        device = client.post(f"{BASE}/devices/simulated", json={"scenario_id": scenario_id},
                             headers=USER).json()
        device_id = device["device_id"]
        client.post(f"{BASE}/devices/{device_id}/scan", headers=USER).raise_for_status()
        client.post(f"{BASE}/devices/{device_id}/connect", headers=USER).raise_for_status()
        owner = state.devices[device_id].owner_user_id
        seed_engineering_session(state, owner_user_id=owner, device_id=device_id,
                                 session_id=session_id)
        started = client.post(f"{BASE}/sessions/{session_id}/start", headers=USER)
        started.raise_for_status()
        with client.websocket_connect(f"{BASE}/sessions/{session_id}/live", headers=USER) as ws:
            while True:
                try:
                    events.append(ws.receive_json())
                except WebSocketDisconnect:
                    break
        late_stop = client.post(f"{BASE}/sessions/{session_id}/stop", headers=USER)
    entry = state.sessions[session_id]
    coordinator = entry.coordinator
    return {
        "scenario_id": scenario_id, "session_id": session_id, "device_id": device_id,
        "start_response_state": started.json()["state"], "session": json.loads(
            entry.session.model_dump_json()), "events": events,
        "telemetry": coordinator.telemetry, "scientific_trace": coordinator.scientific_trace,
        "inference_attempts": holder["client"].attempts, "late_stop_status": late_stop.status_code,
    }


def _strip_volatile(event: dict[str, Any]) -> dict[str, Any]:
    clean = json.loads(json.dumps(event))
    if clean["event_type"] == "inference.result":
        clean["payload"]["latency_ms"] = None  # wall-clock measurement: excluded
    return clean


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    events = [_strip_volatile(e) for e in result["events"]]
    telemetry = result["telemetry"]
    windows = telemetry["windows"]
    ok = [w for w in windows if w["http_status"] == 200]
    kinds: dict[str, int] = {}
    for event in events:
        kinds[event["event_type"]] = kinds.get(event["event_type"], 0) + 1
    chunks = [e["payload"] for e in events if e["event_type"] == "waveform.chunk"]
    session_events = [e["payload"]["session_state"] for e in events
                      if e["event_type"] == "session.status"]
    return {
        "scenario_id": result["scenario_id"], "session_runtime_identity": result["session"][
            "runtime"], "simulation_provenance": result["session"]["simulation_provenance"],
        "device_state_sequence": telemetry["device_states"],
        "session_state_sequence": session_events,
        "terminal_session_state": result["session"]["state"],
        "windows": [{k: v for k, v in w.items()} for w in windows],
        "http_status_sequence": telemetry["http_statuses"],
        "http_status_counts": {str(s): telemetry["http_statuses"].count(s)
                               for s in sorted(set(telemetry["http_statuses"]))},
        "successful_model_ids": sorted({w["model_id"] for w in ok}),
        "successful_calibration_ids": sorted({w["calibration_id"] for w in ok}),
        "monitoring_state_sequence_from_responses": [w["monitoring_state"] for w in ok],
        "monitoring_state_change_events": telemetry["monitoring_states"],
        "context_availability_sequence": telemetry["context_availability"],
        "product_event_kind_counts": kinds,
        "product_event_kind_order_sha256": hashlib.sha256(canonical_json(
            [e["event_type"] for e in events])).hexdigest(),
        "waveform": {"chunk_count": len(chunks), "samples_covered": sum(
            c["sample_count"] for c in chunks), "first_sample_indices_contiguous": [
            c["first_sample_index"] for c in chunks] == [
            i * 60 for i in range(len(chunks))], "null_intervals": telemetry[
            "waveform_null_intervals"], "chunk_sample_count": sorted({c["sample_count"]
                                                                      for c in chunks}),
            "channels": sorted({c["channel"] for c in chunks}), "units": sorted(
                {c["unit"] for c in chunks}), "rate_hz": sorted({c["source_rate_hz"]
                                                                 for c in chunks})},
        "scientific_trace": result["scientific_trace"],
        "context_values_withheld": telemetry["context_values_withheld"],
        "discarded_future_events": telemetry["discarded_future_events"],
        "sequence_contiguous": [e["sequence_index"] for e in events] == list(range(len(events))),
        "event_count": len(events),
        "claims": {"physical_hardware_used": False, "simulation_truth_used": False,
                   "fl_training_used": False, "mock_model_used": False,
                   "model_efficacy_claimed": False,
                   "note": "systems/product integration evidence; not clinical evidence"},
    }


def semantic_digest(result: dict[str, Any]) -> tuple[str, str]:
    summary = summarize(result)
    stream = hashlib.sha256()
    for event in result["events"]:
        stream.update(canonical_json(_strip_volatile(event)) + b"\n")
    digest = hashlib.sha256(canonical_json({"summary": summary,
                                            "event_stream_sha256": stream.hexdigest()}))
    return digest.hexdigest(), stream.hexdigest()


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] != "run":
        raise SystemExit("usage: run_capstone_monitoring_e2e.py run <N>")
    run = int(sys.argv[2])
    started = time.monotonic()
    with launch_released_inference() as (base, info):
        result = run_session(CANONICAL_SCENARIO, base, f"CAP003-E2E-{CANONICAL_SCENARIO}")
    digest, stream_digest = semantic_digest(result)
    summary = summarize(result)
    payload = {
        "run": run,
        "inference_service": {k: v for k, v in info.items() if k not in ("pid", "port")},
        "inference_service_volatile_excluded_from_digest": ["pid", "port"],
        "product_runtime": {"in_process": True, "reason": "no production auth in CAP-003; the "
                            "CAP003_TEST_IDENTITY_ONLY resolver and Python-only session seeding "
                            "must be in-process", "persistence": "EPHEMERAL_CAP003",
                            "app": "api.product_app:create_product_app"},
        "predeclared_invariants": PREDECLARED, "summary": summary,
        "semantic_digest": digest, "event_stream_sha256": stream_digest,
        "late_stop_status": result["late_stop_status"],
        "excluded_from_digest": ["wall-clock", "latency_ms", "pid", "port", "temp paths",
                                 "OS scheduling"]}
    (OUT / f"canonical_e2e_run_{run}.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")
    with (OUT / f"canonical_event_stream_run_{run}.jsonl").open("w") as handle:
        for event in result["events"]:
            handle.write(json.dumps(_strip_volatile(event), sort_keys=True) + "\n")
    print(json.dumps({"run": run, "semantic_digest": digest, "events": len(result["events"]),
                      "http": summary["http_status_counts"],
                      "wall_seconds_not_recorded": round(time.monotonic() - started, 1)}))


if __name__ == "__main__":
    main()
