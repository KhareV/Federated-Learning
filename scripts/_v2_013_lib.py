"""V2-013 shared harness: fresh-process API launchers, canonical semantic digest, the
deterministic synthetic API-input corpus, and the independent (non-importing-the-runtime)
reference pipeline. No dataset access, no model scoring beyond the frozen gateway artifact on
committed synthetic fixtures, no scientific metric."""

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
import urllib.request
from pathlib import Path
from typing import Any

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("V2_013_OUT", str(ROOT / "reports/model_v2/v2_013")))
REPLAY_BUNDLE = ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json"
ROUTE = "/v1/infer-window"
V2_MODEL_ID = "MODEL_V2_FINAL"
V1_MODEL_ID = "MODEL_V1"

SEMANTIC_RESPONSE_FIELDS = (
    "contract_version", "timestamp_us", "model_id", "target", "raw_probability",
    "source_domain_calibrated_probability", "calibration_domain", "calibration_patient_count",
    "calibration_id", "threshold", "ecg_quality", "monitoring_state", "context",
    "preprocess_version", "alert_policy_id",
)
EXCLUDED_FROM_DIGEST = ("latency_ms", "session_id", "wall_clock_time", "process_id")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


@contextlib.contextmanager
def launch_api(profile: str, *, port: int | None = None, timeout: float = 180.0):
    """Start a FRESH API process. profile 'v1' = the normal operational default launch command
    (`uvicorn api.app:app`); profile 'v2' = the explicit research profile
    (`uvicorn --factory api.app_v2:create_default_research_app`). Yields (base_url, pid)."""
    port = port or free_port()
    if profile == "v1":
        target = ["api.app:app"]
    elif profile == "v2":
        target = ["--factory", "api.app_v2:create_default_research_app"]
    else:
        raise ValueError(profile)
    cmd = [sys.executable, "-m", "uvicorn", *target, "--host", "127.0.0.1", "--port", str(port),
           "--log-level", "warning"]
    process = subprocess.Popen(cmd, cwd=ROOT, env={**os.environ, "PYTHONPATH": "src:."},
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        base = f"http://127.0.0.1:{port}"
        if not _wait(f"{base}/openapi.json", timeout):
            raise RuntimeError(f"V2_013_API_FAILED_TO_START:{profile}")
        yield base, process.pid
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def request_body(session_id: str, timestamp_us: int, samples: list[float], *, quality: str,
                 model_id: str, ppg_context: dict | None = None) -> dict[str, Any]:
    return {
        "contract_version": "API_SCHEMA_V1", "session_id": session_id,
        "timestamp_us": timestamp_us,
        "ecg": {"samples": samples, "target_hz": 250, "window_seconds": 10},
        "ecg_quality": quality, "ppg_context": ppg_context, "model_id": model_id,
    }


def post(client: httpx.Client, base: str, body: dict) -> tuple[int, dict]:
    response = client.post(f"{base}{ROUTE}", json=body, timeout=60.0)
    return response.status_code, response.json()


# ---------------------------------------------------------------------------------------------
# Canonical semantic digest
# ---------------------------------------------------------------------------------------------


def samples_sha256(samples: list[float]) -> str:
    return hashlib.sha256(np.asarray(samples, dtype=np.float64).tobytes()).hexdigest()


def semantic_row(event: dict, status: int, body: dict) -> dict[str, Any]:
    ok = status == 200
    return {
        "sequence_index": event["sequence_index"],
        "window_id": event["window_id"],
        "timestamp_us": event["timestamp_us"],
        "request_ecg_quality": event["ecg_quality"],
        "request_model_id": event["model_id"],
        "ecg_samples_sha256": samples_sha256(event["ecg"]["samples"]),
        "http_status": status,
        "response": {k: body[k] for k in SEMANTIC_RESPONSE_FIELDS} if ok else None,
        "error": None if ok else {"error_type": body.get("error_type"),
                                  "message": body.get("message"),
                                  "status_code": body.get("status_code")},
    }


def episode_transitions(rows: list[dict]) -> list[dict]:
    transitions, previous = [], None
    for row in rows:
        state = row["response"]["monitoring_state"] if row["response"] else None
        if state is None:
            continue
        if state == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN" and previous != state:
            transitions.append(
                {"timestamp_us": row["timestamp_us"], "event": "EPISODE_OPEN_OBSERVED"})
        elif previous == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN" and state != previous:
            transitions.append({"timestamp_us": row["timestamp_us"],
                                "event": f"LEFT_EPISODE_STATE_TO_{state}"})
        previous = state
    return transitions


def _numeric_canonical(value: Any) -> Any:
    """JSON number spelling is language-dependent (JS prints 70.0 as 70). Every non-bool number is
    canonicalized to float so the digest depends on values, never on serializer spelling."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, list):
        return [_numeric_canonical(v) for v in value]
    if isinstance(value, dict):
        return {k: _numeric_canonical(v) for k, v in value.items()}
    return value


def canonical_digest(rows: list[dict]) -> dict[str, Any]:
    rows = _numeric_canonical(rows)
    payload = {"fields_included": [
        *SEMANTIC_RESPONSE_FIELDS, "sequence_index", "window_id", "timestamp_us",
        "request_ecg_quality", "request_model_id", "ecg_samples_sha256", "http_status", "error"],
        "excluded": list(EXCLUDED_FROM_DIGEST),
        "rows": rows, "episode_transitions": episode_transitions(rows)}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {"sha256": hashlib.sha256(blob).hexdigest(), "row_count": len(rows),
            "excluded_fields": list(EXCLUDED_FROM_DIGEST),
            "episode_transitions": payload["episode_transitions"]}


def load_replay_events() -> list[dict]:
    bundle = json.loads(REPLAY_BUNDLE.read_text(encoding="utf-8"))
    return sorted(bundle["events"], key=lambda e: e["sequence_index"])


def direct_replay(base: str, session_id: str, events: list[dict]) -> list[dict]:
    rows = []
    with httpx.Client() as client:
        for event in events:
            body = request_body(session_id, event["timestamp_us"], event["ecg"]["samples"],
                                quality=event["ecg_quality"], model_id=event["model_id"],
                                ppg_context=event["ppg_context"])
            status, response = post(client, base, body)
            rows.append(semantic_row(event, status, response))
    return rows


# ---------------------------------------------------------------------------------------------
# Deterministic synthetic API-input corpus (API representation: filtered, UNNORMALIZED)
# ---------------------------------------------------------------------------------------------

SCALES = (0.1, 0.5, 1.0, 2.0, 5.0)
OFFSETS = (-1.0, 0.0, 0.3, 2.0)
PPG_CONTEXT = {"quality": "VALID", "pr_bpm": 72.0, "spo2_pct": 97.0, "spo2_valid": True}


def synthetic_api_windows(count: int = 300) -> list[np.ndarray]:
    """First `count` windows of the V2-012 synthetic parity corpus, re-expressed in the API input
    representation by a deterministic amplitude scale and DC offset (undone by the locked
    per-window z-score at the runtime boundary). No patient data."""
    from deployment import gateway_v2 as gw

    corpus = gw.load_parity_corpus(ROOT)[:count, 0, :].astype(np.float64)
    return [corpus[i] * SCALES[i % 5] + OFFSETS[(i // 5) % 4] for i in range(count)]


def reference_raw_logits(windows: list[np.ndarray]) -> np.ndarray:
    """Independent reference: locked normalization -> frozen TorchScript artifact (loaded
    directly, NOT through the runtime/wrapper) -> raw logit."""
    import torch

    from deployment import gateway_v2 as gw
    from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

    torch.set_num_threads(1)
    module = gw.load_artifact(ROOT / gw.ARTIFACT_PATH)
    out = []
    with torch.inference_mode():
        for window in windows:
            x = normalize_window_zscore(window, epsilon=NORMALIZATION_EPSILON)
            out.append(float(module(torch.from_numpy(x.astype(np.float32).reshape(1, 1, -1))
                                    ).numpy()[0, 0]))
    return np.asarray(out, dtype=np.float64)


def independent_policy():
    """ALERT_POLICY_V1 semantics written out as LITERALS (K=2, M=2, cooldown 30 s) with the
    threshold read from the frozen CAL_V2 artifact -- deliberately not via the runtime's loader."""
    from fusion.episode_manager import AlertPolicy

    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    return AlertPolicy(
        policy_id="ALERT_POLICY_V1", threshold=float(cal["threshold"]), threshold_comparator=">=",
        required_open=2, required_close=2, cooldown_us=30_000_000,
        disagreement_tolerance_bpm=20.0, disagreement_duration_us=10_000_000,
        model_id="MODEL_V2_FINAL", calibration_id="CAL_V2",
        ecg_hr_context_id="ECG_HR_CONTEXT_V2")
