"""Additive authenticated Research Observatory routes over Product API V1_3.

The existing product API, inference runtime, federation and persistence contracts are unchanged.
Signal routes reconstruct one bounded synthetic window through the canonical operators;
federation routes project frozen/read-only evidence. No route trains or infers.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from api.product_app_v1_1 import DEFAULT_DEV_ORIGINS, DEFAULT_INFERENCE_URL, IdentityResolver
from api.product_app_v1_3 import create_product_app_v1_3
from capstone_persistence.store import CapstoneSqliteStore
from product.api.errors import ProductError, ProductErrorCode
from product.auth.base import AuthProviderDescription
from product.devices.scenarios import TimingMode, load_scenarios
from product.federation.artifact_store import DEFAULT_ROOT as DEFAULT_FEDERATION_ROOT
from product.history.models import ContextSnapshotPayload, InferencePayload
from product.models.candidate_artifacts import DEFAULT_ROOT as DEFAULT_CANDIDATE_ROOT
from product.observatory.federation import (
    FlClientWindowTrace,
    FrozenCohort,
    RunContributions,
    fl_client_window,
    frozen_cohort,
    run_contributions,
)
from product.observatory.live_capture import LiveWindowCapture
from product.observatory.models import (
    CaptureArmResult,
    PersistedInference,
    ScenarioInfo,
    WindowTrace,
)
from product.observatory.pipeline import reconstruct_window
from product.observatory.research_record import (
    ResearchRecord,
    ResearchWindow,
    inspect_train_window,
    list_train_records,
)
from product.session import SessionState
from product.sessions.service import IdGenerator, default_session_id
from simulation.stream_runtime_v2013 import CADENCE_US, EMIT_MARGIN_US, FIRST_RIGHT_EDGE_US

OBSERVATORY_ID = "NHM_RESEARCH_OBSERVATORY_V1_CANDIDATE"
PREFIX = "/product/v1/observatory"
MAX_ACTIVE_RECONSTRUCTIONS = 2
MAX_TRACE_RESPONSE_BYTES = 750_000
MAX_ACTIVE_LIVE_CAPTURES = 2
LIVE_CAPTURE_TTL_S = 3600


def create_product_app_observatory_v1(
    *, store: CapstoneSqliteStore, identity_resolver: IdentityResolver,
    auth_description: AuthProviderDescription,
    inference_base_url: str = DEFAULT_INFERENCE_URL,
    inference_client_factory: Callable[[], Any] | None = None,
    timing_mode: TimingMode = TimingMode.ACCELERATED,
    id_generator: IdGenerator = default_session_id,
    allowed_origins: tuple[str, ...] = DEFAULT_DEV_ORIGINS,
    federation_artifact_root: str | Path = DEFAULT_FEDERATION_ROOT,
    candidate_root: str | Path = DEFAULT_CANDIDATE_ROOT,
    run_id_generator: Callable[[], str] | None = None,
    checkpoint_hook: Callable[[str, int], None] | None = None,
    replay_pace_s: float = 0.0,
    auto_resume: bool = True,
    cohort_provider: Callable[[], Any] | None = None,
) -> FastAPI:
    app = create_product_app_v1_3(
        store=store, identity_resolver=identity_resolver,
        auth_description=auth_description,
        inference_base_url=inference_base_url,
        inference_client_factory=inference_client_factory,
        timing_mode=timing_mode, id_generator=id_generator,
        allowed_origins=allowed_origins,
        federation_artifact_root=federation_artifact_root,
        candidate_root=candidate_root, run_id_generator=run_id_generator,
        checkpoint_hook=checkpoint_hook, replay_pace_s=replay_pace_s,
        auto_resume=auto_resume, cohort_provider=cohort_provider,
    )
    app.state.observatory_id = OBSERVATORY_ID
    trace_slots = asyncio.Semaphore(MAX_ACTIVE_RECONSTRUCTIONS)
    scenarios = load_scenarios()
    armed: dict[str, tuple[str, int]] = {}
    captured: dict[str, LiveWindowCapture] = {}
    capture_errors: dict[str, str] = {}

    def expire_captures() -> None:
        now = time.monotonic()
        for sid, capture in list(captured.items()):
            if now - capture.created_monotonic > LIVE_CAPTURE_TTL_S:
                del captured[sid]
        for sid in list(capture_errors):
            if sid not in armed and sid not in captured:
                del capture_errors[sid]

    monitoring = app.state.session_service._monitoring
    original_start = monitoring.start

    async def observing_start(owner_user_id: str, session_id: str) -> Any:
        result = await original_start(owner_user_id, session_id)
        config = armed.pop(session_id, None)
        if config is not None and config[0] == owner_user_id:
            try:
                entry = app.state.runtime_state.sessions[session_id]
                coordinator = entry.coordinator
                if coordinator is None or coordinator.telemetry["scientific_record_count"] != 0:
                    raise RuntimeError("CAPTURE_MISSED_FIRST_SOURCE_BATCH")
                provenance = entry.session.simulation_provenance
                if provenance is None:
                    raise RuntimeError("CAPTURE_SOURCE_PROVENANCE_MISSING")
                captured[session_id] = LiveWindowCapture(
                    coordinator._runtime, scenario_id=provenance.scenario_id,
                    session_id=session_id, window_index=config[1],
                )
            except Exception as error:  # observability must not change monitoring success
                capture_errors[session_id] = f"CAPTURE_ATTACH_FAILED:{type(error).__name__}"
        return result

    monitoring.start = observing_start

    async def bounded_call(operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if trace_slots.locked():
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               "Observatory trace capacity busy; retry after a trace completes")
        async with trace_slots:
            trace = await asyncio.to_thread(operation, *args, **kwargs)
        if len(trace.model_dump_json().encode()) > MAX_TRACE_RESPONSE_BYTES:
            raise ProductError(ProductErrorCode.INTERNAL_PRODUCT_ERROR,
                               "Observatory trace size limit exceeded")
        return trace

    async def identity(request: Request) -> str:
        resolved = await identity_resolver(request)
        if resolved is None:
            raise ProductError(ProductErrorCode.UNAUTHENTICATED, "authentication required")
        return resolved.user_id

    @app.get(f"{PREFIX}/scenarios", response_model=list[ScenarioInfo])
    async def scenario_list(request: Request) -> list[ScenarioInfo]:
        await identity(request)
        return [ScenarioInfo(
            scenario_id=key, duration_s=spec.duration_s,
            window_count=len(range(FIRST_RIGHT_EDGE_US,
                                   spec.duration_s * 1_000_000 - EMIT_MARGIN_US,
                                   CADENCE_US)),
        ) for key, spec in sorted(scenarios.items())]

    @app.get(f"{PREFIX}/scenarios/{{scenario_id}}/windows/{{window_index}}",
             response_model=WindowTrace)
    async def scenario_window(request: Request, scenario_id: str,
                              window_index: int) -> WindowTrace:
        await identity(request)
        scenario = scenarios.get(scenario_id)
        if scenario is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, "scenario not found")
        try:
            return await bounded_call(reconstruct_window, scenario, window_index)
        except ValueError as error:
            raise ProductError(ProductErrorCode.NOT_FOUND, str(error)) from error

    @app.get(f"{PREFIX}/sessions/{{session_id}}/windows/{{window_index}}",
             response_model=WindowTrace)
    async def owned_session_window(request: Request, session_id: str,
                                   window_index: int) -> WindowTrace:
        user_id = await identity(request)
        session = store.get_session(session_id)
        if session is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, "session not found")
        if session.user_id != user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "session belongs to another user")
        provenance = session.simulation_provenance
        scenario = scenarios.get(provenance.scenario_id) if provenance else None
        if scenario is None or provenance.seed != scenario.seed:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               "only frozen synthetic scenarios can be reconstructed")
        right_us = FIRST_RIGHT_EDGE_US + window_index * CADENCE_US
        timeline = app.state.session_evidence_store.timeline(session_id, user_id)
        inference_items = [item for item in timeline.source_timeline
                           if item.kind == "INFERENCE" and item.source_timestamp_us == right_us]
        if len(inference_items) != 1:
            raise ProductError(ProductErrorCode.NOT_FOUND,
                               "no persisted inference for this window; "
                               "use Scenario Lab for excluded windows")
        payload = inference_items[0].payload
        if not isinstance(payload, InferencePayload):
            raise RuntimeError("PERSISTED_INFERENCE_PAYLOAD_TYPE_MISMATCH")
        trace = await bounded_call(
            reconstruct_window, scenario, window_index, session_id=session_id,
        )
        if trace.quality_state != payload.ecg_quality:
            raise RuntimeError("RECONSTRUCTED_QUALITY_MISMATCH")
        public_context = [item.payload for item in timeline.source_timeline
                          if item.kind == "CONTEXT_SNAPSHOT"
                          and item.source_timestamp_us == right_us
                          and isinstance(item.payload, ContextSnapshotPayload)]
        return trace.model_copy(update={
            "context_available": public_context[0].context_available if public_context else False,
            "persisted_inference": PersistedInference(
                model_id=payload.model_id,
                calibration_domain=payload.calibration_domain,
                raw_probability=payload.raw_probability,
                source_domain_calibrated_probability=(
                    payload.source_domain_calibrated_probability),
                threshold=payload.threshold, monitoring_state=payload.monitoring_state,
                ecg_quality=payload.ecg_quality,
            ),
            "inference_evidence_status": "PERSISTED_INFERENCE_METADATA_MATCHED_BY_SOURCE_TIMESTAMP",
        })

    @app.post(f"{PREFIX}/sessions/{{session_id}}/capture/{{window_index}}",
              response_model=CaptureArmResult)
    async def arm_live_capture(request: Request, session_id: str,
                               window_index: int) -> CaptureArmResult:
        user_id = await identity(request)
        session = store.get_session(session_id)
        if session is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, "session not found")
        if session.user_id != user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "session belongs to another user")
        if session.state is not SessionState.DEVICE_READY:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               "capture must be armed before monitoring starts")
        provenance = session.simulation_provenance
        scenario = scenarios.get(provenance.scenario_id) if provenance else None
        if scenario is None or provenance.seed != scenario.seed:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               "capture requires a frozen synthetic scenario")
        right_us = FIRST_RIGHT_EDGE_US + window_index * CADENCE_US
        if window_index < 0 or right_us + EMIT_MARGIN_US >= scenario.duration_s * 1_000_000:
            raise ProductError(ProductErrorCode.INVALID_REQUEST,
                               "capture window index is outside the scenario")
        expire_captures()
        if session_id not in armed and len(armed) + len(captured) >= MAX_ACTIVE_LIVE_CAPTURES:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               "live capture capacity busy")
        armed[session_id] = (user_id, window_index)
        capture_errors.pop(session_id, None)
        return CaptureArmResult(session_id=session_id, window_index=window_index)

    @app.get(f"{PREFIX}/sessions/{{session_id}}/capture", response_model=WindowTrace)
    async def owned_live_capture(request: Request, session_id: str) -> WindowTrace:
        user_id = await identity(request)
        session = store.get_session(session_id)
        if session is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, "session not found")
        if session.user_id != user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "session belongs to another user")
        expire_captures()
        capture = captured.get(session_id)
        if capture is None:
            reason = capture_errors.get(session_id, "NO_LIVE_CAPTURE_FOR_SESSION")
            raise ProductError(ProductErrorCode.NOT_FOUND, reason)
        if capture.error is not None:
            raise ProductError(ProductErrorCode.INVALID_STATE, capture.error)
        if capture.trace is None:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               "selected live window has not been emitted")
        trace = capture.trace
        timeline = app.state.session_evidence_store.timeline(session_id, user_id)
        inference_items = [item for item in timeline.source_timeline
                           if item.kind == "INFERENCE"
                           and item.source_timestamp_us == trace.right_timestamp_us]
        if len(inference_items) == 1 and isinstance(inference_items[0].payload, InferencePayload):
            payload = inference_items[0].payload
            if trace.quality_state != payload.ecg_quality:
                raise RuntimeError("CAPTURED_QUALITY_PERSISTENCE_MISMATCH")
            trace = trace.model_copy(update={
                "persisted_inference": PersistedInference(
                    model_id=payload.model_id, calibration_domain=payload.calibration_domain,
                    raw_probability=payload.raw_probability,
                    source_domain_calibrated_probability=(
                        payload.source_domain_calibrated_probability),
                    threshold=payload.threshold, monitoring_state=payload.monitoring_state,
                    ecg_quality=payload.ecg_quality),
                "inference_evidence_status": "PERSISTED_INFERENCE_MATCHED_TO_CAPTURED_SOURCE_TIME",
            })
        if len(trace.model_dump_json().encode()) > MAX_TRACE_RESPONSE_BYTES:
            raise ProductError(ProductErrorCode.INTERNAL_PRODUCT_ERROR,
                               "live capture response size limit exceeded")
        return trace

    @app.get(f"{PREFIX}/federation/cohort", response_model=FrozenCohort)
    async def federation_cohort(request: Request) -> FrozenCohort:
        await identity(request)
        return frozen_cohort()

    @app.get(f"{PREFIX}/federation/clients/{{client_id}}/windows/{{window_index}}",
             response_model=FlClientWindowTrace)
    async def federation_client_window(request: Request, client_id: str,
                                       window_index: int) -> FlClientWindowTrace:
        await identity(request)
        try:
            return await bounded_call(fl_client_window, client_id, window_index)
        except ValueError as error:
            raise ProductError(ProductErrorCode.NOT_FOUND, str(error)) from error

    @app.get(f"{PREFIX}/federation/runs/{{run_id}}/contributions", response_model=RunContributions)
    async def federation_contributions(request: Request, run_id: str) -> RunContributions:
        user_id = await identity(request)
        service = app.state.federation_service
        run = service.get_run(user_id, run_id)
        rounds = tuple(service.rounds(user_id, run_id))
        return run_contributions(run, service.artifacts, rounds, service.store)

    @app.get(f"{PREFIX}/research/records", response_model=list[ResearchRecord])
    async def research_train_records(request: Request) -> list[ResearchRecord]:
        await identity(request)
        return await asyncio.to_thread(list_train_records)

    @app.get(f"{PREFIX}/research/records/{{record_id}}/windows/{{window_index}}",
             response_model=ResearchWindow)
    async def research_train_window(request: Request, record_id: str,
                                    window_index: int) -> ResearchWindow:
        await identity(request)
        try:
            return await bounded_call(inspect_train_window, record_id, window_index)
        except ValueError as error:
            raise ProductError(ProductErrorCode.NOT_FOUND, str(error)) from error

    return app
