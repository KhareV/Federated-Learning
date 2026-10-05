"""Deterministic multiplexer over the two public views of a DeviceSource.

``DeviceSource.records()`` and ``.events()`` are two views of ONE underlying source timeline. This
module merges them into a single causally ordered stream using ONLY the frozen public interface
(no private source fields). Order is defined by source time:

    an event whose source_timestamp_us <= a record's timestamp_us precedes that record
    (events with no source timestamp, i.e. pre-stream, precede everything).

Mechanism: ``records()`` is the single driver (it advances the source timeline one item per pull,
so when a record is yielded every event with an earlier-or-equal source time already exists). Event
retrieval uses a single outstanding fetch; a record is released only after the fetch has either
produced an event (compared by timestamp) or is demonstrably still waiting inside the
source's pacing (i.e. no earlier event exists). Any violation of the order rule raises
``MuxOrderError`` loudly instead of silently mis-ordering. Every record and every event is
delivered exactly once.

Guarantee, stated precisely. ``blocking_lookahead=True`` (used for the unpaced ACCELERATED mode)
awaits the event lookahead completely, so the merged order is a pure function of the source
timeline under ANY task scheduling. ``blocking_lookahead=False`` (paced LIVE_SPEED mode, where
awaiting would stall in real time) waits at most ``SETTLE_SLICES`` event-loop turns for the event
view; a view that is slower than that can only produce a loud ``MuxOrderError`` (session FAILED),
never a silently different order. The frozen DeviceSource interface offers no watermark/heartbeat,
so unbounded-latency independent views cannot be proven ordered; a future DeviceSource contract
version should add one (recorded as a CAP-003 contract clarification).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from product.devices.base import DeviceEvent
from simulation.types import ObservedRecord

SETTLE_SLICES = 8


class MuxOrderError(RuntimeError):
    """The merged stream would violate the source-time order rule."""


@dataclass(frozen=True)
class MuxItem:
    kind: Literal["event", "record"]
    value: DeviceEvent | ObservedRecord


_DONE = object()


async def _next(iterator: AsyncIterator[Any]) -> Any:
    try:
        return await iterator.__anext__()
    except StopAsyncIteration:
        return _DONE


async def merge_source_streams(records: AsyncIterator[ObservedRecord],
                               events: AsyncIterator[DeviceEvent],
                               *, should_stop: Any = None,
                               blocking_lookahead: bool = False) -> AsyncIterator[MuxItem]:
    fetch: asyncio.Future[Any] | None = None
    held: DeviceEvent | None = None
    events_done = False
    last_record_ts = -1
    last_event_seq: int | None = None

    def check_event(event: DeviceEvent) -> None:
        nonlocal last_event_seq
        if last_event_seq is not None and event.sequence_index != last_event_seq + 1:
            raise MuxOrderError(f"EVENT_SEQUENCE_GAP:{last_event_seq}->{event.sequence_index}")
        last_event_seq = event.sequence_index
        ts = event.source_timestamp_us
        if ts is not None and ts <= last_record_ts:
            raise MuxOrderError(f"LATE_EVENT:{event.event_type}@{ts}<=record@{last_record_ts}")

    try:
        async for record in records:
            if should_stop is not None and should_stop():
                break
            while True:
                if held is None and not events_done:
                    if fetch is None:
                        fetch = asyncio.ensure_future(_next(events))
                    if blocking_lookahead:
                        # unpaced (ACCELERATED) source: awaiting the lookahead cannot stall in real
                        # time, and the result is correct under ANY scheduling of the two views
                        await asyncio.wait({fetch})
                    else:
                        for _ in range(SETTLE_SLICES):
                            await asyncio.sleep(0)
                            if fetch.done():
                                break
                    if fetch.done():
                        result = fetch.result()
                        fetch = None
                        if result is _DONE:
                            events_done = True
                        else:
                            held = result
                if held is not None and (held.source_timestamp_us is None
                                         or held.source_timestamp_us <= record.timestamp_us):
                    check_event(held)
                    yield MuxItem("event", held)
                    held = None
                    continue
                break
            last_record_ts = record.timestamp_us
            yield MuxItem("record", record)
        # records exhausted (or stop requested): deliver every remaining event, in order
        if held is not None:
            check_event(held)
            yield MuxItem("event", held)
            held = None
        if fetch is not None:
            result = await fetch
            fetch = None
            if result is not _DONE:
                check_event(result)
                yield MuxItem("event", result)
        while True:
            event = await _next(events)
            if event is _DONE:
                return
            check_event(event)
            yield MuxItem("event", event)
    finally:
        if fetch is not None and not fetch.done():
            fetch.cancel()
            await asyncio.gather(fetch, return_exceptions=True)
