"""Authenticated product routes for the telemetry-only MongoDB source."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Request

from api.hardware_v2_experimental import ASSUMPTIONS, LABEL, MIN_SECONDS_FOR_FIRST_WINDOW, V2Cache, build_windows, window_key
from product.api.errors import ProductError, ProductErrorCode
from product.hardware_telemetry import HardwareSessions, MongoTelemetry
from product.inference.client import CapstoneInferenceClient, OutcomeKind
from product.session import default_runtime_identity

V2_WINDOWS_RETURNED = 12
V2_NEW_INFERENCES_PER_REQUEST = 6


def install_hardware_routes(
    app: Any, store: Any, identity_resolver: Any, env: Any = os.environ
) -> None:
    if env.get("NHM_HARDWARE_MONGO_ENABLED", "").lower() != "true":
        return
    uri, database, collection = (
        env.get(k, "")
        for k in (
            "NHM_HARDWARE_MONGO_URI",
            "NHM_HARDWARE_MONGO_DATABASE",
            "NHM_HARDWARE_MONGO_COLLECTION",
        )
    )
    if not all((uri, database, collection)):
        raise ValueError("HARDWARE_MONGO_CONFIGURATION_INCOMPLETE")
    service = HardwareSessions(store, MongoTelemetry(uri, database, collection))
    app.state.hardware_sessions = service
    v2_cache = V2Cache(store)
    inference_url = env.get("NHM_PRODUCT_INFERENCE_URL", "http://127.0.0.1:8001")
    inference: dict[str, Any] = {}
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def hardware_lifespan(application: Any):
        async with previous_lifespan(application):
            try:
                yield
            finally:
                service.source.close()
                if "client" in inference:
                    await inference["client"].aclose()

    app.router.lifespan_context = hardware_lifespan

    async def owner(request: Request) -> str:
        identity = await identity_resolver(request)
        if identity is None:
            raise ProductError(ProductErrorCode.UNAUTHENTICATED, "authentication required")
        store.upsert_user(identity)
        return identity.user_id

    @app.post("/product/v1/hardware/sessions")
    async def start(request: Request) -> dict[str, Any]:
        return await asyncio.to_thread(service.start, await owner(request))

    @app.get("/product/v1/hardware/sessions")
    async def list_sessions(request: Request) -> list[dict[str, Any]]:
        return await asyncio.to_thread(service.list, await owner(request))

    @app.get("/product/v1/hardware/sessions/{sid}")
    async def detail(request: Request, sid: str, after: int = 0) -> dict[str, Any]:
        return await asyncio.to_thread(service.detail, sid, await owner(request), after)

    @app.get("/product/v1/hardware/sessions/{sid}/poll")
    async def poll(request: Request, sid: str, after: int = 0) -> dict[str, Any]:
        return await asyncio.to_thread(service.poll, sid, await owner(request), after)

    @app.post("/product/v1/hardware/sessions/{sid}/stop")
    async def stop(request: Request, sid: str) -> dict[str, Any]:
        return await asyncio.to_thread(service.stop, sid, await owner(request))

    @app.get("/product/v1/hardware/sessions/{sid}/v2-experimental")
    async def v2_experimental(request: Request, sid: str) -> dict[str, Any]:
        """EXPERIMENTAL: V2 on resampled hardware telemetry. Never validated, never diagnostic."""
        user = await owner(request)
        detail = await asyncio.to_thread(service.detail, sid, user, 0)
        model_id = default_runtime_identity().model_id
        windows, summary = await asyncio.to_thread(build_windows, detail["readings"], sid, model_id)
        client = inference.get("client")
        if client is None:
            client = inference["client"] = CapstoneInferenceClient(inference_url)
        shown, budget = [], V2_NEW_INFERENCES_PER_REQUEST
        for window in windows[-V2_WINDOWS_RETURNED:]:
            key = window_key(window)
            result = await asyncio.to_thread(v2_cache.get, sid, key)
            if result is None and budget > 0:
                budget -= 1
                request_model = client.build_request(window, sid)
                try:
                    http = await client._http.post("/v1/infer-window", json=request_model.model_dump(mode="json"))
                    outcome = client._interpret(http)
                except Exception as error:  # transport failure is reported, never invented
                    result = {"outcome": OutcomeKind.SYSTEM_FAILURE.value, "inference": None, "detail": repr(error)[:200]}
                else:
                    response = outcome.response
                    result = {
                        "outcome": outcome.kind.value,
                        "detail": outcome.detail,
                        "inference": response.model_dump(mode="json") if response else None,
                    }
                if result["outcome"] in (OutcomeKind.OK.value, OutcomeKind.EXPECTED_UNUSABLE_WINDOW.value):
                    await asyncio.to_thread(v2_cache.put, sid, key, result)
            shown.append(
                {
                    "window_id": window["window_id"],
                    "wall_time": window["wall_time"],
                    "stream_seconds": window["timestamp_us"] / 1e6,
                    "ecg_quality": window["ecg_quality"],
                    "quality_reasons": window["diagnostics"]["quality_reasons"],
                    "short_gap": window["diagnostics"]["short_gap"],
                    "long_gap_or_missing": window["diagnostics"]["long_gap_or_missing"],
                    "missing_slots": window["diagnostics"]["missing_slots"],
                    "ppg_context": window["ppg_context"],
                    "result": result or {"outcome": "PENDING", "inference": None, "detail": None},
                }
            )
        return {
            "version": "HARDWARE_V2_EXPERIMENTAL_V1",
            "label": LABEL,
            "valid": False,
            "diagnostic": False,
            "model_id": model_id,
            "assumptions": ASSUMPTIONS,
            "min_seconds_for_first_window": MIN_SECONDS_FOR_FIRST_WINDOW,
            "summary": summary,
            "windows": shown,
            "session_status": detail["status"],
        }
