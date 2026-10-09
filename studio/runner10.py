# ruff: noqa: E501
"""Orchestration of the genuine 10-round run for the unified Studio.

Executes ``fl10.runner.run_training`` (the same ``Coordinator`` and ``train_local_epoch_v2`` as every other engine; no second FedAvg) in ONE worker thread and
translates its real progress callbacks into product federation events on a ``FederationEventJournal``. Every committed state is handed to the evaluation
observer the moment the runner commits it. At most one federation run (of either engine) is active; an interrupted run is never a candidate."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fl10.runner import atomic_write, load_state
from product.federation.artifact_store import FederationArtifactStore
from product.federation.events import FederationEmitter
from product.federation.journal import FederationEventJournal
from studio import v2_init
from studio.events10 import Fl10EventTranslator
from studio.observer import EvaluationObserver

CLIENT_IDS = tuple(f"SIM_FL_SITE_{i:02d}" for i in range(8))
MODES = {"A": "CANONICAL_SYNTHETIC", "B": "LIVE_MONITORED_SITE_00"}
PHASES = ("CREATED", "BUILDING_COHORT", "MONITORING_SITE_00", "TRAINING", "EVALUATING", "EXPORTING", "DONE", "FAILED")


class StudioRunError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code, self.detail = code, detail


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Job:
    run_id: str
    owner: str
    mode: str
    created_at: str
    init: str = v2_init.INIT_FRESH               # FL_INIT_V2 (untrained, default) | MODEL_V2_FINAL (pretrained, federated fine-tuning)
    base_audit: dict[str, Any] | None = None     # compatibility audit of the pretrained start (None for FL_INIT_V2)
    status: str = "CREATED"                      # CREATED | RUNNING | COMPLETED | FAILED
    phase: str = "CREATED"
    current_round: int = 0
    failure: dict[str, str] | None = None
    candidate: dict[str, Any] | None = None
    export_status: str = "NOT_STARTED"            # NOT_STARTED | PREPARING | READY | FAILED
    cancelled: bool = False
    journal: FederationEventJournal | None = None
    emitter: FederationEmitter | None = None
    translator: Fl10EventTranslator | None = None
    task: asyncio.Future[Any] | None = field(default=None, repr=False)
    loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)


class StudioFl10Service:
    def __init__(self, *, root: Path, observer: EvaluationObserver, inference_factory: Callable[[], Any] | None, other_run_active: Callable[[], bool],
                 finalize: Callable[[str, Path], None] | None = None) -> None:
        self.root = Path(root)
        self.observer = observer
        self.events = FederationArtifactStore(self.root / "engine10_events")
        self._inference_factory = inference_factory
        self._other_active = other_run_active
        self._finalize = finalize
        self.jobs: dict[str, Job] = {}
        self._claim = asyncio.Lock()
        self._load_existing()

    # ---- identity / persistence ----------------------------------------------------------------------------------------
    def job_dir(self, run_id: str) -> Path:
        if not run_id.startswith("FL10RUN-") or "/" in run_id:
            raise StudioRunError("INVALID_RUN_ID")
        return self.root / run_id

    def _save(self, job: Job) -> None:
        meta = {"run_id": job.run_id, "owner": job.owner, "mode": job.mode, "init": job.init, "base_audit": job.base_audit, "created_at": job.created_at, "status": job.status, "phase": job.phase, "current_round": job.current_round,
                "failure": job.failure, "candidate": job.candidate, "export_status": job.export_status, "run_length": 10, "engine": "FL10_10R"}
        atomic_write(self.job_dir(job.run_id) / "meta.json", (json.dumps(meta, indent=1, sort_keys=True) + "\n").encode())

    def _load_existing(self) -> None:
        for path in sorted(self.root.glob("FL10RUN-*/meta.json")):
            meta = json.loads(path.read_text())
            job = Job(run_id=meta["run_id"], owner=meta["owner"], mode=meta["mode"], init=meta.get("init", v2_init.INIT_FRESH), base_audit=meta.get("base_audit"), created_at=meta["created_at"], status=meta["status"], phase=meta["phase"], current_round=meta["current_round"],
                      failure=meta.get("failure"), candidate=meta.get("candidate"), export_status=meta.get("export_status", "NOT_STARTED"))
            journal = FederationEventJournal(job.run_id)
            for event in self.events.read_events(job.run_id):
                journal.append(event)
            if job.status in ("CREATED", "RUNNING"):          # interrupted by a restart: documented fail-closed behaviour, never a candidate, restart from R0
                job.status, job.phase, job.candidate = "FAILED", "FAILED", None
                job.failure = {"code": "INTERRUPTED_BY_RESTART", "message": "the server restarted during this run; no candidate exists. Start a new run (restarts from R0)."}
                self._save(job)
            journal.close()
            job.journal = journal
            self.jobs[job.run_id] = job

    # ---- API ------------------------------------------------------------------------------------------------------------
    def owner_of(self, run_id: str) -> str | None:
        job = self.jobs.get(run_id)
        return job.owner if job else None

    def get(self, owner: str, run_id: str) -> Job:
        job = self.jobs.get(run_id)
        if job is None:
            raise StudioRunError("NOT_FOUND", "run not found")
        if job.owner != owner:
            raise StudioRunError("FORBIDDEN", "not the owner of this run")
        return job

    def list(self, owner: str) -> list[Job]:
        return sorted((j for j in self.jobs.values() if j.owner == owner), key=lambda j: j.created_at)

    def journal_for(self, run_id: str) -> FederationEventJournal | None:
        job = self.jobs.get(run_id)
        return job.journal if job else None

    def active(self) -> bool:
        return any(j.status == "RUNNING" for j in self.jobs.values())

    def cancel_all(self) -> None:
        for job in self.jobs.values():
            if job.status == "RUNNING":
                job.cancelled = True

    async def shutdown(self, timeout: float = 120.0) -> None:
        """Called from the application lifespan: stop running jobs at their next progress event and wait for their threads (bounded)."""
        self.cancel_all()
        tasks = [j.task for j in self.jobs.values() if j.task is not None and not j.task.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    async def create(self, owner: str, mode: str, init: str = v2_init.INIT_FRESH) -> Job:
        if init not in v2_init.INITS:
            raise StudioRunError("INVALID_REQUEST", "initialisation must be FL_INIT_V2 (untrained) or MODEL_V2_FINAL (pretrained)")
        if mode not in MODES:
            raise StudioRunError("INVALID_REQUEST", "source mode must be A (canonical synthetic cohort) or B (live-monitored simulated SITE_00)")
        if mode == "B" and self._inference_factory is None:
            raise StudioRunError("SOURCE_MODE_UNAVAILABLE", "the live-monitored simulated SITE_00 source needs the monitoring runtime")
        run_id = f"FL10RUN-{secrets.token_hex(6).upper()}"
        job = Job(run_id=run_id, owner=owner, mode=mode, init=init, created_at=_now(), loop=asyncio.get_running_loop())
        job.journal = FederationEventJournal(run_id)
        job.emitter = FederationEmitter(run_id, lambda: time.time_ns() // 1000, [job.journal.append, lambda e: self.events.append_event(run_id, e)], 0)
        job.translator = Fl10EventTranslator(job.emitter, lambda fn: job.loop.call_soon_threadsafe(fn), planned_rounds=10, client_ids=CLIENT_IDS, local_examples={c: 0 for c in CLIENT_IDS})
        self.jobs[run_id] = job
        self._save(job)
        job.translator.created()
        await asyncio.sleep(0)
        return job

    async def start(self, owner: str, run_id: str) -> Job:
        job = self.get(owner, run_id)
        async with self._claim:
            if job.status != "CREATED":
                raise StudioRunError("INVALID_STATE", f"run is {job.status}, not CREATED")
            if self.active() or self._other_active():
                raise StudioRunError("FEDERATION_RUN_ALREADY_ACTIVE", "one federation run at a time (one-laptop demonstration)")
            job.status, job.phase = "RUNNING", "BUILDING_COHORT"
            self._save(job)
        job.translator.running()  # type: ignore[union-attr]
        job.task = asyncio.ensure_future(self._execute(job))
        return job

    # ---- execution ------------------------------------------------------------------------------------------------------
    async def _execute(self, job: Job) -> None:
        try:
            await asyncio.to_thread(self._run, job)
        except Exception as error:   # failure is visible; a partial run is never presented as a candidate
            job.status, job.phase, job.candidate = "FAILED", "FAILED", None
            job.failure = {"code": getattr(error, "code", type(error).__name__), "message": str(error)[:300]}
            self._save(job)
            job.translator.failed(job.failure["code"], job.failure["message"])  # type: ignore[union-attr]
            await asyncio.sleep(0)
        finally:
            job.loop.call_soon_threadsafe(job.journal.close)  # type: ignore[union-attr]

    def _set_phase(self, job: Job, phase: str) -> None:
        job.phase = phase
        self._save(job)

    def _run(self, job: Job) -> None:
        import asyncio as aio

        from federated.wearable_fl_runner_v1 import build_cohort
        from fl10 import runner
        from scripts.run_fl10 import git_head, manifest_for, protocol_sha

        directory = self.job_dir(job.run_id)
        run_dir = directory / "run"
        self._set_phase(job, "BUILDING_COHORT")
        initial_state, initialisation = None, {"model_id": v2_init.INIT_FRESH}
        if job.init == v2_init.INIT_V2_FINAL:          # verified before any training: a digest / layout problem fails the run closed at R0
            initial_state, initialisation = v2_init.load_v2_final()
            job.base_audit = initialisation
            self._save(job)
        _, datasets, manifest = build_cohort()
        monitored: dict[str, Any] | None = None
        live = None
        if job.mode == "B":
            from final_showcase import live_link as ll
            from simulation.fl_cohort_v1 import cohort_profiles

            self._set_phase(job, "MONITORING_SITE_00")
            profile = cohort_profiles()[0]
            monitored = aio.run(ll.monitor_site00(self._inference_factory, session_id=f"LIVELINK-{job.run_id}"))
            live = ll.dataset_from_windows(monitored["windows"], profile)
            parity = ll.parity(monitored, live, profile, datasets[0].dataset_sha256) | {"inference_http_statuses": monitored["inference_http_statuses"]}
            datasets = [live, *datasets[1:]]
            manifest = manifest_for(datasets)
        examples = {d.client_id: len(d.labels) for d in datasets}
        job.translator.examples = examples  # type: ignore[union-attr]
        atomic_write(directory / "training_cohort.json", (json.dumps([{"client_id": d.client_id, "participant_id": d.participant_id, "session_id": d.session_id, "dataset_sha256": d.dataset_sha256,
                                                                       "counts": d.counts} for d in datasets], indent=1, sort_keys=True) + "\n").encode())
        self.observer.declare_pair(job.run_id, 3, 10)

        def progress(event: dict[str, Any]) -> None:
            if job.cancelled:      # cooperative stop (application shutdown): the runner fails closed, the run is never a candidate
                raise StudioRunError("CANCELLED", "the server is shutting down")
            job.translator.on_progress(event)  # type: ignore[union-attr]
            kind, r = event["event"], event.get("round", 0)
            if kind == "ROUND_OPENED":
                job.current_round = r
                if r == 1:       # R0 exists on disk before round 1 opens; its digest is the base of round 1
                    sha = event["base_state_sha256"]
                    self.observer.submit(run_id=job.run_id, run_length=10, round_id=0, state=load_state(run_dir, 0, sha), expected_digest=sha)
            elif kind == "ROUND_COMMITTED":
                sha = event["global_state_sha256"]
                self.observer.submit(run_id=job.run_id, run_length=10, round_id=r, state=load_state(run_dir, r, sha), expected_digest=sha,
                                     candidate_id=f"FL10_CANDIDATE_{job.run_id}" if r == 10 else None)

        self._set_phase(job, "TRAINING")
        pretrained = {"initial_state": initial_state, "initialisation": initialisation} if initial_state is not None else {}
        if job.mode == "A":
            report = runner.run_training(mode="A", run_id=job.run_id, out_dir=run_dir, datasets=datasets, manifest=manifest, require_prefix_parity=initial_state is None, progress=progress, git_commit=git_head(), protocol_sha256=protocol_sha(), **pretrained)
        else:
            from final_showcase import link_trace
            from fl10.trace import Fl10TrainerTap
            from product.edge.local_training_buffer import LocalTrainingBufferV1

            with Fl10TrainerTap() as tap:
                report = runner.run_training(mode="B", run_id=job.run_id, out_dir=run_dir, datasets=datasets, manifest=manifest, require_prefix_parity=False, progress=progress, git_commit=git_head(), protocol_sha256=protocol_sha(), **pretrained)
            expected = link_trace.expected_trace(live)
            buffer = LocalTrainingBufferV1(live.client_id, live.participant_id)
            buffer.ingest_dataset(live)
            trace = link_trace.verify_trace(expected, link_trace.buffer_trace(buffer), tap.calls, client_id=live.client_id, rounds=10)
            link = {"label": "LIVE-MONITORED SIMULATED ECG — NOT A REAL PHYSIOLOGICAL PATIENT", "monitoring": {k: v for k, v in (monitored or {}).items() if k != "windows"}, "parity": parity, "trace": trace,
                    "monitoring_sessions_executed": 1, "buffer_reused_for_rounds": 10, "site00_source": "LIVE_MONITORED_WINDOWS"}
            atomic_write(run_dir / "monitoring_link.json", (json.dumps(link, sort_keys=True, indent=1) + "\n").encode())
        job.candidate = {**report["candidate"], "candidate_id": f"FL10_CANDIDATE_{job.run_id}"}
        job.status, job.phase, job.current_round = "COMPLETED", "EVALUATING", 10
        self._save(job)
        job.translator.completed(10)  # type: ignore[union-attr]
        self._wait_evaluations(job)
        if self._finalize is not None:
            job.export_status = "PREPARING"
            self._set_phase(job, "EXPORTING")
            try:
                self._finalize(job.run_id, directory)
                job.export_status = "READY"
            except Exception as error:
                job.export_status = "FAILED"
                job.failure = {"code": "EXPORT_FAILED", "message": str(error)[:300]}
        self._set_phase(job, "DONE")

    def _wait_evaluations(self, job: Job, timeout: float = 1800.0) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            records = self.observer.records(job.run_id)
            if len(records) == 11 and all(r.evaluation_status in ("COMPLETED", "FAILED") for r in records) and self.observer.paired(job.run_id) is not None:
                return
            if len(records) == 11 and all(r.evaluation_status in ("COMPLETED", "FAILED") for r in records) and any(r.evaluation_status == "FAILED" for r in records):
                return
            time.sleep(0.5)
