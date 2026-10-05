# ruff: noqa: E501
"""CAPSTONE_PRODUCT_API_V1_2 -- the CAP-007 product app (additive successor of api/product_app_v1_1.py).

It COMPOSES ``create_product_app_v1_1`` (every CAP-003/CAP-004 route, behaviour and the monitoring path are
reused unchanged; the V1_1 module is neither edited nor copied) and adds exactly the ten CAP-007 routes
(federation overview/clients/runs/start/rounds/live, models list/get). Only ``GET /system`` is
re-published to report ``federation_runtime = ENABLED_ENGINEERING``. There is NO promote / deploy /
set-default / select-model route and no inference route for candidates: the released runtime keeps
MODEL_V2_FINAL. Run ownership (OWN) governs create/list/get/start/rounds/live; federation overview,
clients and models are authenticated GLOBAL_READ.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket

from api.product_app_v1_1 import (
    API_PREFIX,
    DEFAULT_DEV_ORIGINS,
    DEFAULT_INFERENCE_URL,
    WS_FORBIDDEN,
    WS_NOT_FOUND,
    WS_POLICY_VIOLATION,
    WS_UNAUTHENTICATED,
    IdentityResolver,
    create_product_app_v1_1,
)
from capstone_persistence.federation_store import FederationStore
from capstone_persistence.store import CapstoneSqliteStore
from product.api.errors import ProductError, ProductErrorCode
from product.api.models_v2 import SystemInfoV2
from product.auth.base import AuthIdentity, AuthProviderDescription
from product.devices.scenarios import TimingMode
from product.federation.artifact_store import DEFAULT_ROOT as DEFAULT_FEDERATION_ROOT
from product.federation.artifact_store import FederationArtifactStore
from product.federation.base import FederationRound, FederationRun, FLClientIdentity
from product.federation.service import FederationService, default_run_id
from product.models.candidate_artifacts import DEFAULT_ROOT as DEFAULT_CANDIDATE_ROOT
from product.models.candidate_artifacts import CandidateArtifactStore
from product.models.governance import GovernanceRuntime
from product.models.registry import ModelRegistry, RegistryError
from product.models.registry_contract import CandidateModel, ReleasedModelRef
from product.models.views import CreateFederationRunRequest, FederationOverview, ModelRegistryView
from product.session import default_runtime_identity
from product.sessions.service import IdGenerator, default_session_id

IMPLEMENTATION_ID = "CAPSTONE_PRODUCT_API_V1_2"
CAP007_ROUTES = (
    ("GET", "/federation"), ("GET", "/federation/clients"), ("POST", "/federation/runs"),
    ("GET", "/federation/runs"), ("GET", "/federation/runs/{id}"),
    ("POST", "/federation/runs/{id}/start"), ("GET", "/federation/runs/{id}/rounds"),
    ("WS", "/federation/runs/{id}/live"), ("GET", "/models"), ("GET", "/models/{id}"),
)


def create_product_app_v1_2(
    *, store: CapstoneSqliteStore, identity_resolver: IdentityResolver,
    auth_description: AuthProviderDescription,
    inference_base_url: str = DEFAULT_INFERENCE_URL,
    inference_client_factory: Callable[[], Any] | None = None,
    timing_mode: TimingMode = TimingMode.ACCELERATED,
    id_generator: IdGenerator = default_session_id,
    allowed_origins: tuple[str, ...] = DEFAULT_DEV_ORIGINS,
    federation_artifact_root: str | Path = DEFAULT_FEDERATION_ROOT,
    candidate_root: str | Path = DEFAULT_CANDIDATE_ROOT,
    run_id_generator: Callable[[], str] = default_run_id,
    checkpoint_hook: Callable[[str, int], None] | None = None,
    replay_pace_s: float = 0.0,
    auto_resume: bool = True,
    cohort_provider: Callable[[], Any] | None = None,
) -> FastAPI:
    app = create_product_app_v1_1(
        store=store, identity_resolver=identity_resolver, auth_description=auth_description,
        inference_base_url=inference_base_url, inference_client_factory=inference_client_factory,
        timing_mode=timing_mode, id_generator=id_generator, allowed_origins=allowed_origins)
    app.title, app.version = "NHM Capstone Product API (CAP-007)", "PRODUCT_API_V2"
    fed_store = FederationStore(store.path, clock=store.clock)
    registry = ModelRegistry(fed_store, CandidateArtifactStore(candidate_root))
    kwargs: dict[str, Any] = {}
    if cohort_provider is not None:
        kwargs["cohort_provider"] = cohort_provider
    service = FederationService(
        store=fed_store, artifacts=FederationArtifactStore(federation_artifact_root),
        registry=registry, governance=GovernanceRuntime(fed_store), id_generator=run_id_generator,
        checkpoint_hook=checkpoint_hook, replay_pace_s=replay_pace_s, **kwargs)
    app.state.federation_service, app.state.model_registry = service, registry
    app.state.federation_store = fed_store

    # re-publish ONLY /system (the V1_1 route would still report federation_runtime NOT_IMPLEMENTED)
    app.router.routes[:] = [r for r in app.router.routes
                            if getattr(r, "path", None) != f"{API_PREFIX}/system"]

    @asynccontextmanager
    async def lifespan(application: FastAPI):  # type: ignore[no-untyped-def]
        async with original_lifespan(application):
            application.state.federation_recovery = await service.recover(auto_resume=auto_resume)
            yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = lifespan

    upserted: set[tuple[str, str | None, str | None, bool]] = set()

    def remember(identity: AuthIdentity) -> AuthIdentity:
        key = (identity.user_id, identity.display_name, identity.email, identity.demo_mode)
        if key not in upserted:
            store.upsert_user(identity)
            upserted.add(key)
        return identity

    async def identity(request: Request) -> AuthIdentity:
        resolved = await identity_resolver(request)
        if resolved is None:
            raise ProductError(ProductErrorCode.UNAUTHENTICATED, "authentication required")
        return remember(resolved)

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
            federation_runtime="ENABLED_ENGINEERING", auth_status="CONFIGURED",
            auth_provider=auth_description.provider.value, demo_mode=auth_description.demo_mode,
            claim="research prototype; simulated device; not diagnostic; no clinical claim")

    # ---- federation (GLOBAL_READ) -----------------------------------------------------------------
    @app.get(f"{API_PREFIX}/federation", response_model=FederationOverview)
    async def federation_overview(request: Request) -> FederationOverview:
        await identity(request)
        return service.overview()

    @app.get(f"{API_PREFIX}/federation/clients", response_model=list[FLClientIdentity])
    async def federation_clients(request: Request) -> list[FLClientIdentity]:
        await identity(request)
        return await service.clients()

    # ---- federation runs (OWN) --------------------------------------------------------------------
    @app.post(f"{API_PREFIX}/federation/runs", response_model=FederationRun)
    async def create_run(request: Request, body: CreateFederationRunRequest) -> FederationRun:
        user = await identity(request)
        return service.create_run(
            user.user_id, run_type=body.run_type.value, algorithm=body.algorithm.value,
            secagg_mode=body.secagg_mode.value, planned_rounds=body.planned_rounds,
            scenario_id=body.scenario_id)

    @app.get(f"{API_PREFIX}/federation/runs", response_model=list[FederationRun])
    async def list_runs(request: Request) -> list[FederationRun]:
        return service.list_runs((await identity(request)).user_id)

    @app.get(API_PREFIX + "/federation/runs/{id}", response_model=FederationRun)
    async def get_run(request: Request, id: str) -> FederationRun:
        return service.get_run((await identity(request)).user_id, id)

    @app.post(API_PREFIX + "/federation/runs/{id}/start", response_model=FederationRun)
    async def start_run(request: Request, id: str) -> FederationRun:
        return await service.start_run((await identity(request)).user_id, id)

    @app.get(API_PREFIX + "/federation/runs/{id}/rounds", response_model=list[FederationRound])
    async def run_rounds(request: Request, id: str) -> list[FederationRound]:
        return service.rounds((await identity(request)).user_id, id)

    # ---- models (GLOBAL_READ, read-only) ----------------------------------------------------------
    @app.get(f"{API_PREFIX}/models", response_model=ModelRegistryView)
    async def list_models(request: Request) -> ModelRegistryView:
        await identity(request)
        return ModelRegistryView(**registry.view())

    @app.get(API_PREFIX + "/models/{id}", response_model=ReleasedModelRef | CandidateModel)
    async def get_model(request: Request, id: str) -> ReleasedModelRef | CandidateModel:
        await identity(request)
        try:
            return registry.get_model(id)
        except RegistryError as error:
            raise ProductError(ProductErrorCode.NOT_FOUND, "model not found") from error

    # ---- LIVE: server -> client federation events only --------------------------------------------
    @app.websocket(API_PREFIX + "/federation/runs/{id}/live")
    async def live(websocket: WebSocket, id: str) -> None:
        await websocket.accept()
        resolved = await identity_resolver(websocket)
        if resolved is None:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return
        remember(resolved)
        owner = service.owner_of(id)
        if owner is None:
            await websocket.close(code=WS_NOT_FOUND)
            return
        if owner != resolved.user_id:
            await websocket.close(code=WS_FORBIDDEN)
            return
        journal = service.journal_for(id)
        if journal is None:
            await websocket.close(code=WS_NOT_FOUND)
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
