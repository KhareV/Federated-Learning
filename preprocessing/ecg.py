"""Canonical ECG preprocessing integration layer: GAP_POLICY_V1 -> T011 stateful resampler ->
causal ECG SOS bandpass filter, in that locked order.

Owns: the ECG filter identity (PREPROC_V1_ECG_FILTER_V1, StatefulECGFilter) and the narrow
streaming pipeline that wires GapController -> StatefulRationalResampler -> StatefulECGFilter
together, propagating segment resets and gap provenance correctly. Does not own window
construction, per-window normalization, QRS/feature engineering, or model input construction
-- all of that is T013+.

The only rational resampling path used here is the validated T011
`preprocessing.resample.StatefulRationalResampler`; this module never reimplements or
reroutes around it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from preprocessing.filters import FilterSpec, StatefulSOSFilter, load_filter_spec
from preprocessing.gaps import GapController, GapEvent
from preprocessing.resample import ResamplerSpec, StatefulRationalResampler, load_resampler_spec

ECG_FILTER_ID = "PREPROC_V1_ECG_FILTER_V1"


class StatefulECGFilter(StatefulSOSFilter):
    """Thin identity-bound wrapper: always PREPROC_V1_ECG_FILTER_V1 (0.5-40 Hz, fs=250 Hz,
    4th-order Butterworth bandpass, SOS)."""

    def __init__(self, spec: FilterSpec | None = None) -> None:
        super().__init__(spec or load_filter_spec(ECG_FILTER_ID))
        if self.spec.filter_id != ECG_FILTER_ID:
            raise ValueError(
                f"StatefulECGFilter requires {ECG_FILTER_ID}, got {self.spec.filter_id}"
            )


@dataclass(frozen=True)
class ECGPipelineChunk:
    segment_id: int
    starts_new_segment: bool
    global_source_index_start: int
    output_indices: np.ndarray
    filtered_values: np.ndarray
    output_time_seconds: np.ndarray
    timestamps_us: np.ndarray | None
    source_gap_mask: np.ndarray


@dataclass(frozen=True)
class ECGPipelineOutput:
    chunks: list[ECGPipelineChunk]
    events: list[GapEvent]


class ECGPreprocessingPipeline:
    """source samples (with source indices, and optional source timestamps) -> GAP_POLICY_V1
    -> validated T011 resampler -> causal ECG SOS filter. No windows, no normalization, no
    feature extraction."""

    def __init__(
        self,
        source_rate_hz: int,
        resampler_id: str,
        *,
        filter_id: str = ECG_FILTER_ID,
        resampler_spec: ResamplerSpec | None = None,
        filter_spec: FilterSpec | None = None,
    ) -> None:
        self.gap_controller = GapController(source_rate_hz)
        self.resampler_spec = resampler_spec or load_resampler_spec(resampler_id)
        self.filter_spec = filter_spec or load_filter_spec(filter_id)
        self.resampler = StatefulRationalResampler(self.resampler_spec)
        self.filter = StatefulECGFilter(self.filter_spec)
        # T011's causal-readiness arithmetic is only exercised (by every T011 test) with
        # source_start_index == 0 at each segment start; it is not validated for an arbitrary
        # nonzero per-segment origin, and integration testing here showed passing a raw global
        # index after a post-gap reset produces wrong output counts. Rather than editing the
        # validated T011 module, this pipeline always feeds the resampler segment-local
        # (0-based) indices -- exactly the segment-local contract T012 is written to expect --
        # and keeps the true global source index only as separate provenance
        # (ECGPipelineChunk.global_source_index_start), never passed into the resampler.
        self._segment_origin_global_index = 0

    def process(
        self,
        values: np.ndarray,
        source_indices: np.ndarray,
        *,
        source_timestamps_us: np.ndarray | None = None,
    ) -> ECGPipelineOutput:
        timestamp_by_index: dict[int, int] = {}
        if source_timestamps_us is not None:
            timestamp_by_index = dict(
                zip(
                    np.asarray(source_indices, dtype=np.int64).tolist(),
                    np.asarray(source_timestamps_us, dtype=np.int64).tolist(),
                    strict=True,
                )
            )

        gap_output = self.gap_controller.process(values, source_indices)
        chunks: list[ECGPipelineChunk] = []

        for chunk in gap_output.chunks:
            global_source_index_start = int(chunk.source_indices[0])
            if chunk.starts_new_segment:
                segment_timestamp_us = timestamp_by_index.get(global_source_index_start)
                self.resampler.reset(segment_start_timestamp_us=segment_timestamp_us)
                self.filter.reset(segment_id=chunk.segment_id)
                self._segment_origin_global_index = global_source_index_start

            local_source_start = global_source_index_start - self._segment_origin_global_index
            resampled = self.resampler.process(chunk.values, local_source_start)
            filtered_values = self.filter.process(resampled.values)

            chunks.append(
                ECGPipelineChunk(
                    segment_id=chunk.segment_id,
                    starts_new_segment=chunk.starts_new_segment,
                    global_source_index_start=global_source_index_start,
                    output_indices=resampled.output_indices,
                    filtered_values=filtered_values,
                    output_time_seconds=resampled.output_time_seconds,
                    timestamps_us=resampled.timestamps_us,
                    source_gap_mask=chunk.gap_mask,
                )
            )

        return ECGPipelineOutput(chunks=chunks, events=gap_output.events)

    def state_metadata(self) -> dict[str, Any]:
        return {
            "resampler": self.resampler.state_metadata(),
            "filter": self.filter.state_metadata(),
        }
