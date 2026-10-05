"""CAPSTONE_DEVICE_REPLAY_V1 -- deterministic semantic replay of the device/edge layer.

Drives a scenario through the real edge path (VirtualEdgeNode -> SimulatedWearableSource) and
summarises WHAT was delivered: the device-event sequence, record statistics, gap and context
intervals, and (optionally) the windows the EXISTING ``WearableStreamRuntime`` derives from that
exact record sequence. The semantic digest excludes only wall-clock/process metadata (runtime
seconds, pids, paths), which this module never records. No model/inference API is touched.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from itertools import pairwise
from typing import Any

from product.devices.scenarios import ScenarioSpec, TimingMode
from product.devices.simulated import SimulatedWearableSource
from product.edge.virtual import VirtualEdgeNode, monitoring_edge_identity
from simulation.profile_v2013 import SOURCE_RATE_HZ
from simulation.stream_runtime_v2013 import WearableStreamRuntime, deliver_chunks
from simulation.types import ObservedRecord

REPLAY_ID = "CAPSTONE_DEVICE_REPLAY_V1"
RUNTIME_MODEL_ID = "NONE"  # the stream runtime only labels windows; no model is ever called


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def event_dict(event: Any) -> dict[str, Any]:
    return json.loads(event.model_dump_json())


def _intervals(flags: list[tuple[int, bool]]) -> list[list[int]]:
    """Contiguous [first_sample_index, last_sample_index] runs where the flag is True."""
    runs: list[list[int]] = []
    open_run: list[int] | None = None
    for index, flag in flags:
        if flag and open_run is None:
            open_run = [index, index]
        elif flag and open_run is not None:
            open_run[1] = index
        elif not flag and open_run is not None:
            runs.append(open_run)
            open_run = None
    if open_run is not None:
        runs.append(open_run)
    return runs


def summarize_records(records: list[ObservedRecord]) -> dict[str, Any]:
    digest = hashlib.sha256()
    gaps: list[list[int]] = []
    previous = None
    context_flags: list[tuple[int, bool]] = []
    ecg_none: list[tuple[int, bool]] = []
    for record in records:
        digest.update(canonical_json(record.to_canonical_dict()) + b"\n")
        if previous is not None and record.sample_index != previous.sample_index + 1:
            gaps.append([previous.sample_index + 1, record.sample_index - 1])
        previous = record
        context_flags.append((record.sample_index, record.ppg_quality is None))
        ecg_none.append((record.sample_index, record.ecg_raw is None))
    sources = sorted({r.source for r in records})
    return {
        "record_count": len(records),
        "first_sample_index": records[0].sample_index if records else None,
        "last_sample_index": records[-1].sample_index if records else None,
        "first_timestamp_us": records[0].timestamp_us if records else None,
        "last_timestamp_us": records[-1].timestamp_us if records else None,
        "records_sha256": digest.hexdigest(), "delivery_gap_index_intervals": gaps,
        "context_absent_index_intervals": _intervals(context_flags),
        "ecg_sensor_dropout_index_intervals": _intervals(ecg_none),
        "record_sources": sources, "participant_ids": sorted({r.participant_id for r in records}),
        "monotonic_sample_index": all(b.sample_index > a.sample_index
                                      for a, b in pairwise(records)),
        "monotonic_timestamp": all(b.timestamp_us > a.timestamp_us
                                   for a, b in pairwise(records)),
    }


def run_stream_runtime(records: list[ObservedRecord], session_id: str) -> dict[str, Any]:
    """Feed the delivered records, unchanged, to the existing WearableStreamRuntime."""
    runtime = WearableStreamRuntime(session_id=session_id, model_id=RUNTIME_MODEL_ID,
                                    replay_id=REPLAY_ID)
    windows: list[dict[str, Any]] = []
    for chunk in deliver_chunks(records, mode="ACCELERATED_REPLAY"):
        windows.extend(runtime.ingest(chunk))
    windows.extend(runtime.finish())
    rows = []
    sample_digest = hashlib.sha256()
    for window in windows:
        samples = window["ecg"]["samples"]
        sample_digest.update(canonical_json(samples) + b"\n")
        rows.append({
            "timestamp_us": window["timestamp_us"], "ecg_quality": window["ecg_quality"],
            "ecg_sample_count": len(samples), "ecg_target_hz": window["ecg"]["target_hz"],
            "window_seconds": window["ecg"]["window_seconds"],
            "context_present": window["ppg_context"] is not None,
            "quality_reasons": window["diagnostics"]["quality_reasons"],
            "missing_slots": window["diagnostics"]["missing_slots"]})
    quality_counts: dict[str, int] = {}
    for row in rows:
        quality_counts[row["ecg_quality"]] = quality_counts.get(row["ecg_quality"], 0) + 1
    return {
        "runtime": "simulation.stream_runtime_v2013.WearableStreamRuntime (unchanged)",
        "window_count": len(rows), "windows": rows, "quality_counts": quality_counts,
        "windows_with_context": sum(1 for r in rows if r["context_present"]),
        "all_windows_2500_samples_250hz_10s": all(
            r["ecg_sample_count"] == 2500 and r["ecg_target_hz"] == 250
            and r["window_seconds"] == 10 for r in rows),
        "gap_events_seen_by_runtime": len(runtime.gap_events),
        "windows_samples_sha256": sample_digest.hexdigest(),
    }


async def _drive(spec: ScenarioSpec, mode: TimingMode, sleep: Any, clock: Any
                 ) -> tuple[list[ObservedRecord], list[dict[str, Any]], dict[str, Any]]:
    kwargs: dict[str, Any] = {}
    if sleep is not None:
        kwargs["sleep"] = sleep
    if clock is not None:
        kwargs["clock"] = clock
    source = SimulatedWearableSource(spec, mode=mode, **kwargs)
    node = VirtualEdgeNode(monitoring_edge_identity(source.descriptor.device_id), source)
    await node.start_live_monitoring(spec.session_id)

    async def collect_records() -> list[ObservedRecord]:
        return [r async for r in node.live_records()]

    async def collect_events() -> list[dict[str, Any]]:
        return [event_dict(e) async for e in node.live_events()]

    records, events = await asyncio.gather(collect_records(), collect_events())
    descriptor = json.loads(source.descriptor.model_dump_json())
    return records, events, descriptor


def run_replay(spec: ScenarioSpec, *, mode: TimingMode = TimingMode.ACCELERATED,
               include_stream_runtime: bool = True, sleep: Any = None, clock: Any = None
               ) -> dict[str, Any]:
    records, events, descriptor = asyncio.run(_drive(spec, mode, sleep, clock))
    summary = summarize_records(records)
    semantic: dict[str, Any] = {
        "replay_id": REPLAY_ID, "scenario_id": spec.scenario_id, "seed": spec.seed,
        "duration_s": spec.duration_s, "source_rate_hz_simulation_convention": SOURCE_RATE_HZ,
        "provenance": spec.provenance(), "device_descriptor_at_end": descriptor,
        "device_event_sequence": [e["event_type"] for e in events], "device_events": events,
        "records": summary,
        "expected_outage_index_intervals": [list(i) for i in spec.outage_intervals()],
    }
    if include_stream_runtime:
        semantic["stream_runtime"] = run_stream_runtime(records, spec.session_id)
    return {"semantic": semantic, "semantic_digest": sha256_hex(canonical_json(semantic)),
            "timing_mode": mode.value}
