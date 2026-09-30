"""Pure sample-count-weighted model-delta aggregation for T024."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FL_STATE_TRANSPORT_ID = "FL_STATE_TRANSPORT_V1"
FEDAVG_AGGREGATION_ID = "SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1"
State = Mapping[str, NDArray[np.generic]]


class AggregationError(ValueError):
    """Raised when an update cannot be safely aggregated."""


@dataclass(frozen=True)
class ClientUpdate:
    """One complete client model-state delta and its training-example count."""

    client_id: str
    num_examples: int
    delta: State
    transport_id: str = FL_STATE_TRANSPORT_ID


def _copy_state(state: State) -> dict[str, NDArray[np.generic]]:
    if not state:
        raise AggregationError("empty model state")
    return {key: np.array(value, copy=True, order="C") for key, value in state.items()}


def _validate_update(global_state: State, update: ClientUpdate) -> None:
    if isinstance(update.num_examples, bool) or not isinstance(update.num_examples, int):
        raise AggregationError(f"{update.client_id}: num_examples must be an integer")
    if update.num_examples <= 0:
        raise AggregationError(f"{update.client_id}: num_examples must be positive")
    if update.transport_id != FL_STATE_TRANSPORT_ID:
        raise AggregationError(f"{update.client_id}: transport-policy version mismatch")
    if set(update.delta) != set(global_state):
        raise AggregationError(f"{update.client_id}: state keys mismatch")
    for key, global_value in global_state.items():
        delta = np.asarray(update.delta[key])
        if delta.shape != global_value.shape:
            raise AggregationError(f"{update.client_id}: shape mismatch for {key}")
        if delta.dtype != global_value.dtype:
            raise AggregationError(f"{update.client_id}: dtype-role mismatch for {key}")
        if np.issubdtype(global_value.dtype, np.floating) and not np.isfinite(delta).all():
            raise AggregationError(f"{update.client_id}: nonfinite delta for {key}")


def aggregate_weighted_deltas(
    global_state: State, updates: Sequence[ClientUpdate]
) -> tuple[dict[str, NDArray[np.generic]], dict[str, NDArray[np.generic]]]:
    """Return ``(new_state, weighted_delta)`` without mutating any input.

    Every floating state entry is aggregated by local ``num_examples``. Non-floating
    bookkeeping buffers remain exactly equal to the server/global value.
    """

    server = _copy_state(global_state)
    if not updates:
        raise AggregationError("at least one client update is required")
    for value in server.values():
        if np.issubdtype(value.dtype, np.floating) and not np.isfinite(value).all():
            raise AggregationError("global state contains nonfinite floating values")
    for update in updates:
        _validate_update(server, update)

    total_examples = sum(update.num_examples for update in updates)
    new_state: dict[str, NDArray[np.generic]] = {}
    weighted_delta: dict[str, NDArray[np.generic]] = {}
    for key, global_value in server.items():
        if np.issubdtype(global_value.dtype, np.floating):
            accumulator = np.zeros(global_value.shape, dtype=np.float64)
            for update in updates:
                accumulator += np.asarray(update.delta[key], dtype=np.float64) * update.num_examples
            mean_delta = accumulator / total_examples
            cast_delta = np.asarray(mean_delta, dtype=global_value.dtype)
            candidate = np.asarray(global_value + cast_delta, dtype=global_value.dtype)
            if not np.isfinite(candidate).all():
                raise AggregationError(f"nonfinite aggregate for {key}")
            weighted_delta[key] = np.array(cast_delta, copy=True)
            new_state[key] = np.array(candidate, copy=True)
        else:
            weighted_delta[key] = np.zeros_like(global_value)
            new_state[key] = np.array(global_value, copy=True)
    return new_state, weighted_delta

