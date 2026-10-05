"""CAP-002: CAPSTONE_DEVICE_REPLAY_V1, timing equivalence, existing stream-runtime compatibility."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from itertools import pairwise

import pytest

from product.contracts import ROOT
from product.devices.replay import canonical_json, run_replay, run_stream_runtime, sha256_hex
from product.devices.scenarios import MONITORING_SCENARIO_IDS, TimingMode
from simulation.profile_v2013 import iter_observed_records
from src.nhm.hashing import hash_file
from tests.capstone_device_support import drain, replay, scenario
from tests.test_capstone_simulated_device import SHORT


class FakeTime:
    """Injectable clock/sleep so LIVE_SPEED pacing is tested without waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_replay_digest_is_over_semantic_content_only() -> None:
    result = replay("NORMAL_MONITORING")
    semantic = result["semantic"]
    assert result["semantic_digest"] == sha256_hex(canonical_json(semantic))
    text = json.dumps(semantic).lower()
    for process_metadata in ("pid", "wall", "elapsed", "hostname", "tmp", "runtime_seconds"):
        assert f'"{process_metadata}' not in text
    assert semantic["replay_id"] == "CAPSTONE_DEVICE_REPLAY_V1"
    assert semantic["provenance"]["engineering_only"] is True


@pytest.mark.parametrize("scenario_id", MONITORING_SCENARIO_IDS)
def test_replay_semantics_are_stable_when_rerun(scenario_id: str) -> None:
    again = run_replay(scenario(scenario_id), include_stream_runtime=True)
    assert again["semantic"] == replay(scenario_id)["semantic"]


def test_replay_digest_reproduces_in_a_fresh_process() -> None:
    code = ("from product.devices.replay import run_replay;"
            "from product.devices.scenarios import load_scenarios;"
            "print(run_replay(load_scenarios()['DISCONNECT_RECONNECT'])['semantic_digest'])")
    outputs = {subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True,
                              capture_output=True, text=True,
                              env={"PYTHONPATH": "src:.", "PATH": ""}).stdout.strip()
               for _ in range(2)}
    assert outputs == {replay("DISCONNECT_RECONNECT")["semantic_digest"]}


def test_live_speed_and_accelerated_are_semantically_identical() -> None:
    fake = FakeTime()
    live = run_replay(SHORT, mode=TimingMode.LIVE_SPEED, sleep=fake.sleep, clock=fake.clock)
    fast = run_replay(SHORT, mode=TimingMode.ACCELERATED)
    assert live["semantic"] == fast["semantic"]
    assert live["semantic_digest"] == fast["semantic_digest"]
    assert live["timing_mode"] == "LIVE_SPEED" and fast["timing_mode"] == "ACCELERATED"
    # LIVE_SPEED really paces to the source timeline; ACCELERATED does not wait at all
    assert fake.sleeps and all(s > 0 for s in fake.sleeps)
    last_ts = fast["semantic"]["records"]["last_timestamp_us"] / 1_000_000
    assert last_ts - 0.5 <= sum(fake.sleeps) <= SHORT.duration_s + 0.5
    quiet = FakeTime()
    run_replay(SHORT, mode=TimingMode.ACCELERATED, sleep=quiet.sleep, clock=quiet.clock)
    assert quiet.sleeps == []


def test_live_speed_pacing_follows_source_timestamps_including_the_outage() -> None:
    fake = FakeTime()
    run_replay(SHORT, mode=TimingMode.LIVE_SPEED, sleep=fake.sleep, clock=fake.clock,
               include_stream_runtime=False)
    assert max(fake.sleeps) >= 1.9  # the ~2 s link outage is waited out, not skipped


def test_replay_event_digest_changes_if_event_order_changes() -> None:
    semantic = dict(replay("DISCONNECT_RECONNECT")["semantic"])
    base = sha256_hex(canonical_json(semantic))
    events = list(semantic["device_events"])
    events[5], events[6] = events[6], events[5]
    assert sha256_hex(canonical_json({**semantic, "device_events": events})) != base


# ---- existing stream runtime compatibility ----------------------------------------------------
def test_existing_stream_runtime_and_generator_are_unchanged() -> None:
    entry = json.loads(
        (ROOT / "reports/capstone/cap_001/upstream_protection_entry.json").read_text())
    for path in ("simulation/stream_runtime_v2013.py", "simulation/profile_v2013.py",
                 "simulation/types.py", "simulation/wearable.py", "api/schemas.py",
                 "contracts/sample_schema_v1.json"):
        assert hash_file(ROOT / path) == entry["tracked_files_sha256"][path], path
    import product.devices.replay as replay_module
    import simulation.stream_runtime_v2013 as runtime_module
    assert replay_module.WearableStreamRuntime is runtime_module.WearableStreamRuntime


def test_normal_source_feeds_the_existing_runtime_and_yields_canonical_windows() -> None:
    runtime = replay("NORMAL_MONITORING")["semantic"]["stream_runtime"]
    assert runtime["window_count"] == 21
    assert runtime["all_windows_2500_samples_250hz_10s"] is True
    stamps = [w["timestamp_us"] for w in runtime["windows"]]
    assert stamps[0] == 15_000_000
    assert all(b - a == 5_000_000 for a, b in pairwise(stamps))
    assert runtime["quality_counts"] == {"VALID": 21} and runtime["windows_with_context"] == 21
    assert runtime["gap_events_seen_by_runtime"] == 0


def _records(scenario_id: str):
    return list(iter_observed_records(scenario(scenario_id).profile()))


def test_quality_is_computed_downstream_not_taken_from_the_device_records() -> None:
    records = _records("POOR_SIGNAL")
    original = run_stream_runtime(records, "S")
    relabelled = [replace(r, ecg_quality="VALID") for r in records]  # lie in the source field
    again = run_stream_runtime(relabelled, "S")
    assert again["windows"] == original["windows"]  # QUALITY_V1 path ignores that field
    counts = original["quality_counts"]
    assert set(counts) - {"VALID"} and counts == replay("POOR_SIGNAL")["semantic"][
        "stream_runtime"]["quality_counts"]
    assert all(w["quality_reasons"] for w in original["windows"] if w["ecg_quality"] != "VALID")


def test_context_comes_from_observed_records_and_is_never_fabricated() -> None:
    runtime = replay("CONTEXT_LOSS")["semantic"]["stream_runtime"]
    flags = [w["context_present"] for w in runtime["windows"]]
    stamps = [w["timestamp_us"] for w in runtime["windows"]]
    assert flags[0] is True and flags[-1] is True and False in flags
    absent = [t for t, f in zip(stamps, flags, strict=True) if not f]
    assert absent and all(60_000_000 <= t <= 130_000_000 for t in absent)
    assert runtime["window_count"] > runtime["windows_with_context"] > 0
    stripped = [replace(r, ppg_quality=None, pr_ppg_bpm=None, spo2_pct=None, spo2_valid=False)
                for r in _records("NORMAL_MONITORING")]
    none = run_stream_runtime(stripped, "S")
    assert none["windows_with_context"] == 0  # adapter/runtime invent no context


def test_disconnect_outage_delivers_no_records_and_the_gap_is_observable_downstream() -> None:
    result = replay("DISCONNECT_RECONNECT")["semantic"]
    runtime = result["stream_runtime"]
    assert runtime["gap_events_seen_by_runtime"] >= 1
    outage_us = (70_000_000, 85_000_000)
    affected = [w for w in runtime["windows"]
                if w["missing_slots"] > 0 and w["timestamp_us"] >= outage_us[0]]
    assert affected and any(w["ecg_quality"] != "VALID" for w in affected)
    assert result["records"]["delivery_gap_index_intervals"] == [[25200, 30599]]
    assert runtime["all_windows_2500_samples_250hz_10s"] is True


def test_every_scenario_remains_compatible_with_the_ten_second_2500_sample_path() -> None:
    for scenario_id in MONITORING_SCENARIO_IDS:
        runtime = replay(scenario_id)["semantic"]["stream_runtime"]
        assert runtime["window_count"] > 0 and runtime["all_windows_2500_samples_250hz_10s"]


def test_replay_never_calls_a_model_or_the_inference_api() -> None:
    import product.devices.replay as module
    text = (ROOT / "product/devices/replay.py").read_text()
    for forbidden in ("infer-window", "MODEL_V2", "gateway", "torch", "fastapi", "requests"):
        assert forbidden not in text.replace('"NONE"', ""), forbidden
    assert module.RUNTIME_MODEL_ID == "NONE"
    for window in replay("NORMAL_MONITORING")["semantic"]["stream_runtime"]["windows"]:
        assert not {"raw_probability", "monitoring_state"} & set(window)


def test_stopping_early_still_produces_a_consistent_prefix() -> None:
    import asyncio

    from product.devices.simulated import SimulatedWearableSource
    source = SimulatedWearableSource(SHORT)

    async def go() -> int:
        await source.scan(0.0)
        await source.connect(source.descriptor.device_id)
        await source.start_stream("S")
        count = 0
        async for _ in source.records():
            count += 1
            if count == 50:
                await source.stop_stream()
        return count

    assert asyncio.run(go()) == 50
    events = drain(source.events())
    assert events[-1].event_type.value == "STREAM_STOPPED" and events[-1].reason_code == "USER_STOP"
