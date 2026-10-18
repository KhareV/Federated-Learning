# ruff: noqa: E501
"""Live federation jobs for RECORDED-HARDWARE runs, observed through the same Studio surface as every other run.

A hardware run is validated and prepared on the caller's thread (any data problem is an immediate 4xx), then trained in ONE worker thread. The trainer's real progress
callbacks are translated by the unchanged ``Fl10EventTranslator`` into PRODUCT_LIVE_EVENT_V1 federation events on a ``FederationEventJournal`` (and persisted), so the Live page
renders a hardware run exactly like a synthetic one. At most one hardware run is active; a run interrupted by a restart is reported FAILED (never a result)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from product.federation.artifact_store import FederationArtifactStore
from product.federation.base import AggregationMode, Algorithm, RunType
from product.federation.events import FederationEmitter
from product.federation.journal import FederationEventJournal
from studio.events10 import Fl10EventTranslator
from studio.hardware_bundle import ENGINE, MODE
from studio.hardware_demo import CLIENT_IDS, MODEL_ID, HardwareDemoService

RUN_PREFIX = "HDFLRUN-"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class HardwareJob:
    run_id: str
    owner: str
    rounds: int
    algorithm: str
    secagg_mode: str
    initialisation: str
    warm_info: dict[str, Any] | None
    created_at: str
    cohort: str = "ORIGINAL"                       # the synthetic cohort the seven peers (and the evaluation holdout) come from: ORIGINAL | REALISTIC (pretrained-V2 family only)
    client_ids: tuple[str, ...] = CLIENT_IDS       # the logical clients of this run (eight recorded blocks, or one recorded client + seven synthetic peers for the pretrained-V2 family)
    status: str = "RUNNING"                       # RUNNING | COMPLETED | FAILED
    phase: str = "TRAINING"
    current_round: int = 0
    failure: dict[str, str] | None = None
    export_status: str = "NOT_STARTED"             # NOT_STARTED | PREPARING | READY | FAILED
    journal: FederationEventJournal | None = None
    translator: Fl10EventTranslator | None = None
    thread: threading.Thread | None = field(default=None, repr=False)


class HardwareRunJobs:
    def __init__(self, demo: HardwareDemoService, root: Path, finalize: Any = None) -> None:
        self.demo = demo
        self._finalize = finalize                  # (run_id, run_dir) -> None; renders the figure/table exports of a completed run
        self.events = FederationArtifactStore(Path(root) / "hardware_demo_events")
        self.jobs: dict[str, HardwareJob] = {}
        self.state_sink: Any = None                # (run_id, run_length, round_id, state, digest) -> None; lets a V2-family run mirror its committed states to the unseen-cohort lane
        self._lock = threading.Lock()
        self._load_existing()

    # ---- persistence -------------------------------------------------------------------------------------------------------
    def _load_existing(self) -> None:
        for path in sorted(self.demo.root.glob(f"{RUN_PREFIX}*/run.json")):
            data = json.loads(path.read_text())
            run_id = data["run_id"]
            status = data.get("status", "COMPLETED")
            failure = data.get("failure")
            if status == "RUNNING":                # interrupted by a restart: fail closed, never presented as a result
                status, failure = "FAILED", {"code": "INTERRUPTED_BY_RESTART", "message": "the server restarted during this run; start a new run."}
                data |= {"status": status, "failure": failure}
                path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
            journal = FederationEventJournal(run_id)
            for event in self.events.read_events(run_id):
                journal.append(event)
            journal.close()
            exported = (self.demo.root / run_id / "export" / "export_manifest.json").exists()
            self.jobs[run_id] = HardwareJob(
                run_id=run_id, owner=data["owner"], rounds=int(data["rounds_planned"]), algorithm=data["algorithm"], secagg_mode=data["secagg_mode"],
                initialisation=data["model"]["initialisation"], warm_info=data["model"].get("base_audit") if data["model"]["initialisation"] == "MODEL_V2_FINAL" else data["model"].get("warm_start"), created_at=data["created_at"], client_ids=tuple(data.get("client_ids") or CLIENT_IDS), cohort=data.get("cohort", "ORIGINAL"), status=status,
                phase="DONE" if status == "COMPLETED" else "FAILED", current_round=len(data["rounds"]), failure=failure, journal=journal,
                export_status="READY" if exported else ("NOT_STARTED" if status == "COMPLETED" else "NOT_STARTED"))

    # ---- API ------------------------------------------------------------------------------------------------------------
    def owner_of(self, run_id: str) -> str | None:
        job = self.jobs.get(run_id)
        return job.owner if job else None

    def journal_for(self, run_id: str) -> FederationEventJournal | None:
        job = self.jobs.get(run_id)
        return job.journal if job else None

    def list(self, owner: str) -> list[HardwareJob]:
        return sorted((j for j in self.jobs.values() if j.owner == owner), key=lambda j: j.created_at)

    def active(self) -> bool:
        return any(j.status == "RUNNING" for j in self.jobs.values())

    def start(self, owner: str, loop: asyncio.AbstractEventLoop, **config: Any) -> HardwareJob:
        """Validate + prepare synchronously (ValueError / LookupError / PermissionError propagate), then train in a worker thread."""
        if not self.demo._run_lock.acquire(blocking=False):
            raise RuntimeError("HARDWARE_DEMO_RUN_ALREADY_ACTIVE")
        try:
            ctx = self.demo.prepare(owner, **config)
        except BaseException:
            self.demo._run_lock.release()
            raise
        run_id = ctx["run_id"]
        ctx["state_sink"] = self.state_sink
        job = HardwareJob(run_id=run_id, owner=owner, rounds=ctx["rounds"], algorithm=ctx["algorithm"], secagg_mode=ctx["secagg_mode"], initialisation=ctx["initialisation"],
                          warm_info=ctx["warm_info"], created_at=_now(), client_ids=tuple(ctx.get("client_ids") or CLIENT_IDS), cohort=ctx.get("cohort", "ORIGINAL"))
        job.journal = FederationEventJournal(run_id)
        emitter = FederationEmitter(run_id, lambda: time.time_ns() // 1000, [job.journal.append, lambda e: self.events.append_event(run_id, e)], 0)
        job.translator = Fl10EventTranslator(
            emitter, lambda fn: loop.call_soon_threadsafe(fn), planned_rounds=job.rounds, client_ids=job.client_ids, local_examples=dict(ctx["examples"]),
            run_type=RunType.LIVE_RUN, algorithm=Algorithm(job.algorithm), secagg_mode=AggregationMode(job.secagg_mode))
        directory = self.demo.root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        initial = self.demo._result(ctx, status="RUNNING", started_at=job.created_at, completed_at=None, secagg=None, round_rows=[], progression={})
        (directory / "run.json").write_text(json.dumps(initial, indent=2, sort_keys=True) + "\n")
        with self._lock:
            self.jobs[run_id] = job
        job.translator.created()
        job.translator.running()
        job.thread = threading.Thread(target=self._execute, args=(job, ctx, loop), name=f"hardware-demo-{run_id}", daemon=True)
        job.thread.start()
        return job

    def _execute(self, job: HardwareJob, ctx: dict[str, Any], loop: asyncio.AbstractEventLoop) -> None:
        def progress(event: dict[str, Any]) -> None:
            job.translator.on_progress(event)  # type: ignore[union-attr]
            if event["event"] == "ROUND_OPENED":
                job.current_round = int(event["round"])

        try:
            self.demo.train(ctx, progress)
            job.status, job.phase, job.current_round = "COMPLETED", "DONE", job.rounds
            job.translator.completed(job.rounds)  # type: ignore[union-attr]
        except Exception as error:                      # a partial run is never presented as a result
            job.status, job.phase = "FAILED", "FAILED"
            job.failure = {"code": getattr(error, "code", type(error).__name__), "message": str(error)[:300]}
            path = self.demo.root / job.run_id / "run.json"
            try:
                data = json.loads(path.read_text())
                path.write_text(json.dumps(data | {"status": "FAILED", "failure": job.failure}, indent=2, sort_keys=True) + "\n")
            except OSError:
                pass
            job.translator.failed(job.failure["code"], job.failure["message"])  # type: ignore[union-attr]
        finally:
            loop.call_soon_threadsafe(job.journal.close)  # type: ignore[union-attr]
            self.demo._run_lock.release()
        if job.status == "COMPLETED" and self._finalize is not None:
            job.export_status = "PREPARING"
            try:
                self._finalize(job.run_id, self.demo.root / job.run_id)
                job.export_status = "READY"
            except Exception as error:
                job.export_status = "FAILED"
                job.failure = {"code": "EXPORT_FAILED", "message": str(error)[:300]}

    # ---- descriptors (the StudioRun shape the Live page already consumes) ----------------------------------------------
    @staticmethod
    def _base_model(job: HardwareJob) -> dict[str, Any]:
        info = job.warm_info or {}
        if job.initialisation == "MODEL_V2_FINAL" and info.get("kind") == "CANDIDATE":     # the V2-family run started from a stored engineering candidate
            return {"model_id": info.get("model_id"), "kind": "CANDIDATE", "family": "V2", "label": info.get("label"), "state_sha256": info.get("state_sha256"), "architecture_id": info.get("architecture_id"),
                    "training_target_of_checkpoint": info.get("training_target_of_checkpoint"), "parent_model_id": info.get("parent_model_id"), "source_run_id": info.get("source_run_id"),
                    "source_kind": info.get("source_kind"), "candidate_cohort": info.get("candidate_cohort"), "candidate_run_length": info.get("candidate_run_length"), "initialisation": None}
        if job.initialisation == "MODEL_V2_FINAL":     # pretrained V2 fine-tuned on resampled recorded windows (studio.hardware_v2)
            return {"model_id": "MODEL_V2_FINAL", "label": "Pretrained V2 (MODEL_V2_FINAL) — federated fine-tuning on resampled recorded windows", "state_sha256": info.get("state_sha256"),
                    "checkpoint_sha256": info.get("checkpoint_sha256"), "state_entries": info.get("state_entries"), "architecture_id": info.get("architecture_id"),
                    "training_target_of_checkpoint": info.get("training_target_of_checkpoint"), "initialisation": None}
        return {"model_id": MODEL_ID, "label": ("Warm start from " + str(info.get("source_run_id"))) if job.initialisation == "WARM_START" else "Fresh seeded initialisation (untrained)",
                "state_sha256": info.get("source_state_sha256"), "initialisation": job.initialisation}

    def describe(self, job: HardwareJob) -> dict[str, Any]:
        done = job.status == "COMPLETED"
        return {
            "run_id": job.run_id, "run_length": job.rounds, "engine": ENGINE, "origin": "LIVE", "run_type": "LIVE_RUN", "algorithm": job.algorithm, "secagg_mode": job.secagg_mode,
            "source_mode": "RECORDED_HARDWARE", "status": job.status, "phase": job.phase, "current_round": job.current_round, "planned_rounds": job.rounds,
            "client_ids": list(job.client_ids), "cohort": job.cohort, "candidate": None, "failure": job.failure,
            "label": f"{job.rounds}-round recorded-hardware run" + (" — warm start" if job.initialisation == "WARM_START" else " — candidate start" if (job.warm_info or {}).get("kind") == "CANDIDATE" else " — pretrained V2" if job.initialisation == "MODEL_V2_FINAL" else ""),
            "base_model": self._base_model(job),
            "source_label": "RECORDED HARDWARE (this account)", "replay_of": None,
            "evaluation": {"available": True, "source": "LIVE", "evaluation_run_id": job.run_id, "reason": None, "revision": job.current_round + (1 if done else 0)},
            "export_status": job.export_status, "created_at": job.created_at, "mode": MODE,
        }
