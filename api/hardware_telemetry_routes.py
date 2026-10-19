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
from product.observatory import hardware_trace
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
    service = HardwareSessions(store, MongoTelemetry(uri, database, collection, demo_database=env.get("NHM_HARDWARE_DEMO_DATABASE") or None))
    service.demo_collection = env.get("NHM_HARDWARE_DEMO_COLLECTION") or None
    service.history_import = env.get("NHM_HARDWARE_HISTORY_IMPORT", "").lower() == "on"
    if env.get("NHM_HARDWARE_HISTORY_GAP_SECONDS"):
        service.history_gap_seconds = float(env["NHM_HARDWARE_HISTORY_GAP_SECONDS"])
    app.state.hardware_sessions = service
    v2_cache = V2Cache(store)
    inference_url = env.get("NHM_PRODUCT_INFERENCE_URL", "http://127.0.0.1:8001")
    inference: dict[str, Any] = {}
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def hardware_lifespan(application: Any):
        async with previous_lifespan(application):
            await asyncio.to_thread(service.seed_demo_collection)   # the prerecorded demo session's documents, created in Mongo only if missing
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

    # ---- Observatory views of recorded-hardware sessions (read-only, EXPERIMENTAL; see product.observatory.hardware_trace) ------------------------
    def _readings(sid: str, user: str) -> list[dict[str, Any]]:
        service._row(sid, user)                                     # owner-scoped: unknown / foreign sessions are refused exactly like the Monitor routes
        with store._lock:
            rows = store._connection.execute(
                "SELECT document_id,ingested_at,ecg,bpm,spo2 FROM hardware_trace WHERE session_id=? ORDER BY ordinal", (sid,)
            ).fetchall()
        return [dict(r) for r in rows]

    async def _score(sid: str, window: dict[str, Any]) -> dict[str, Any]:
        """The experimental V2 result of one window: cached per window content (shared with the Monitor page) or scored once by the released service."""
        key = window_key(window)
        cached = await asyncio.to_thread(v2_cache.get, sid, key)
        if cached is not None:
            return cached
        client = inference.get("client")
        if client is None:
            client = inference["client"] = CapstoneInferenceClient(inference_url)
        request_model = client.build_request(window, f"{sid}~W{int(window['sequence_index']):05d}")  # one inference session per window: the released service demands monotonic timestamps per session id, and the Observatory scores windows in any order
        try:
            http = await client._http.post("/v1/infer-window", json=request_model.model_dump(mode="json"))
            outcome = client._interpret(http)
        except Exception as error:  # transport failure is reported, never invented
            return {"outcome": OutcomeKind.SYSTEM_FAILURE.value, "inference": None, "detail": repr(error)[:200]}
        response = outcome.response
        result = {"outcome": outcome.kind.value, "detail": outcome.detail, "inference": response.model_dump(mode="json") if response else None}
        if result["outcome"] in (OutcomeKind.OK.value, OutcomeKind.EXPECTED_UNUSABLE_WINDOW.value):
            await asyncio.to_thread(v2_cache.put, sid, key, result)
        return result

    @app.get("/product/v1/hardware/sessions/{sid}/observatory/windows")
    async def observatory_windows(request: Request, sid: str) -> dict[str, Any]:
        user = await owner(request)
        readings = await asyncio.to_thread(_readings, sid, user)
        return await asyncio.to_thread(hardware_trace.window_list, sid, readings)

    @app.get("/product/v1/hardware/sessions/{sid}/observatory/windows/{window_index}")
    async def observatory_window(request: Request, sid: str, window_index: int) -> dict[str, Any]:
        user = await owner(request)
        readings = await asyncio.to_thread(_readings, sid, user)
        try:
            window = await asyncio.to_thread(hardware_trace.emitted_window, sid, readings, window_index)
            response = None
            if window["ecg_quality"] != "UNUSABLE":
                response = (await _score(sid, window)).get("inference")
            trace = await asyncio.to_thread(hardware_trace.window_trace, sid, readings, window_index, response)
        except LookupError as error:
            raise ProductError(ProductErrorCode.NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise ProductError(ProductErrorCode.INVALID_REQUEST, str(error)) from error
        return trace.model_dump(mode="json")

    @app.get("/product/v1/hardware/sessions/{sid}/observatory/timeline")
    async def observatory_timeline(request: Request, sid: str, budget: int = 24) -> dict[str, Any]:
        """Replay timeline of a recorded session. At most ``budget`` (<= 48) not-yet-scored windows are scored per call; the response says how many are still pending."""
        user = await owner(request)
        readings = await asyncio.to_thread(_readings, sid, user)
        windows, _, _ = await asyncio.to_thread(hardware_trace._prepared, sid, readings)
        results: dict[str, dict[str, Any]] = {}
        todo: list[dict[str, Any]] = []
        for window in windows:
            if window["ecg_quality"] == "UNUSABLE":
                continue
            cached = await asyncio.to_thread(v2_cache.get, sid, window_key(window))
            if cached is not None:
                results[window_key(window)] = cached
            else:
                todo.append(window)
        gate = asyncio.Semaphore(6)

        async def one(window: dict[str, Any]) -> None:
            async with gate:
                results[window_key(window)] = await _score(sid, window)

        await asyncio.gather(*(one(w) for w in todo[: max(0, min(budget, 48))]))
        return await asyncio.to_thread(hardware_trace.timeline, sid, readings, results)

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
