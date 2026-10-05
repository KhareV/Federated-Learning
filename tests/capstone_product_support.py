"""Shared CAP-003 test support. The strict HTTP contract double below is used ONLY by isolated unit
tests (the canonical E2E always uses the real released inference process)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
from fastapi.testclient import TestClient

from api.product_app import create_product_app
from api.schemas import ErrorResponse, InferWindowRequest, InferWindowResponse
from product.devices.scenarios import TimingMode
from product.inference.client import CapstoneInferenceClient
from product.monitoring.runtime_state import RuntimeState, seed_engineering_session
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver, headers_for

USER_A, USER_B = headers_for("user-a"), headers_for("user-b")
BASE = "/product/v1"


class StrictInferenceDouble:
    """Validates every request against the frozen API_SCHEMA_V1 models and answers per contract."""

    def __init__(self, *, fail_with: int | None = None, fail_after: int = 0,
                 monitoring_state: str = "NORMAL_MONITORED_PATTERN") -> None:
        self.requests: list[InferWindowRequest] = []
        self._fail_with, self._fail_after = fail_with, fail_after
        self._state = monitoring_state
        self._last: dict[str, int] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/infer-window" and request.method == "POST"
        payload = InferWindowRequest.model_validate(json.loads(request.content))
        self.requests.append(payload)
        if self._fail_with is not None and len(self.requests) > self._fail_after:
            return httpx.Response(self._fail_with, json={"detail": "double failure"})
        if payload.model_id != "MODEL_V2_FINAL":
            return httpx.Response(400, json=ErrorResponse(
                status_code=400, error_type="UNSUPPORTED_MODEL_ID", message="x").model_dump())
        previous = self._last.get(payload.session_id)
        if previous is not None and payload.timestamp_us <= previous:
            return httpx.Response(400, json=ErrorResponse(
                status_code=400, error_type="NON_MONOTONIC_TIMESTAMP", message="x").model_dump())
        self._last[payload.session_id] = payload.timestamp_us
        if payload.ecg_quality.value == "UNUSABLE" or len(payload.ecg.samples) != 2500:
            return httpx.Response(422, json=ErrorResponse(
                status_code=422, error_type="UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW",
                message="unusable").model_dump())
        context = payload.ppg_context
        available = context is not None and context.quality is not None
        body = InferWindowResponse(
            timestamp_us=payload.timestamp_us, model_id="MODEL_V2_FINAL",
            raw_probability=0.25, source_domain_calibrated_probability=0.5,
            calibration_domain="DOUBLE", calibration_patient_count=1, calibration_id="CAL_V2",
            threshold=0.75, ecg_quality=payload.ecg_quality, monitoring_state=self._state,
            context={"ppg_quality": context.quality.value if available else None,
                     "pr_ppg_bpm": context.pr_bpm if available else None,
                     "spo2_pct": context.spo2_pct if available else None,
                     "spo2_valid": bool(context.spo2_valid) if available else False,
                     "hr_ecg_bpm": 70.0, "context_available": available},
            latency_ms=1.0, preprocess_version="PREPROC_V1", alert_policy_id="ALERT_POLICY_V1")
        return httpx.Response(200, json=body.model_dump(mode="json"))

    def client(self) -> CapstoneInferenceClient:
        return CapstoneInferenceClient("http://inference.test",
                                       transport=httpx.MockTransport(self.handler))


def make_app(double: StrictInferenceDouble | None = None, *, resolver: Any = "default",
             mode: TimingMode = TimingMode.ACCELERATED,
             factory: Callable[[], CapstoneInferenceClient] | None = None,
             state: RuntimeState | None = None):
    chosen = cap003_test_identity_resolver if resolver == "default" else resolver
    return create_product_app(
        identity_resolver=chosen, state=state, timing_mode=mode,
        inference_client_factory=factory or (double.client if double else None))


def ready_session(client: TestClient, scenario_id: str, session_id: str,
                  headers: dict[str, str] | None = None) -> str:
    """Create + scan + connect a device over REST, then seed the DEVICE_READY session (harness)."""
    headers = headers or USER_A
    created = client.post(f"{BASE}/devices/simulated", json={"scenario_id": scenario_id},
                          headers=headers)
    assert created.status_code == 200, created.text
    device_id = created.json()["device_id"]
    assert client.post(f"{BASE}/devices/{device_id}/scan", headers=headers).status_code == 200
    assert client.post(f"{BASE}/devices/{device_id}/connect", headers=headers).status_code == 200
    state: RuntimeState = client.app.state.runtime_state
    owner = state.devices[device_id].owner_user_id
    seed_engineering_session(state, owner_user_id=owner, device_id=device_id,
                             session_id=session_id)
    return device_id


def collect_ws(client: TestClient, session_id: str, headers: dict[str, str] | None = None
               ) -> list[dict[str, Any]]:
    from starlette.websockets import WebSocketDisconnect
    events: list[dict[str, Any]] = []
    with client.websocket_connect(f"{BASE}/sessions/{session_id}/live",
                                  headers=headers or USER_A) as ws:
        while True:
            try:
                events.append(ws.receive_json())
            except WebSocketDisconnect:
                break
    return events
