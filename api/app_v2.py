"""API_RUNTIME_V2 research app: POST /v1/infer-window bound to MODEL_V2_FINAL.

The HTTP contract is UNCHANGED (API_SCHEMA_V1, same route, same request/response schemas, same
400/422/500 semantics, same five public monitoring states): MODEL_V2 does not require a new
contract version. The only behavioral difference from api.app.create_app is that the accepted
request `model_id` is the model the runtime was BOUND to at construction (`runtime.bound_model_id`),
instead of the literal "MODEL_V1". There is deliberately NO public model/checkpoint/threshold
selector: a V2 research process accepts only MODEL_V2_FINAL requests (anything else is a 400),
exactly as the production process accepts only MODEL_V1.

This module intentionally does NOT import api.app (whose import-time `app = create_app(
runtime=ProductionRuntime())` would instantiate the V1 production runtime inside a V2 process).
The route body mirrors api.app.create_app one-for-one; tests/test_v2_013_api_runtime.py proves
behavioral equality against api.app.create_app on the same scripted sequences.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api.schemas import (
    CONTRACT_VERSION,
    ECG_WINDOW_SAMPLE_COUNT,
    TARGET_ID,
    ErrorResponse,
    InferWindowRequest,
    InferWindowResponse,
    MonitoringState,
    QualityState,
)
from api.session import SessionRuntimeStore
from fusion.state_machine import FusionObservation

ROUTE_PATH = "/v1/infer-window"


class RequestContractError(Exception):
    def __init__(self, error_type: str, message: str) -> None:
        self.error_type = error_type
        self.message = message
        super().__init__(message)


class UnusableSignalWindowError(Exception):
    def __init__(self, error_type: str, message: str) -> None:
        self.error_type = error_type
        self.message = message
        super().__init__(message)


def _validation_error_summary(exc: ValidationError | RequestValidationError) -> str:
    parts = []
    for error in exc.errors():
        location = ".".join(str(piece) for piece in error.get("loc", ()))
        parts.append(f"{location}: {error.get('msg', 'invalid')}")
    return "; ".join(parts) or "request failed schema validation"


def _sanitize_ppg_context(ppg_context: Any) -> dict[str, Any]:
    if ppg_context is None:
        return {"ppg_quality": None, "pr_ppg_bpm": None, "pr_ppg_valid": False,
                "spo2_pct": None, "spo2_valid": False}
    pr_bpm = ppg_context.pr_bpm
    pr_valid = pr_bpm is not None and pr_bpm > 0
    spo2_pct = ppg_context.spo2_pct
    spo2_valid = bool(ppg_context.spo2_valid) and spo2_pct is not None and 0.0 <= spo2_pct <= 100.0
    quality = ppg_context.quality.value if ppg_context.quality is not None else None
    return {"ppg_quality": quality, "pr_ppg_bpm": pr_bpm if pr_valid else None,
            "pr_ppg_valid": pr_valid, "spo2_pct": spo2_pct, "spo2_valid": spo2_valid}


def _response_context(decision: Any, *, ecg_hr_context_id: str) -> dict[str, Any]:
    return {
        "ppg_quality": decision.ppg_quality,
        "pr_ppg_bpm": decision.pr_ppg_bpm,
        "spo2_pct": decision.spo2_pct,
        "spo2_valid": decision.spo2_valid,
        "hr_ecg_bpm": decision.hr_ecg_bpm,
        "context_available": decision.context_available,
        "quality_warning": decision.quality_warning,
        "quality_warning_reasons": list(decision.quality_warning_reasons),
        "possible_pattern": decision.possible_pattern,
        "ecg_hr_context_id": ecg_hr_context_id,
    }


def create_research_app(*, runtime: Any, session_store: SessionRuntimeStore | None = None
                        ) -> FastAPI:
    """App factory for the V2 research runtime. `runtime` must expose `bound_model_id`."""
    bound_model_id = runtime.bound_model_id
    store = session_store or SessionRuntimeStore(runtime.policy)

    app = FastAPI(
        title="NHM Research Runtime API (MODEL_V2 research binding)",
        version=CONTRACT_VERSION,
        description=(
            "Research-prototype-only typed inference API for the observed-window target "
            f"{TARGET_ID}, bound to the parallel research runtime API_RUNTIME_V2. Never a "
            "diagnosis, beat classifier output, or future forecast; not the operational runtime."
        ),
    )
    app.state.runtime = runtime
    app.state.session_store = store

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(request: Request, exc: RequestValidationError
                                               ) -> JSONResponse:
        del request
        body = ErrorResponse(status_code=400, error_type="REQUEST_SCHEMA_ERROR",
                             message=_validation_error_summary(exc))
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(RequestContractError)
    async def _handle_request_contract_error(request: Request, exc: RequestContractError
                                             ) -> JSONResponse:
        del request
        body = ErrorResponse(status_code=400, error_type=exc.error_type, message=exc.message)
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(UnusableSignalWindowError)
    async def _handle_unusable(request: Request, exc: UnusableSignalWindowError) -> JSONResponse:
        del request
        body = ErrorResponse(status_code=422, error_type=exc.error_type, message=exc.message)
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        del request, exc
        body = ErrorResponse(
            status_code=500, error_type="INTERNAL_SERVER_ERROR",
            message="An internal server error occurred. The window may be retried.")
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.post(
        ROUTE_PATH,
        response_model=InferWindowResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Request/schema contract error."},
            422: {"model": ErrorResponse, "description": "Unusable or incomplete signal window."},
            500: {"model": ErrorResponse, "description": "Internal server failure."},
        },
        summary="Infer the AAMI_SVF_WINDOW_V1 target for one observed 10-second ECG window.",
    )
    def infer_window(payload: InferWindowRequest) -> InferWindowResponse:
        start_ns = time.perf_counter_ns()

        if payload.model_id != bound_model_id:
            raise RequestContractError(
                "UNSUPPORTED_MODEL_ID", f"model_id {payload.model_id!r} is not supported")

        session = store.get_or_create(payload.session_id)
        with session.lock:
            if (session.last_accepted_timestamp_us is not None
                    and payload.timestamp_us <= session.last_accepted_timestamp_us):
                raise RequestContractError(
                    "NON_MONOTONIC_TIMESTAMP",
                    f"timestamp_us {payload.timestamp_us} is not strictly increasing")

            incomplete = len(payload.ecg.samples) != ECG_WINDOW_SAMPLE_COUNT
            unusable = incomplete or payload.ecg_quality == QualityState.UNUSABLE
            context = _sanitize_ppg_context(payload.ppg_context)

            if unusable:
                observation = FusionObservation(
                    session_id=payload.session_id, timestamp_us=payload.timestamp_us,
                    source_domain_calibrated_probability=0.0,
                    ecg_quality=QualityState.UNUSABLE.value,
                    ppg_quality=context["ppg_quality"], spo2_pct=context["spo2_pct"],
                    spo2_valid=context["spo2_valid"], hr_ecg_bpm=None, hr_ecg_valid=False,
                    pr_ppg_bpm=context["pr_ppg_bpm"], pr_ppg_valid=context["pr_ppg_valid"],
                    model_id=runtime.policy.model_id, calibration_id=runtime.policy.calibration_id)
                session.episode_manager.process(observation)
                session.last_accepted_timestamp_us = payload.timestamp_us
                reason = ("UNUSABLE_SIGNAL_WINDOW" if payload.ecg_quality == QualityState.UNUSABLE
                          else "INCOMPLETE_SIGNAL_WINDOW")
                raise UnusableSignalWindowError(
                    "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW",
                    f"{reason}: {len(payload.ecg.samples)} samples, ecg_quality="
                    f"{payload.ecg_quality.value}")

            outcome = runtime.infer(payload.ecg.samples)
            hr_result = runtime.estimate_ecg_hr(payload.ecg.samples,
                                                timestamp_us=payload.timestamp_us)
            observation = FusionObservation(
                session_id=payload.session_id, timestamp_us=payload.timestamp_us,
                source_domain_calibrated_probability=outcome.source_domain_calibrated_probability,
                ecg_quality=payload.ecg_quality.value, ppg_quality=context["ppg_quality"],
                spo2_pct=context["spo2_pct"], spo2_valid=context["spo2_valid"],
                hr_ecg_bpm=hr_result.hr_ecg_bpm, hr_ecg_valid=hr_result.valid,
                pr_ppg_bpm=context["pr_ppg_bpm"], pr_ppg_valid=context["pr_ppg_valid"],
                model_id=outcome.model_id, calibration_id=outcome.calibration_id)
            decision = session.episode_manager.process(observation)
            session.last_accepted_timestamp_us = payload.timestamp_us

            latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            return InferWindowResponse(
                timestamp_us=payload.timestamp_us,
                model_id=outcome.model_id,
                raw_probability=outcome.raw_probability,
                source_domain_calibrated_probability=outcome.source_domain_calibrated_probability,
                calibration_domain=outcome.calibration_domain,
                calibration_patient_count=runtime.calibration_patient_count,
                calibration_id=outcome.calibration_id,
                threshold=outcome.threshold,
                ecg_quality=payload.ecg_quality,
                monitoring_state=MonitoringState(decision.monitoring_state),
                context=_response_context(
                    decision, ecg_hr_context_id=runtime.policy.ecg_hr_context_id),
                latency_ms=latency_ms,
                preprocess_version=runtime.preprocess_id,
                alert_policy_id=decision.alert_policy_id,
            )

    return app


def create_default_research_app() -> FastAPI:
    """uvicorn factory entry point: `uvicorn --factory api.app_v2:create_default_research_app`.
    Nothing is constructed at import time."""
    from api.runtime_v2 import ResearchRuntimeV2

    return create_research_app(runtime=ResearchRuntimeV2())
