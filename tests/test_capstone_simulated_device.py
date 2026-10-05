"""CAP-002: SIMULATED_WEARABLE_SOURCE_V1 lifecycle, events, data flow and monitoring scenarios."""

from __future__ import annotations

import asyncio
import inspect
import re

import pytest

from product.contracts import IllegalTransitionError, load_contract
from product.devices.base import (
    AdapterType,
    DeviceEventType,
    DeviceSource,
    DeviceState,
    event_state_effect,
)
from product.devices.scenarios import (
    MONITORING_SCENARIO_IDS,
    ScenarioSegment,
    ScenarioSpec,
    TimingMode,
    load_scenarios,
)
from product.devices.simulated import SimulatedWearableSource, UnknownDeviceError
from simulation import SIMULATION_VERSION
from simulation.types import ObservedRecord
from tests.capstone_device_support import (
    check_no_delivery_in_outages,
    check_only_observed_records,
    check_records_ordered,
    drain,
    replay,
    scenario,
)

SHORT = ScenarioSpec(
    scenario_id="TEST_SHORT", seed=20269999, duration_s=20,
    segments=(ScenarioSegment("up", 0, 8, None, "VALID"),
              ScenarioSegment("down", 8, 10, "TRANSPORT_DROPPED_CHUNK", "VALID"),
              ScenarioSegment("up2", 10, 20, None, "VALID")))


def _source(spec: ScenarioSpec = SHORT, **kw) -> SimulatedWearableSource:
    return SimulatedWearableSource(spec, **kw)


async def _attach(source: SimulatedWearableSource) -> None:
    await source.scan(0.0)
    await source.connect(source.descriptor.device_id)


# ---- DeviceSource compliance + descriptor ---------------------------------------------------
def test_simulated_wearable_implements_the_frozen_device_source_protocol() -> None:
    source = _source()
    assert isinstance(source, DeviceSource)
    contract = load_contract("device_source")
    for name, spec in contract["methods"].items():
        member = getattr(SimulatedWearableSource, name)
        assert inspect.iscoroutinefunction(member) is spec["async"] or (
            name in ("records", "events") and inspect.isasyncgenfunction(member)), name
        assert [p for p in inspect.signature(member).parameters if p != "self"] == spec["args"]


def test_descriptor_is_deterministic_synthetic_and_claims_no_hardware() -> None:
    first, second = _source().descriptor, _source().descriptor
    assert first == second
    assert first.adapter_type is AdapterType.SIMULATED and first.simulation is True
    assert first.simulation_version == SIMULATION_VERSION == "WEARABLE_SIM_V1"
    assert first.source_dataset_id == "WEARABLE_SIM_V1"
    assert first.source_mode == "SYNTHETIC_PHYSIOLOGY"
    assert first.connection_state is DeviceState.DETACHED
    assert first.hardware_specific_fields_status == "NOT_APPLICABLE"
    caps = first.capabilities
    assert caps.supports_ecg and caps.supports_spo2_context and caps.supports_device_events
    assert caps.supports_ppg is False  # the generator emits no PPG waveform
    assert list(caps.nominal_source_rates_hz) == ["ECG_SIMULATION_CONVENTION"]
    assert caps.nominal_source_rates_hz["ECG_SIMULATION_CONVENTION"] == 360
    dumped = first.model_dump_json().lower().replace("wearable_sim_v1", "")
    assert not re.search(r"\bble\b|bluetooth|battery|wearable_v1|certif|clinical", dumped)


# ---- lifecycle ------------------------------------------------------------------------------
def test_attachment_flow_scan_pair_connect_start_and_stop() -> None:
    source = _source()
    assert source.connection_state is DeviceState.DETACHED

    async def run() -> list[DeviceState]:
        seen = []
        found = await source.scan(1.0)
        seen.append(source.connection_state)
        assert [d.device_id for d in found] == [source.descriptor.device_id]
        await source.connect(found[0].device_id)
        seen.append(source.connection_state)
        await source.start_stream("S1")
        seen.append(source.connection_state)
        await source.stop_stream()
        seen.append(source.connection_state)
        return seen

    assert asyncio.run(run()) == [DeviceState.FOUND, DeviceState.CONNECTED,
                                  DeviceState.STREAMING, DeviceState.STOPPED]
    events = drain(source.events())
    assert [e.event_type.value for e in events] == [
        "SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED",
        "STREAM_STARTED", "STREAM_STOPPED"]
    assert [e.device_state.value for e in events] == [
        "SCANNING", "FOUND", "PAIRING", "CONNECTED", "STREAMING", "STOPPED"]


def test_stopped_may_return_to_connected_or_detached_per_the_frozen_contract() -> None:
    async def to_stopped() -> SimulatedWearableSource:
        source = _source()
        await _attach(source)
        await source.start_stream("S1")
        await source.stop_stream()
        return source

    source = asyncio.run(to_stopped())

    async def resume() -> None:
        await source.connect(source.descriptor.device_id)  # STOPPED -> CONNECTED
        await source.start_stream("S2")  # restart is a fresh deterministic stream
        await source.stop_stream()
        await source.disconnect()  # STOPPED -> DETACHED

    asyncio.run(resume())
    assert source.connection_state is DeviceState.DETACHED
    with pytest.raises(IllegalTransitionError):  # STOPPED -> STREAMING stays illegal
        async def bad() -> None:
            other = _source()
            await _attach(other)
            await other.start_stream("S")
            await other.stop_stream()
            await other.start_stream("S")
        asyncio.run(bad())


@pytest.mark.parametrize("command", ["connect", "start_stream", "stop_stream", "disconnect",
                                     "scan_twice", "connect_unknown"])
def test_illegal_commands_fail_closed_without_state_or_event_change(command: str) -> None:
    source = _source()

    async def run() -> None:
        if command == "scan_twice":
            await source.scan(0.0)
            await source.scan(0.0)
        elif command == "connect":
            await source.connect(source.descriptor.device_id)  # DETACHED -> PAIRING illegal
        elif command == "start_stream":
            await source.start_stream("S")
        elif command == "stop_stream":
            await source.stop_stream()
        elif command == "disconnect":
            await source.disconnect()
        else:
            await source.scan(0.0)
            await source.connect("SOME_OTHER_DEVICE")

    expected = UnknownDeviceError if command == "connect_unknown" else IllegalTransitionError
    with pytest.raises(expected):
        asyncio.run(run())
    state_after = source.connection_state
    events_after = len(drain(source.events()))
    if command == "scan_twice" or command == "connect_unknown":
        assert state_after is DeviceState.FOUND and events_after == 2
    else:
        assert state_after is DeviceState.DETACHED and events_after == 0


def test_every_accepted_transition_emits_one_typed_deterministic_event() -> None:
    def run_once() -> list[dict]:
        source = _source()

        async def go() -> None:
            await _attach(source)
            await source.start_stream("S1")
            async for _ in source.records():
                pass

        asyncio.run(go())
        return [e.model_dump(mode="json") for e in drain(source.events())]

    first, second = run_once(), run_once()
    assert first == second  # fresh-instance determinism of the full event stream
    contract = load_contract("device_source")
    for event in first:
        assert event["event_version"] == "DEVICE_EVENT_V1" and event["source"] == "SIMULATED"
        assert event["event_id"] == f"NHM_VIRTUAL_WEARABLE_00-EV{event['sequence_index']:06d}"
        assert event["device_state"] == contract["event_type_state_effects"][event["event_type"]]
        assert event["recoverable"] is True
        assert event["metadata"]["scenario_id"] == "TEST_SHORT"
    indices = [e["sequence_index"] for e in first]
    assert indices == list(range(len(first)))
    stamps = [e["product_timestamp_us"] for e in first]
    assert stamps == sorted(stamps)
    assert all(e["session_id"] is None for e in first[:4])
    assert all(e["session_id"] == "S1" for e in first[4:])
    for event in first:  # events never carry model or physiological output
        assert not {"probability", "monitoring_state", "ecg_quality"} & set(event)


def test_device_error_follows_the_frozen_lifecycle() -> None:
    source = _source()

    async def go() -> None:
        await source.scan(0.0)
        await source.connect(source.descriptor.device_id)
        await source.start_stream("S1")
        source.simulate_error("TEST_ERROR", recoverable=False)

    asyncio.run(go())
    assert source.connection_state is DeviceState.ERROR
    last = drain(source.events())[-1]
    assert last.event_type is DeviceEventType.DEVICE_ERROR and last.recoverable is False
    assert last.reason_code == "TEST_ERROR"
    assert event_state_effect(last.event_type) is DeviceState.ERROR
    with pytest.raises(IllegalTransitionError):
        _source().simulate_error("X")  # DETACHED -> ERROR is not legal
    assert drain(source.records()) == []  # a streamed error ends delivery


def test_user_stop_halts_record_delivery() -> None:
    source = _source()

    async def go() -> int:
        await _attach(source)
        await source.start_stream("S1")
        got = 0
        async for _ in source.records():
            got += 1
            if got == 100:
                await source.stop_stream()
        return got

    assert asyncio.run(go()) == 100
    assert source.connection_state is DeviceState.STOPPED
    assert [e.event_type.value for e in drain(source.events())][-1] == "STREAM_STOPPED"


# ---- data flow ------------------------------------------------------------------------------
def test_records_are_observed_records_only_ordered_and_synthetic() -> None:
    source = _source()

    async def go() -> list:
        await _attach(source)
        await source.start_stream("S1")
        return [r async for r in source.records()]

    records = asyncio.run(go())
    assert records and check_only_observed_records(records)
    assert check_records_ordered(records)
    for record in records:
        assert isinstance(record, ObservedRecord)
        assert record.source == "SYNTHETIC_PHYSIOLOGY"
        assert record.participant_id.startswith("SIM_P")
        assert record.timestamp_us >= 0 and record.contract_version == "SAMPLE_SCHEMA_V1"
        assert record.preprocess_version is None  # preprocessing is downstream
    assert not [name for name in vars(records[0]) if "truth" in name.lower()]
    forbidden = {"probability", "calibrated", "monitoring_state", "prediction", "label"}
    fields = set(records[0].to_canonical_dict())
    assert not [f for f in fields if any(word in f for word in forbidden)]


# ---- link outage ----------------------------------------------------------------------------
def test_disconnect_actually_interrupts_delivery_and_nothing_is_fabricated() -> None:
    spec = scenario("DISCONNECT_RECONNECT")
    out = replay("DISCONNECT_RECONNECT")["semantic"]
    (start, end), = spec.outage_intervals()
    gaps = out["records"]["delivery_gap_index_intervals"]
    assert gaps == [[start, end - 1]]  # exactly the outage is absent
    assert out["records"]["record_count"] == spec.duration_s * 360 - (end - start)
    assert out["device_event_sequence"][4:] == [
        "STREAM_STARTED", "DEVICE_DISCONNECTED", "RECONNECT_STARTED", "DEVICE_RECONNECTED",
        "STREAM_STARTED", "STREAM_STOPPED"]
    events = out["device_events"]
    down = next(e for e in events if e["event_type"] == "DEVICE_DISCONNECTED")
    up = next(e for e in events if e["event_type"] == "DEVICE_RECONNECTED")
    assert down["source_timestamp_us"] == round(start * 1_000_000 / 360)
    assert up["source_timestamp_us"] == round(end * 1_000_000 / 360)
    assert down["device_state"] == "DISCONNECTED"
    assert [e["device_state"] for e in events if e["sequence_index"] > down["sequence_index"]][
        :3] == ["RECONNECTING", "CONNECTED", "STREAMING"]


def test_no_record_is_delivered_between_disconnect_and_reconnect() -> None:
    source = _source()

    async def go() -> list[tuple[str, int]]:
        await _attach(source)
        await source.start_stream("S1")
        timeline: list[tuple[str, int]] = []

        async def watch_records() -> None:
            async for record in source.records():
                timeline.append((source.connection_state.value, record.sample_index))

        await watch_records()
        return timeline

    timeline = asyncio.run(go())
    assert timeline and {state for state, _ in timeline} <= {"STREAMING", "CONNECTED"}
    indices = [i for _, i in timeline]
    outage = SHORT.outage_intervals()[0]
    assert not [i for i in indices if outage[0] <= i < outage[1]]
    assert indices[indices.index(outage[0] - 1) + 1] == outage[1]  # resumes at the source clock


def test_post_reconnect_indices_and_timestamps_follow_the_source_clock() -> None:
    records = drain_all(_source())
    outage_end = SHORT.outage_intervals()[0][1]
    first_after = next(r for r in records if r.sample_index >= outage_end)
    assert first_after.sample_index == outage_end
    assert first_after.timestamp_us == round(outage_end * 1_000_000 / 360)
    before = [r for r in records if r.sample_index < outage_end][-1]
    assert first_after.timestamp_us - before.timestamp_us > 1_000_000 * 1.9  # ~2 s outage


def drain_all(source: SimulatedWearableSource) -> list[ObservedRecord]:
    async def go() -> list[ObservedRecord]:
        await _attach(source)
        await source.start_stream("S1")
        return [r async for r in source.records()]

    return asyncio.run(go())


# ---- negative controls (the checkers must fail on corrupted data) -----------------------------
def test_negative_controls_the_invariant_checkers_detect_corruption() -> None:
    records = drain_all(_source())
    outages = SHORT.outage_intervals()
    assert check_records_ordered(records) and check_no_delivery_in_outages(records, outages)
    assert check_only_observed_records(records)
    assert not check_only_observed_records([*records, {"sample_index": 1}])  # wrong type
    assert not check_only_observed_records([*records, object()])
    swapped = [records[1], records[0], *records[2:]]
    assert not check_records_ordered(swapped)  # non-monotonic sequence
    stray = next(r for r in records if r.sample_index == outages[0][0] - 1)
    from dataclasses import replace
    injected = [*records, replace(stray, sample_index=outages[0][0] + 5)]
    assert not check_no_delivery_in_outages(injected, outages)  # record during DISCONNECTED


# ---- scenarios ------------------------------------------------------------------------------
@pytest.mark.parametrize("scenario_id", MONITORING_SCENARIO_IDS)
def test_scenario_matches_the_frozen_cap001_contract_and_is_engineering_only(
        scenario_id: str) -> None:
    spec = scenario(scenario_id)
    entry = next(s for s in load_contract("demo_scenarios")["scenarios"]
                 if s["scenario_id"] == scenario_id)
    assert spec.seed == entry["seed"] and spec.duration_s == entry["duration_s"]
    out = replay(scenario_id)["semantic"]
    assert out["device_event_sequence"] == entry["expected_connection_events"]
    provenance = out["provenance"]
    assert provenance["engineering_only"] is True and provenance["scientific_evidence"] is False
    assert provenance["virtual_participant_is_human"] is False
    assert provenance["wearable_v1"] is False
    assert provenance["dataset_id"] == "WEARABLE_SIM_V1"
    assert provenance["source_mode"] == "SYNTHETIC_PHYSIOLOGY"
    assert out["records"]["record_sources"] == ["SYNTHETIC_PHYSIOLOGY"]
    assert out["records"]["monotonic_sample_index"] and out["records"]["monotonic_timestamp"]
    assert out["records"]["participant_ids"] == [out["records"]["participant_ids"][0]]
    assert entry["engineering_only"] is True and entry["model_v2_live_inference_invoked"] is True
    assert "probability" not in str(out["device_events"]).lower()


@pytest.mark.parametrize("scenario_id", MONITORING_SCENARIO_IDS)
def test_scenario_is_deterministic_across_fresh_runs(scenario_id: str) -> None:
    from product.devices.replay import run_replay
    again = run_replay(load_scenarios()[scenario_id])
    assert again["semantic_digest"] == replay(scenario_id)["semantic_digest"]


def test_different_scenarios_and_seeds_yield_different_streams() -> None:
    digests = {sid: replay(sid)["semantic"]["records"]["records_sha256"]
               for sid in MONITORING_SCENARIO_IDS}
    assert len(set(digests.values())) == len(digests)
    from dataclasses import replace

    from product.devices.replay import run_replay
    base = scenario("NORMAL_MONITORING")
    other = run_replay(replace(base, seed=base.seed + 1), include_stream_runtime=False)
    assert other["semantic"]["records"]["records_sha256"] != digests["NORMAL_MONITORING"]


def test_normal_monitoring_is_continuous_with_context_and_no_faults() -> None:
    out = replay("NORMAL_MONITORING")["semantic"]["records"]
    spec = scenario("NORMAL_MONITORING")
    assert out["record_count"] == spec.duration_s * 360
    assert out["delivery_gap_index_intervals"] == []
    assert out["context_absent_index_intervals"] == []
    assert out["ecg_sensor_dropout_index_intervals"] == []
    assert (out["first_sample_index"], out["last_sample_index"]) == (0, spec.duration_s * 360 - 1)


def test_context_loss_removes_ppg_context_but_keeps_ecg_flowing() -> None:
    out = replay("CONTEXT_LOSS")["semantic"]["records"]
    spec = scenario("CONTEXT_LOSS")
    assert out["record_count"] == spec.duration_s * 360  # ECG never interrupted
    assert out["context_absent_index_intervals"] == [[60 * 360, 120 * 360 - 1]]
    assert out["delivery_gap_index_intervals"] == []
    assert out["ecg_sensor_dropout_index_intervals"] == []
    assert "CONTEXT_UNAVAILABLE" not in str(replay("CONTEXT_LOSS")["semantic"]["device_events"])


def test_poor_signal_uses_existing_source_faults_and_no_outage_events() -> None:
    spec = scenario("POOR_SIGNAL")
    assert {s.ecg_fault for s in spec.segments} - {None} <= {"ECG_FLATLINE", "ECG_CLIPPING"}
    out = replay("POOR_SIGNAL")["semantic"]
    assert out["records"]["record_count"] == spec.duration_s * 360
    assert "DEVICE_DISCONNECTED" not in out["device_event_sequence"]


def test_mixed_session_sequences_context_loss_fault_disconnect_and_recovery() -> None:
    spec = scenario("MIXED_MONITORING_SESSION")
    out = replay("MIXED_MONITORING_SESSION")["semantic"]
    order = [s.name for s in spec.segments]
    assert order == ["clean", "ppg_missing", "invalid_spo2", "clipping", "link_down", "clean_tail"]
    assert out["records"]["context_absent_index_intervals"] == [[100 * 360, 160 * 360 - 1]]
    assert out["records"]["delivery_gap_index_intervals"] == [[330 * 360, 345 * 360 - 1]]
    assert out["device_event_sequence"].count("DEVICE_RECONNECTED") == 1
    assert out["records"]["last_sample_index"] == spec.duration_s * 360 - 1  # recovered streaming
    assert out["device_events"][-1]["event_type"] == "STREAM_STOPPED"


def test_scenario_spec_rejects_malformed_timelines() -> None:
    with pytest.raises(ValueError, match="ORDERED"):
        ScenarioSpec("X", 1, 10, (ScenarioSegment("a", 5, 8, None, "VALID"),
                                  ScenarioSegment("b", 0, 3, None, "VALID")))
    with pytest.raises(ValueError, match="UNKNOWN_ECG_FAULT"):
        ScenarioSpec("X", 1, 10, (ScenarioSegment("a", 0, 3, "ECG_MAGIC", "VALID"),))
    with pytest.raises(ValueError, match="UNKNOWN_CONTEXT_MODE"):
        ScenarioSpec("X", 1, 10, (ScenarioSegment("a", 0, 3, None, "NOPE"),))
    with pytest.raises(ValueError, match="OUTAGE_MUST_END"):
        ScenarioSpec("X", 1, 10, (ScenarioSegment("a", 5, 10, "TRANSPORT_DROPPED_CHUNK",
                                                  "VALID"),))


def test_timing_mode_names_and_unimplemented_scenarios_are_untouched() -> None:
    assert [m.value for m in TimingMode] == ["LIVE_SPEED", "ACCELERATED"]
    ids = {s["scenario_id"] for s in load_contract("demo_scenarios")["scenarios"]}
    assert {"ALERT_POLICY_ENGINEERING_FIXTURE", "FL_SINGLE_RUN", "FULL_CAPSTONE_DEMO"} <= ids
    assert not set(load_scenarios()) & {"ALERT_POLICY_ENGINEERING_FIXTURE", "FL_SINGLE_RUN",
                                        "FULL_CAPSTONE_DEMO"}
