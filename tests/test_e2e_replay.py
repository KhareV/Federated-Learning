"""T034 backend E2E replay test: the canonical PUBLIC_ECG_REPLAY_V1 fixture run against a
fresh, real, unmocked production API app (api.app.app / ProductionRuntime()).

Uses FastAPI's TestClient for fast, isolated verification (no port binding); the real-socket
localhost HTTP path required for canonical EVIDENCE generation lives in scripts/run_replay.py
and is exercised by `make replay-demo` / `make t034-evidence`, not by this test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from api.app import app
from scripts.run_replay import _public_requests, _sim_requests
from tests._t032_support import build_app, make_payload

ROOT = Path(__file__).resolve().parents[1]


def _response_validator() -> Draft202012Validator:
    schema = json.loads((ROOT / "contracts/API_SCHEMA_V1.json").read_text(encoding="utf-8"))
    combined = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/inferWindowResponse",
    }
    return Draft202012Validator(combined)


def test_canonical_public_replay_processes_all_twelve_windows() -> None:
    client = TestClient(app)
    requests_ = _public_requests("T034-PYTEST-PUBLIC-REPLAY")
    assert len(requests_) == 12

    validator = _response_validator()
    responses = []
    last_timestamp = None
    for payload in requests_:
        payload = dict(payload)
        payload.pop("_window_id")
        response = client.post("/v1/infer-window", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert list(validator.iter_errors(body)) == []
        assert body["model_id"] == "MODEL_V1"
        assert body["calibration_id"] == "CAL_V1"
        assert body["alert_policy_id"] == "ALERT_POLICY_V1"
        assert body["preprocess_version"] == "PREPROC_V1"
        if last_timestamp is not None:
            assert body["timestamp_us"] > last_timestamp
        last_timestamp = body["timestamp_us"]
        responses.append(body)

    assert len(responses) == 12
    assert all(r["monitoring_state"] for r in responses)


def test_canonical_public_replay_uses_real_model_never_mocked() -> None:
    """A mocked/fixed-probability backend would not produce window-to-window variation;
    assert at least one real-valued raw_probability is present and the gateway/model IDs are
    the real frozen ones (never MOCK_INFERENCE_V0)."""
    client = TestClient(app)
    requests_ = _public_requests("T034-PYTEST-MOCK-CHECK")
    payload = dict(requests_[0])
    payload.pop("_window_id")
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "MODEL_V1"
    assert body["model_id"] != "MOCK_INFERENCE_V0"
    assert isinstance(body["raw_probability"], float)


def test_canonical_public_replay_never_produces_an_unexpected_500() -> None:
    client = TestClient(app)
    requests_ = _public_requests("T034-PYTEST-NO-500")
    for payload in requests_:
        payload = dict(payload)
        payload.pop("_window_id")
        response = client.post("/v1/infer-window", json=payload)
        assert response.status_code != 500


def test_sim_replay_produces_expected_200_200_422_sequence() -> None:
    client = TestClient(app)
    requests_ = _sim_requests("T034-PYTEST-SIM-REPLAY")
    statuses = []
    for payload in requests_:
        payload = dict(payload)
        payload.pop("_window_id")
        response = client.post("/v1/infer-window", json=payload)
        statuses.append(response.status_code)
    assert statuses == [200, 200, 422]


def test_replay_is_semantically_deterministic_across_two_fresh_sessions() -> None:
    """Two independent fresh TestClient sessions replaying the same canonical public fixture
    must produce identical semantic digests (raw/calibrated probability, threshold,
    monitoring_state, version IDs -- excluding latency)."""

    def run(session_id: str) -> str:
        client = TestClient(app)
        requests_ = _public_requests(session_id)
        semantic_rows = []
        for payload in requests_:
            payload = dict(payload)
            payload.pop("_window_id")
            response = client.post("/v1/infer-window", json=payload)
            body = response.json()
            body.pop("latency_ms", None)
            semantic_rows.append(body)
        return hashlib.sha256(
            json.dumps(semantic_rows, sort_keys=True).encode("utf-8")
        ).hexdigest()

    digest_a = run("T034-PYTEST-DETERMINISM-A")
    digest_b = run("T034-PYTEST-DETERMINISM-B")
    assert digest_a == digest_b


def test_upstream_model_and_gateway_hashes_are_unchanged() -> None:
    """As of the C032-NORM-RUNTIME successor (API_RUNTIME_V1_1), api/runtime.py has
    legitimately moved on from the predecessor API_RUNTIME_V1 lock (restores PREPROC_V1
    PER_WINDOW_ZSCORE_V1 normalization) -- its own verify() now correctly reports that drift;
    the successor's equivalent check is tests/test_c032_lock_versioning.py::
    test_api_runtime_v1_1_verify_passes. MODEL_V1/GATEWAY_ARTIFACT_V1 themselves are
    unaffected and still verified via the successor lock."""
    from scripts.verify_api_runtime_t032 import verify as verify_api_runtime
    from scripts.verify_api_runtime_v1_1_c032 import verify as verify_api_runtime_v1_1

    with pytest.raises(RuntimeError, match="API_RUNTIME_V1_TAMPER"):
        verify_api_runtime()

    result = verify_api_runtime_v1_1()
    assert result["status"] == "PASS"


def test_replay_requests_never_use_mock_inference_module() -> None:
    text = (ROOT / "scripts/run_replay.py").read_text(encoding="utf-8")
    assert "mock_inference" not in text
    assert "MOCK_INFERENCE_V0" not in text
    assert "FIXTURE_STATE_POLICY_V0" not in text


def test_engineering_failure_sequence_uses_test_only_500_injection() -> None:
    """The non-canonical failure fixture exercises 200/422/200/500/200 while keeping
    the canonical public replay entirely production-backed and failure-free."""
    healthy_app, _, _ = build_app(probability=0.2)
    healthy = TestClient(healthy_app)
    statuses = [
        healthy.post("/v1/infer-window", json=make_payload("T034-FAILURE", 5_000_000)).status_code,
        healthy.post(
            "/v1/infer-window",
            json=make_payload("T034-FAILURE", 10_000_000, ecg_quality="UNUSABLE"),
        ).status_code,
        healthy.post("/v1/infer-window", json=make_payload("T034-FAILURE", 15_000_000)).status_code,
    ]

    failing_app, _, _ = build_app(raise_on_infer=RuntimeError("controlled test failure"))
    failing = TestClient(failing_app, raise_server_exceptions=False)
    statuses.append(
        failing.post(
            "/v1/infer-window", json=make_payload("T034-FAILURE-500", 20_000_000)
        ).status_code
    )

    retry_app, _, _ = build_app(probability=0.2)
    retry = TestClient(retry_app)
    statuses.append(
        retry.post(
            "/v1/infer-window", json=make_payload("T034-FAILURE-RETRY", 25_000_000)
        ).status_code
    )
    assert statuses == [200, 422, 200, 500, 200]
