"""Authenticated product routes for the telemetry-only MongoDB source."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Request

from product.api.errors import ProductError, ProductErrorCode
from product.hardware_telemetry import HardwareSessions, MongoTelemetry


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
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def hardware_lifespan(application: Any):
        async with previous_lifespan(application):
            try:
                yield
            finally:
                service.source.close()

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
