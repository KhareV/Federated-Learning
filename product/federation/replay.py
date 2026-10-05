# ruff: noqa: E501
"""REPLAY runs: a real replay of a prior COMPLETED LIVE_RUN's recorded federation events.

No training, submission, aggregation, SecAgg, candidate creation or governance happens in a replay. The
stream is semantically identical to its source (same kinds, payloads and order) except the new run id,
event ids, timestamps, and the visible ``run_type=REPLAY`` of ``federation.status`` events."""

from __future__ import annotations

from typing import Any

from product.events import FederationLiveEvent
from product.federation.base import RunType

REPLAY_ID = "CAPSTONE_FEDERATION_REPLAY_V1"


def semantic_projection(events: list[FederationLiveEvent]) -> list[dict[str, Any]]:
    """The comparison projection used for source/replay parity (and by the tests/evidence)."""
    out = []
    for e in events:
        payload = e.payload.model_dump(mode="json")
        if e.event_type == "federation.status":
            payload.pop("run_type")
        out.append({"event_type": e.event_type, "sequence_index": e.sequence_index,
                    "payload": payload})
    return out


def retarget(event: FederationLiveEvent) -> FederationLiveEvent:
    """Mark a cloned federation.status event as a REPLAY (every other kind is untouched)."""
    if event.event_type != "federation.status":
        return event
    payload = event.payload.model_copy(update={"run_type": RunType.REPLAY})
    return event.model_copy(update={"payload": payload})
