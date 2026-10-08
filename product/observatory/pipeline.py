"""Opt-in, bounded reconstruction using the UNCHANGED canonical streaming operators.

This is not a captured historical trace and never performs model inference. Observers delegate
to the real gap controller, resampler and filter; parity tests compare the resulting runtime
windows with an unobserved WearableStreamRuntime on the same ObservedRecords.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np

from preprocessing.windowing import NORMALIZATION_EPSILON, NORMALIZATION_ID, normalize_window_zscore
from product.devices.scenarios import ScenarioSpec
from product.observatory.models import (
    GapTrace,
    NormalizationTrace,
    SignalPoint,
    SignalStage,
    WindowTrace,
)
from simulation.profile_v2013 import iter_observed_records
from simulation.stream_runtime_v2013 import (
    CADENCE_US,
    CHUNK_RECORDS,
    EMIT_MARGIN_US,
    FIRST_RIGHT_EDGE_US,
    SLOT_US,
    SOURCE_RATE_HZ,
    WINDOW_SLOTS,
    WearableStreamRuntime,
)
from simulation.types import ObservedRecord

TRACE_VERSION = "NHM_PIPELINE_TRACE_V1"
DISPLAY_LIMIT = 1200
COUNTS_PER_MV = 1000  # the frozen synthetic source/runtime conversion, not hardware calibration


def _display(points: list[SignalPoint]) -> list[SignalPoint]:
    if len(points) <= DISPLAY_LIMIT:
        return points
    # Preserve missing-run boundaries so chart decimation can never draw through a gap.
    mandatory = {0, len(points) - 1}
    for i in range(1, len(points)):
        if (points[i].value is None) != (points[i - 1].value is None):
            mandatory.update((i - 1, i))
    if len(mandatory) > DISPLAY_LIMIT:
        raise ValueError("TOO_MANY_GAP_BOUNDARIES_FOR_BOUNDED_DISPLAY")
    budget = DISPLAY_LIMIT - len(mandatory)
    stride = max(1, math.ceil(len(points) / max(1, budget)))
    chosen = set(mandatory)
    for i in range(0, len(points), stride):
        if len(chosen) >= DISPLAY_LIMIT:
            break
        chosen.add(i)
    return [points[i] for i in sorted(chosen)]


def _stage(stage_id: str, unit: str, rate: int, points: list[SignalPoint]) -> SignalStage:
    shown = _display(points)
    return SignalStage(
        stage_id=stage_id, unit=unit, sample_rate_hz=rate,
        actual_point_count=len(points), displayed_point_count=len(shown),
        display_is_decimated=len(shown) != len(points), points=shown,
    )


def _actual_stage_points(values: dict[int, float], cadence_us: int = SLOT_US) -> list[SignalPoint]:
    """Plot exact operator timestamps; insert null sentinels for discontinuities.

    The rational resampler's timestamps are source-clock mapped and need not be
    exact multiples of 4 ms. Snapping to a 4 ms grid would silently omit samples.
    """
    result: list[SignalPoint] = []
    previous: int | None = None
    for timestamp, value in sorted(values.items()):
        if previous is not None and timestamp - previous > cadence_us * 1.5:
            result.append(SignalPoint(timestamp_us=previous + cadence_us, value=None))
        result.append(SignalPoint(timestamp_us=timestamp, value=value))
        previous = timestamp
    return result


class _DelegatingObserver:
    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class _GapObserver(_DelegatingObserver):
    def __init__(self, inner: Any, left_index: int, right_index: int) -> None:
        super().__init__(inner)
        self.left_index, self.right_index = left_index, right_index
        self.values: dict[int, float] = {}

    def process(self, values: np.ndarray, indices: np.ndarray) -> Any:
        result = self.inner.process(values, indices)
        for chunk in result.chunks:
            for index, value in zip(chunk.source_indices, chunk.values, strict=True):
                i = int(index)
                if self.left_index <= i < self.right_index:
                    self.values[i] = float(value)
        return result


class _ResamplerObserver(_DelegatingObserver):
    def __init__(self, inner: Any, left_us: int, right_us: int) -> None:
        super().__init__(inner)
        self.left_us, self.right_us = left_us, right_us
        self.values: dict[int, float] = {}
        self.latest_timestamps: np.ndarray | None = None

    def process(self, values: np.ndarray, source_start_index: int) -> Any:
        result = self.inner.process(values, source_start_index)
        self.latest_timestamps = result.timestamps_us
        if result.timestamps_us is not None:
            for timestamp, value in zip(result.timestamps_us, result.values, strict=True):
                ts = int(timestamp)
                if self.left_us <= ts < self.right_us:
                    self.values[ts] = float(value)
        return result


class _FilterObserver(_DelegatingObserver):
    def __init__(self, inner: Any, resampler: _ResamplerObserver) -> None:
        super().__init__(inner)
        self.resampler = resampler
        self.values: dict[int, float] = {}

    def process(self, values: np.ndarray) -> np.ndarray:
        result = self.inner.process(values)
        timestamps = self.resampler.latest_timestamps
        if timestamps is not None:
            for timestamp, value in zip(timestamps, result, strict=True):
                ts = int(timestamp)
                if self.resampler.left_us <= ts < self.resampler.right_us:
                    self.values[ts] = float(value)
        return result


def reconstruct_window(
    scenario: ScenarioSpec, window_index: int, *, session_id: str | None = None,
    records_factory: Callable[[Any], Iterable[ObservedRecord]] = iter_observed_records,
) -> WindowTrace:
    """Reconstruct one selected synthetic window without inference, training or persistent writes.

    Only the actual frozen scenario/profile is accepted. The generated source stream is fed to
    the canonical WearableStreamRuntime in its production 360-record chunk cadence. Observers
    copy bounded values while delegating every operation to the original operator.
    """
    right_us = FIRST_RIGHT_EDGE_US + window_index * CADENCE_US
    if window_index < 0 or right_us + EMIT_MARGIN_US >= scenario.duration_s * 1_000_000:
        raise ValueError("WINDOW_INDEX_OUT_OF_SCENARIO_RANGE")
    left_us = right_us - WINDOW_SLOTS * SLOT_US
    left_index = math.ceil(left_us * SOURCE_RATE_HZ / 1_000_000)
    right_index = math.ceil(right_us * SOURCE_RATE_HZ / 1_000_000)
    trace_session_id = session_id or f"OBSERVATORY_{scenario.scenario_id}"
    runtime = WearableStreamRuntime(
        session_id=trace_session_id, model_id="MODEL_V2_FINAL",
        replay_id=TRACE_VERSION,
    )
    gap = _GapObserver(runtime.pipeline.gap_controller, left_index, right_index)
    resampler = _ResamplerObserver(runtime.pipeline.resampler, left_us, right_us)
    filt = _FilterObserver(runtime.pipeline.filter, resampler)
    runtime.pipeline.gap_controller = gap
    runtime.pipeline.resampler = resampler
    runtime.pipeline.filter = filt

    raw: dict[int, int | None] = {}
    batch = []
    selected: dict[str, Any] | None = None
    for record in records_factory(scenario.profile()):
        if left_index <= record.sample_index < right_index:
            raw[record.sample_index] = record.ecg_raw
        batch.append(record)
        if len(batch) < CHUNK_RECORDS:
            continue
        emitted = runtime.ingest(batch)
        batch = []
        selected = next((w for w in emitted if w["sequence_index"] == window_index), None)
        if selected is not None:
            break
    if selected is None and batch:
        selected = next((w for w in runtime.ingest(batch)
                         if w["sequence_index"] == window_index), None)
    if selected is None:
        raise RuntimeError("CANONICAL_WINDOW_NOT_EMITTED")

    raw_points = [SignalPoint(
        timestamp_us=round(i * 1_000_000 / SOURCE_RATE_HZ), source_index=i,
        value=None if raw.get(i) is None else float(raw[i]) / COUNTS_PER_MV,
    ) for i in range(left_index, right_index)]
    filled_points = [SignalPoint(
        timestamp_us=round(i * 1_000_000 / SOURCE_RATE_HZ), source_index=i,
        value=gap.values.get(i),
    ) for i in range(left_index, right_index)]
    target_times = range(left_us, right_us, SLOT_US)
    resampled_points = _actual_stage_points(resampler.values)
    filtered_points = _actual_stage_points(filt.values)
    stages = [
        _stage("SOURCE_OBSERVED", "synthetic mV convention", SOURCE_RATE_HZ, raw_points),
        _stage("GAP_POLICY_V1", "synthetic mV convention", SOURCE_RATE_HZ, filled_points),
        _stage("MITDB_360_TO_250_V1", "synthetic mV convention", 250, resampled_points),
        _stage("PREPROC_V1_ECG_FILTER_V1", "synthetic mV convention", 250, filtered_points),
    ]
    quality = selected["ecg_quality"]
    if quality == "UNUSABLE":
        normalization = NormalizationTrace(
            status="NOT_APPLIED_UNUSABLE", identity=NORMALIZATION_ID,
            mean=None, std=None, epsilon=NORMALIZATION_EPSILON,
            shape=None, dtype=None, tensor_sha256=None,
        )
    else:
        api_window = np.asarray(selected["ecg"]["samples"], dtype=np.float64)
        normalized = normalize_window_zscore(api_window, epsilon=NORMALIZATION_EPSILON)
        tensor = np.ascontiguousarray(normalized.astype(np.float32).reshape(1, 2500))
        normalization = NormalizationTrace(
            status="RECONSTRUCTED_MODEL_INPUT", identity=NORMALIZATION_ID,
            mean=float(np.mean(api_window)), std=float(np.std(api_window, ddof=0)),
            epsilon=NORMALIZATION_EPSILON, shape=[1, 2500], dtype="float32",
            tensor_sha256=hashlib.sha256(tensor.tobytes()).hexdigest(),
        )
        stages.append(_stage(
            "PER_WINDOW_ZSCORE_V1", "dimensionless", 250,
            [SignalPoint(timestamp_us=ts, value=float(value))
             for ts, value in zip(target_times, tensor[0], strict=True)],
        ))
    gaps = [GapTrace(
        kind=event.gap_kind, first_missing_index=event.first_missing_index,
        last_missing_index=event.last_missing_index, missing_count=event.missing_count,
        duration_ms=event.duration_ms, fill_count=event.fill_count,
        previous_segment_id=event.previous_segment_id,
        next_segment_id=event.next_segment_id,
        quality_requirement=event.quality_requirement,
    ) for event in runtime.gap_events
        if event.last_missing_index >= left_index and event.first_missing_index < right_index]
    return WindowTrace(
        scenario_id=scenario.scenario_id, session_id=session_id,
        window_index=window_index, window_id=selected["window_id"],
        left_timestamp_us=left_us, right_timestamp_us=right_us,
        source_rate_hz=SOURCE_RATE_HZ, target_rate_hz=250,
        window_sample_count=WINDOW_SLOTS, cadence_us=CADENCE_US,
        quality_state=quality, quality_reasons=selected["diagnostics"]["quality_reasons"],
        missing_slots=int(selected["diagnostics"]["missing_slots"]),
        context_available=selected["ppg_context"] is not None,
        gaps=gaps, stages=stages, normalization=normalization,
        persisted_inference=None, inference_evidence_status="NOT_ATTACHED_SCENARIO_RECONSTRUCTION",
        limitations=[
            "Deterministic reconstruction from the frozen synthetic profile, "
            "not captured live intermediate arrays.",
            "Displayed chart points are decimated from the actual selected arrays; "
            "no interpolated values.",
            "No model inference is executed by this read-only reconstruction.",
            "Synthetic mV is a generator convention, not physical wearable calibration.",
        ],
    )
