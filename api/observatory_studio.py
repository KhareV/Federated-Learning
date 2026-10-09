# ruff: noqa: E501
"""Unified Federation Studio routes (additive, owner-scoped): ``/product/v1/studio/...``.

The frozen 3-round product routes and contract are NOT changed: a 3-round run is created and started through ``POST /product/v1/federation/runs`` exactly as before and
only OBSERVED here. ``POST /product/v1/studio/runs`` starts the separate 10-round engine. Evaluation records, figures, tables and exports are run-scoped and owner-scoped;
a run id of another user is indistinguishable from a missing one for data endpoints (403 for explicit ownership mismatches, as in the product API)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response

from api.product_app_v1_1 import WS_FORBIDDEN, WS_NOT_FOUND, WS_POLICY_VIOLATION, WS_UNAUTHENTICATED
from product.api.errors import ProductError, ProductErrorCode
from studio import STUDIO_ID, g1_cohort, v2_init
from studio.constants import (
    CLAIM_BOUNDARY,
    COHORT_USE_DETAIL,
    COHORT_USE_LABEL,
    EVAL_PROTOCOL_ID,
    OBSERVER_ID,
    RUN_LENGTHS,
)
from studio.runner10 import MODES, StudioRunError
from studio.service import StudioService, _as_product_error

MEDIA = {"svg": "image/svg+xml", "png": "image/png", "csv": "text/csv", "json": "application/json", "md": "text/markdown", "provenance": "application/json"}
STUDIO = "/product/v1/studio"
FEDERATION_RUNS = "/product/v1/federation/runs"


def register_studio(app: FastAPI, identity: Callable[[Request], Awaitable[str]], *, identity_resolver: Callable[[Any], Awaitable[Any]], artifact_root: Path, store: Any) -> StudioService:
    def inference_factory() -> Any:
        return app.state.session_service._monitoring._inference_factory()

    def other_active() -> bool:
        provider = getattr(app.state, "live_link_provider", None)
        fl10_active = getattr(app.state, "fl10_job_active", None)
        return bool((provider is not None and provider.armed) or (fl10_active is not None and fl10_active()))

    service = StudioService(root=Path(artifact_root), federation=app.state.federation_service, inference_factory=inference_factory, other_run_active=other_active)
    app.state.studio_service = service
    inner_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def studio_lifespan(application: FastAPI) -> Any:
        async with inner_lifespan(application):
            try:
                yield
            finally:        # a running 10-round job is stopped (fail closed) and the evaluation worker is released when the application stops
                await service.runner10.shutdown()
                service.observer.close()
                service.generalisation.close()

    app.router.lifespan_context = studio_lifespan

    @app.middleware("http")
    async def one_federation_run_at_a_time(request: Request, call_next: Any) -> Response:
        """A running Studio 10-round job blocks creating/starting a product 3-round LIVE run (one-laptop demonstration); the product contract itself is untouched."""
        path = request.url.path
        if request.method == "POST" and service.runner10.active() and (path == FEDERATION_RUNS or (path.startswith(FEDERATION_RUNS + "/") and path.endswith("/start"))):
            return JSONResponse(status_code=409, content={"error": {"code": "INVALID_STATE", "message": "FEDERATION_RUN_ALREADY_ACTIVE: a 10-round Studio run is active"}})
        return await call_next(request)

    def guard(call: Callable[[], Any]) -> Any:
        try:
            return call()
        except StudioRunError as error:
            raise _as_product_error(error) from error

    @app.get(f"{STUDIO}/capabilities")
    async def capabilities(request: Request) -> dict[str, Any]:
        await identity(request)
        return {"studio_id": STUDIO_ID, "run_lengths": list(RUN_LENGTHS), "default_run_length": 3,
                "ten_round": {"available": True, "engine": "FL10_10R", "rounds_by_initialisation": {"FL_INIT_V2": [10], "MODEL_V2_FINAL": [3, 10]}, "default_initialisation": v2_init.INIT_V2_FINAL, "initialisations": [{"id": k, "label": v2_init.INIT_LABELS[k], "default": k == v2_init.INIT_V2_FINAL} for k in v2_init.INITS], "source_modes": list(MODES.values()), "algorithms": ["FEDAVG"], "aggregation_modes": ["PLAIN"],
                              "unsupported": {"FEDPROX": "not implemented or verified by the 10-round engine", "SECAGG_SHADOW": "not implemented or verified by the 10-round engine"}, "expected_updates": 80},
                "three_round": {"available": True, "engine": "PRODUCT_3R", "route": FEDERATION_RUNS, "expected_updates": 24},
                "generalisation": {"cohort_id": g1_cohort.COHORT_ID, "label": g1_cohort.COHORT_USE_LABEL, "claim_boundary": g1_cohort.CLAIM_BOUNDARY, "baseline": "MODEL_V2_FINAL (unchanged, frozen)"},
                "evaluation": {"observer_id": OBSERVER_ID, "protocol_id": EVAL_PROTOCOL_ID, "threshold": 0.5, "calibration": "NONE", "cohort_use": COHORT_USE_LABEL, "cohort_use_detail": COHORT_USE_DETAIL, "claim_boundary": CLAIM_BOUNDARY}}

    @app.get(f"{STUDIO}/runs")
    async def list_runs(request: Request) -> list[dict[str, Any]]:
        user = await identity(request)
        return await asyncio.to_thread(service.list_runs, user)

    @app.post(f"{STUDIO}/runs")
    async def start_ten_round(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        user = await identity(request)
        rounds = body.get("run_length")
        if rounds == 3 and body.get("initialisation") != v2_init.INIT_V2_FINAL:
            raise ProductError(ProductErrorCode.INVALID_REQUEST, f"3-round runs from the untrained start use the frozen product contract: POST {FEDERATION_RUNS}")
        mode_names = {v: k for k, v in MODES.items()}
        if rounds not in (3, 10) or set(body) - {"run_length", "source_mode", "algorithm", "secagg_mode", "run_type", "initialisation"} or body.get("source_mode", "CANONICAL_SYNTHETIC") not in mode_names:
            raise ProductError(ProductErrorCode.INVALID_REQUEST, "run_length must be 10 (or 3 with initialisation MODEL_V2_FINAL) and source_mode CANONICAL_SYNTHETIC or LIVE_MONITORED_SITE_00")
        if body.get("algorithm", "FEDAVG") != "FEDAVG" or body.get("secagg_mode", "PLAIN") != "PLAIN" or body.get("run_type", "LIVE_RUN") != "LIVE_RUN":
            raise ProductError(ProductErrorCode.INVALID_REQUEST, "the 10-round engine supports LIVE_RUN FedAvg with plain aggregation only; an unsupported combination is never reinterpreted")
        resolved = await identity_resolver(request)
        store.upsert_user(resolved)
        try:
            job = await service.runner10.create(user, mode_names[body.get("source_mode", "CANONICAL_SYNTHETIC")], body.get("initialisation", "FL_INIT_V2"), rounds)
            job = await service.runner10.start(user, job.run_id)
        except StudioRunError as error:
            raise _as_product_error(error) from error
        return await asyncio.to_thread(service.describe, user, job.run_id)

    @app.get(STUDIO + "/runs/{run_id}")
    async def get_run(request: Request, run_id: str) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.describe, user, run_id)

    @app.get(STUDIO + "/runs/{run_id}/overview")
    async def overview(request: Request, run_id: str) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.overview, user, run_id)

    @app.get(STUDIO + "/runs/{run_id}/evaluation")
    async def evaluation(request: Request, run_id: str) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.evaluation_summary, user, run_id)

    @app.get(STUDIO + "/runs/{run_id}/evaluation/{round_id}")
    async def evaluation_round(request: Request, run_id: str, round_id: int) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.evaluation_round, user, run_id, round_id)

    @app.get(STUDIO + "/runs/{run_id}/generalisation")
    async def generalisation(request: Request, run_id: str) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.generalisation_summary, user, run_id)

    @app.get(STUDIO + "/runs/{run_id}/generalisation/curves/{round_id}")
    async def generalisation_curves(request: Request, run_id: str, round_id: int) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.generalisation_curves, user, run_id, round_id)

    @app.get(STUDIO + "/runs/{run_id}/generalisation/participants/{round_id}")
    async def generalisation_participants(request: Request, run_id: str, round_id: int) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.generalisation_participants, user, run_id, round_id)

    @app.get(STUDIO + "/runs/{run_id}/rounds/{round_id}")
    async def round_detail(request: Request, run_id: str, round_id: int) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.round_detail, user, run_id, round_id)

    @app.get(STUDIO + "/runs/{run_id}/figures")
    async def figures(request: Request, run_id: str, round: int | None = None) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.figures, user, run_id, round)

    @app.get(STUDIO + "/runs/{run_id}/tables")
    async def tables(request: Request, run_id: str) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.tables, user, run_id)

    @app.get(STUDIO + "/runs/{run_id}/exports")
    async def exports(request: Request, run_id: str) -> dict[str, Any]:
        user = await identity(request)
        return await asyncio.to_thread(service.export_manifest, user, run_id)

    @app.get(STUDIO + "/runs/{run_id}/exports/{item_id}/{fmt}")
    async def export_file(request: Request, run_id: str, item_id: str, fmt: str) -> Response:
        user = await identity(request)
        service.authorize(user, run_id)
        return await asyncio.to_thread(_verified_export, service, run_id, item_id, fmt)

    @app.websocket(STUDIO + "/runs/{run_id}/live")
    async def live(websocket: WebSocket, run_id: str) -> None:
        await websocket.accept()
        resolved = await identity_resolver(websocket)
        if resolved is None:
            await websocket.close(code=WS_UNAUTHENTICATED)
            return
        owner = service.owner_of(run_id)
        if not service.is_recorded(run_id):         # recorded FL10 evidence is a global read-only reference; every live run is owner-scoped
            if owner is None:
                await websocket.close(code=WS_NOT_FOUND)
                return
            if owner != resolved.user_id:
                await websocket.close(code=WS_FORBIDDEN)
                return
        journal = await asyncio.to_thread(service.journal_for, run_id)
        if journal is None:
            await websocket.close(code=WS_NOT_FOUND)
            return
        stream = journal.subscribe()
        receive: asyncio.Task[Any] = asyncio.ensure_future(websocket.receive())
        next_event: asyncio.Task[Any] | None = None
        try:
            while True:
                next_event = asyncio.ensure_future(stream.__anext__())
                done, _ = await asyncio.wait({receive, next_event}, return_when=asyncio.FIRST_COMPLETED)
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
            await asyncio.gather(*(t for t in (receive, next_event) if t is not None), return_exceptions=True)
            await stream.aclose()

    return service


def _verified_export(service: StudioService, run_id: str, item_id: str, fmt: str) -> Response:
    export_root = service.export_dir(run_id)
    manifest_path = export_root / "export_manifest.json"
    if not manifest_path.exists() or fmt not in MEDIA:
        raise ProductError(ProductErrorCode.NOT_FOUND, "export not found (EXPORT PREPARING or not generated)")
    manifest = json.loads(manifest_path.read_text())
    entry = (manifest["figures"].get(item_id) or manifest["tables"].get(item_id) or manifest.get("data", {}).get(item_id) or {}).get(fmt)
    if entry is None:
        raise ProductError(ProductErrorCode.NOT_FOUND, "export not found")
    from fl10.evaluate import ROOT

    recorded = manifest.get("schema_version") != "STUDIO_EXPORT_MANIFEST_V1"
    base = ROOT if recorded else export_root
    path = (base / entry["path"]).resolve()
    if not path.is_relative_to(export_root.resolve()):
        raise ProductError(ProductErrorCode.NOT_FOUND, "export path outside the run's export directory")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ProductError(ProductErrorCode.INTERNAL_PRODUCT_ERROR, "export hash mismatch")
    name = f"{item_id}.{'provenance.json' if fmt == 'provenance' else fmt}"
    return Response(content=data, media_type=MEDIA[fmt], headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Content-SHA256": entry["sha256"], "X-Export-Run-Id": run_id})
