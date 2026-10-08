# ruff: noqa: E501
"""NHM-FL10-001 routes (additive, opt-in, owner-scoped). The frozen 3-round product federation route and contract are NOT touched; the 10-round job runs the same Coordinator/trainer through fl10.runner.
At most one FL10 job (and no live federation run) may be active; an interrupted job is never a candidate and must restart from R0 (documented fail-closed behaviour)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response

from fl10 import service
from fl10.constants import METHOD_COMMIT, RECORDED
from fl10.evaluate import ROOT
from product.api.errors import ProductError, ProductErrorCode

MEDIA = {"svg": "image/svg+xml", "png": "image/png", "csv": "text/csv", "json": "application/json", "md": "text/markdown"}
PUBLICATION = ROOT / "reports/fl10/publication"


def register(app: FastAPI, prefix: str, identity: Callable[[Request], Awaitable[str]], *, artifact_root: Path, store: Any, identity_resolver: Callable[[Request], Awaitable[Any]]) -> None:
    jobs: dict[str, dict[str, Any]] = {}
    tasks: dict[str, asyncio.Task[None]] = {}
    counter = {"n": 0}
    start_lock = asyncio.Lock()
    root = Path(artifact_root) / "fl10_runs"

    @app.middleware("http")
    async def prevent_conflicting_default_run(request: Request, call_next: Any) -> Response:
        if request.method == "POST" and request.url.path == f"{prefix}/federation/runs":
            async with start_lock:
                if any(not task.done() for task in tasks.values()):
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=409,
                        content={"code": "FL10_RUN_ALREADY_ACTIVE",
                                 "message": "An opt-in ten-round run is active"},
                    )
                return await call_next(request)
        return await call_next(request)

    def inference_factory() -> Any:
        return app.state.session_service._monitoring._inference_factory()

    def public(job: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in job.items() if k not in ("owner", "payload", "dir")}

    def run_job(job: dict[str, Any]) -> None:
        """Executed in a worker thread: train (Mode A or B) -> evaluate on the frozen holdout -> assemble bundle. Raises are recorded, never swallowed."""
        import asyncio as aio

        from federated.wearable_fl_runner_v1 import build_cohort
        from fl10 import evaluate as ev
        from fl10 import runner
        from fl10.bundle import build_bundle
        from fl10.figures import export_all
        from fl10.trace import Fl10TrainerTap
        from scripts.run_fl10 import git_head, manifest_for, protocol_sha

        run_dir, eval_dir, pub_dir = job["dir"] / "run", job["dir"] / "eval", job["dir"] / "publication"
        progress = lambda event: job["events"].append({**event, "t": round(time.time(), 3)})  # noqa: E731
        job["phase"] = "BUILDING_COHORT"
        _, datasets, manifest = build_cohort()
        if job["mode"] == "B":
            from final_showcase import link_trace
            from final_showcase import live_link as ll
            from product.edge.local_training_buffer import LocalTrainingBufferV1
            from simulation.fl_cohort_v1 import cohort_profiles

            job["phase"] = "MONITORING_SITE_00"
            profile = cohort_profiles()[0]
            monitored = aio.run(ll.monitor_site00(inference_factory, session_id=f"LIVELINK-{job['job_id']}"))
            live = ll.dataset_from_windows(monitored["windows"], profile)
            job["monitoring"] = ll.parity(monitored, live, profile, datasets[0].dataset_sha256) | {"inference_http_statuses": monitored["inference_http_statuses"]}
            datasets = [live, *datasets[1:]]
            manifest = manifest_for(datasets)
        job["phase"] = "TRAINING"
        tap = Fl10TrainerTap() if job["mode"] == "B" else None
        if tap is None:
            runner.run_training(mode=job["mode"], run_id=job["job_id"], out_dir=run_dir,
                                datasets=datasets, manifest=manifest, require_prefix_parity=True,
                                progress=progress, git_commit=git_head(), protocol_sha256=protocol_sha())
        else:
            with tap:
                runner.run_training(mode="B", run_id=job["job_id"], out_dir=run_dir,
                                    datasets=datasets, manifest=manifest, require_prefix_parity=False,
                                    progress=progress, git_commit=git_head(), protocol_sha256=protocol_sha())
            expected = link_trace.expected_trace(live)
            buffer = LocalTrainingBufferV1(live.client_id, live.participant_id)
            buffer.ingest_dataset(live)
            trace = link_trace.verify_trace(
                expected, link_trace.buffer_trace(buffer), tap.calls,
                client_id=live.client_id, rounds=10,
            )
            link = {
                "label": "LIVE-MONITORED SIMULATED ECG — NOT A REAL PHYSIOLOGICAL PATIENT",
                "monitoring": {k: v for k, v in monitored.items() if k != "windows"},
                "parity": job["monitoring"], "trace": trace,
                "monitoring_sessions_executed": 1, "buffer_reused_for_rounds": 10,
                "site00_source": "LIVE_MONITORED_WINDOWS",
            }
            runner.atomic_write(run_dir / "monitoring_link.json",
                                (json.dumps(link, sort_keys=True, indent=1) + "\n").encode())
        job["phase"] = "EVALUATING"
        _, training, _ = build_cohort()
        ev.evaluate_run(run_dir, eval_dir, method_commit=METHOD_COMMIT, training_datasets=training)
        job["phase"] = "EXPORTING"
        label = "LIVE RUN (this session)"
        bundle = build_bundle(run_dir, eval_dir, source_label=label)
        export_all(bundle, pub_dir)
        job["payload"] = service.payload(run_dir, eval_dir, source_label=label)

    async def execute(job_id: str) -> None:
        job = jobs[job_id]
        try:
            await asyncio.to_thread(run_job, job)
            job["phase"] = "COMPLETED"
        except Exception as error:   # the failure is visible; a partial run is never presented as a candidate
            job.update(phase="FAILED_NOT_A_CANDIDATE", failure={"type": type(error).__name__, "message": str(error)[:300]})
            # Preserve failed attempts, including any training artifacts, but mark the
            # whole job invalid. No evaluation bundle or candidate is served.
            failure_path = job["dir"] / "job_failure.json"
            failure_path.parent.mkdir(parents=True, exist_ok=True)
            from fl10.runner import atomic_write

            atomic_write(failure_path, (json.dumps({"job_id": job_id,
                "status": "FAILED_NOT_A_CANDIDATE", "failure": job["failure"]},
                sort_keys=True, indent=1) + "\n").encode())

    @app.get(f"{prefix}/fl10/recorded")
    async def fl10_recorded(request: Request) -> list[dict[str, Any]]:
        await identity(request)
        return await asyncio.to_thread(service.recorded_index)

    @app.get(f"{prefix}/fl10/recorded/{{run_key}}")
    async def fl10_recorded_bundle(request: Request, run_key: str) -> dict[str, Any]:
        await identity(request)
        if run_key not in RECORDED:
            raise ProductError(ProductErrorCode.NOT_FOUND, "unknown recorded run")
        return await asyncio.to_thread(service.recorded, run_key)

    @app.get(f"{prefix}/fl10/recorded/{{run_key}}/exports")
    async def fl10_exports(request: Request, run_key: str) -> dict[str, Any]:
        await identity(request)
        if run_key not in RECORDED:
            raise ProductError(ProductErrorCode.NOT_FOUND, "unknown recorded run")
        return json.loads((PUBLICATION / RECORDED[run_key][0] / "export_manifest.json").read_text())

    def verified_export(export_root: Path, item_id: str, fmt: str) -> Response:
        manifest = json.loads((export_root / "export_manifest.json").read_text())
        entry = (manifest["figures"].get(item_id) or manifest["tables"].get(item_id) or {}).get(fmt)
        if entry is None or fmt not in MEDIA:
            raise ProductError(ProductErrorCode.NOT_FOUND, "export not found")
        export_root = export_root.resolve()
        export_path = (ROOT / entry["path"]).resolve()
        if not export_path.is_relative_to(export_root):
            raise ProductError(ProductErrorCode.NOT_FOUND, "export path outside recorded run")
        data = export_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ProductError(ProductErrorCode.INTERNAL_PRODUCT_ERROR, "export hash mismatch")
        return Response(content=data, media_type=MEDIA[fmt], headers={"Content-Disposition": f'attachment; filename="{item_id}.{fmt}"', "X-Content-SHA256": entry["sha256"]})

    @app.get(f"{prefix}/fl10/recorded/{{run_key}}/exports/{{item_id}}/{{fmt}}")
    async def fl10_export_file(request: Request, run_key: str, item_id: str, fmt: str) -> Response:
        await identity(request)
        if run_key not in RECORDED:
            raise ProductError(ProductErrorCode.NOT_FOUND, "unknown recorded run")
        return await asyncio.to_thread(
            verified_export, PUBLICATION / RECORDED[run_key][0], item_id, fmt
        )

    @app.post(f"{prefix}/fl10/runs")
    async def fl10_start(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        user_id = await identity(request)
        mode = body.get("mode")
        if mode not in ("A", "B") or set(body) - {"mode"}:
            raise ProductError(ProductErrorCode.INVALID_REQUEST, "mode must be 'A' or 'B'")
        async with start_lock:
            if any(not task.done() for task in tasks.values()):
                raise ProductError(ProductErrorCode.INVALID_STATE, "FL10_RUN_ALREADY_ACTIVE")
            if app.state.federation_service.active_live_run() or app.state.live_link_provider.armed:
                raise ProductError(ProductErrorCode.INVALID_STATE, "FEDERATION_RUN_ALREADY_ACTIVE")
            resolved = await identity_resolver(request)
            store.upsert_user(resolved)
            counter["n"] += 1
            job_id = f"FL10-{mode}-{int(time.time())}-{counter['n']:02d}"
            directory = root / job_id
            if directory.exists():
                raise ProductError(ProductErrorCode.INVALID_STATE, "FL10_RUN_ARTIFACT_ALREADY_EXISTS")
            jobs[job_id] = {"job_id": job_id, "owner": user_id, "mode": mode,
                            "phase": "STARTING", "events": [], "dir": directory,
                            "source_label": "LIVE RUN (this session)",
                            "candidate_promoted": False,
                            "note": "Opt-in 10-round synthetic engineering run. "
                                    "Interruption leaves NO candidate; restart from R0."}
            tasks[job_id] = asyncio.create_task(execute(job_id))
            return public(jobs[job_id])

    def owned(user_id: str, job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None or job["owner"] != user_id:
            raise ProductError(ProductErrorCode.NOT_FOUND, "FL10 run not found")
        return job

    @app.get(f"{prefix}/fl10/runs/{{job_id}}")
    async def fl10_status(request: Request, job_id: str) -> dict[str, Any]:
        job = owned(await identity(request), job_id)
        rounds_done = sum(1 for e in job["events"] if e.get("event") == "ROUND_COMMITTED")
        return {**public(job), "rounds_committed": rounds_done, "events": job["events"][-40:]}

    @app.get(f"{prefix}/fl10/runs/{{job_id}}/bundle")
    async def fl10_job_bundle(request: Request, job_id: str) -> dict[str, Any]:
        job = owned(await identity(request), job_id)
        if job["phase"] != "COMPLETED" or "payload" not in job:
            raise ProductError(ProductErrorCode.INVALID_STATE, f"run is {job['phase']}, not COMPLETED")
        return job["payload"]

    @app.get(f"{prefix}/fl10/runs/{{job_id}}/exports/{{item_id}}/{{fmt}}")
    async def fl10_job_export(request: Request, job_id: str, item_id: str, fmt: str) -> Response:
        job = owned(await identity(request), job_id)
        if job["phase"] != "COMPLETED":
            raise ProductError(ProductErrorCode.INVALID_STATE, "FL10 run is not complete")
        return await asyncio.to_thread(
            verified_export, job["dir"] / "publication", item_id, fmt
        )
