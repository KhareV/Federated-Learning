"""Typed builders for the 12 PRODUCT_LIVE_EVENT_V1 federation events of one run (deterministic event
ids ``<run_id>-FEV000000``). Values come from the real orchestrator; nothing is invented."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from product.events import (
    AggregationStatusEvent,
    CandidateCreatedEvent,
    CandidateGovernanceEvent,
    CandidateValidationEvent,
    ClientStatusEvent,
    ClientTrainingProgressEvent,
    ClientUpdateReadyEvent,
    FederationCompletedEvent,
    FederationErrorEvent,
    FederationLiveEvent,
    FederationStatusEvent,
    RoundStatusEvent,
    SecAggStatusEvent,
)

Sink = Callable[[FederationLiveEvent], None]


def event_id(run_id: str, sequence_index: int) -> str:
    return f"{run_id}-FEV{sequence_index:06d}"


class FederationEmitter:
    """Builds, validates (through the typed models) and hands each event to the sinks, in order."""

    def __init__(self, run_id: str, clock: Callable[[], int], sinks: list[Sink],
                 first_sequence_index: int = 0) -> None:
        self.run_id, self._clock, self._sinks = run_id, clock, sinks
        self.next_sequence = first_sequence_index

    def _emit(self, cls: type, kind: str, payload: dict[str, Any]) -> FederationLiveEvent:
        event = cls(event_id=event_id(self.run_id, self.next_sequence),
                    sequence_index=self.next_sequence, emitted_at_us=self._clock(),
                    run_id=self.run_id, event_type=kind, payload=payload)
        self.next_sequence += 1
        for sink in self._sinks:
            sink(event)
        return event

    def federation_status(self, **p: Any) -> FederationLiveEvent:
        return self._emit(FederationStatusEvent, "federation.status", p)

    def round_status(self, **p: Any) -> FederationLiveEvent:
        return self._emit(RoundStatusEvent, "round.status", p)

    def client_status(self, **p: Any) -> FederationLiveEvent:
        return self._emit(ClientStatusEvent, "client.status", p)

    def training_progress(self, **p: Any) -> FederationLiveEvent:
        return self._emit(ClientTrainingProgressEvent, "client.training_progress", p)

    def update_ready(self, **p: Any) -> FederationLiveEvent:
        return self._emit(ClientUpdateReadyEvent, "client.update_ready", p)

    def aggregation_status(self, **p: Any) -> FederationLiveEvent:
        return self._emit(AggregationStatusEvent, "aggregation.status", p)

    def secagg_status(self, **p: Any) -> FederationLiveEvent:
        return self._emit(SecAggStatusEvent, "secagg.status", p)

    def candidate_created(self, **p: Any) -> FederationLiveEvent:
        return self._emit(CandidateCreatedEvent, "candidate.created", p)

    def candidate_validation(self, **p: Any) -> FederationLiveEvent:
        return self._emit(CandidateValidationEvent, "candidate.validation", p)

    def candidate_governance(self, **p: Any) -> FederationLiveEvent:
        return self._emit(CandidateGovernanceEvent, "candidate.governance", p)

    def completed(self, **p: Any) -> FederationLiveEvent:
        return self._emit(FederationCompletedEvent, "federation.completed", p)

    def error(self, **p: Any) -> FederationLiveEvent:
        return self._emit(FederationErrorEvent, "federation.error", p)


def clone_event_for_replay(source: FederationLiveEvent, *, run_id: str, sequence_index: int,
                           emitted_at_us: int) -> FederationLiveEvent:
    """REPLAY: identical kind/payload/order; only run id, event id, sequence timestamp are new."""
    return type(source)(
        event_id=event_id(run_id, sequence_index), sequence_index=sequence_index,
        emitted_at_us=emitted_at_us, run_id=run_id, event_type=source.event_type,
        payload=source.payload)
