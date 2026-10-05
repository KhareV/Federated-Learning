# ruff: noqa: E501
"""CAPSTONE_FEDERATION_SERVICE_V1 -- the live federation orchestrator.

Glue only. It creates/starts runs, verifies the per-round base-state lineage, builds one
CAPSTONE_FL_CLIENT_ADAPTER_V2 per client per round over the CAP-006 local buffers, submits the genuine
V2 envelopes to the UNCHANGED ``federated.wearable_fl_system_v1.Coordinator``, lets that coordinator
(through the unchanged ``aggregate_weighted_deltas``) aggregate, persists run/round/client rows and the
event journal, writes round-boundary checkpoints, creates the single final-round candidate and runs the
structural governance. It contains NO training, aggregation or inference mathematics and never imports
a truth module. Blocking work (a local epoch, aggregation, the SecAgg shadow) runs in worker threads.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from capstone_persistence.federation_store import FederationStore
from federated.model_v2_fl import state_sha
from federated.wearable_fl_runner_v1 import new_session
from federated.wearable_fl_system_v1 import Coordinator, semantic_digest, state_spec_sha
from product.api.errors import ProductError, ProductErrorCode
from product.events import FederationLiveEvent
from product.federation.artifact_store import FederationArtifactStore
from product.federation.base import (
    AggregationMode,
    Algorithm,
    ClientState,
    FederationRound,
    FederationRun,
    FLClientIdentity,
    RoundState,
    RunState,
    RunType,
    SecAggStatus,
)
from product.federation.client_v2 import CapstoneFlClientAdapterV2
from product.federation.events import FederationEmitter, clone_event_for_replay
from product.federation.execution_binding import (
    BINDING_ID,
    PROTOCOL_ID,
    PUBLIC_SCENARIO,
    RUN_BASE_MODEL_ID,
    BindingViolation,
    check_public_request,
    frozen_fl_init_sha,
    validate_round_transition_v2,
    verify_round_base,
)
from product.federation.journal import FederationEventJournal
from product.federation.local_cohort import build_client
from product.federation.recovery import assess
from product.federation.replay import retarget
from product.federation.secagg_shadow import SecAggShadowFailure, run_round1_shadow
from product.federation.update_bridge import export_envelope
from product.models.governance import GovernanceRuntime, ValidationEvidence, run_checks
from product.models.registry import ModelRegistry
from product.models.views import FederationOverview
from simulation.fl_cohort_v1 import COHORT_ID

SERVICE_ID = "CAPSTONE_FEDERATION_SERVICE_V1"
CLIENT_COUNT = 8
BANNER = ("FL ENGINEERING DEMO - synthetic virtual clients on one laptop; engineering candidate only; "
          "no scientific evidence; nothing is deployed")
TERMINAL_RUN = (RunState.COMPLETED.value, RunState.FAILED.value)
IdGenerator = Callable[[], str]


def default_run_id() -> str:
    return f"FEDRUN-{uuid.uuid4().hex[:12].upper()}"


# ---- the frozen cohort (built once per process; datasets live only in the client buffers) ----------
@dataclass(frozen=True)
class CohortClient:
    client_id: str
    participant_id: str
    session_id: str
    edge_node_id: str
    buffer: Any


@dataclass(frozen=True)
class Cohort:
    clients: tuple[CohortClient, ...]
    manifest: dict[str, dict[str, str]]
    identity: str

    @property
    def client_ids(self) -> tuple[str, ...]:
        return tuple(c.client_id for c in self.clients)


_COHORT_LOCK = threading.Lock()
_COHORT: Cohort | None = None


def get_cohort() -> Cohort:
    global _COHORT
    with _COHORT_LOCK:
        if _COHORT is None:
            base, _ = new_session()
            built = []
            for index in range(CLIENT_COUNT):
                client, buffer = build_client(index, base, algorithm=Algorithm.FEDAVG)
                ident = client.identity
                built.append(CohortClient(
                    client_id=buffer.client_id, participant_id=client._participant_id,
                    session_id=client._session_id, edge_node_id=ident.edge_node_id, buffer=buffer))
            manifest = {c.client_id: {"participant_id": c.participant_id, "session_id": c.session_id,
                                      "dataset_sha": str(c.buffer.dataset_sha256)} for c in built}
            _COHORT = Cohort(tuple(built), manifest, semantic_digest(manifest))
        return _COHORT


class RoundTracker:
    def __init__(self, final: bool) -> None:
        self.state, self.final = RoundState.CREATED, final

    def move(self, new: RoundState) -> None:
        validate_round_transition_v2(self.state, new, final_round=self.final)
        self.state = new


class RunFailure(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code, self.detail = code, message or code


@dataclass
class RunContext:
    run_id: str
    user_id: str
    run_type: RunType
    algorithm: Algorithm
    secagg_mode: AggregationMode
    planned_rounds: int
    journal: FederationEventJournal
    emitter: FederationEmitter
    round_bases: dict[int, str] = field(default_factory=dict)
    committed: dict[int, str] = field(default_factory=dict)
    coordinator_digests: dict[int, dict[str, str]] = field(default_factory=dict)
    published_digests: dict[int, dict[str, str]] = field(default_factory=dict)
    client_digests: dict[tuple[int, str], str] = field(default_factory=dict)
    training_record: dict[int, dict[str, dict[str, Any]]] = field(default_factory=dict)
    secagg_summary: dict[str, Any] | None = None
    current_round: int = 0
    candidate_id: str | None = None
    started_at_us: int | None = None
    replay_source: str | None = None
    task: asyncio.Task[Any] | None = None


class FederationService:
    def __init__(self, *, store: FederationStore, artifacts: FederationArtifactStore,
                 registry: ModelRegistry, governance: GovernanceRuntime,
                 id_generator: IdGenerator = default_run_id,
                 checkpoint_hook: Callable[[str, int], None] | None = None,
                 replay_pace_s: float = 0.0,
                 cohort_provider: Callable[[], Cohort] = get_cohort) -> None:
        self.store, self.artifacts, self.registry, self.governance = (
            store, artifacts, registry, governance)
        self._ids, self._hook, self._pace = id_generator, checkpoint_hook, replay_pace_s
        self._cohort_provider = cohort_provider
        self._contexts: dict[str, RunContext] = {}
        self._active: str | None = None
        self._client_view: dict[str, tuple[ClientState, int, str | None]] = {}

    # ---- helpers ---------------------------------------------------------------------------------
    @property
    def clock(self) -> Callable[[], int]:
        return self.store.clock

    def _row(self, user_id: str, run_id: str) -> dict[str, Any]:
        row = self.store.get_run(run_id)
        if row is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, "federation run not found")
        if row["user_id"] != user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "not the owner of this federation run")
        return row

    def run_model(self, row: dict[str, Any]) -> FederationRun:
        return FederationRun(
            run_id=row["run_id"], run_type=RunType(row["run_type"]), base_model_id=row["base_model_id"],
            federation_protocol_id=row["federation_protocol_id"], algorithm=Algorithm(row["algorithm"]),
            client_ids=self._cohort_ids(), planned_rounds=row["planned_rounds"],
            current_round=row["current_round"], started_at_us=row["started_at_us"],
            completed_at_us=row["completed_at_us"], status=RunState(row["status"]),
            secagg_mode=AggregationMode(row["secagg_mode"]),
            candidate_ids=tuple(json.loads(row["candidate_ids_json"])),
            engineering_only=True)

    def _cohort_ids(self) -> tuple[str, ...]:
        return tuple(f"SIM_FL_SITE_{i:02d}" for i in range(CLIENT_COUNT))

    def _sinks(self, ctx: RunContext) -> list[Callable[[FederationLiveEvent], None]]:
        return [ctx.journal.append,
                lambda e: self.artifacts.append_event(ctx.run_id, e),
                lambda e: self._persist(ctx, e)]

    # ---- event -> SQLite rows --------------------------------------------------------------------
    def _persist(self, ctx: RunContext, event: FederationLiveEvent) -> None:
        kind, p = event.event_type, event.payload
        if kind == "federation.status":
            status = p.run_status.value
            if status == RunState.CREATED.value:
                return
            if status == RunState.RUNNING.value and ctx.started_at_us is None:
                ctx.started_at_us = event.emitted_at_us
                self.store.update_run(ctx.run_id, started_at_us=ctx.started_at_us)
            self.store.update_run(
                ctx.run_id, status=status, current_round=p.current_round,
                completed_at_us=event.emitted_at_us if status in TERMINAL_RUN else None)
        elif kind == "round.status":
            ctx.current_round = p.round_id
            in_candidate_phase = (ctx.run_type is RunType.LIVE_RUN and p.round_id == ctx.planned_rounds
                                  and p.round_state in (RoundState.CANDIDATE_CREATED, RoundState.VALIDATING,
                                                        RoundState.ACCEPTED_TO_SANDBOX, RoundState.REJECTED,
                                                        RoundState.COMPLETED))
            self.store.upsert_round(
                run_id=ctx.run_id, round_id=p.round_id, state=p.round_state.value,
                base_state_digest=ctx.round_bases[p.round_id], algorithm=ctx.algorithm.value,
                accepted_update_count=p.accepted_updates,
                candidate_id=ctx.candidate_id if in_candidate_phase else None)
        elif kind == "client.update_ready":
            ctx.client_digests[(p.round_id, p.client_id)] = p.update_digest
        elif kind == "client.status":
            self.store.upsert_client_status(
                run_id=ctx.run_id, client_id=p.client_id, round_id=ctx.current_round,
                client_state=p.client_state.value, local_example_count=p.local_example_count,
                update_digest=ctx.client_digests.get((ctx.current_round, p.client_id)),
                reason_code=p.reason_code)
            if ctx.run_type is RunType.LIVE_RUN:
                self._client_view[p.client_id] = (p.client_state, ctx.current_round,
                                                  ctx.client_digests.get((ctx.current_round, p.client_id)))

    # ---- contexts / journals ---------------------------------------------------------------------
    def _new_context(self, row: dict[str, Any], meta: dict[str, Any]) -> RunContext:
        run_id = row["run_id"]
        journal = FederationEventJournal(run_id)
        ctx = RunContext(
            run_id=run_id, user_id=row["user_id"], run_type=RunType(row["run_type"]),
            algorithm=Algorithm(row["algorithm"]), secagg_mode=AggregationMode(row["secagg_mode"]),
            planned_rounds=row["planned_rounds"], journal=journal,
            emitter=FederationEmitter(run_id, self.clock, [], 0),
            replay_source=meta.get("replay_source_run_id"))
        ctx.emitter._sinks = self._sinks(ctx)
        self._contexts[run_id] = ctx
        return ctx

    def _context(self, row: dict[str, Any]) -> RunContext:
        ctx = self._contexts.get(row["run_id"])
        if ctx is None:  # a created-but-unstarted run of an earlier process
            ctx = self._new_context(row, self.artifacts.read_run_meta(row["run_id"]) or {})
            for event in self.artifacts.read_events(row["run_id"]):
                ctx.journal.append(event)
            ctx.emitter.next_sequence = len(ctx.journal)
        return ctx

    def journal_for(self, run_id: str) -> FederationEventJournal | None:
        ctx = self._contexts.get(run_id)
        if ctx is not None:
            return ctx.journal
        row = self.store.get_run(run_id)
        if row is None:
            return None
        journal = FederationEventJournal(run_id)  # a finished run of an earlier process: its JSONL
        for event in self.artifacts.read_events(run_id):
            journal.append(event)
        if row["status"] in TERMINAL_RUN:
            journal.close()
        return journal

    # ---- public API ------------------------------------------------------------------------------
    def create_run(self, user_id: str, *, run_type: str, algorithm: str, secagg_mode: str,
                   planned_rounds: int, scenario_id: str) -> FederationRun:
        try:
            check_public_request(run_type=str(run_type), algorithm=str(algorithm),
                                 secagg_mode=str(secagg_mode), planned_rounds=planned_rounds,
                                 scenario_id=scenario_id)
        except (BindingViolation, ValueError) as error:
            code = getattr(error, "code", str(error))
            raise ProductError(ProductErrorCode.INVALID_REQUEST, f"{code}") from error
        run_type_e, algo, mode = RunType(run_type), Algorithm(algorithm), AggregationMode(secagg_mode)
        meta: dict[str, Any] = {"scenario_id": scenario_id, "binding_id": BINDING_ID,
                                "run_type": run_type_e.value, "algorithm": algo.value,
                                "secagg_mode": mode.value, "planned_rounds": planned_rounds}
        if run_type_e is RunType.REPLAY:
            source = self._replay_source(user_id, algo, mode, planned_rounds)
            meta["replay_source_run_id"] = source["run_id"]
        run_id = self._ids()
        if self.store.get_run(run_id) is not None:
            raise ProductError(ProductErrorCode.INVALID_STATE, "run id already exists")
        self.store.insert_run(run_id=run_id, user_id=user_id, run_type=run_type_e.value,
                              base_model_id=RUN_BASE_MODEL_ID, protocol_id=PROTOCOL_ID,
                              algorithm=algo.value, secagg_mode=mode.value,
                              planned_rounds=planned_rounds)
        meta["run_id"] = run_id
        self.artifacts.write_run_meta(run_id, meta)
        row = self.store.get_run(run_id)
        ctx = self._new_context(row, meta)
        ctx.emitter.federation_status(run_type=run_type_e, run_status=RunState.CREATED, algorithm=algo,
                                      current_round=0, planned_rounds=planned_rounds,
                                      client_count=CLIENT_COUNT, engineering_only=True)
        return self.run_model(self.store.get_run(run_id))

    def get_run(self, user_id: str, run_id: str) -> FederationRun:
        return self.run_model(self._row(user_id, run_id))

    def list_runs(self, user_id: str) -> list[FederationRun]:
        return [self.run_model(r) for r in self.store.list_runs(user_id)]

    def rounds(self, user_id: str, run_id: str) -> list[FederationRound]:
        row = self._row(user_id, run_id)
        return [FederationRound(
            run_id=run_id, round_id=r["round_id"], state=RoundState(r["state"]),
            participating_client_ids=self._cohort_ids(), base_state_digest=r["base_state_digest"],
            algorithm=Algorithm(r["algorithm"]), accepted_update_count=r["accepted_update_count"],
            candidate_id=r["candidate_id"]) for r in self.store.list_rounds(row["run_id"])]

    def owner_of(self, run_id: str) -> str | None:
        row = self.store.get_run(run_id)
        return None if row is None else row["user_id"]

    def active_live_run(self) -> bool:
        return self._active is not None or bool(self.store.runs_with_status("RUNNING", "LIVE_RUN"))

    def overview(self) -> FederationOverview:
        return FederationOverview(
            banner=BANNER, client_count=CLIENT_COUNT, cohort_id=COHORT_ID,
            active_live_run=self.active_live_run(), candidate_count=len(self.store.list_candidates()),
            released_model_id="MODEL_V2_FINAL")

    async def clients(self) -> list[FLClientIdentity]:
        cohort = await asyncio.to_thread(self._cohort_provider)
        out = []
        for c in cohort.clients:
            state, round_id, digest = self._client_view.get(c.client_id, (ClientState.IDLE, 0, None))
            if state in (ClientState.UPDATE_READY, ClientState.SUBMITTED) and digest is None:
                state = ClientState.IDLE
            count = c.buffer.eligible_count()
            out.append(FLClientIdentity(
                client_id=c.client_id, edge_node_id=c.edge_node_id, base_model_id=RUN_BASE_MODEL_ID,
                global_round=round_id, local_example_count=count, client_state=state,
                update_digest=digest, eligible=count > 0,
                ineligible_reason=None if count > 0 else "NONPOSITIVE_EXAMPLES"))
        return out

    def _replay_source(self, user_id: str, algo: Algorithm, mode: AggregationMode,
                       rounds: int) -> dict[str, Any]:
        row = self.store.latest_completed_live_run(user_id, algo.value, mode.value, rounds)
        meta = self.artifacts.read_run_meta(row["run_id"]) if row else None
        if row is None or meta is None or meta.get("scenario_id") != PUBLIC_SCENARIO:
            raise ProductError(ProductErrorCode.INVALID_STATE, "NO_COMPLETED_SOURCE_RUN_FOR_REPLAY")
        events = self.artifacts.read_events(row["run_id"])
        if not events or events[-1].event_type != "federation.completed":
            raise ProductError(ProductErrorCode.INVALID_STATE, "REPLAY_SOURCE_EVENT_LOG_INCOMPLETE")
        return row

    async def start_run(self, user_id: str, run_id: str) -> FederationRun:
        row = self._row(user_id, run_id)
        if row["status"] != RunState.CREATED.value:
            raise ProductError(ProductErrorCode.INVALID_STATE, f"run is {row['status']}, not CREATED")
        ctx = self._context(row)
        live = ctx.run_type is RunType.LIVE_RUN
        if live:
            self._claim_active(run_id)
        try:
            ctx.emitter.federation_status(
                run_type=ctx.run_type, run_status=RunState.RUNNING, algorithm=ctx.algorithm,
                current_round=0, planned_rounds=ctx.planned_rounds, client_count=CLIENT_COUNT,
                engineering_only=True)
        except Exception:
            if live:
                self._active = None
            raise
        coro = self._live(ctx, None) if live else self._replay(ctx)
        ctx.task = asyncio.ensure_future(coro)
        return self.run_model(self.store.get_run(run_id))

    def _claim_active(self, run_id: str) -> None:
        others = [r for r in self.store.runs_with_status("RUNNING", "LIVE_RUN") if r["run_id"] != run_id]
        if self._active is not None or others:
            raise ProductError(ProductErrorCode.INVALID_STATE, "FEDERATION_RUN_ALREADY_ACTIVE")
        self._active = run_id

    async def wait(self, run_id: str) -> None:
        ctx = self._contexts.get(run_id)
        if ctx is not None and ctx.task is not None:
            await asyncio.shield(ctx.task)

    # ---- recovery --------------------------------------------------------------------------------
    async def recover(self, *, auto_resume: bool = True) -> list[dict[str, Any]]:
        """App-start recovery of RUNNING LIVE runs left by a dead process."""
        report = []
        for row in self.store.runs_with_status("RUNNING"):
            if row["run_id"] in self._contexts:
                continue
            if row["run_type"] != RunType.LIVE_RUN.value:
                self._fail_without_checkpoint(row, "REPLAY_INTERRUPTED")
                report.append({"run_id": row["run_id"], "action": "FAIL", "reason": "REPLAY_INTERRUPTED"})
                continue
            cohort = await asyncio.to_thread(self._cohort_provider)
            decision = assess(row, self.artifacts, cohort.identity)
            if decision.action == "RESUME" and auto_resume:
                self._resume(row, decision)
            else:
                self._fail_without_checkpoint(row, decision.reason)
            report.append({"run_id": row["run_id"], "action": decision.action,
                           "reason": decision.reason, "last_committed_round": decision.last_committed_round})
        return report

    def _fail_without_checkpoint(self, row: dict[str, Any], reason: str) -> None:
        meta = self.artifacts.read_run_meta(row["run_id"]) or {}
        ctx = self._new_context(row, meta)
        events = self.artifacts.read_events(row["run_id"])
        for event in events:
            ctx.journal.append(event)
        ctx.emitter.next_sequence = len(events)
        if events:  # never fabricate history: only append the terminal facts
            ctx.round_bases = {r["round_id"]: r["base_state_digest"]
                               for r in self.store.list_rounds(row["run_id"])}
            ctx.emitter.error(error_code="RUN_INTERRUPTED_NO_RESUME", message=reason[:300],
                              recoverable=False, round_id=None)
            ctx.emitter.federation_status(
                run_type=ctx.run_type, run_status=RunState.FAILED, algorithm=ctx.algorithm,
                current_round=row["current_round"], planned_rounds=ctx.planned_rounds,
                client_count=CLIENT_COUNT, engineering_only=True)
        else:
            self.store.update_run(row["run_id"], status=RunState.FAILED.value,
                                  completed_at_us=self.clock())
        ctx.journal.close()

    def _resume(self, row: dict[str, Any], decision: Any) -> None:
        run_id, last = row["run_id"], decision.last_committed_round
        meta = self.artifacts.read_run_meta(run_id) or {}
        self._claim_active(run_id)
        for orphan in self.registry.artifacts.directories():
            md = self.registry.artifacts.read_metadata(orphan)
            if md.get("federation_run_id") == run_id and self.store.get_candidate(orphan) is None:
                self.registry.artifacts.remove(orphan)  # artifact written, row never committed
        self.artifacts.truncate_events(run_id, decision.record["event_count"])
        self.store.delete_after_round(run_id, last)
        ctx = self._new_context(row, meta)
        for event in self.artifacts.read_events(run_id):
            ctx.journal.append(event)
        ctx.emitter.next_sequence = len(ctx.journal)
        ctx.started_at_us = row["started_at_us"]
        ctx.round_bases = {int(k): v for k, v in decision.record["round_bases"].items()}
        ctx.committed = {int(k): v for k, v in decision.record["committed"].items()}
        ctx.coordinator_digests = {int(k): v for k, v in decision.record["coordinator_digests"].items()}
        ctx.published_digests = {int(k): v for k, v in decision.record["published_digests"].items()}
        ctx.training_record = {int(k): v for k, v in decision.record["training_record"].items()}
        ctx.task = asyncio.ensure_future(self._live(ctx, decision))

    # ---- LIVE execution --------------------------------------------------------------------------
    async def _live(self, ctx: RunContext, resume: Any) -> None:
        tracker = None
        try:
            cohort = await asyncio.to_thread(self._cohort_provider)
            state, spec_sha = new_session()
            init_digest = verify_round_base(round_id=1, state=state, committed={})
            coordinator = Coordinator(cohort.manifest, spec_sha)
            start_round = 1
            if resume is not None:
                state, start_round = resume.state, resume.last_committed_round + 1
                for r, sha in sorted(ctx.committed.items()):
                    coordinator.committed[r] = sha
            for round_id in range(start_round, ctx.planned_rounds + 1):
                tracker = RoundTracker(final=round_id == ctx.planned_rounds)
                state = await self._round(ctx, cohort, coordinator, tracker, round_id, state,
                                          init_digest, spec_sha)
            self._finish(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._fail(ctx, tracker, error)
        finally:
            if self._active == ctx.run_id:
                self._active = None
            ctx.journal.close()

    def _round_event(self, ctx: RunContext, tracker: RoundTracker, round_id: int, new: RoundState,
                     accepted: int) -> None:
        tracker.move(new)
        ctx.emitter.round_status(round_id=round_id, round_state=new, accepted_updates=accepted,
                                 expected_updates=CLIENT_COUNT)

    @staticmethod
    def _train_sync(adapter: CapstoneFlClientAdapterV2, round_id: int, digest: str) -> None:
        asyncio.run(adapter.local_train(round_id, digest))

    async def _round(self, ctx: RunContext, cohort: Cohort, coordinator: Coordinator,
                     tracker: RoundTracker, round_id: int, state: dict[str, np.ndarray],
                     init_digest: str, spec_sha: str) -> dict[str, np.ndarray]:
        em = ctx.emitter
        final = round_id == ctx.planned_rounds
        base_digest = verify_round_base(round_id=round_id, state=state, committed=ctx.committed)
        ctx.round_bases[round_id] = base_digest
        em.federation_status(run_type=ctx.run_type, run_status=RunState.RUNNING,
                             algorithm=ctx.algorithm, current_round=round_id,
                             planned_rounds=ctx.planned_rounds, client_count=CLIENT_COUNT,
                             engineering_only=True)
        coordinator.open(round_id, base_digest)
        self._round_event(ctx, tracker, round_id, RoundState.COLLECTING, 0)
        adapters: dict[str, CapstoneFlClientAdapterV2] = {}
        for c in sorted(cohort.clients, key=lambda x: x.client_id):
            adapter = CapstoneFlClientAdapterV2(
                c.buffer, edge_node_id=c.edge_node_id, participant_id=c.participant_id,
                session_id=c.session_id, round_id=round_id, base_state=state, committed=ctx.committed,
                base_model_id=RUN_BASE_MODEL_ID, algorithm=ctx.algorithm)
            adapter.prepare()
            adapters[c.client_id] = adapter
            em.client_status(client_id=c.client_id, client_state=ClientState.DATA_READY,
                             local_example_count=c.buffer.eligible_count(), reason_code=None)
        self._round_event(ctx, tracker, round_id, RoundState.LOCAL_TRAINING, 0)
        published: dict[str, str] = {}
        envelopes: dict[str, dict[str, Any]] = {}
        for cid, adapter in adapters.items():
            count = adapter._buffer.eligible_count()
            em.client_status(client_id=cid, client_state=ClientState.TRAINING,
                             local_example_count=count, reason_code=None)
            em.training_progress(client_id=cid, round_id=round_id, progress_fraction=0.0,
                                 examples_seen=0)
            await asyncio.to_thread(self._train_sync, adapter, round_id, base_digest)
            envelope, _ = export_envelope(adapter, state)
            envelopes[cid], published[cid] = envelope, envelope["update_sha256"]
            diagnostics = adapter.diagnostics()
            ctx.training_record.setdefault(round_id, {})[cid] = {
                "examples_seen": diagnostics["examples_seen"], "shuffle_seed": diagnostics["shuffle_seed"],
                "update_sha256": envelope["update_sha256"]}
            em.training_progress(client_id=cid, round_id=round_id, progress_fraction=1.0,
                                 examples_seen=adapter.examples_seen)
            ctx.client_digests[(round_id, cid)] = envelope["update_sha256"]
            em.client_status(client_id=cid, client_state=ClientState.UPDATE_READY,
                             local_example_count=count, reason_code=None)
            em.update_ready(client_id=cid, round_id=round_id, update_digest=envelope["update_sha256"],
                            examples_seen=adapter.examples_seen)
            decision = coordinator.submit(envelope, state)
            if decision["decision"] == "ACCEPTED":
                adapter.mark_submitted()
                em.client_status(client_id=cid, client_state=ClientState.SUBMITTED,
                                 local_example_count=count, reason_code=None)
            else:
                adapter.reject()
                em.client_status(client_id=cid, client_state=ClientState.REJECTED,
                                 local_example_count=count, reason_code=decision["code"])
                raise RunFailure("UPDATE_REJECTED", f"{cid}:{decision['code']}")
        if not coordinator.ready():
            raise RunFailure("ROUND_INCOMPLETE", f"round {round_id}")
        ctx.published_digests[round_id] = published
        ctx.coordinator_digests[round_id] = {c: m["update_sha256"] for c, m in coordinator.accepted.items()}
        self._round_event(ctx, tracker, round_id, RoundState.UPDATES_READY, len(coordinator.accepted))
        self._round_event(ctx, tracker, round_id, RoundState.AGGREGATING, len(coordinator.accepted))
        await self._secagg(ctx, round_id, state, coordinator)
        new_state = await asyncio.to_thread(coordinator.aggregate, state)
        new_sha = state_sha(new_state)
        coordinator.commit(round_id, new_sha)
        ctx.committed[round_id] = new_sha
        em.aggregation_status(round_id=round_id, algorithm=ctx.algorithm,
                              aggregation_mode=AggregationMode.PLAIN,
                              accepted_updates=len(coordinator.accepted), state_digest=new_sha)
        if not final:
            self._round_event(ctx, tracker, round_id, RoundState.COMPLETED, len(coordinator.accepted))
            self._checkpoint(ctx, cohort, round_id, new_state)
            return new_state
        await self._candidate(ctx, coordinator, tracker, round_id, new_state, spec_sha, init_digest)
        return new_state

    async def _secagg(self, ctx: RunContext, round_id: int, state: dict[str, np.ndarray],
                      coordinator: Coordinator) -> None:
        em = ctx.emitter
        if ctx.secagg_mode is AggregationMode.PLAIN:
            em.secagg_status(round_id=round_id, mode=AggregationMode.PLAIN, status=SecAggStatus.NOT_USED)
            return
        if round_id != 1:
            return  # the shadow covers round 1 only (frozen scope)
        em.secagg_status(round_id=1, mode=AggregationMode.SECAGG_SHADOW,
                         status=SecAggStatus.SHADOW_RUNNING)
        deltas = {c: coordinator.deltas[c] for c in coordinator.accepted}
        examples = {c: int(m["examples_seen"]) for c, m in coordinator.accepted.items()}
        try:
            report = await asyncio.to_thread(run_round1_shadow, state, deltas, examples)
            ctx.secagg_summary = {
                "status": report["status"], "claim_scope": report["claim_scope"],
                "authoritative_aggregation": report["authoritative_aggregation"], "round": report["round"],
                "clients": len(deltas), "max_weight": report["preflight"]["max_weight"],
                "plain_clear_update_count": report["plain_clear_update_count"],
                "protected_clear_update_count": report["protected_clear_update_count"],
                "protected_aggregate_available": report["protected_aggregate_available"],
                "maximum_absolute_difference": report["maximum_absolute_difference"],
                "relative_L2_difference": report["relative_L2_difference"],
                "tolerance": report["tolerance"]}
        except SecAggShadowFailure as error:
            em.secagg_status(round_id=1, mode=AggregationMode.SECAGG_SHADOW,
                             status=SecAggStatus.SHADOW_FAILED)
            raise RunFailure("SECAGG_SHADOW_FAILED", error.code) from error
        em.secagg_status(round_id=1, mode=AggregationMode.SECAGG_SHADOW,
                         status=SecAggStatus.SHADOW_VERIFIED)

    def _checkpoint(self, ctx: RunContext, cohort: Cohort, round_id: int,
                    state: dict[str, np.ndarray]) -> None:
        record = {"protocol_id": PROTOCOL_ID, "binding_id": BINDING_ID,
                  "cohort_manifest_sha256": cohort.identity, "algorithm": ctx.algorithm.value,
                  "secagg_mode": ctx.secagg_mode.value, "planned_rounds": ctx.planned_rounds,
                  "event_count": ctx.emitter.next_sequence,
                  "committed": {str(k): v for k, v in ctx.committed.items()},
                  "round_bases": {str(k): v for k, v in ctx.round_bases.items()},
                  "coordinator_digests": {str(k): v for k, v in ctx.coordinator_digests.items()},
                  "published_digests": {str(k): v for k, v in ctx.published_digests.items()},
                  "training_record": {str(k): v for k, v in ctx.training_record.items()}}
        self.artifacts.write_checkpoint(ctx.run_id, round_id, state, record)
        if self._hook is not None:
            self._hook(ctx.run_id, round_id)

    async def _candidate(self, ctx: RunContext, coordinator: Coordinator, tracker: RoundTracker,
                         round_id: int, state: dict[str, np.ndarray], spec_sha: str,
                         init_digest: str) -> None:
        em = ctx.emitter
        accepted = len(coordinator.accepted)
        candidate = self.registry.create_candidate(
            federation_run_id=ctx.run_id, parent_model_id=RUN_BASE_MODEL_ID, round_id=round_id,
            algorithm=ctx.algorithm, client_count=CLIENT_COUNT, state=state,
            extra_metadata={"federation_protocol_id": PROTOCOL_ID, "binding_id": BINDING_ID,
                            "round_base_digests": {str(k): v for k, v in ctx.round_bases.items()},
                            "committed_digests": {str(k): v for k, v in ctx.committed.items()}})
        ctx.candidate_id = candidate.candidate_id
        self.store.update_run(ctx.run_id, candidate_ids=[candidate.candidate_id])
        self._round_event(ctx, tracker, round_id, RoundState.CANDIDATE_CREATED, accepted)
        em.candidate_created(candidate_id=candidate.candidate_id, parent_model_id=RUN_BASE_MODEL_ID,
                             round_id=round_id, state_digest=candidate.state_digest,
                             production_deployed=False)
        self._round_event(ctx, tracker, round_id, RoundState.VALIDATING, accepted)
        self.governance.mark_pending(candidate.candidate_id)
        self.governance.mark_validating(candidate.candidate_id)
        from product.models.registry_contract import ValidationStatus
        em.candidate_validation(candidate_id=candidate.candidate_id,
                                validation_status=ValidationStatus.RUNNING, checks=())
        stored = self.registry.artifacts.load_verified(candidate.candidate_id, candidate.state_digest)
        base_state, _ = new_session()
        evidence = ValidationEvidence(
            candidate_state=stored, base_state_spec_sha=state_spec_sha(base_state),
            fl_init_sha=frozen_fl_init_sha(), cohort_size=CLIENT_COUNT, planned_rounds=ctx.planned_rounds,
            round_bases=dict(ctx.round_bases), committed=dict(ctx.committed),
            coordinator_digests=dict(ctx.coordinator_digests),
            published_digests=dict(ctx.published_digests),
            candidate_state_digest=candidate.state_digest)
        checks = run_checks(evidence)
        decision = self.governance.decide(candidate.candidate_id, checks)
        accepted_to_sandbox = decision["decision"] == "ACCEPTED_TO_SANDBOX"
        em.candidate_validation(
            candidate_id=candidate.candidate_id,
            validation_status=ValidationStatus.PASSED if accepted_to_sandbox else ValidationStatus.FAILED,
            checks=tuple(c["check_id"] for c in checks if c["passed"]))
        final_candidate = self.registry.get_candidate(candidate.candidate_id)
        em.candidate_governance(candidate_id=candidate.candidate_id,
                                governance_status=final_candidate.governance_status,
                                sandbox_status=final_candidate.sandbox_status, production_deployed=False)
        self._round_event(ctx, tracker, round_id,
                          RoundState.ACCEPTED_TO_SANDBOX if accepted_to_sandbox else RoundState.REJECTED,
                          accepted)
        self._round_event(ctx, tracker, round_id, RoundState.COMPLETED, accepted)

    def _finish(self, ctx: RunContext) -> None:
        em = ctx.emitter
        ids = tuple(self.store.candidate_ids_for_run(ctx.run_id))
        meta = self.artifacts.read_run_meta(ctx.run_id) or {}
        meta.update({"training_record": {str(k): v for k, v in ctx.training_record.items()},
                     "round_base_digests": {str(k): v for k, v in ctx.round_bases.items()},
                     "committed_digests": {str(k): v for k, v in ctx.committed.items()},
                     "final_global_state_sha256": ctx.committed.get(ctx.planned_rounds),
                     "candidate_ids": list(ids)})
        if ctx.secagg_summary is not None:
            meta["secagg_shadow"] = ctx.secagg_summary
        self.artifacts.write_run_meta(ctx.run_id, meta)
        em.federation_status(run_type=ctx.run_type, run_status=RunState.COMPLETED,
                             algorithm=ctx.algorithm, current_round=ctx.planned_rounds,
                             planned_rounds=ctx.planned_rounds, client_count=CLIENT_COUNT,
                             engineering_only=True)
        em.completed(rounds_completed=ctx.planned_rounds, candidate_ids=ids, production_deployed=False)
        self._client_view.clear()

    def _fail(self, ctx: RunContext, tracker: RoundTracker | None, error: Exception) -> None:
        em = ctx.emitter
        code = getattr(error, "code", type(error).__name__)
        try:
            if tracker is not None and tracker.state not in (RoundState.COMPLETED, RoundState.FAILED) \
                    and ctx.current_round in ctx.round_bases:
                self._round_event(ctx, tracker, ctx.current_round, RoundState.FAILED, 0)
            em.error(error_code=str(code)[:80], message=str(error)[:300], recoverable=False,
                     round_id=ctx.current_round or None)
            em.federation_status(run_type=ctx.run_type, run_status=RunState.FAILED,
                                 algorithm=ctx.algorithm, current_round=ctx.current_round,
                                 planned_rounds=ctx.planned_rounds, client_count=CLIENT_COUNT,
                                 engineering_only=True)
        finally:
            self._client_view.clear()

    # ---- REPLAY ----------------------------------------------------------------------------------
    async def _replay(self, ctx: RunContext) -> None:
        try:
            source_id = ctx.replay_source
            source_events = self.artifacts.read_events(source_id) if source_id else []
            if not source_events or source_events[-1].event_type != "federation.completed":
                raise RunFailure("REPLAY_SOURCE_EVENT_LOG_INCOMPLETE", str(source_id))
            ctx.round_bases = {r["round_id"]: r["base_state_digest"]
                               for r in self.store.list_rounds(source_id)}
            # events 0 (CREATED) and 1 (RUNNING, round 0) were emitted by this run's own create/start
            for source in source_events[2:]:
                clone = retarget(clone_event_for_replay(
                    source, run_id=ctx.run_id, sequence_index=ctx.emitter.next_sequence,
                    emitted_at_us=self.clock()))
                for sink in ctx.emitter._sinks:
                    sink(clone)
                ctx.emitter.next_sequence += 1
                if self._pace:
                    await asyncio.sleep(self._pace)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._fail(ctx, None, error)
        finally:
            ctx.journal.close()

    # ---- invalid-update probe (internal harness scenario FL_REJECT_INVALID_UPDATE) ---------------
    def invalid_update_probe(self) -> dict[str, Any]:
        """Genuine client-0 round-1 envelope + four mutated submissions through the UNCHANGED
        coordinator rejection logic. No run, round, candidate or database row is created."""
        cohort = self._cohort_provider()
        state, spec_sha = new_session()
        coordinator = Coordinator(cohort.manifest, spec_sha)
        digest = verify_round_base(round_id=1, state=state, committed={})
        coordinator.open(1, digest)
        c0 = cohort.clients[0]
        adapter = CapstoneFlClientAdapterV2(
            c0.buffer, edge_node_id=c0.edge_node_id, participant_id=c0.participant_id,
            session_id=c0.session_id, round_id=1, base_state=state, committed={},
            algorithm=Algorithm.FEDAVG)
        adapter.prepare()
        self._train_sync(adapter, 1, digest)
        envelope, _ = export_envelope(adapter, state)
        cases = [
            ("VALID", envelope),
            ("DUPLICATE_UPDATE", envelope),
            ("STALE_ROUND", dict(envelope, round_id=0)),
            ("BASE_STATE_MISMATCH", dict(envelope, base_global_state_sha256="0" * 64)),
            ("UNKNOWN_CLIENT", dict(envelope, client_id="SIM_FL_SITE_99")),
        ]
        results = []
        for name, env in cases:
            decision = coordinator.submit(env, state)
            results.append({"case": name, "decision": decision["decision"], "code": decision["code"]})
        return {"results": results, "accepted_after": len(coordinator.accepted),
                "round_complete": coordinator.ready(),
                "candidate_created": False, "run_rows_created": False}
