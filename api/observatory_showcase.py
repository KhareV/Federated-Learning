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
