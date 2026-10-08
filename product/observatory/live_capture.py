"""Opt-in one-window observations on an existing live monitoring runtime instance.

Only instance-local delegating observers are installed before the first source batch. The
frozen runtime, operator implementations, window output and inference path are unchanged.
The normalized tensor is reconstructed from the *captured emitted window*, not captured at
the separate gateway boundary; this distinction remains explicit in the returned trace.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Sequence
from typing import Any

import numpy as np

from preprocessing.windowing import NORMALIZATION_EPSILON, NORMALIZATION_ID, normalize_window_zscore
from product.observatory.models import GapTrace, NormalizationTrace, SignalPoint, WindowTrace
from product.observatory.pipeline import (
    COUNTS_PER_MV,
    _actual_stage_points,
    _FilterObserver,
    _GapObserver,
    _ResamplerObserver,
    _stage,
)
from simulation.stream_runtime_v2013 import (
    CADENCE_US,
    FIRST_RIGHT_EDGE_US,
    SLOT_US,
    SOURCE_RATE_HZ,
    WINDOW_SLOTS,
    WearableStreamRuntime,
)
from simulation.types import ObservedRecord


class LiveWindowCapture:
    """A bounded memory-only capture of one actual selected session window."""

    def __init__(self, runtime: WearableStreamRuntime, *, scenario_id: str,
                 session_id: str, window_index: int) -> None:
        if window_index < 0:
            raise ValueError("INVALID_CAPTURE_WINDOW_INDEX")
        self.scenario_id, self.session_id, self.window_index = scenario_id, session_id, window_index
        self.right_us = FIRST_RIGHT_EDGE_US + window_index * CADENCE_US
        self.left_us = self.right_us - WINDOW_SLOTS * SLOT_US
        self.left_index = math.ceil(self.left_us * SOURCE_RATE_HZ / 1_000_000)
        self.right_index = math.ceil(self.right_us * SOURCE_RATE_HZ / 1_000_000)
        self.created_monotonic = time.monotonic()
        self.trace: WindowTrace | None = None
        self.error: str | None = None
        self.raw: dict[int, int | None] = {}
        self.runtime = runtime
        self.gap = _GapObserver(runtime.pipeline.gap_controller, self.left_index, self.right_index)
        self.resampler = _ResamplerObserver(runtime.pipeline.resampler, self.left_us, self.right_us)
        self.filt = _FilterObserver(runtime.pipeline.filter, self.resampler)
        runtime.pipeline.gap_controller = self.gap
        runtime.pipeline.resampler = self.resampler
        runtime.pipeline.filter = self.filt
        original_ingest = runtime.ingest

        def observed_ingest(records: Sequence[ObservedRecord]) -> list[dict[str, Any]]:
            for record in records:
                if self.left_index <= record.sample_index < self.right_index:
                    self.raw[record.sample_index] = record.ecg_raw
            emitted = original_ingest(records)
            if self.trace is None and self.error is None:
                selected = next((item for item in emitted
                                 if item["sequence_index"] == self.window_index), None)
                if selected is not None:
                    try:
                        self.trace = self._snapshot(selected)
                    except Exception as error:  # observer must never make monitoring fail
                        self.error = f"CAPTURE_SERIALIZATION_FAILED:{type(error).__name__}"
            return emitted

        runtime.ingest = observed_ingest  # type: ignore[method-assign]

    def _snapshot(self, selected: dict[str, Any]) -> WindowTrace:
        raw_points = [SignalPoint(
            timestamp_us=round(index * 1_000_000 / SOURCE_RATE_HZ), source_index=index,
            value=None if self.raw.get(index) is None else float(self.raw[index]) / COUNTS_PER_MV,
        ) for index in range(self.left_index, self.right_index)]
        filled_points = [SignalPoint(
            timestamp_us=round(index * 1_000_000 / SOURCE_RATE_HZ), source_index=index,
            value=self.gap.values.get(index),
        ) for index in range(self.left_index, self.right_index)]
        stages = [
            _stage("SOURCE_OBSERVED", "synthetic mV convention", SOURCE_RATE_HZ, raw_points),
            _stage("GAP_POLICY_V1", "synthetic mV convention", SOURCE_RATE_HZ, filled_points),
            _stage("MITDB_360_TO_250_V1", "synthetic mV convention", 250,
                   _actual_stage_points(self.resampler.values)),
            _stage("PREPROC_V1_ECG_FILTER_V1", "synthetic mV convention", 250,
                   _actual_stage_points(self.filt.values)),
        ]
        if selected["ecg_quality"] == "UNUSABLE":
            normalized = NormalizationTrace(
                status="NOT_APPLIED_UNUSABLE", identity=NORMALIZATION_ID,
                mean=None, std=None, epsilon=NORMALIZATION_EPSILON,
                shape=None, dtype=None, tensor_sha256=None,
            )
        else:
            emitted = np.asarray(selected["ecg"]["samples"], dtype=np.float64)
            tensor = np.ascontiguousarray(normalize_window_zscore(
                emitted, epsilon=NORMALIZATION_EPSILON).astype(np.float32).reshape(1, 2500))
            normalized = NormalizationTrace(
                status="RECONSTRUCTED_MODEL_INPUT", identity=NORMALIZATION_ID,
                mean=float(np.mean(emitted)), std=float(np.std(emitted, ddof=0)),
                epsilon=NORMALIZATION_EPSILON, shape=[1, 2500], dtype="float32",
                tensor_sha256=hashlib.sha256(tensor.tobytes()).hexdigest(),
            )
            stages.append(_stage(
                "PER_WINDOW_ZSCORE_V1", "dimensionless", 250,
                [SignalPoint(timestamp_us=timestamp, value=float(value))
                 for timestamp, value in zip(range(self.left_us, self.right_us, SLOT_US),
                                             tensor[0], strict=True)],
            ))
        gaps = [GapTrace(
            kind=event.gap_kind, first_missing_index=event.first_missing_index,
            last_missing_index=event.last_missing_index, missing_count=event.missing_count,
            duration_ms=event.duration_ms, fill_count=event.fill_count,
            previous_segment_id=event.previous_segment_id,
            next_segment_id=event.next_segment_id,
            quality_requirement=event.quality_requirement,
        ) for event in self.runtime.gap_events
            if event.last_missing_index >= self.left_index
            and event.first_missing_index < self.right_index]
        return WindowTrace(
            classification="CAPTURED_LIVE_PREPROCESSING",
            scenario_id=self.scenario_id, session_id=self.session_id,
            window_index=self.window_index, window_id=selected["window_id"],
            left_timestamp_us=self.left_us, right_timestamp_us=self.right_us,
            source_rate_hz=SOURCE_RATE_HZ, target_rate_hz=250,
            window_sample_count=WINDOW_SLOTS, cadence_us=CADENCE_US,
            quality_state=selected["ecg_quality"],
            quality_reasons=selected["diagnostics"]["quality_reasons"],
            missing_slots=int(selected["diagnostics"]["missing_slots"]),
            context_available=selected["ppg_context"] is not None,
            gaps=gaps, stages=stages, normalization=normalized,
            persisted_inference=None,
            inference_evidence_status="NOT_ATTACHED_CAPTURED_LIVE_PREPROCESSING",
            claim_boundary="CAPTURED_LIVE_PREPROCESSING_NORMALIZED_INPUT_RECONSTRUCTED_NOT_GATEWAY_CAPTURED",
            limitations=[
                "Source, gap, resampler and filter arrays were captured "
                "from this live runtime instance.",
                "The normalized tensor is reconstructed from its actual emitted filtered window; "
                "it was not captured inside the separate inference gateway.",
                "Only one selected bounded window is kept in memory; restart discards it.",
                "Displayed chart points are decimated actual captured samples.",
                "Synthetic mV is a generator convention, not physical wearable calibration.",
            ],
        )
