"""CAPSTONE_PRODUCT_API_V1_3: additive CAP-009 history and research views.

Composes V1_2 unchanged. Exactly four CAP-009 GET routes are added; /system is
re-published solely to identify this implementation. No inference or FL controls.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from api.product_app_v1_1 import (
    API_PREFIX,
    DEFAULT_DEV_ORIGINS,
    DEFAULT_INFERENCE_URL,
    IdentityResolver,
)
from api.product_app_v1_2 import create_product_app_v1_2
from capstone_persistence.session_evidence_store import SessionEvidenceStore
from capstone_persistence.store import CapstoneSqliteStore
from product.api.errors import ProductError, ProductErrorCode
from product.api.models_v2 import SystemInfoV2
from product.auth.base import AuthIdentity, AuthProviderDescription
from product.devices.scenarios import TimingMode
from product.federation.artifact_store import DEFAULT_ROOT as DEFAULT_FEDERATION_ROOT
from product.history.models import SessionSummary, SessionTimeline
from product.models.candidate_artifacts import DEFAULT_ROOT as DEFAULT_CANDIDATE_ROOT
from product.research.models import FlResearchEvidence, MlResearchEvidence
from product.research.service import ResearchEvidenceService
from product.session import default_runtime_identity
from product.sessions.service import IdGenerator, default_session_id

IMPLEMENTATION_ID = "CAPSTONE_PRODUCT_API_V1_3"
CAP009_ROUTES = (
    ("GET", "/sessions/{id}/summary"),
    ("GET", "/sessions/{id}/timeline"),
    ("GET", "/research/ml"),
    ("GET", "/research/fl"),
)


def create_product_app_v1_3(
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
    kwargs: dict[str, Any] = {}
    if run_id_generator is not None:
        kwargs["run_id_generator"] = run_id_generator
    app = create_product_app_v1_2(
        store=store, identity_resolver=identity_resolver,
        auth_description=auth_description, inference_base_url=inference_base_url,
        inference_client_factory=inference_client_factory, timing_mode=timing_mode,
        id_generator=id_generator, allowed_origins=allowed_origins,
        federation_artifact_root=federation_artifact_root, candidate_root=candidate_root,
        checkpoint_hook=checkpoint_hook, replay_pace_s=replay_pace_s,
        auto_resume=auto_resume, cohort_provider=cohort_provider, **kwargs,
    )
    app.title = "NHM Capstone Product API (CAP-009)"
    evidence = SessionEvidenceStore(store.path, clock=store.clock)
    research = ResearchEvidenceService()
    app.state.session_evidence_store = evidence
    app.state.research_evidence_service = research

    # Same narrow successor pattern as V1_2: no other inherited route is replaced.
    app.router.routes[:] = [route for route in app.router.routes
                            if getattr(route, "path", None) != f"{API_PREFIX}/system"]

    upserted: set[tuple[str, str | None, str | None, bool]] = set()

    async def identity(request: Request) -> AuthIdentity:
        resolved = await identity_resolver(request)
        if resolved is None:
            raise ProductError(ProductErrorCode.UNAUTHENTICATED, "authentication required")
        key = (resolved.user_id, resolved.display_name, resolved.email, resolved.demo_mode)
        if key not in upserted:
            store.upsert_user(resolved)
            upserted.add(key)
        return resolved

    @app.get(f"{API_PREFIX}/system", response_model=SystemInfoV2)
    async def system() -> SystemInfoV2:
        runtime = default_runtime_identity()
        return SystemInfoV2(
            product_api_version="PRODUCT_API_V2",
            product_api_implementation=IMPLEMENTATION_ID,
            capstone_protocol="CAPSTONE_PRODUCT_PROTOCOL_V1",
            monitoring_protocol="CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1",
            software_system=runtime.software_system_id, model_id=runtime.model_id,
            calibration_id=runtime.calibration_id,
            api_contract_version=runtime.api_contract_version,
            hardware_mode="SIMULATED_ONLY", physical_hardware_available=False,
            persistence_mode="SQLITE", federation_runtime="ENABLED_ENGINEERING",
            auth_status="CONFIGURED", auth_provider=auth_description.provider.value,
            demo_mode=auth_description.demo_mode,
            claim="research prototype; simulated device; not diagnostic; no clinical claim",
        )

    @app.get(f"{API_PREFIX}/sessions/{{id}}/summary", response_model=SessionSummary)
    async def session_summary(request: Request, id: str) -> SessionSummary:
        return evidence.summary(id, (await identity(request)).user_id)

    @app.get(f"{API_PREFIX}/sessions/{{id}}/timeline", response_model=SessionTimeline)
    async def session_timeline(request: Request, id: str) -> SessionTimeline:
        return evidence.timeline(id, (await identity(request)).user_id)

    @app.get(f"{API_PREFIX}/research/ml", response_model=MlResearchEvidence)
    async def research_ml(request: Request) -> MlResearchEvidence:
        await identity(request)
        return research.ml()

    @app.get(f"{API_PREFIX}/research/fl", response_model=FlResearchEvidence)
    async def research_fl(request: Request) -> FlResearchEvidence:
        await identity(request)
        return research.fl()

    return app
