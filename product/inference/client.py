"""CAPSTONE_INFERENCE_CLIENT_V1 -- the ONLY route from the product layer to inference.

Talks HTTP to the released SOFTWARE_SYSTEM_V2 service (POST /v1/infer-window, API_SCHEMA_V1). It
never imports a model, gateway, runtime or training code: the only repository import is
``api.schemas`` (the frozen typed contract). The bound model identity is supplied here, server-side;
no product route, body, header or WebSocket message can choose it.

Outcome semantics: HTTP 200 -> OK (response validated and identity-checked); HTTP 422 with the
frozen unusable-window error -> EXPECTED_UNUSABLE_WINDOW (an expected contract outcome, never a
fabricated result); HTTP 400 -> INTEGRATION_ERROR (a product-side defect); 5xx / transport failure /
identity mismatch -> SYSTEM_FAILURE. No automatic retry (a retry policy needs separate governance).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from pydantic import ValidationError

from api.schemas import ErrorResponse, InferWindowRequest, InferWindowResponse
from product.session import default_runtime_identity

INFER_PATH = "/v1/infer-window"
UNUSABLE_ERROR_TYPE = "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW"


class OutcomeKind(StrEnum):
    OK = "OK"
    EXPECTED_UNUSABLE_WINDOW = "EXPECTED_UNUSABLE_WINDOW"
    INTEGRATION_ERROR = "INTEGRATION_ERROR"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"


@dataclass(frozen=True)
class InferenceOutcome:
    kind: OutcomeKind
    status_code: int | None
    response: InferWindowResponse | None = None
    error: ErrorResponse | None = None
    detail: str | None = None


class NonMonotonicTimestampError(RuntimeError):
    """A product bug: window timestamps for one session must be strictly increasing."""


class CapstoneInferenceClient:
    def __init__(self, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 timeout_s: float = 60.0) -> None:
        identity = default_runtime_identity()
        self._bound = identity
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=timeout_s)
        self._last_timestamp: dict[str, int] = {}
        self.attempts: list[dict[str, Any]] = []

    @property
    def bound_model_id(self) -> str:
        return self._bound.model_id

    def build_request(self, window: Mapping[str, Any], session_id: str) -> InferWindowRequest:
        """Exactly API_SCHEMA_V1 from a WearableStreamRuntime window event."""
        return InferWindowRequest.model_validate({
            "contract_version": "API_SCHEMA_V1", "session_id": session_id,
            "timestamp_us": window["timestamp_us"], "ecg": window["ecg"],
            "ecg_quality": window["ecg_quality"], "ppg_context": window["ppg_context"],
            "model_id": self._bound.model_id,
        })

    def _check_identity(self, response: InferWindowResponse) -> None:
        expected = {"model_id": self._bound.model_id, "calibration_id": self._bound.calibration_id,
                    "preprocess_version": self._bound.preprocess_id,
                    "alert_policy_id": self._bound.alert_policy_id}
        actual = {"model_id": response.model_id, "calibration_id": response.calibration_id,
                  "preprocess_version": response.preprocess_version,
                  "alert_policy_id": response.alert_policy_id}
        if actual != expected:
            raise ValueError(f"RELEASED_IDENTITY_MISMATCH:{actual}")

    async def infer_window(self, window: Mapping[str, Any], session_id: str) -> InferenceOutcome:
        request = self.build_request(window, session_id)
        previous = self._last_timestamp.get(session_id)
        if previous is not None and request.timestamp_us <= previous:
            raise NonMonotonicTimestampError(f"{request.timestamp_us} <= {previous}")
        self._last_timestamp[session_id] = request.timestamp_us
        try:
            http = await self._http.post(INFER_PATH, json=request.model_dump(mode="json"))
        except httpx.HTTPError as error:
            outcome = InferenceOutcome(OutcomeKind.SYSTEM_FAILURE, None, detail=repr(error))
            return self._record(request.timestamp_us, outcome)
        outcome = self._interpret(http)
        return self._record(request.timestamp_us, outcome)

    def _interpret(self, http: httpx.Response) -> InferenceOutcome:
        status = http.status_code
        try:
            body = http.json()
        except ValueError:
            return InferenceOutcome(OutcomeKind.SYSTEM_FAILURE, status, detail="NON_JSON_BODY")
        try:
            if status == 200:
                response = InferWindowResponse.model_validate(body)
                self._check_identity(response)
                return InferenceOutcome(OutcomeKind.OK, 200, response=response)
            if status in (400, 422):
                error = ErrorResponse.model_validate(body)
                if status == 422 and error.error_type == UNUSABLE_ERROR_TYPE:
                    return InferenceOutcome(OutcomeKind.EXPECTED_UNUSABLE_WINDOW, 422,
                                            error=error)
                return InferenceOutcome(OutcomeKind.INTEGRATION_ERROR, status, error=error,
                                        detail=error.error_type)
        except (ValidationError, ValueError) as error:
            return InferenceOutcome(OutcomeKind.SYSTEM_FAILURE, status, detail=repr(error)[:300])
        return InferenceOutcome(OutcomeKind.SYSTEM_FAILURE, status, detail="UNEXPECTED_STATUS")

    def _record(self, timestamp_us: int, outcome: InferenceOutcome) -> InferenceOutcome:
        response = outcome.response
        self.attempts.append({
            "timestamp_us": timestamp_us, "http_status": outcome.status_code,
            "kind": outcome.kind.value,
            "model_id": response.model_id if response else None,
            "calibration_id": response.calibration_id if response else None})
        return outcome

    async def aclose(self) -> None:
        await self._http.aclose()
