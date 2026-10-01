"""Production research-runtime HTTP API: POST /v1/infer-window (v2.2 Section 27).

Binds, read-only: GATEWAY_ARTIFACT_V1 (F14) + MODEL_V1 + PREPROC_V1 (F06) + CAL_V1 (F09) +
ALERT_POLICY_V1 + ECG_HR_CONTEXT_V2 + HR_DISAGREEMENT_TOLERANCE_V1. No training, no
calibration fitting, no threshold/policy mutation, no dataset access, no SimulationTruth, no
MongoDB/auth/TLS. This module is orchestration only -- every state-machine decision comes from
the already-frozen, already-tested `fusion.episode_manager.AlertEpisodeManager`; it is never
reimplemented here.

The production app (`app`, built by `create_app()` with real frozen dependencies) never calls
MOCK_INFERENCE_V0 or FIXTURE_STATE_POLICY_V0 -- those remain isolated in api/fixture_v0.py,
re-exported below only so historical T005 regression tests keep passing unmodified.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api.fixture_v0 import (  # noqa: F401 -- re-exported for T005 regression tests
    FIXTURE_API_RESPONSE_VERSION,
    FUTURE_PRODUCTION_CONTRACT,
    process_observed_record,
)
from api.runtime import ProductionRuntime
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
    """A syntactically-parseable request that nonetheless violates an application-level
    request contract (unsupported model_id, non-monotonic timestamp). Maps to HTTP 400."""

    def __init__(self, error_type: str, message: str) -> None:
        self.error_type = error_type
        self.message = message
        super().__init__(message)


class UnusableSignalWindowError(Exception):
    """A syntactically valid inference request representing an unusable or incomplete ECG
    signal window. MODEL_V1 is never run for this request. Maps to HTTP 422."""

    def __init__(self, error_type: str, message: str, *, decision: Any = None) -> None:
        self.error_type = error_type
        self.message = message
        self.decision = decision
        super().__init__(message)


class InferenceRuntime(Protocol):
    """Structural contract `create_app()` requires of any injected runtime -- satisfied by
    `api.runtime.ProductionRuntime` in production and by a deterministic fake in tests."""

    preprocess_id: str
    policy: Any
    calibration_patient_count: int

    def infer(self, ecg_samples: list[float]) -> Any: ...

    def estimate_ecg_hr(self, ecg_samples: list[float], *, timestamp_us: int) -> Any: ...


def _validation_error_summary(exc: ValidationError | RequestValidationError) -> str:
    """Summarize loc+msg only -- never echo the raw input value (which for `ecg.samples`
    could be a 2500-element array) back into an error message."""
    parts = []
    for error in exc.errors():
        location = ".".join(str(piece) for piece in error.get("loc", ()))
        parts.append(f"{location}: {error.get('msg', 'invalid')}")
    return "; ".join(parts) or "request failed schema validation"


def _sanitize_ppg_context(ppg_context: Any) -> dict[str, Any]:
    """Defensive context normalization: out-of-range/contradictory PPG/SpO2 values degrade to
    'unavailable' for fusion purposes rather than ever reaching
    `fusion.state_machine.validate_observation` in a shape it would reject. Context must never
    be able to crash ECG inference."""
    if ppg_context is None:
        return {
            "ppg_quality": None, "pr_ppg_bpm": None, "pr_ppg_valid": False,
            "spo2_pct": None, "spo2_valid": False,
        }
    pr_bpm = ppg_context.pr_bpm
    pr_valid = pr_bpm is not None and pr_bpm > 0
    spo2_pct = ppg_context.spo2_pct
    spo2_valid = bool(ppg_context.spo2_valid) and spo2_pct is not None and 0.0 <= spo2_pct <= 100.0
    quality = ppg_context.quality.value if ppg_context.quality is not None else None
    return {
        "ppg_quality": quality,
        "pr_ppg_bpm": pr_bpm if pr_valid else None,
        "pr_ppg_valid": pr_valid,
        "spo2_pct": spo2_pct,
        "spo2_valid": spo2_valid,
    }


def _response_context(
    decision: Any, *, ecg_hr_context_id: str
) -> dict[str, Any]:
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


def create_app(
    *, runtime: InferenceRuntime, session_store: SessionRuntimeStore | None = None
) -> FastAPI:
    """App factory. Production code builds `runtime=ProductionRuntime()` (verified at
    construction); tests may inject a deterministic fake implementing the same narrow
    `InferenceRuntime` protocol. `session_store` defaults to a fresh process-local store bound
    to `runtime.policy` if not supplied."""
    store = session_store or SessionRuntimeStore(runtime.policy)

    app = FastAPI(
        title="NHM Research Runtime API",
        version=CONTRACT_VERSION,
        description=(
            "Research-prototype-only typed inference API for the observed-window target "
            f"{TARGET_ID}. Never a diagnosis, beat classifier output, or future forecast."
        ),
    )
    app.state.runtime = runtime
    app.state.session_store = store

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        body = ErrorResponse(
            status_code=400,
            error_type="REQUEST_SCHEMA_ERROR",
            message=_validation_error_summary(exc),
        )
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(RequestContractError)
    async def _handle_request_contract_error(
        request: Request, exc: RequestContractError
    ) -> JSONResponse:
        del request
        body = ErrorResponse(status_code=400, error_type=exc.error_type, message=exc.message)
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(UnusableSignalWindowError)
    async def _handle_unusable_signal_window_error(
        request: Request, exc: UnusableSignalWindowError
    ) -> JSONResponse:
        del request
        body = ErrorResponse(status_code=422, error_type=exc.error_type, message=exc.message)
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        del request, exc
        body = ErrorResponse(
            status_code=500,
            error_type="INTERNAL_SERVER_ERROR",
            message="An internal server error occurred. The window may be retried.",
        )
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

        if payload.model_id != "MODEL_V1":
            raise RequestContractError(
                "UNSUPPORTED_MODEL_ID", f"model_id {payload.model_id!r} is not supported"
            )

        session = store.get_or_create(payload.session_id)
        with session.lock:
            if (
                session.last_accepted_timestamp_us is not None
                and payload.timestamp_us <= session.last_accepted_timestamp_us
            ):
                raise RequestContractError(
                    "NON_MONOTONIC_TIMESTAMP",
                    f"timestamp_us {payload.timestamp_us} is not strictly increasing",
                )

            incomplete = len(payload.ecg.samples) != ECG_WINDOW_SAMPLE_COUNT
            unusable = incomplete or payload.ecg_quality == QualityState.UNUSABLE
            context = _sanitize_ppg_context(payload.ppg_context)

            if unusable:
                observation = FusionObservation(
                    session_id=payload.session_id,
                    timestamp_us=payload.timestamp_us,
                    source_domain_calibrated_probability=0.0,
                    ecg_quality=QualityState.UNUSABLE.value,
                    ppg_quality=context["ppg_quality"],
                    spo2_pct=context["spo2_pct"],
                    spo2_valid=context["spo2_valid"],
                    hr_ecg_bpm=None,
                    hr_ecg_valid=False,
                    pr_ppg_bpm=context["pr_ppg_bpm"],
                    pr_ppg_valid=context["pr_ppg_valid"],
                    model_id=runtime.policy.model_id,
                    calibration_id=runtime.policy.calibration_id,
                )
                session.episode_manager.process(observation)
                session.last_accepted_timestamp_us = payload.timestamp_us
                reason = (
                    "UNUSABLE_SIGNAL_WINDOW" if payload.ecg_quality == QualityState.UNUSABLE
                    else "INCOMPLETE_SIGNAL_WINDOW"
                )
                raise UnusableSignalWindowError(
                    "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW",
                    f"{reason}: {len(payload.ecg.samples)} samples, ecg_quality="
                    f"{payload.ecg_quality.value}",
                )

            outcome = runtime.infer(payload.ecg.samples)
            hr_result = runtime.estimate_ecg_hr(
                payload.ecg.samples, timestamp_us=payload.timestamp_us
            )
            observation = FusionObservation(
                session_id=payload.session_id,
                timestamp_us=payload.timestamp_us,
                source_domain_calibrated_probability=outcome.source_domain_calibrated_probability,
                ecg_quality=payload.ecg_quality.value,
                ppg_quality=context["ppg_quality"],
                spo2_pct=context["spo2_pct"],
                spo2_valid=context["spo2_valid"],
                hr_ecg_bpm=hr_result.hr_ecg_bpm,
                hr_ecg_valid=hr_result.valid,
                pr_ppg_bpm=context["pr_ppg_bpm"],
                pr_ppg_valid=context["pr_ppg_valid"],
                model_id=outcome.model_id,
                calibration_id=outcome.calibration_id,
            )
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
                    decision, ecg_hr_context_id=runtime.policy.ecg_hr_context_id
                ),
                latency_ms=latency_ms,
                preprocess_version=runtime.preprocess_id,
                alert_policy_id=decision.alert_policy_id,
            )

    return app


app = create_app(runtime=ProductionRuntime())
