# ruff: noqa: E501
"""NHM-FINAL-SHOWCASE-001 read-only routes: the authoritative research bundle and the exported publication files. Additive; no frozen route is touched."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response

from final_showcase import research
from product.api.errors import ProductError, ProductErrorCode

EXPORT_DIR = research.ROOT / "reports/final_showcase/publication"
MEDIA = {"svg": "image/svg+xml", "png": "image/png", "csv": "text/csv", "json": "application/json", "md": "text/markdown"}


def _manifest() -> dict[str, Any]:
    path = EXPORT_DIR / "export_manifest.json"
    if not path.exists():
        raise ProductError(ProductErrorCode.NOT_FOUND, "publication exports not generated")
    return json.loads(path.read_text())


def register(app: FastAPI, prefix: str, identity: Callable[[Request], Awaitable[str]]) -> None:
    @app.get(f"{prefix}/showcase/bundle")
    async def showcase_bundle(request: Request) -> dict[str, Any]:
        await identity(request)
        try:
            return await asyncio.to_thread(research.bundle)
        except research.ResearchError as error:
            raise ProductError(ProductErrorCode.INTERNAL_PRODUCT_ERROR, str(error)) from error

    @app.get(f"{prefix}/showcase/exports")
    async def showcase_exports(request: Request) -> dict[str, Any]:
        await identity(request)
        return _manifest()

    @app.get(f"{prefix}/showcase/exports/{{item_id}}/{{fmt}}")
    async def showcase_export_file(request: Request, item_id: str, fmt: str) -> Response:
        await identity(request)
        manifest = _manifest()
        entry = (manifest["figures"].get(item_id) or manifest["tables"].get(item_id) or {}).get(fmt)
        if entry is None or fmt not in MEDIA:
            raise ProductError(ProductErrorCode.NOT_FOUND, "export not found")
        data = Path(research.ROOT / entry["path"]).read_bytes()
        return Response(content=data, media_type=MEDIA[fmt], headers={"Content-Disposition": f'attachment; filename="{item_id}.{fmt}"', "X-Content-SHA256": entry["sha256"]})


# ---------------------------------------------------------------- live-monitored SITE_00 link (opt-in)
LINK_ROOT_NAME = "live_link"


def register_live_link(app: FastAPI, prefix: str, identity: Callable[[Request], Awaitable[str]], *, artifact_root: Path,
                       store: Any, identity_resolver: Callable[[Request], Awaitable[Any]]) -> None:
    from final_showcase import live_link as ll

    links: dict[str, dict[str, Any]] = {}
    tasks: dict[str, asyncio.Task[None]] = {}
    counter = {"n": 0}

    def inference_factory() -> Any:
        return app.state.session_service._monitoring._inference_factory()

    async def execute(link_id: str, user_id: str) -> None:
        record = links[link_id]

        def phase(name: str, data: dict[str, Any]) -> None:
            record["phase"] = name
            record.update(data)

        try:
            result = await ll.run_live_link(service=app.state.federation_service, provider=app.state.live_link_provider, inference_factory=inference_factory,
                                            user_id=user_id, link_id=link_id, on_phase=phase)
            record.update(result)
            record["phase"] = "COMPLETED" if result["status"] == "COMPLETED" else "RUN_" + result["status"]
        except ll.LiveLinkBlocked as error:
            record.update(phase="BLOCKED", blocked={"code": error.code, "detail": error.detail}, trained=False,
                          note="Truthful blocked state: capture did not reach the FL boundary; no federation run was started and nothing was fabricated.")
        except Exception as error:  # surfaced, never swallowed
            app.state.live_link_provider.disarm()
            record.update(phase="BLOCKED", blocked={"code": "LIVE_LINK_INTERNAL_ERROR", "detail": type(error).__name__}, trained=False)
        finally:
            directory = artifact_root / LINK_ROOT_NAME
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{link_id}.json").write_text(json.dumps({k: v for k, v in record.items() if k != "owner"}, indent=1, sort_keys=True, default=str) + "\n")

    @app.post(f"{prefix}/live-link/runs")
    async def live_link_start(request: Request) -> dict[str, Any]:
        user_id = await identity(request)
        resolved = await identity_resolver(request)
        store.upsert_user(resolved)   # the federation tables reference the user row
        if any(t for t in tasks.values() if not t.done()) or app.state.live_link_provider.armed:
            raise ProductError(ProductErrorCode.INVALID_STATE, "LIVE_LINK_ALREADY_ACTIVE")
        if app.state.federation_service.active_live_run():
            raise ProductError(ProductErrorCode.INVALID_STATE, "FEDERATION_RUN_ALREADY_ACTIVE")
        counter["n"] += 1
        link_id = f"LL{counter['n']:04d}"
        links[link_id] = {"link_id": link_id, "owner": user_id, "phase": "STARTING", "link_label": ll.LINK_LABEL, "mode": "OPT_IN_LIVE_MONITORED_SITE_00", "production_deployed": False}
        tasks[link_id] = asyncio.create_task(execute(link_id, user_id))
        return {k: v for k, v in links[link_id].items() if k != "owner"}

    @app.get(f"{prefix}/live-link/runs/{{link_id}}")
    async def live_link_status(request: Request, link_id: str) -> dict[str, Any]:
        user_id = await identity(request)
        record = links.get(link_id)
        if record is None or record["owner"] != user_id:
            raise ProductError(ProductErrorCode.NOT_FOUND, "live link not found")
        return {k: v for k, v in record.items() if k != "owner"}
