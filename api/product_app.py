"""CAPSTONE_PRODUCT_API_V1 -- the capstone product FastAPI app (not the frozen inference API).

Implements ONLY the PRODUCT_API_CONTRACT_V1 routes owned by CAP-003. It never imports or builds a
model/runtime: monitoring reaches inference through ``CapstoneInferenceClient`` over HTTP.

Authentication is INJECTED, never implemented here. ``identity_resolver`` receives the request or
WebSocket connection and returns an ``AuthIdentity`` or ``None``. With no resolver every
AUTHENTICATED route fails closed (HTTP 401 / WebSocket close 4401); there is no debug or
no-token bypass. Real providers (Clerk / DemoAuth) are CAP-004's.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import HTTPConnection

from product.api.errors import (
    ProductError,
    ProductErrorBody,
    ProductErrorCode,
    ProductErrorResponse,
)
from product.api.models import CreateSimulatedDeviceRequest, SystemInfo
from product.auth.base import AuthIdentity
from product.devices.base import DeviceDescriptor
from product.devices.manager import DeviceManager
from product.devices.scenarios import TimingMode
from product.inference.client import CapstoneInferenceClient
from product.monitoring.coordinator import MonitoringService
from product.monitoring.runtime_state import PERSISTENCE_MODE, RuntimeState
from product.session import MonitoringSession, default_runtime_identity

API_PREFIX = "/product/v1"
DEFAULT_INFERENCE_URL = "http://127.0.0.1:8001"
IdentityResolver = Callable[[HTTPConnection], Awaitable[AuthIdentity | None]]

WS_UNAUTHENTICATED, WS_FORBIDDEN, WS_NOT_FOUND = 4401, 4403, 4404
WS_POLICY_VIOLATION = 1008


def create_product_app(
    *, identity_resolver: IdentityResolver | None = None, state: RuntimeState | None = None,
    inference_base_url: str = DEFAULT_INFERENCE_URL,
    inference_client_factory: Callable[[], CapstoneInferenceClient] | None = None,
    timing_mode: TimingMode = TimingMode.ACCELERATED,
) -> FastAPI:
    runtime_state = state or RuntimeState()
    devices = DeviceManager(runtime_state, timing_mode=timing_mode)
    factory = inference_client_factory or (lambda: CapstoneInferenceClient(inference_base_url))
    monitoring = MonitoringService(runtime_state, factory,
                                   blocking_lookahead=timing_mode is TimingMode.ACCELERATED)

    app = FastAPI(title="NHM Capstone Product API (CAP-003)", version="PRODUCT_API_V1",
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime_state = runtime_state
    app.state.monitoring_service = monitoring

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

    async def identity(request: Request) -> AuthIdentity:
        if identity_resolver is None:
            raise ProductError(ProductErrorCode.UNAUTHENTICATED, "authentication not configured")
        resolved = await identity_resolver(request)
        if resolved is None:
            raise ProductError(ProductErrorCode.UNAUTHENTICATED, "authentication required")
        return resolved

    # ---- SYSTEM (public) ----------------------------------------------------------------------
    @app.get(f"{API_PREFIX}/system", response_model=SystemInfo)
    async def system() -> SystemInfo:
        runtime = default_runtime_identity()
        return SystemInfo(
            product_api_version="PRODUCT_API_V1", capstone_protocol="CAPSTONE_PRODUCT_PROTOCOL_V1",
            monitoring_protocol="CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1",
            software_system=runtime.software_system_id, model_id=runtime.model_id,
            calibration_id=runtime.calibration_id,
            api_contract_version=runtime.api_contract_version,
            hardware_mode="SIMULATED_ONLY", physical_hardware_available=False,
            persistence_mode=PERSISTENCE_MODE, federation_runtime="NOT_IMPLEMENTED_IN_CAP003",
            auth_status="INJECTED" if identity_resolver is not None else "NOT_CONFIGURED",
            claim="research prototype; simulated device; not diagnostic; no clinical claim")

    # ---- DEVICES (authenticated, owner-scoped) ------------------------------------------------
    @app.get(f"{API_PREFIX}/devices", response_model=list[DeviceDescriptor])
    async def list_devices(request: Request) -> list[DeviceDescriptor]:
        user = await identity(request)
        return devices.list_devices(user.user_id)

    @app.post(f"{API_PREFIX}/devices/simulated", response_model=DeviceDescriptor)
    async def create_simulated(request: Request, body: CreateSimulatedDeviceRequest
                               ) -> DeviceDescriptor:
        user = await identity(request)
        return devices.create_simulated(user.user_id, body.display_name, body.scenario_id)

    @app.post(API_PREFIX + "/devices/{id}/scan", response_model=DeviceDescriptor)
    async def scan_device(request: Request, id: str) -> DeviceDescriptor:
        user = await identity(request)
        return await devices.scan(user.user_id, id)

    @app.post(API_PREFIX + "/devices/{id}/connect", response_model=DeviceDescriptor)
    async def connect_device(request: Request, id: str) -> DeviceDescriptor:
        user = await identity(request)
        return await devices.connect(user.user_id, id)

    @app.post(API_PREFIX + "/devices/{id}/disconnect", response_model=DeviceDescriptor)
    async def disconnect_device(request: Request, id: str) -> DeviceDescriptor:
        user = await identity(request)
        return await devices.disconnect(user.user_id, id)

    # ---- SESSIONS: start / stop only (create/list/get are CAP-004) ------------------------------
    @app.post(API_PREFIX + "/sessions/{id}/start", response_model=MonitoringSession)
    async def start_session(request: Request, id: str) -> MonitoringSession:
        user = await identity(request)
        return await monitoring.start(user.user_id, id)

    @app.post(API_PREFIX + "/sessions/{id}/stop", response_model=MonitoringSession)
    async def stop_session(request: Request, id: str) -> MonitoringSession:
        user = await identity(request)
        return await monitoring.stop(user.user_id, id)

    # ---- LIVE: server -> client monitoring events only ----------------------------------------
    @app.websocket(API_PREFIX + "/sessions/{id}/live")
    async def live(websocket: WebSocket, id: str) -> None:
        await websocket.accept()
        resolved = None
        if identity_resolver is not None:
            resolved = await identity_resolver(websocket)
        if resolved is None:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return
        entry = runtime_state.sessions.get(id)
        if entry is None:
            await websocket.close(code=WS_NOT_FOUND)
            return
        if entry.owner_user_id != resolved.user_id:
            await websocket.close(code=WS_FORBIDDEN)
            return
        stream = entry.journal.subscribe()
        receive: asyncio.Task[Any] = asyncio.ensure_future(websocket.receive())
        next_event: asyncio.Task[Any] | None = None
        try:
            while True:
                next_event = asyncio.ensure_future(stream.__anext__())
                done, _ = await asyncio.wait({receive, next_event},
                                             return_when=asyncio.FIRST_COMPLETED)
                if receive in done:
                    message = receive.result()
                    if message["type"] == "websocket.disconnect":
                        return
                    # clients never control monitoring over this socket: any frame is rejected
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
