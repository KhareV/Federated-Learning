"""GAP_POLICY_V1 -- source-time gap classification, causal zero-order-hold short-gap fill,
and long-gap segment reset provenance.

Operates entirely on the SOURCE sampling grid, before the T011 stateful resampler ever sees
the stream (locked preprocessing order: source validation -> GAP_POLICY_V1 -> resampler ->
physiological filter). A short gap (<=100 ms) is filled with the exact last valid pre-gap
value at every missing source position, never anything derived from the first post-gap real
sample. A long gap (>100 ms) receives no fill: it ends the current continuous segment and the
next real sample begins a new one, carrying enough provenance for T013 to mark any spanning
10-second window UNUSABLE.

Owns: gap classification and fill/segment provenance only. Does not own the resampler, any
physiological filter, real window construction, or final QUALITY_V1 classification -- those
values (DEGRADED / UNUSABLE) are floors/requirements for T013 to apply, not window-level
quality decisions made here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

GAP_POLICY_ID = "GAP_POLICY_V1"
SHORT_GAP_MAX_MS = 100.0

REAL_SOURCE_SAMPLE = "REAL_SOURCE_SAMPLE"
CAUSAL_ZOH_FILL = "CAUSAL_ZOH_FILL"

GAP_KIND_SHORT = "SHORT"
GAP_KIND_LONG = "LONG"

QUALITY_FLOOR_DEGRADED = "DEGRADED"
QUALITY_REQUIREMENT_UNUSABLE = "UNUSABLE"


class NonMonotonicSourceIndexError(ValueError):
    """NON_MONOTONIC_SOURCE_INDEX: the next real source index was <= the previous one
    (duplicate or backward index). Never silently reordered or interpreted as a gap."""


def is_short_gap(missing_count: int, source_rate_hz: int) -> bool:
    """Exact integer form of `missing_count / source_rate_hz <= 0.100` seconds -- no
    floating-point threshold comparison. missing_count == 0 (no gap) is trivially short."""
    return 10 * missing_count <= source_rate_hz


@dataclass(frozen=True)
class GapEvent:
    gap_policy_id: str
    gap_kind: str  # GAP_KIND_SHORT | GAP_KIND_LONG
    missing_count: int
    duration_num: int  # missing_count
    duration_den: int  # source_rate_hz; duration_seconds == duration_num / duration_den
    duration_ms: float
    first_missing_index: int
    last_missing_index: int
    last_pre_gap_index: int
    first_post_gap_index: int
    fill_count: int  # missing_count for SHORT, 0 for LONG
    previous_segment_id: int
    next_segment_id: int
    quality_requirement: str  # QUALITY_FLOOR_DEGRADED | QUALITY_REQUIREMENT_UNUSABLE


@dataclass(frozen=True)
class SegmentChunk:
    segment_id: int
    source_indices: np.ndarray
    values: np.ndarray
    gap_mask: np.ndarray
    starts_new_segment: bool


@dataclass(frozen=True)
class GapControllerOutput:
    chunks: list[SegmentChunk]
    events: list[GapEvent]


class GapController:
    """Streaming GAP_POLICY_V1 state machine. Feed real (value, source_index) samples in
    monotonically increasing source-index order, in any chunking; the result is identical
    regardless of how the input is chunked (cross-call and cross-chunk gaps are both
    detected from the same persisted `_last_real_index`/`_last_real_value` state)."""

    def __init__(self, source_rate_hz: int, *, gap_policy_id: str = GAP_POLICY_ID) -> None:
        self.source_rate_hz = source_rate_hz
        self.gap_policy_id = gap_policy_id
        self._last_real_index: int | None = None
        self._last_real_value: float | None = None
        self._segment_id = 0

    def reset(self, *, segment_id: int | None = None) -> None:
        """Force a fresh segment (e.g. a new session/recording). Does not itself touch any
        downstream resampler/filter -- the integration layer reacts to
        SegmentChunk.starts_new_segment."""
        self._last_real_index = None
        self._last_real_value = None
        self._segment_id = segment_id if segment_id is not None else self._segment_id + 1

    def process(
        self, values: np.ndarray, source_indices: np.ndarray
    ) -> GapControllerOutput:
        values = np.asarray(values, dtype=np.float64)
        source_indices = np.asarray(source_indices, dtype=np.int64)
        if values.shape != source_indices.shape:
            raise ValueError("values and source_indices must have the same shape")
        if values.size and not np.all(np.isfinite(values)):
            raise ValueError("NONFINITE_SOURCE_SAMPLE: values must be finite")

        chunks: list[SegmentChunk] = []
        events: list[GapEvent] = []

        pending_indices: list[int] = []
        pending_values: list[float] = []
        pending_mask: list[int] = []
        chunk_starts_new_segment = self._last_real_index is None

        def flush() -> None:
            nonlocal pending_indices, pending_values, pending_mask, chunk_starts_new_segment
            if not pending_indices:
                return
            chunks.append(
                SegmentChunk(
                    segment_id=self._segment_id,
                    source_indices=np.asarray(pending_indices, dtype=np.int64),
                    values=np.asarray(pending_values, dtype=np.float64),
                    gap_mask=np.asarray(pending_mask, dtype=np.int8),
                    starts_new_segment=chunk_starts_new_segment,
                )
            )
            pending_indices, pending_values, pending_mask = [], [], []
            chunk_starts_new_segment = False

        for value, index in zip(values.tolist(), source_indices.tolist(), strict=True):
            index = int(index)
            if self._last_real_index is None:
                pending_indices.append(index)
                pending_values.append(value)
                pending_mask.append(0)
                self._last_real_index = index
                self._last_real_value = value
                continue

            if index <= self._last_real_index:
                raise NonMonotonicSourceIndexError(
                    f"NON_MONOTONIC_SOURCE_INDEX: next index {index} <= previous "
                    f"{self._last_real_index}"
                )

            missing_count = index - self._last_real_index - 1
            if missing_count == 0:
                pending_indices.append(index)
                pending_values.append(value)
                pending_mask.append(0)
                self._last_real_index = index
                self._last_real_value = value
                continue

            short = is_short_gap(missing_count, self.source_rate_hz)
            first_missing = self._last_real_index + 1
            last_missing = index - 1
            duration_ms = round(1000.0 * missing_count / self.source_rate_hz, 6)
            previous_segment_id = self._segment_id

            if short:
                for missing_index in range(first_missing, last_missing + 1):
                    pending_indices.append(missing_index)
                    pending_values.append(self._last_real_value)
                    pending_mask.append(1)
                pending_indices.append(index)
                pending_values.append(value)
                pending_mask.append(0)
                events.append(
                    GapEvent(
                        gap_policy_id=self.gap_policy_id,
                        gap_kind=GAP_KIND_SHORT,
                        missing_count=missing_count,
                        duration_num=missing_count,
                        duration_den=self.source_rate_hz,
                        duration_ms=duration_ms,
                        first_missing_index=first_missing,
                        last_missing_index=last_missing,
                        last_pre_gap_index=self._last_real_index,
                        first_post_gap_index=index,
                        fill_count=missing_count,
                        previous_segment_id=previous_segment_id,
                        next_segment_id=previous_segment_id,
                        quality_requirement=QUALITY_FLOOR_DEGRADED,
                    )
                )
                self._last_real_index = index
                self._last_real_value = value
            else:
                flush()
                self._segment_id += 1
                events.append(
                    GapEvent(
                        gap_policy_id=self.gap_policy_id,
                        gap_kind=GAP_KIND_LONG,
                        missing_count=missing_count,
                        duration_num=missing_count,
                        duration_den=self.source_rate_hz,
                        duration_ms=duration_ms,
                        first_missing_index=first_missing,
                        last_missing_index=last_missing,
                        last_pre_gap_index=self._last_real_index,
                        first_post_gap_index=index,
                        fill_count=0,
                        previous_segment_id=previous_segment_id,
                        next_segment_id=self._segment_id,
                        quality_requirement=QUALITY_REQUIREMENT_UNUSABLE,
                    )
                )
                chunk_starts_new_segment = True
                pending_indices.append(index)
                pending_values.append(value)
                pending_mask.append(0)
                self._last_real_index = index
                self._last_real_value = value

        flush()
        return GapControllerOutput(chunks=chunks, events=events)
