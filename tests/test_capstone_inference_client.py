"""CAP-003: CAPSTONE_INFERENCE_CLIENT_V1 request/response/error semantics (HTTP contract double)."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json

import httpx
import pytest

from api.schemas import ErrorResponse, InferWindowRequest, InferWindowResponse
from product.contracts import ROOT
from product.inference.client import (
    CapstoneInferenceClient,
    NonMonotonicTimestampError,
    OutcomeKind,
)
from tests.capstone_product_support import StrictInferenceDouble


def _window(ts: int = 15_000_000, quality: str = "VALID", samples: int = 2500) -> dict:
    return {"timestamp_us": ts, "ecg": {"samples": [0.0] * samples, "target_hz": 250,
                                         "window_seconds": 10},
            "ecg_quality": quality,
            "ppg_context": {"quality": "VALID", "pr_bpm": 70.0, "spo2_pct": 97.0,
                            "spo2_valid": True}}


def _client(handler) -> CapstoneInferenceClient:
    return CapstoneInferenceClient("http://inference.test", transport=httpx.MockTransport(handler))


def _infer(client: CapstoneInferenceClient, window: dict, session: str = "S"):
    async def go():
        try:
            return await client.infer_window(window, session)
        finally:
            await client.aclose()

    return asyncio.run(go())


def test_request_is_exactly_api_schema_v1_with_the_server_side_bound_model() -> None:
    double = StrictInferenceDouble()
    client = double.client()
    request = client.build_request(_window(), "SESSION-1")
    assert isinstance(request, InferWindowRequest)
    body = request.model_dump(mode="json")
    assert set(body) == {"contract_version", "session_id", "timestamp_us", "ecg", "ecg_quality",
                         "ppg_context", "model_id"}
    assert body["contract_version"] == "API_SCHEMA_V1" and body["model_id"] == "MODEL_V2_FINAL"
    assert body["ecg"]["target_hz"] == 250 and len(body["ecg"]["samples"]) == 2500
    parameters = inspect.signature(CapstoneInferenceClient.infer_window).parameters
    assert list(parameters) == ["self", "window", "session_id"]  # no model selector exists
    assert client.bound_model_id == "MODEL_V2_FINAL"
    outcome = _infer(double.client(), _window())
    assert outcome.kind is OutcomeKind.OK and double.requests[0].model_id == "MODEL_V2_FINAL"
    assert double.requests[0].session_id == "S" and double.requests[0].timestamp_us == 15_000_000


def test_a_window_cannot_smuggle_a_different_model_id() -> None:
    double = StrictInferenceDouble()
    window = {**_window(), "model_id": "MODEL_V1"}  # ignored: the client supplies the identity
    _infer(double.client(), window)
    assert double.requests[0].model_id == "MODEL_V2_FINAL"


def test_a_200_is_parsed_into_the_typed_response_and_identity_checked() -> None:
    outcome = _infer(StrictInferenceDouble().client(), _window())
    assert outcome.kind is OutcomeKind.OK and outcome.status_code == 200
    assert isinstance(outcome.response, InferWindowResponse)
    assert (outcome.response.model_id, outcome.response.calibration_id) == (
        "MODEL_V2_FINAL", "CAL_V2")
    assert outcome.response.preprocess_version == "PREPROC_V1"
    assert outcome.response.alert_policy_id == "ALERT_POLICY_V1"


def test_an_unusable_window_422_is_an_expected_typed_outcome_not_an_error() -> None:
    outcome = _infer(StrictInferenceDouble().client(), _window(quality="UNUSABLE"))
    assert outcome.kind is OutcomeKind.EXPECTED_UNUSABLE_WINDOW and outcome.status_code == 422
    assert isinstance(outcome.error, ErrorResponse) and outcome.response is None
    assert outcome.error.error_type == "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW"


def test_other_422_bodies_and_400_are_integration_failures() -> None:
    def other_422(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json=ErrorResponse(
            status_code=422, error_type="SOMETHING_ELSE", message="x").model_dump())

    assert _infer(_client(other_422), _window()).kind is OutcomeKind.INTEGRATION_ERROR

    def bad_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=ErrorResponse(
            status_code=400, error_type="NON_MONOTONIC_TIMESTAMP", message="x").model_dump())

    outcome = _infer(_client(bad_request), _window())
    assert outcome.kind is OutcomeKind.INTEGRATION_ERROR and outcome.status_code == 400


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_errors_are_system_failures(status: int) -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "boom"})

    outcome = _infer(_client(failing), _window())
    assert outcome.kind is OutcomeKind.SYSTEM_FAILURE and outcome.status_code == status


def test_network_failure_and_garbage_bodies_are_system_failures_without_retry() -> None:
    calls = []

    def unreachable(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("refused")

    outcome = _infer(_client(unreachable), _window())
    assert outcome.kind is OutcomeKind.SYSTEM_FAILURE and outcome.status_code is None
    assert len(calls) == 1  # no automatic retry

    def garbage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    assert _infer(_client(garbage), _window()).kind is OutcomeKind.SYSTEM_FAILURE


def test_a_response_with_a_different_released_identity_is_rejected() -> None:
    def wrong_model(request: httpx.Request) -> httpx.Response:
        good = StrictInferenceDouble().handler(request)
        body = json.loads(good.content)
        body["calibration_id"] = "CAL_V1"
        return httpx.Response(200, json=body)

    outcome = _infer(_client(wrong_model), _window())
    assert outcome.kind is OutcomeKind.SYSTEM_FAILURE
    assert "RELEASED_IDENTITY_MISMATCH" in (outcome.detail or "")


def test_window_timestamps_must_be_strictly_increasing_per_session() -> None:
    double = StrictInferenceDouble()
    client = double.client()

    async def go() -> None:
        await client.infer_window(_window(15_000_000), "S")
        await client.infer_window(_window(20_000_000), "S")
        await client.infer_window(_window(15_000_000), "OTHER")  # a different session is fine
        with pytest.raises(NonMonotonicTimestampError):
            await client.infer_window(_window(20_000_000), "S")
        await client.aclose()

    asyncio.run(go())
    assert [a["timestamp_us"] for a in client.attempts] == [15_000_000, 20_000_000, 15_000_000]
    assert [a["http_status"] for a in client.attempts] == [200, 200, 200]


def test_malformed_windows_never_reach_the_network() -> None:
    double = StrictInferenceDouble()
    client = double.client()
    bad = {**_window(), "ecg": {"samples": [0.0], "target_hz": 100, "window_seconds": 10}}
    with pytest.raises(ValueError):
        client.build_request(bad, "S")
    assert double.requests == []


def test_the_client_imports_no_model_gateway_runtime_or_training_code() -> None:
    tree = ast.parse((ROOT / "product/inference/client.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    allowed = {"__future__", "collections.abc", "dataclasses", "enum", "typing", "httpx",
               "pydantic", "api.schemas", "product.session"}
    assert imported <= allowed, imported - allowed
    for forbidden in ("torch", "deployment", "api.runtime", "api.runtime_v2", "api.app_v2",
                      "training", "models", "federated"):
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported)
    text = (ROOT / "product/inference/client.py").read_text()
    for token in ("ResearchRuntimeV2", "load_state_dict", "torch.jit", "gateway_v2"):
        assert token not in text, token
