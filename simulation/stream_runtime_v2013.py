"""Streaming source-to-window runtime for the V2 software path (PRODUCTION side).

Consumes ONLY canonical `ObservedRecord`s -- the same interface a future physical wearable adapter
would feed -- and applies the production-like chain: timestamp/index ordering -> GAP_POLICY_V1 ->
causal stateful 360->250 Hz resampling -> causal ECG band-pass (the existing
ECGPreprocessingPipeline) -> 10 s windows at a 5 s cadence (right-edge timestamp) -> QUALITY_V1 ->
causal (latest-at-or-before) device-reported PPG/SpO2/pulse context -> API request events.

The window samples emitted here are the FILTERED, amplitude-preserving ECG (API input
representation). PER_WINDOW_ZSCORE_V1 is applied later, exactly once, by API_RUNTIME_V2 right
before the gateway; the ECG-HR context branch receives the unnormalized window.

Never imports SimulationTruth, the generator profile, or the truth module.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any

import numpy as np

from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.quality import evaluate_ecg_quality
from preprocessing.sync import latest_at_or_before
from simulation.types import ObservedRecord

SOURCE_RATE_HZ = 360
RESAMPLER_ID = "MITDB_360_TO_250_V1"
SLOT_US = 4000
WINDOW_SLOTS = 2500
CADENCE_US = 5_000_000
FIRST_RIGHT_EDGE_US = 15_000_000
EMIT_MARGIN_US = 500_000
CONTEXT_TOLERANCE_US = 5_000_000
ADC_RAIL_COUNTS = 2500
COUNTS_PER_MV = 1000
CHUNK_RECORDS = 360
SAMPLE_DECIMALS = 6


class WearableStreamRuntime:
    def __init__(self, *, session_id: str, model_id: str, replay_id: str) -> None:
        self.session_id, self.model_id, self.replay_id = session_id, model_id, replay_id
        self.pipeline = ECGPreprocessingPipeline(SOURCE_RATE_HZ, RESAMPLER_ID)
        capacity = 1 << 17
        self._values = np.full(capacity, np.nan)
        self._short = np.zeros(capacity, dtype=bool)
        self._long = np.zeros(capacity, dtype=bool)
        self._clip = np.zeros(capacity, dtype=bool)
        self._ctx_ts: list[int] = []
        self._ctx_val: list[tuple] = []
        self._last_ts = -1
        self._last_index = -1
        self._next_right_edge = FIRST_RIGHT_EDGE_US
        self._sequence = 0
        self.gap_events: list[Any] = []
        self.windows_emitted = 0

    # -- storage ---------------------------------------------------------------------------
    def _ensure(self, slot: int) -> None:
        while slot >= self._values.size:
            for name in ("_values", "_short", "_long", "_clip"):
                old = getattr(self, name)
                grown = np.full(old.size * 2, np.nan) if name == "_values" else np.zeros(
                    old.size * 2, dtype=bool)
                grown[: old.size] = old
                setattr(self, name, grown)

    # -- ingestion ---------------------------------------------------------------------------
    def ingest(self, records: Sequence[ObservedRecord]) -> list[dict[str, Any]]:
        usable = []
        for record in records:
            if record.sample_index <= self._last_index:
                raise ValueError("NON_MONOTONIC_SOURCE_INDEX")
            self._last_index = record.sample_index
            self._last_ts = record.timestamp_us
            ctx = (record.ppg_quality, record.pr_ppg_bpm, record.spo2_pct, record.spo2_valid)
            if (not self._ctx_val or self._ctx_val[-1] != ctx
                    or record.timestamp_us - self._ctx_ts[-1] >= 1_000_000):
                self._ctx_ts.append(record.timestamp_us)
                self._ctx_val.append(ctx)
            if record.ecg_raw is None:
                continue  # sensor dropout: sample never reaches the pipeline (becomes a gap)
            usable.append(record)
            if abs(record.ecg_raw) >= ADC_RAIL_COUNTS:
                slot = round(record.timestamp_us / SLOT_US)
                self._ensure(slot)
                self._clip[slot] = True
        if usable:
            values = np.asarray([r.ecg_raw for r in usable], dtype=np.float64) / COUNTS_PER_MV
            indices = np.asarray([r.sample_index for r in usable], dtype=np.int64)
            stamps = np.asarray([r.timestamp_us for r in usable], dtype=np.int64)
            out = self.pipeline.process(values, indices, source_timestamps_us=stamps)
            for chunk in out.chunks:
                slots = np.rint(chunk.timestamps_us / SLOT_US).astype(np.int64)
                self._ensure(int(slots.max()))
                self._values[slots] = chunk.filtered_values
            for event in out.events:
                self.gap_events.append(event)
                a = round(event.first_missing_index * 1_000_000 / SOURCE_RATE_HZ) // SLOT_US
                b = round(event.last_missing_index * 1_000_000 / SOURCE_RATE_HZ) // SLOT_US + 1
                self._ensure(b)
                flag = self._short if event.gap_kind == "SHORT" else self._long
                flag[a:b] = True
        return self._emit_ready()

    def _emit_ready(self, *, final: bool = False) -> list[dict[str, Any]]:
        events = []
        while self._last_ts >= self._next_right_edge + (0 if final else EMIT_MARGIN_US):
            events.append(self._window(self._next_right_edge))
            self._next_right_edge += CADENCE_US
        return events

    def finish(self) -> list[dict[str, Any]]:
        return self._emit_ready(final=False)

    # -- window construction ---------------------------------------------------------------
    def _window(self, right_edge_us: int) -> dict[str, Any]:
        end = right_edge_us // SLOT_US
        self._ensure(end)
        sl = slice(end - WINDOW_SLOTS, end)
        raw = self._values[sl].copy()
        missing = np.isnan(raw)
        long_span = bool(self._long[sl].any() or missing.any())
        short = bool(self._short[sl].any())
        quality = evaluate_ecg_quality(
            np.nan_to_num(raw), short_gap_intersects=short, long_gap_spans=long_span,
            clipping_mask=self._clip[sl])
        context = None
        if self._ctx_ts:
            aligned = latest_at_or_before(
                np.asarray(self._ctx_ts, dtype=np.int64), self._ctx_val, right_edge_us,
                tolerance_us=CONTEXT_TOLERANCE_US)
            if aligned.available:
                ppg_quality, pr, spo2, spo2_valid = aligned.value
                if ppg_quality is not None or pr is not None:
                    context = {"quality": ppg_quality, "pr_bpm": pr,
                               "spo2_pct": spo2 if spo2_valid else None,
                               "spo2_valid": bool(spo2_valid and spo2 is not None)}
        samples = np.round(np.nan_to_num(raw), SAMPLE_DECIMALS).tolist()
        event = {
            "sequence_index": self._sequence,
            "window_id": f"{self.session_id}-W{self._sequence:04d}",
            "replay_id": self.replay_id,
            "contract_version": "API_SCHEMA_V1",
            "timestamp_us": right_edge_us,
            "ecg": {"samples": samples, "target_hz": 250, "window_seconds": 10},
            "ecg_quality": quality.state.value,
            "ppg_context": context,
            "model_id": self.model_id,
            "diagnostics": {"quality_reasons": [r.value for r in quality.reasons],
                            "short_gap": short, "long_gap_or_missing": long_span,
                            "missing_slots": int(missing.sum())},
        }
        self._sequence += 1
        self.windows_emitted += 1
        return event


def deliver_chunks(
    records: Iterable[ObservedRecord], *, mode: str = "ACCELERATED",
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[list[ObservedRecord]]:
    """Chunk the canonical stream. LIVE_SPEED_REPLAY paces delivery to the record timestamps
    (real time); ACCELERATED_REPLAY delivers immediately. Pacing never alters any record."""
    if mode not in ("LIVE_SPEED_REPLAY", "ACCELERATED_REPLAY", "ACCELERATED"):
        raise ValueError(f"unknown replay mode {mode}")
    buffer: list[ObservedRecord] = []
    started = clock()
    for record in records:
        buffer.append(record)
        if len(buffer) >= CHUNK_RECORDS:
            if mode == "LIVE_SPEED_REPLAY":
                wait = buffer[-1].timestamp_us / 1_000_000 - (clock() - started)
                if wait > 0:
                    sleep(wait)
            yield buffer
            buffer = []
    if buffer:
        yield buffer


def run_stream(records: Iterable[ObservedRecord], *, session_id: str, model_id: str,
               replay_id: str, mode: str = "ACCELERATED_REPLAY",
               sleep: Callable[[float], None] = time.sleep) -> list[dict[str, Any]]:
    runtime = WearableStreamRuntime(session_id=session_id, model_id=model_id, replay_id=replay_id)
    events: list[dict[str, Any]] = []
    for chunk in deliver_chunks(records, mode=mode, sleep=sleep):
        events.extend(runtime.ingest(chunk))
    events.extend(runtime.finish())
    return events
