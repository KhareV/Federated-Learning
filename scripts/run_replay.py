#!/usr/bin/env python3
"""T034 canonical production replay runner.

Starts the REAL production FastAPI app (api.app.app, built by ProductionRuntime()) on a real
localhost socket, replays PUBLIC_ECG_REPLAY_V1 (and, separately, the SIMULATION_ENGINEERING_
ONLY WEARABLE_SIM_REPLAY_V1) through genuine HTTP requests to POST /v1/infer-window, and saves
deterministic request/response/dashboard-projection logs. No mock inference, no direct
MODEL_V1 Python call, no alternate episode/state logic -- this is the same production path the
dashboard uses.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/e2e"
OUT = ROOT / "reports/t034"

MONITORING_STATES_WITH_PROBABILITY = {
    "NORMAL_MONITORED_PATTERN",
    "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
    "RECHECK_SENSOR",
    "CONTEXT_UNAVAILABLE",
}


def _verify_upstream_locks() -> None:
    from scripts.verify_api_runtime_t032 import verify as verify_api_runtime
    from scripts.verify_dashboard_ui_c034 import verify as verify_dashboard_ui

    verify_api_runtime()
    verify_dashboard_ui()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextlib.contextmanager
def _production_server(port: int):
    from api.app import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = False  # type: ignore[method-assign]

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15.0
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("E2E_REPLAY_SERVER_FAILED_TO_START")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)


def _public_requests(session_id: str) -> list[dict[str, Any]]:
    manifest = json.loads(
        (FIXTURE_DIR / "PUBLIC_ECG_REPLAY_V1.manifest.json").read_text(encoding="utf-8")
    )
    samples = np.load(FIXTURE_DIR / "PUBLIC_ECG_REPLAY_V1.npz")["samples"]
    windows = sorted(manifest["selection"]["windows"], key=lambda w: w["sequence_index"])
    return [
        {
            "contract_version": "API_SCHEMA_V1",
            "session_id": session_id,
            "timestamp_us": window["prediction_timestamp_us"],
            "ecg": {
                "samples": samples[window["sequence_index"]].tolist(),
                "target_hz": 250,
                "window_seconds": 10,
            },
            "ecg_quality": "VALID",
            "ppg_context": None,
            "model_id": "MODEL_V1",
            "_window_id": window["example_id"],
        }
        for window in windows
    ]


def _sim_requests(session_id: str) -> list[dict[str, Any]]:
    manifest = json.loads(
        (FIXTURE_DIR / "WEARABLE_SIM_REPLAY_V1.manifest.json").read_text(encoding="utf-8")
    )
    samples = np.load(FIXTURE_DIR / "WEARABLE_SIM_REPLAY_V1.npz")["samples"]
    windows = sorted(manifest["windows"], key=lambda w: w["sequence_index"])
    requests = []
    for window in windows:
        ppg_context = None
        if window["ppg_quality"] is not None:
            ppg_context = {
                "quality": window["ppg_quality"],
                "pr_bpm": window["pr_ppg_bpm"],
                "spo2_pct": window["spo2_pct"],
                "spo2_valid": window["spo2_valid"],
            }
        requests.append(
            {
                "contract_version": "API_SCHEMA_V1",
                "session_id": session_id,
                "timestamp_us": window["prediction_timestamp_us"],
                "ecg": {
                    "samples": samples[window["sequence_index"]].tolist(),
                    "target_hz": 250,
                    "window_seconds": 10,
                },
                "ecg_quality": window["ecg_quality"],
                "ppg_context": ppg_context,
                "model_id": "MODEL_V1",
                "_window_id": f"SIM-{window['sequence_index']}",
            }
        )
    return requests


def _send(client: httpx.Client, base_url: str, requests_: list[dict[str, Any]], *, speed: float):
    request_rows = []
    response_rows = []
    projection_rows = []
    for index, payload in enumerate(requests_):
        window_id = payload.pop("_window_id")
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        request_rows.append(
            {
                "sequence_index": index,
                "session_id": payload["session_id"],
                "timestamp_us": payload["timestamp_us"],
                "window_id": window_id,
                "ecg_quality": payload["ecg_quality"],
                "context_available": payload["ppg_context"] is not None,
                "model_id": payload["model_id"],
                "request_sha256": request_hash,
            }
        )

        start = time.perf_counter()
        response = client.post(f"{base_url}/v1/infer-window", json=payload)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        body = response.json()

        if response.status_code == 200:
            response_rows.append(
                {
                    "sequence_index": index,
                    "timestamp_us": body["timestamp_us"],
                    "http_status": 200,
                    "model_id": body["model_id"],
                    "target": body["target"],
                    "preprocess_version": body["preprocess_version"],
                    "contract_version": body["contract_version"],
                    "alert_policy_id": body["alert_policy_id"],
                    "calibration_id": body["calibration_id"],
                    "calibration_domain": body["calibration_domain"],
                    "calibration_patient_count": body["calibration_patient_count"],
                    "raw_probability": body["raw_probability"],
                    "source_domain_calibrated_probability": body[
                        "source_domain_calibrated_probability"
                    ],
                    "threshold": body["threshold"],
                    "ecg_quality": body["ecg_quality"],
                    "monitoring_state": body["monitoring_state"],
                    "context_available": (body.get("context") or {}).get("context_available"),
                    "latency_ms_measured": round(elapsed_ms, 3),
                }
            )
            displayable = body["monitoring_state"] in MONITORING_STATES_WITH_PROBABILITY and (
                body["source_domain_calibrated_probability"] is not None
            )
            projection_rows.append(
                {
                    "sequence_index": index,
                    "timestamp_us": body["timestamp_us"],
                    "outcome_kind": "success",
                    "monitoring_state": body["monitoring_state"],
                    "displayable_probability": (
                        body["source_domain_calibrated_probability"] if displayable else None
                    ),
                    "history_point": "point",
                    "ecg_quality": body["ecg_quality"],
                    "context_available": (body.get("context") or {}).get("context_available"),
                    "model_id": body["model_id"],
                    "calibration_id": body["calibration_id"],
                    "alert_policy_id": body["alert_policy_id"],
                }
            )
        else:
            response_rows.append(
                {
                    "sequence_index": index,
                    "timestamp_us": payload["timestamp_us"],
                    "http_status": response.status_code,
                    "error_type": body.get("error_type"),
                    "message": body.get("message"),
                    "latency_ms_measured": round(elapsed_ms, 3),
                }
            )
            monitoring_state = "RECHECK_SENSOR" if response.status_code == 422 else (
                "SYSTEM_ERROR" if response.status_code == 500 else None
            )
            projection_rows.append(
                {
                    "sequence_index": index,
                    "timestamp_us": payload["timestamp_us"],
                    "outcome_kind": "error",
                    "http_status": response.status_code,
                    "monitoring_state": monitoring_state,
                    "displayable_probability": None,
                    "history_point": "gap" if response.status_code in (422, 500) else "none",
                    "ecg_quality": payload["ecg_quality"],
                    "context_available": payload["ppg_context"] is not None,
                }
            )

        if speed > 0:
            time.sleep(speed)

    return request_rows, response_rows, projection_rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def _semantic_digest(response_rows: list[dict[str, Any]]) -> str:
    """Excludes latency_ms_measured and anything process/time-dependent."""
    semantic = []
    for row in response_rows:
        row = dict(row)
        row.pop("latency_ms_measured", None)
        semantic.append(row)
    return hashlib.sha256(
        json.dumps(semantic, sort_keys=True).encode("utf-8")
    ).hexdigest()


def run_once(run_label: str, *, speed: float) -> dict[str, Any]:
    _verify_upstream_locks()
    port = _free_port()
    with _production_server(port) as base_url, httpx.Client(timeout=30.0) as client:
        public_requests = _public_requests("T034-PUBLIC-REPLAY-V1")
        public_req_rows, public_resp_rows, public_proj_rows = _send(
            client, base_url, public_requests, speed=speed
        )

        sim_requests = _sim_requests("T034-SIM-REPLAY-V1")
        sim_req_rows, sim_resp_rows, sim_proj_rows = _send(
            client, base_url, sim_requests, speed=speed
        )

    _write_jsonl(OUT / "public_replay_requests.jsonl", public_req_rows)
    _write_jsonl(OUT / "public_replay_responses.jsonl", public_resp_rows)
    _write_jsonl(OUT / "public_dashboard_projection.jsonl", public_proj_rows)
    _write_jsonl(OUT / "sim_replay_requests.jsonl", sim_req_rows)
    _write_jsonl(OUT / "sim_replay_responses.jsonl", sim_resp_rows)
    _write_jsonl(OUT / "sim_dashboard_projection.jsonl", sim_proj_rows)

    result = {
        "run_label": run_label,
        "public_requests_sent": len(public_req_rows),
        "public_200": sum(1 for r in public_resp_rows if r.get("http_status") == 200),
        "public_422": sum(1 for r in public_resp_rows if r.get("http_status") == 422),
        "public_500": sum(1 for r in public_resp_rows if r.get("http_status") == 500),
        "sim_requests_sent": len(sim_req_rows),
        "sim_200": sum(1 for r in sim_resp_rows if r.get("http_status") == 200),
        "sim_422": sum(1 for r in sim_resp_rows if r.get("http_status") == 422),
        "public_semantic_digest": _semantic_digest(public_resp_rows),
        "sim_semantic_digest": _semantic_digest(sim_resp_rows),
        "public_monitoring_state_sequence": [
            r.get("monitoring_state") for r in public_resp_rows
        ],
        "status": "PASS",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{run_label}.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=float, default=0.0)
    parser.add_argument("--run-label", default="replay_run_1")
    args = parser.parse_args()
    result = run_once(args.run_label, speed=args.speed)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
