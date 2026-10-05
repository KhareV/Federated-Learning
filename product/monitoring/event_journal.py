"""CAPSTONE_MONITORING_EVENT_JOURNAL_V1 -- append-only, in-memory event journal for one session.

Subscribers replay the journal from sequence 0 and then tail new events (frozen CAP-003 reconnect
policy); the wire contract (PRODUCT_LIVE_EVENT_V1) is unchanged and CAP-004 persistence may back the
journal later. The monitoring pipeline never depends on a subscriber: appending never waits.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from product.events import MONITORING_ADAPTER, MonitoringLiveEvent


class MonitoringEventJournal:
    def __init__(self) -> None:
        self._events: list[MonitoringLiveEvent] = []
        self._closed = False
        self._waiters: list[asyncio.Future[None]] = []

    def __len__(self) -> int:
        return len(self._events)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def events(self) -> tuple[MonitoringLiveEvent, ...]:
        return tuple(self._events)

    def append(self, event: MonitoringLiveEvent) -> None:
        if self._closed:
            raise RuntimeError("JOURNAL_CLOSED")
        # defence in depth: only valid monitoring events may ever enter the journal
        MONITORING_ADAPTER.validate_python(event.model_dump(mode="json"))
        if event.sequence_index != len(self._events):
            raise ValueError(f"NON_CONTIGUOUS_SEQUENCE:{event.sequence_index}!={len(self._events)}")
        self._events.append(event)
        self._wake()

    def close(self) -> None:
        self._closed = True
        self._wake()

    def _wake(self) -> None:
        waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(None)

    async def subscribe(self) -> AsyncIterator[MonitoringLiveEvent]:
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
