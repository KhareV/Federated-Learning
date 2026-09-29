"""SYNC_CAUSAL_V1 timestamp-only synchronization primitives.

The central rule is latest valid context at or before the ECG right-edge boundary.  No helper
in this module can select a future context sample.  Hardware timing tolerance is intentionally
not defined while T004 is blocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

import numpy as np

SYNC_CONTRACT_ID = "SYNC_CAUSAL_V1"
HARDWARE_TOLERANCE_STATUS = "VERIFICATION_REQUIRED_T004"
T = TypeVar("T")


@dataclass(frozen=True)
class AlignedContext(Generic[T]):
    available: bool
    timestamp_us: int | None
    value: T | None
    age_us: int | None
    status: str


def _validated_timestamps(timestamps_us: np.ndarray) -> np.ndarray:
    timestamps = np.asarray(timestamps_us, dtype=np.int64)
    if timestamps.ndim != 1:
        raise ValueError("timestamps_us must be one-dimensional")
    if timestamps.size > 1 and bool(np.any(np.diff(timestamps) < 0)):
        raise ValueError("OUT_OF_ORDER_TIMESTAMPS: timestamps must be nondecreasing")
    return timestamps


def latest_at_or_before(
    timestamps_us: np.ndarray,
    values: list[T] | tuple[T, ...] | np.ndarray,
    boundary_timestamp_us: int,
    *,
    tolerance_us: int | None = None,
) -> AlignedContext[T]:
    """Select the rightmost sample ``<= boundary``; rightmost wins duplicate timestamps."""
    timestamps = _validated_timestamps(timestamps_us)
    if len(values) != timestamps.size:
        raise ValueError("values and timestamps_us must have equal length")
    if tolerance_us is not None and tolerance_us < 0:
        raise ValueError("tolerance_us must be nonnegative")
    index = int(np.searchsorted(timestamps, boundary_timestamp_us, side="right") - 1)
    if index < 0:
        return AlignedContext(False, None, None, None, "CONTEXT_UNAVAILABLE")
    timestamp = int(timestamps[index])
    age = boundary_timestamp_us - timestamp
    if tolerance_us is not None and age > tolerance_us:
        return AlignedContext(False, None, None, age, "CONTEXT_OUTSIDE_TOLERANCE")
    return AlignedContext(True, timestamp, values[index], age, "ALIGNED_CAUSALLY")


def causal_context_window(
    timestamps_us: np.ndarray,
    values: np.ndarray,
    boundary_timestamp_us: int,
    *,
    duration_us: int = 10_000_000,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract a continuous-context timestamp slice on ``[t-duration, t)``."""
    timestamps = _validated_timestamps(timestamps_us)
    samples = np.asarray(values)
    if samples.shape[0] != timestamps.size:
        raise ValueError("values first dimension must match timestamps_us")
    left = int(np.searchsorted(timestamps, boundary_timestamp_us - duration_us, side="left"))
    right = int(np.searchsorted(timestamps, boundary_timestamp_us, side="left"))
    return timestamps[left:right].copy(), samples[left:right].copy()


def measured_event_offset_us(reference_timestamp_us: int, context_timestamp_us: int) -> int:
    """Return context minus reference offset; this is timestamp engineering, not physiology."""
    return int(context_timestamp_us) - int(reference_timestamp_us)


def offset_within_tolerance(offset_us: int, tolerance_us: int) -> bool:
    if tolerance_us < 0:
        raise ValueError("tolerance_us must be nonnegative")
    return abs(offset_us) <= tolerance_us
