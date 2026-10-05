# ruff: noqa: E501
"""CAPSTONE_FEDERATION_EVENT_JOURNAL_V1 -- append-only in-memory journal of ONE federation run.

Separate from the monitoring journal. One global contiguous sequence_index per run starting at 0; only
the 12 frozen federation event kinds are accepted. Subscribers replay from sequence 0 and then tail new
events; the run never waits for a subscriber (zero or many subscribers are fine)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from product.events import FEDERATION_ADAPTER, FEDERATION_EVENT_KINDS, FederationLiveEvent

JOURNAL_ID = "CAPSTONE_FEDERATION_EVENT_JOURNAL_V1"


class FederationEventJournal:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._events: list[FederationLiveEvent] = []
        self._closed = False
        self._waiters: list[asyncio.Future[None]] = []

    def __len__(self) -> int:
        return len(self._events)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def events(self) -> tuple[FederationLiveEvent, ...]:
        return tuple(self._events)

    def append(self, event: FederationLiveEvent) -> None:
        if self._closed:
            raise RuntimeError("JOURNAL_CLOSED")
        FEDERATION_ADAPTER.validate_python(event.model_dump(mode="json"))  # defence in depth
        if event.event_type not in FEDERATION_EVENT_KINDS:
            raise ValueError(f"NOT_A_FEDERATION_EVENT_KIND:{event.event_type}")
        if event.run_id != self.run_id:
            raise ValueError("EVENT_RUN_ID_MISMATCH")
        if event.sequence_index != len(self._events):
            raise ValueError(f"NON_CONTIGUOUS_SEQUENCE:{event.sequence_index}!={len(self._events)}")
        self._events.append(event)
        self._wake()

    def truncate(self, count: int) -> None:
        """Recovery only: drop events past the last durable checkpoint boundary."""
        if self._closed or count > len(self._events):
            raise ValueError("INVALID_TRUNCATION")
        del self._events[count:]

    def close(self) -> None:
        self._closed = True
        self._wake()

    def _wake(self) -> None:
        waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(None)

    async def subscribe(self) -> AsyncIterator[FederationLiveEvent]:
        index = 0
        while True:
            if index < len(self._events):
                yield self._events[index]
                index += 1
                continue
            if self._closed:
                return
            waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self._waiters.append(waiter)
            await waiter
