"""CAPSTONE_PRODUCT_API_V1_1 -- the CAP-004 product app (additive successor of api/product_app.py).

Same route family (base path /product/v1) plus exactly the CAP-004 routes GET /me, POST /sessions,
GET /sessions, GET /sessions/{id}. Authentication is a REAL AuthProvider (Clerk or explicit Demo)
behind ``identity_resolver``; persistence is SQLite. Device, monitoring, inference, event-adapter
and journal logic is REUSED from the frozen CAP-003 modules (nothing is copied); the frozen
``api/product_app.py`` is neither modified nor imported. This module never builds a model/runtime.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import HTTPConnection

from capstone_persistence.store import CapstoneSqliteStore
from product.api.errors import (
    ProductError,
    ProductErrorBody,
    ProductErrorCode,
    ProductErrorResponse,
)
from product.api.models import CreateSimulatedDeviceRequest
from product.api.models_v2 import CreateSessionRequest, SystemInfoV2
from product.auth.base import AuthIdentity, AuthProviderDescription
from product.devices.base import DeviceDescriptor
from product.devices.manager import DeviceManager
from product.devices.scenarios import TimingMode
from product.inference.client import CapstoneInferenceClient
from product.monitoring.coordinator import MonitoringService
from product.monitoring.runtime_state import RuntimeState
from product.persistence.bridge import PersistenceBridge, observing_factory
from product.persistence.recovery import RecoveryReport, recover
from product.session import MonitoringSession, default_runtime_identity
from product.sessions.service import (
    IdGenerator,
    PersistentDeviceService,
    SessionService,
    default_session_id,
)

API_PREFIX = "/product/v1"
IMPLEMENTATION_ID = "CAPSTONE_PRODUCT_API_V1_1"
DEFAULT_INFERENCE_URL = "http://127.0.0.1:8001"
DEFAULT_DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
IdentityResolver = Callable[[HTTPConnection], Awaitable[AuthIdentity | None]]
WS_UNAUTHENTICATED, WS_FORBIDDEN, WS_NOT_FOUND, WS_POLICY_VIOLATION = 4401, 4403, 4404, 1008


def create_product_app_v1_1(
    *, store: CapstoneSqliteStore, identity_resolver: IdentityResolver,
    auth_description: AuthProviderDescription,
    inference_base_url: str = DEFAULT_INFERENCE_URL,
    inference_client_factory: Callable[[], CapstoneInferenceClient] | None = None,
    timing_mode: TimingMode = TimingMode.ACCELERATED,
    id_generator: IdGenerator = default_session_id,
    allowed_origins: tuple[str, ...] = DEFAULT_DEV_ORIGINS,
) -> FastAPI:
    if "*" in allowed_origins:
        raise ValueError("WILDCARD_CORS_ORIGIN_IS_NOT_ALLOWED_WITH_CREDENTIALS")
    state = RuntimeState()
    report: RecoveryReport = recover(store, state, timing_mode=timing_mode)  # restart recovery
    bridge = PersistenceBridge(store)
    inner_factory = inference_client_factory or (
        lambda: CapstoneInferenceClient(inference_base_url))
    monitoring = MonitoringService(state, observing_factory(inner_factory, bridge),
                                   blocking_lookahead=timing_mode is TimingMode.ACCELERATED)
    devices = PersistentDeviceService(store, state, DeviceManager(state, timing_mode=timing_mode))
    sessions = SessionService(store, state, bridge, monitoring, id_generator=id_generator)

    app = FastAPI(title="NHM Capstone Product API (CAP-004)", version="PRODUCT_API_V2",
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=list(allowed_origins), allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization",
                                                                      "Content-Type"])
    app.state.runtime_state, app.state.store = state, store
    app.state.recovery_report, app.state.bridge = report, bridge
    app.state.session_service, app.state.device_service = sessions, devices
    upserted: set[tuple[str, str | None, str | None, bool]] = set()

    @app.exception_handler(ProductError)
    async def _product_error(request: Request, exc: ProductError) -> JSONResponse:
        del request
        body = ProductErrorResponse(error=ProductErrorBody(code=exc.code, message=exc.message))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        del request
        body = ProductErrorResponse(error=ProductErrorBody(
            code=ProductErrorCode.INVALID_REQUEST,
            message="; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                              for e in exc.errors())[:300]))
        return JSONResponse(status_code=400, content=body.model_dump(mode="json"))

    def remember(identity: AuthIdentity) -> AuthIdentity:
        key = (identity.user_id, identity.display_name, identity.email, identity.demo_mode)
        if key not in upserted:  # users mirror verified identity metadata only
            store.upsert_user(identity)
            upserted.add(key)
        return identity

    async def identity(request: Request) -> AuthIdentity:
        resolved = await identity_resolver(request)
        if resolved is None:
            raise ProductError(ProductErrorCode.UNAUTHENTICATED, "authentication required")
        return remember(resolved)

    # ---- SYSTEM (public) ----------------------------------------------------------------------
    @app.get(f"{API_PREFIX}/system", response_model=SystemInfoV2)
    async def system() -> SystemInfoV2:
        runtime = default_runtime_identity()
        return SystemInfoV2(
            product_api_version="PRODUCT_API_V2", product_api_implementation=IMPLEMENTATION_ID,
            capstone_protocol="CAPSTONE_PRODUCT_PROTOCOL_V1",
            monitoring_protocol="CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1",
            software_system=runtime.software_system_id, model_id=runtime.model_id,
            calibration_id=runtime.calibration_id,
            api_contract_version=runtime.api_contract_version, hardware_mode="SIMULATED_ONLY",
            physical_hardware_available=False, persistence_mode="SQLITE",
            federation_runtime="NOT_IMPLEMENTED", auth_status="CONFIGURED",
            auth_provider=auth_description.provider.value, demo_mode=auth_description.demo_mode,
            claim="research prototype; simulated device; not diagnostic; no clinical claim")

    @app.get(f"{API_PREFIX}/me", response_model=AuthIdentity)
    async def me(request: Request) -> AuthIdentity:
        return await identity(request)

    # ---- DEVICES ------------------------------------------------------------------------------
    @app.get(f"{API_PREFIX}/devices", response_model=list[DeviceDescriptor])
    async def list_devices(request: Request) -> list[DeviceDescriptor]:
        return devices.list_devices(await identity(request))

    @app.post(f"{API_PREFIX}/devices/simulated", response_model=DeviceDescriptor)
    async def create_simulated(request: Request, body: CreateSimulatedDeviceRequest
                               ) -> DeviceDescriptor:
        return devices.create_simulated(await identity(request), body.display_name,
                                        body.scenario_id)

    @app.post(API_PREFIX + "/devices/{id}/scan", response_model=DeviceDescriptor)
    async def scan_device(request: Request, id: str) -> DeviceDescriptor:
        return await devices.scan(await identity(request), id)

    @app.post(API_PREFIX + "/devices/{id}/connect", response_model=DeviceDescriptor)
    async def connect_device(request: Request, id: str) -> DeviceDescriptor:
        return await devices.connect(await identity(request), id)

    @app.post(API_PREFIX + "/devices/{id}/disconnect", response_model=DeviceDescriptor)
    async def disconnect_device(request: Request, id: str) -> DeviceDescriptor:
        return await devices.disconnect(await identity(request), id)

    # ---- SESSIONS (CAP-004: create / list / get; CAP-003: start / stop) -----------------------
    @app.post(f"{API_PREFIX}/sessions", response_model=MonitoringSession)
    async def create_session(request: Request, body: CreateSessionRequest) -> MonitoringSession:
        return sessions.create(await identity(request), body.device_id, body.scenario_id)

    @app.get(f"{API_PREFIX}/sessions", response_model=list[MonitoringSession])
    async def list_sessions(request: Request) -> list[MonitoringSession]:
        return sessions.list(await identity(request))

    @app.get(API_PREFIX + "/sessions/{id}", response_model=MonitoringSession)
    async def get_session(request: Request, id: str) -> MonitoringSession:
        return sessions.get(await identity(request), id)

    @app.post(API_PREFIX + "/sessions/{id}/start", response_model=MonitoringSession)
    async def start_session(request: Request, id: str) -> MonitoringSession:
        return await sessions.start(await identity(request), id)

    @app.post(API_PREFIX + "/sessions/{id}/stop", response_model=MonitoringSession)
    async def stop_session(request: Request, id: str) -> MonitoringSession:
        return await sessions.stop(await identity(request), id)

    # ---- LIVE: server -> client monitoring events only ----------------------------------------
    @app.websocket(API_PREFIX + "/sessions/{id}/live")
    async def live(websocket: WebSocket, id: str) -> None:
        await websocket.accept()
        resolved = await identity_resolver(websocket)
        if resolved is None:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return
        remember(resolved)
        session = store.get_session(id)
        if session is None:
            await websocket.close(code=WS_NOT_FOUND)
            return
        if session.user_id != resolved.user_id:
            await websocket.close(code=WS_FORBIDDEN)
            return
        journal = sessions.journal_for(id)
        if journal is None:  # an owned session from an earlier process: its live journal is gone
            await websocket.close(code=1000)
            return
        stream = journal.subscribe()
        receive: asyncio.Task[Any] = asyncio.ensure_future(websocket.receive())
        next_event: asyncio.Task[Any] | None = None
        try:
            while True:
                next_event = asyncio.ensure_future(stream.__anext__())
                done, _ = await asyncio.wait({receive, next_event},
                                             return_when=asyncio.FIRST_COMPLETED)
                if receive in done:
                    if receive.result()["type"] != "websocket.disconnect":
                        await websocket.close(code=WS_POLICY_VIOLATION)
                    return
                try:
                    event = next_event.result()
                except StopAsyncIteration:
                    await websocket.close(code=1000)
                    return
                next_event = None
                await websocket.send_json(event.model_dump(mode="json"))
        finally:
            for task in (receive, next_event):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(t for t in (receive, next_event) if t is not None),
                                 return_exceptions=True)
            await stream.aclose()

    return app
