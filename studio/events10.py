# ruff: noqa: E501
"""Translate the FL10 runner's genuine progress callbacks into the product's typed PRODUCT_LIVE_EVENT_V1 federation events.

Every event is derived from a callback of the unchanged runner at the moment the work happened; nothing is interpolated or pre-announced.
``client.status SUBMITTED`` is emitted only from the coordinator's ACCEPTED decision (UPDATES_ACCEPTED), never from the end of local training."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from product.events import FederationLiveEvent
from product.federation.base import (
    AggregationMode,
    Algorithm,
    ClientState,
    RoundState,
    RunState,
    RunType,
    SecAggStatus,
)
from product.federation.events import FederationEmitter

CLIENT_COUNT = 8


class Fl10EventTranslator:
    """``post(fn)`` runs ``fn`` on the thread that owns the journal (the event loop); order of calls is preserved."""

    def __init__(self, emitter: FederationEmitter, post: Callable[[Callable[[], None]], None], *, planned_rounds: int, client_ids: tuple[str, ...], local_examples: dict[str, int], run_type: RunType = RunType.LIVE_RUN) -> None:
        self.em, self._post, self.run_type = emitter, post, run_type
        self.planned, self.clients, self.examples = planned_rounds, client_ids, local_examples
        self.round = 0

    def _status(self, status: RunState, round_id: int) -> None:
        self.em.federation_status(run_type=self.run_type, run_status=status, algorithm=Algorithm.FEDAVG, current_round=round_id, planned_rounds=self.planned, client_count=CLIENT_COUNT, engineering_only=True)

    def created(self) -> None:
        self._post(lambda: self._status(RunState.CREATED, 0))

    def running(self) -> None:
        self._post(lambda: self._status(RunState.RUNNING, 0))

    def on_progress(self, event: dict[str, Any]) -> None:
        kind, r = event["event"], event.get("round", 0)
        if kind == "ROUND_OPENED":
            self.round = r

            def opened() -> None:
                self._status(RunState.RUNNING, r)
                self.em.round_status(round_id=r, round_state=RoundState.COLLECTING, accepted_updates=0, expected_updates=CLIENT_COUNT)
                for c in self.clients:
                    self.em.client_status(client_id=c, client_state=ClientState.DATA_READY, local_example_count=self.examples[c], reason_code=None)
                self.em.round_status(round_id=r, round_state=RoundState.LOCAL_TRAINING, accepted_updates=0, expected_updates=CLIENT_COUNT)

            self._post(opened)
        elif kind == "CLIENT_TRAINING_STARTED":
            c = event["client_id"]

            def started() -> None:
                self.em.client_status(client_id=c, client_state=ClientState.TRAINING, local_example_count=self.examples[c], reason_code=None)
                self.em.training_progress(client_id=c, round_id=r, progress_fraction=0.0, examples_seen=0)

            self._post(started)
        elif kind == "CLIENT_TRAINING_FINISHED":
            c, n, digest = event["client_id"], int(event["examples"]), event["update_sha256"]

            def finished() -> None:
                self.em.training_progress(client_id=c, round_id=r, progress_fraction=1.0, examples_seen=n)
                self.em.client_status(client_id=c, client_state=ClientState.UPDATE_READY, local_example_count=self.examples[c], reason_code=None)
                self.em.update_ready(client_id=c, round_id=r, update_digest=digest, examples_seen=n)

            self._post(finished)
        elif kind == "UPDATES_ACCEPTED":
            accepted = list(event["accepted_clients"])

            def accept() -> None:
                for c in accepted:      # the coordinator accepted these updates: only now is a client SUBMITTED
                    self.em.client_status(client_id=c, client_state=ClientState.SUBMITTED, local_example_count=self.examples[c], reason_code=None)
                self.em.round_status(round_id=r, round_state=RoundState.UPDATES_READY, accepted_updates=len(accepted), expected_updates=CLIENT_COUNT)
                self.em.round_status(round_id=r, round_state=RoundState.AGGREGATING, accepted_updates=len(accepted), expected_updates=CLIENT_COUNT)
                self.em.secagg_status(round_id=r, mode=AggregationMode.PLAIN, status=SecAggStatus.NOT_USED)

            self._post(accept)
        elif kind == "ROUND_COMMITTED":
            digest = event["global_state_sha256"]

            def committed() -> None:
                self.em.aggregation_status(round_id=r, algorithm=Algorithm.FEDAVG, aggregation_mode=AggregationMode.PLAIN, accepted_updates=CLIENT_COUNT, state_digest=digest)
                self.em.round_status(round_id=r, round_state=RoundState.COMPLETED, accepted_updates=CLIENT_COUNT, expected_updates=CLIENT_COUNT)

            self._post(committed)

    def completed(self, rounds: int) -> None:
        def done() -> None:
            self._status(RunState.COMPLETED, rounds)
            self.em.completed(rounds_completed=rounds, candidate_ids=(), production_deployed=False)

        self._post(done)

    def failed(self, code: str, message: str) -> None:
        def fail() -> None:
            self.em.error(error_code=code[:64] or "FL10_RUN_FAILED", message=message[:300] or code, recoverable=False, round_id=self.round or None)
            self._status(RunState.FAILED, self.round)

        self._post(fail)


def last_event(journal: Any) -> FederationLiveEvent | None:
    events = journal.events
    return events[-1] if events else None
