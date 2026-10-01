"""T032 HTTP status-code contract: 400 (request/schema), 422 (unusable/incomplete signal
window), 500 (internal server failure) -- overriding FastAPI's default behavior, which would
otherwise map request-validation failures to 422. Uses the fake runtime from
tests/_t032_support.py so these tests are fast and do not depend on MODEL_V1/torch.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests._t032_support import build_app, make_payload


def test_malformed_json_body_is_400() -> None:
    app, _, _ = build_app()
    client = TestClient(app)
    response = client.post(
        "/v1/infer-window",
        content="{not valid json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["status_code"] == 400
    assert body["error_type"] == "REQUEST_SCHEMA_ERROR"


def test_wrong_contract_version_is_400() -> None:
    app, _, _ = build_app()
    client = TestClient(app)
    payload = make_payload("ERR-1", 1_000_000)
    payload["contract_version"] = "API_SCHEMA_V0"
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 400
    assert response.json()["error_type"] == "REQUEST_SCHEMA_ERROR"


def test_extra_unknown_field_is_400() -> None:
    app, _, _ = build_app()
    client = TestClient(app)
    payload = make_payload("ERR-2", 1_000_000)
    payload["unexpected_field"] = "nope"
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 400


def test_wrong_enum_value_is_400() -> None:
    app, _, _ = build_app()
    client = TestClient(app)
    payload = make_payload("ERR-3", 1_000_000, ecg_quality="SUPER_VALID")
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 400


def test_raw_nan_in_ecg_samples_is_400_and_does_not_echo_waveform() -> None:
    """Non-finite values are permitted by stdlib json.loads as a non-standard extension, so
    this must be rejected explicitly at the Pydantic validator layer (api/schemas.py). The
    error message must never echo the raw (potentially 2500-element) input array back."""
    app, _, _ = build_app()
    client = TestClient(app)
    payload = make_payload("ERR-4", 1_000_000)
    body_text = json.dumps(payload).replace('"samples": [0.0,', '"samples": [NaN,', 1)
    response = client.post(
        "/v1/infer-window",
        content=body_text,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error_type"] == "REQUEST_SCHEMA_ERROR"
    assert "0.0, 0.0, 0.0" not in body["message"]
    assert len(body["message"]) < 500


def test_unsupported_model_id_is_400() -> None:
    app, _, _ = build_app()
    client = TestClient(app)
    payload = make_payload("ERR-5", 1_000_000, model_id="MODEL_V2")
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 400
    assert response.json()["error_type"] == "UNSUPPORTED_MODEL_ID"


def test_non_monotonic_timestamp_is_400() -> None:
    app, _, _ = build_app()
    client = TestClient(app)
    sid = "ERR-6"
    client.post("/v1/infer-window", json=make_payload(sid, 5_000_000))
    response = client.post("/v1/infer-window", json=make_payload(sid, 5_000_000))
    assert response.status_code == 400
    assert response.json()["error_type"] == "NON_MONOTONIC_TIMESTAMP"

    earlier = client.post("/v1/infer-window", json=make_payload(sid, 4_999_999))
    assert earlier.status_code == 400
    assert earlier.json()["error_type"] == "NON_MONOTONIC_TIMESTAMP"


def test_string_timestamp_is_rejected_not_coerced() -> None:
    """timestamp_us uses Field(strict=True) specifically to reject numeric-string coercion
    (e.g. "1000"), unlike the StrEnum fields which intentionally accept plain JSON strings."""
    app, _, _ = build_app()
    client = TestClient(app)
    payload = make_payload("ERR-7", 1_000_000)
    payload["timestamp_us"] = "1000000"
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 400


def test_declared_unusable_ecg_is_422_and_does_not_run_model() -> None:
    app, runtime, _ = build_app()
    client = TestClient(app)
    payload = make_payload("ERR-8", 1_000_000, ecg_quality="UNUSABLE")
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error_type"] == "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW"
    assert "UNUSABLE_SIGNAL_WINDOW" in body["message"]
    assert runtime.infer_calls == []


def test_incomplete_window_is_422_and_does_not_run_model() -> None:
    app, runtime, _ = build_app()
    client = TestClient(app)
    payload = make_payload("ERR-9", 1_000_000, samples=[0.0] * 2499)
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error_type"] == "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW"
    assert "INCOMPLETE_SIGNAL_WINDOW" in body["message"]
    assert runtime.infer_calls == []


def test_unusable_window_still_commits_session_timestamp() -> None:
    """A 422 for an unusable/incomplete window must not corrupt session monotonicity: the
    timestamp is still consumed (ALERT_POLICY_V1 still observes the unusable sample)."""
    app, _, _ = build_app()
    client = TestClient(app)
    sid = "ERR-10"
    first = client.post(
        "/v1/infer-window", json=make_payload(sid, 1_000_000, ecg_quality="UNUSABLE")
    )
    assert first.status_code == 422
    replay = client.post(
        "/v1/infer-window", json=make_payload(sid, 1_000_000, ecg_quality="UNUSABLE")
    )
    assert replay.status_code == 400
    assert replay.json()["error_type"] == "NON_MONOTONIC_TIMESTAMP"


def test_internal_failure_is_500_with_safe_generic_body() -> None:
    app, _, _ = build_app(raise_on_infer=RuntimeError("deliberate failure"))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/v1/infer-window", json=make_payload("ERR-11", 1_000_000))
    assert response.status_code == 500
    body = response.json()
    assert body["status_code"] == 500
    assert body["error_type"] == "INTERNAL_SERVER_ERROR"
    assert "deliberate failure" not in body["message"]
    assert "Traceback" not in body["message"]


def test_error_responses_conform_to_api_schema_v1_error_shape() -> None:
    app, _, _ = build_app()
    client = TestClient(app)
    response = client.post(
        "/v1/infer-window", json=make_payload("ERR-12", 1_000_000, ecg_quality="UNUSABLE")
    )
    body = response.json()
    assert set(body) == {"contract_version", "status_code", "error_type", "message"}
    assert body["contract_version"] == "API_SCHEMA_V1"
