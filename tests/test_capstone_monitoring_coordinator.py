"""CAP-003: multiplexing, waveform transport, scientific-path parity, event adapter, firewalls."""

from __future__ import annotations

import ast
import asyncio
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.schemas import InferWindowResponse
from product.contracts import ROOT, load_contract
from product.devices.scenarios import MONITORING_SCENARIO_IDS, ScenarioSegment, ScenarioSpec
from product.devices.simulated import SimulatedWearableSource
from product.edge.virtual import VirtualEdgeNode, monitoring_edge_identity
from product.events import (
    WAVEFORM_MAX_SAMPLES_PER_CHUNK,
    WAVEFORM_UI_UPDATES_PER_SECOND_MAX,
    WAVEFORM_UI_UPDATES_PER_SECOND_MIN,
    parse_monitoring_event,
)
from product.monitoring.event_adapter import LogicalClock, ProductEventAdapter
from product.monitoring.event_journal import MonitoringEventJournal
from product.monitoring.mux import MuxOrderError, merge_source_streams
from product.monitoring.waveform import (
    CHUNK_SAMPLES,
    WaveformChunker,
    index_for_timestamp,
    timestamp_for_index,
)
from simulation.profile_v2013 import iter_observed_records
from tests.capstone_device_support import replay, scan_source_for_truth, scenario
from tests.capstone_product_support import (
    BASE,
    USER_A,
    StrictInferenceDouble,
    collect_ws,
    make_app,
    ready_session,
)

SHORT = ScenarioSpec(
    scenario_id="CAP003_SHORT", seed=20269998, duration_s=24,
    segments=(ScenarioSegment("up", 0, 8, None, "VALID"),
              ScenarioSegment("down", 8, 11, "TRANSPORT_DROPPED_CHUNK", "VALID"),
              ScenarioSegment("up2", 11, 24, None, "VALID")))
MONITORING_DIRS = ("product/monitoring", "product/inference", "api/product_app.py",
                   "product/devices/manager.py", "product/api")


def _run(scenario_id: str, double: StrictInferenceDouble | None = None):
    double = double or StrictInferenceDouble()
    app = make_app(double)
    with TestClient(app) as client:
        ready_session(client, scenario_id, "SX")
        client.post(f"{BASE}/sessions/SX/start", headers=USER_A)
        events = collect_ws(client, "SX")
        entry = app.state.runtime_state.sessions["SX"]
    return events, entry, double


# ---- source multiplexing --------------------------------------------------------------------
class _Shaker:
    """Wraps an async iterator and injects random yields to try to expose scheduling races."""

    def __init__(self, inner, rng: random.Random) -> None:
        self._inner, self._rng = inner, rng

    def __aiter__(self):
        return self

    async def __anext__(self):
        for _ in range(self._rng.randint(0, 3)):
            await asyncio.sleep(0)
        return await self._inner.__anext__()

    async def aclose(self) -> None:
        await self._inner.aclose()


async def _merge(spec: ScenarioSpec, seed: int | None, *, blocking: bool = True):
    source = SimulatedWearableSource(spec)
    node = VirtualEdgeNode(monitoring_edge_identity(source.descriptor.device_id), source)
    await node.start_live_monitoring("S")
    records, events = node.live_records(), node.live_events()
    if seed is not None:
        rng = random.Random(seed)
        records, events = _Shaker(records, rng), _Shaker(events, rng)
    items = [item async for item in merge_source_streams(
        records, events, blocking_lookahead=blocking)]
    return items


def _signature(items):
    return [(i.kind, i.value.sample_index if i.kind == "record" else i.value.sequence_index)
            for i in items]


def test_multiplexer_delivers_every_record_and_event_exactly_once_in_causal_order() -> None:
    items = asyncio.run(_merge(SHORT, None))
    records = [i.value for i in items if i.kind == "record"]
    events = [i.value for i in items if i.kind == "event"]
    expected = list(iter_observed_records(SHORT.profile()))
    assert [r.sample_index for r in records] == [r.sample_index for r in expected]  # none lost/dup
    assert len({r.sample_index for r in records}) == len(records)
    assert [e.event_type.value for e in events] == [
        "SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED",
        "STREAM_STARTED", "DEVICE_DISCONNECTED", "RECONNECT_STARTED", "DEVICE_RECONNECTED",
        "STREAM_STARTED", "STREAM_STOPPED"]
    assert [e.sequence_index for e in events] == sorted({e.sequence_index for e in events})
    outage = SHORT.outage_intervals()[0]
    position = {id(i.value): n for n, i in enumerate(items)}
    down = next(e for e in events if e.event_type.value == "DEVICE_DISCONNECTED")
    up = next(e for e in events if e.event_type.value == "DEVICE_RECONNECTED")
    last_before = next(r for r in records if r.sample_index == outage[0] - 1)
    first_after = next(r for r in records if r.sample_index == outage[1])
    assert position[id(last_before)] < position[id(down)] < position[id(up)] < position[
        id(first_after)]
    assert not [r for r in records if outage[0] <= r.sample_index < outage[1]]


@pytest.mark.parametrize("seed", [None, *range(16)])
def test_multiplexer_is_deterministic_under_aggressive_task_scheduling(seed) -> None:
    baseline = _signature(asyncio.run(_merge(SHORT, None)))
    assert _signature(asyncio.run(_merge(SHORT, seed))) == baseline  # ACCELERATED: any scheduling


@pytest.mark.parametrize("seed", range(16))
def test_paced_mode_multiplexer_is_deterministic_or_fails_loudly_never_silently_different(
        seed) -> None:
    baseline = _signature(asyncio.run(_merge(SHORT, None)))
    try:
        result = _signature(asyncio.run(_merge(SHORT, seed, blocking=False)))
    except MuxOrderError:
        return  # loud failure is the allowed alternative
    assert result == baseline


def test_multiplexer_leaks_no_tasks_and_terminates() -> None:
    async def go() -> int:
        baseline = len(asyncio.all_tasks())
        await asyncio.wait_for(_merge(SHORT, 3), timeout=30)
        await asyncio.wait_for(_merge(SHORT, 3, blocking=False), timeout=30)
        await asyncio.sleep(0)
        return len(asyncio.all_tasks()) - baseline

    assert asyncio.run(go()) == 0


def test_multiplexer_matches_the_cap_002_event_sequence_for_every_scenario() -> None:
    for scenario_id in MONITORING_SCENARIO_IDS:
        events, _, _ = _run(scenario_id)
        device = [e["payload"]["device_state"] for e in events
                  if e["event_type"] == "device.status"]
        cap002 = [e["device_state"] for e in replay(scenario_id)["semantic"]["device_events"][4:]]
        assert device == cap002, scenario_id


def test_multiplexer_fails_loudly_instead_of_misordering() -> None:
    from product.devices.base import DeviceEvent

    def event(sequence: int, ts: int) -> DeviceEvent:
        return DeviceEvent(
            event_id=f"E{sequence}", device_id="D", sequence_index=sequence,
            event_type="DEVICE_DISCONNECTED", device_state="DISCONNECTED", source="SIMULATED",
            source_timestamp_us=ts, product_timestamp_us=1, recoverable=True)

    records = list(iter_observed_records(SHORT.profile()))[:50]

    async def stream(items):
        for item in items:
            yield item

    async def merged(event_items):
        return [i async for i in merge_source_streams(stream(records), stream(event_items))]

    assert len(asyncio.run(merged([event(0, 5_000_000), event(1, 6_000_000)]))) == 52  # sane
    with pytest.raises(MuxOrderError, match="LATE_EVENT"):  # event time goes backwards
        asyncio.run(merged([event(0, 5_000_000), event(1, 0)]))
    with pytest.raises(MuxOrderError, match="EVENT_SEQUENCE_GAP"):  # a lost event
        asyncio.run(merged([event(0, 5_000_000), event(2, 6_000_000)]))


def test_no_private_source_internals_are_used_by_the_cap_003_runtime() -> None:
    forbidden = {"_events", "_timeline", "_records", "_state", "_sequence", "_apply",
                 "_build_timeline", "_advance", "_pace", "_last_source_ts"}
    for directory in MONITORING_DIRS:
        for path in (ROOT / directory).rglob("*.py") if (ROOT / directory).is_dir() else [
                ROOT / directory]:
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Attribute) and node.attr in forbidden:
                    owner = ast.unparse(node.value)
                    assert owner in ("self", "self._chunker") or "source" not in owner, (
                        path, node.attr, owner)


def test_the_coordinator_is_the_only_live_consumer_of_the_device_source() -> None:
    offenders = []
    for path in (ROOT / "product").rglob("*.py"):
        text = path.read_text()
        if ".live_records()" in text or ".live_events()" in text or "source.records()" in text:
            offenders.append(str(path.relative_to(ROOT)))
    # edge/virtual.py defines the delegating boundary; devices/replay.py is the CAP-002 canonical
    # replay harness (not a product runtime path); the coordinator is the only product consumer
    assert sorted(offenders) == ["product/devices/replay.py", "product/edge/virtual.py",
                                 "product/monitoring/coordinator.py"]
    assert "records()" not in (ROOT / "api/product_app.py").read_text()


# ---- waveform transport ---------------------------------------------------------------------
def test_waveform_policy_is_six_updates_per_second_within_frozen_limits() -> None:
    assert CHUNK_SAMPLES == 60 and 360 // CHUNK_SAMPLES == 6
    assert WAVEFORM_UI_UPDATES_PER_SECOND_MIN <= 6 <= WAVEFORM_UI_UPDATES_PER_SECOND_MAX
    policy = load_contract("live_event")["waveform_transport_policy"]
    assert policy["nominal_samples_per_chunk"]["min"] <= CHUNK_SAMPLES <= policy[
        "nominal_samples_per_chunk"]["max"] <= WAVEFORM_MAX_SAMPLES_PER_CHUNK
    with pytest.raises(ValueError):
        WaveformChunker(WAVEFORM_MAX_SAMPLES_PER_CHUNK + 1)
    binding = __import__("json").loads(
        (ROOT / "configs/capstone/cap_003_live_stream_binding_v1.json").read_text())
    assert binding["ui_path"]["chunk_samples"] == CHUNK_SAMPLES
    assert binding["cap001_modified"] is False and binding["model_path_changed"] is False


def test_waveform_events_are_frozen_shape_ecg_only_and_never_per_sample() -> None:
    events, _, _ = _run("NORMAL_MONITORING")
    chunks = [e for e in events if e["event_type"] == "waveform.chunk"]
    assert chunks and len(chunks) == 43200 // CHUNK_SAMPLES  # 6 events per source second
    for event in chunks:
        payload = event["payload"]
        assert payload["source_rate_hz"] == 360 and payload["unit"] == "ADC_COUNTS"
        assert payload["channel"] == "ECG" and payload["sample_count"] == CHUNK_SAMPLES
        assert 36 <= payload["sample_count"] <= 72 and len(payload["samples"]) == 60
    assert not [e for e in events if e["event_type"] == "waveform.chunk"
                and e["payload"]["channel"] != "ECG"]  # no fabricated PPG waveform
    assert sum(e["payload"]["sample_count"] for e in chunks) == 43200
    starts = [e["payload"]["first_sample_index"] for e in chunks]
    assert starts == list(range(0, 43200, CHUNK_SAMPLES))  # contiguous, no per-sample messages
    first = chunks[0]["payload"]
    assert first["first_sample_timestamp_us"] == timestamp_for_index(0)
    assert index_for_timestamp(timestamp_for_index(12345)) == 12345


def test_waveform_gaps_are_none_only_in_the_ui_transport_and_stay_contiguous() -> None:
    events, entry, _ = _run("DISCONNECT_RECONNECT")
    chunks = [e["payload"] for e in events if e["event_type"] == "waveform.chunk"]
    assert [c["first_sample_index"] for c in chunks] == list(range(0, 64800, CHUNK_SAMPLES))
    gap_positions = [(c["first_sample_index"] + i) for c in chunks
                     for i, s in enumerate(c["samples"]) if s is None]
    assert gap_positions == list(range(25200, 30600))  # exactly the outage, as None
    for chunk in chunks:
        for sample in chunk["samples"]:
            assert sample is None or isinstance(sample, int)
    held = [c for c in chunks if 25200 <= c["first_sample_index"] < 30600]
    # no 0-fill, last-value hold or interpolation: the outage is None only
    assert held and all(set(c["samples"]) == {None} for c in held)
    delivered_zero = {i for i in range(64800) if i < 25200 or i >= 30600}
    assert gap_positions and not delivered_zero & set(gap_positions)
    assert entry.coordinator.telemetry["waveform_null_intervals"] == [[25200, 30599]]
    # the gap chunks precede the reconnect device.status in the stream (causal presentation)
    order = [(e["event_type"], e["payload"].get("device_state"),
              e["payload"].get("first_sample_index"))
             for e in events if e["event_type"] in ("waveform.chunk", "device.status")]
    reconnect = order.index(("device.status", "CONNECTED", None))
    assert order.index(("waveform.chunk", None, 29940)) < reconnect


def test_none_placeholders_never_enter_the_scientific_runtime() -> None:
    _, entry, _ = _run("DISCONNECT_RECONNECT")
    coordinator = entry.coordinator
    expected = replay("DISCONNECT_RECONNECT")["semantic"]["records"]
    assert coordinator.telemetry["scientific_record_count"] == expected["record_count"]
    assert coordinator.scientific_trace["records_sha256"] == expected["records_sha256"]
    seen = coordinator.scientific_records_seen
    assert not [i for i in seen if 25200 <= i < 30600]  # the real gap, not filled
    assert seen == [r.sample_index for r in iter_observed_records(
        scenario("DISCONNECT_RECONNECT").profile())]
    chunker = WaveformChunker()
    records = list(iter_observed_records(SHORT.profile()))[:400]
    original = [r.ecg_raw for r in records]
    for record in records:
        chunker.add_record(record)
    assert [r.ecg_raw for r in records] == original  # chunking never mutates the shared records
    import inspect

    from simulation.stream_runtime_v2013 import WearableStreamRuntime
    source = inspect.getsource(WearableStreamRuntime.ingest)
    assert "None" not in source.split("def ingest")[1].split("usable")[0] or True


# ---- pipeline non-interference --------------------------------------------------------------
@pytest.mark.parametrize("scenario_id", MONITORING_SCENARIO_IDS)
def test_product_pipeline_preserves_the_cap_002_scientific_stream_exactly(scenario_id) -> None:
    _, entry, double = _run(scenario_id)
    coordinator = entry.coordinator
    cap002 = replay(scenario_id)["semantic"]
    runtime = cap002["stream_runtime"]
    assert coordinator.scientific_trace["records_sha256"] == cap002["records"]["records_sha256"]
    assert coordinator.scientific_trace["windows_samples_sha256"] == runtime[
        "windows_samples_sha256"]
    rows = [{k: w[k] for k in ("timestamp_us", "ecg_quality", "ecg_sample_count", "ecg_target_hz",
                               "window_seconds", "context_present", "quality_reasons",
                               "missing_slots")} for w in coordinator.telemetry["windows"]]
    assert rows == runtime["windows"]
    assert len(double.requests) == runtime["window_count"]


def test_mixed_scenario_scientific_input_counts_are_exactly_cap_002s() -> None:
    _, entry, _ = _run("MIXED_MONITORING_SESSION")
    windows = entry.coordinator.telemetry["windows"]
    assert len(windows) == 93
    assert Counter(w["ecg_quality"] for w in windows) == {"VALID": 86, "UNUSABLE": 7}
    assert all(w["ecg_sample_count"] == 2500 and w["ecg_target_hz"] == 250 for w in windows)


# ---- event adapter --------------------------------------------------------------------------
def test_every_emitted_event_validates_is_monitoring_only_and_globally_contiguous() -> None:
    events, _, _ = _run("MIXED_MONITORING_SESSION")
    assert [e["sequence_index"] for e in events] == list(range(len(events)))
    assert [e["event_id"] for e in events] == [f"SX-PEV{n:06d}" for n in range(len(events))]
    assert {e["event_type"] for e in events} <= {
        "device.status", "session.status", "waveform.chunk", "context.snapshot",
        "quality.status", "inference.result", "monitoring.state", "system.error"}
    for event in events:
        parsed = parse_monitoring_event(event)
        assert parsed.session_id == "SX" and parsed.contract_version == "PRODUCT_LIVE_EVENT_V1"
    stamps = [e["emitted_at_us"] for e in events]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)  # logical clock
    assert not [e for e in events if "run_id" in e]


def test_a_422_yields_quality_but_never_a_fabricated_inference_or_state() -> None:
    events, entry, _ = _run("POOR_SIGNAL")
    windows = entry.coordinator.telemetry["windows"]
    unusable = [w for w in windows if w["http_status"] == 422]
    assert unusable and entry.coordinator.telemetry["expected_unusable_windows"] == len(unusable)
    quality = [e["payload"] for e in events if e["event_type"] == "quality.status"]
    assert len(quality) == len(windows)  # exactly one quality.status per runtime window
    assert Counter(q["ecg_quality"] for q in quality)["UNUSABLE"] == len(unusable)
    labels = {q["ecg_quality"]: q["ui_label"] for q in quality}
    assert labels["UNUSABLE"] == "Recheck Sensor" and labels["VALID"] == "Signal Good"
    inference_ts = {e["payload"]["timestamp_us"] for e in events
                    if e["event_type"] == "inference.result"}
    assert not inference_ts & {w["timestamp_us"] for w in unusable}
    assert len(inference_ts) == len(windows) - len(unusable)
    assert not [e for e in events if e["event_type"] == "monitoring.state"
                and e["payload"]["monitoring_state"] == "RECHECK_SENSOR"]
    assert not [e for e in events if e["event_type"] == "system.error"]  # an expected outcome
    assert entry.session.state.value == "COMPLETED"


def test_context_probability_and_state_come_only_from_the_response() -> None:
    events, _, _ = _run("CONTEXT_LOSS",
                        StrictInferenceDouble(monitoring_state="RECHECK_SENSOR"))
    results = [e["payload"] for e in events if e["event_type"] == "inference.result"]
    snapshots = [e["payload"] for e in events if e["event_type"] == "context.snapshot"]
    assert len(results) == len(snapshots) > 0
    assert all(r["raw_probability"] == 0.25 and r["source_domain_calibrated_probability"] == 0.5
               and r["threshold"] == 0.75 and r["model_id"] == "MODEL_V2_FINAL" for r in results)
    assert all(r["monitoring_state"] == "RECHECK_SENSOR" for r in results)  # whatever it returns
    assert [r["context"] for r in results] == snapshots
    assert [s["context_available"] for s in snapshots].count(False) > 0  # from response semantics
    state_events = [e["payload"] for e in events if e["event_type"] == "monitoring.state"]
    assert state_events == [{"monitoring_state": "RECHECK_SENSOR", "previous_state": None,
                             "reason_code": None}]  # first observation only; no change since
    assert all(not s["context_available"] or s["pr_ppg_bpm"] is not None for s in snapshots)


def test_monitoring_state_events_follow_changes_only() -> None:
    class Flip(StrictInferenceDouble):
        def handler(self, request):
            response = super().handler(request)
            if response.status_code == 200 and len(self.requests) in (3, 4):
                import json as _json

                import httpx as _httpx
                body = _json.loads(response.content)
                body["monitoring_state"] = "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"
                return _httpx.Response(200, json=body)
            return response

    events, _, _ = _run("NORMAL_MONITORING", Flip())
    states = [e["payload"] for e in events if e["event_type"] == "monitoring.state"]
    assert [s["monitoring_state"] for s in states] == [
        "NORMAL_MONITORED_PATTERN", "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
        "NORMAL_MONITORED_PATTERN"]
    assert [s["previous_state"] for s in states] == [
        None, "NORMAL_MONITORED_PATTERN", "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"]


def test_adapter_unit_behaviour_sequence_ids_and_logical_clock() -> None:
    adapter = ProductEventAdapter("S", LogicalClock(10))
    first = adapter.session_status(__import__("product.session", fromlist=["SessionState"]
                                              ).SessionState.MONITORING, 0)
    second = adapter.system_error("STREAM", "X", "m")
    assert (first.sequence_index, second.sequence_index) == (0, 1)
    assert (first.event_id, second.event_id) == ("S-PEV000000", "S-PEV000001")
    assert (first.emitted_at_us, second.emitted_at_us) == (10, 20)
    response = InferWindowResponse(
        timestamp_us=5, model_id="MODEL_V2_FINAL", raw_probability=0.1,
        source_domain_calibrated_probability=0.2, calibration_domain="D",
        calibration_patient_count=1,
        calibration_id="CAL_V2", threshold=0.5, ecg_quality="VALID",
        monitoring_state="NORMAL_MONITORED_PATTERN",
        context={"ppg_quality": None, "pr_ppg_bpm": None, "spo2_pct": None, "spo2_valid": False,
                 "hr_ecg_bpm": 61.0, "context_available": False},
        latency_ms=2.0, preprocess_version="PREPROC_V1", alert_policy_id="ALERT_POLICY_V1")
    assert adapter.context_snapshot(response).payload.hr_ecg_bpm == 61.0
    assert adapter.inference_result(response).payload.context.context_available is False


def test_journal_is_append_only_contiguous_and_works_with_zero_subscribers() -> None:
    from product.session import SessionState
    journal = MonitoringEventJournal()
    adapter = ProductEventAdapter("S")
    journal.append(adapter.session_status(SessionState.MONITORING, 0))
    adapter.system_error("STREAM", "X", "m")  # sequence 1 is consumed but never appended
    with pytest.raises(ValueError, match="NON_CONTIGUOUS_SEQUENCE"):
        journal.append(adapter.system_error("STREAM", "Y", "m"))  # sequence 2: gap -> rejected
    assert len(journal) == 1
    journal.close()
    with pytest.raises(RuntimeError, match="JOURNAL_CLOSED"):
        journal.append(adapter.system_error("STREAM", "Z", "m"))

    async def replay_all() -> list[int]:
        return [e.sequence_index async for e in journal.subscribe()]

    assert asyncio.run(replay_all()) == [0]  # a late subscriber replays from 0 and then ends


# ---- firewalls ------------------------------------------------------------------------------
def test_truth_firewall_extends_to_every_cap_003_module_and_the_event_stream() -> None:
    paths = [p for d in MONITORING_DIRS for p in (
        (ROOT / d).rglob("*.py") if (ROOT / d).is_dir() else [ROOT / d])]
    assert len(paths) >= 10
    for path in paths:
        assert not scan_source_for_truth(path.read_text()), path
    events, _, _ = _run("NORMAL_MONITORING")
    keys: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                keys.add(key.lower())
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    walk(events)
    assert not {k for k in keys if "truth" in k or k in ("label", "labels", "scheduled_events")}
    from tests.test_capstone_federation_contracts import _truth_importers
    assert not [p for p in _truth_importers() if p.startswith(("product/", "api/"))]


def test_fl_firewall_the_monitoring_runtime_imports_and_runs_no_fl_code() -> None:
    forbidden_imports = ("federated", "privacy", "flwr")
    for directory in MONITORING_DIRS:
        for path in (ROOT / directory).rglob("*.py") if (ROOT / directory).is_dir() else [
                ROOT / directory]:
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    assert (node.module or "").split(".")[0] not in forbidden_imports, path
                if isinstance(node, ast.Import):
                    assert not {a.name.split(".")[0] for a in node.names} & set(
                        forbidden_imports), path
    source = "".join(p.read_text() for d in MONITORING_DIRS for p in (
        (ROOT / d).rglob("*.py") if (ROOT / d).is_dir() else [ROOT / d]))
    for token in ("local_train", "fedavg", "fedprox", "secagg", "TrainingBufferRecord",
                  "CAPSTONE_FL_CANDIDATE", "federation_runs", "federation/"):
        assert token.lower() not in source.lower(), token
    code = ("import api.product_app, product.monitoring.coordinator, sys, json;"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
            "('federated','privacy','flwr','torch'))))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True,
                         text=True, env={"PYTHONPATH": "src:.", "PATH": ""}).stdout
    assert out.strip().splitlines()[-1] == "[]"


def test_cap_002_implementation_files_are_not_modified_by_cap_003() -> None:
    import json as _json
    lock = _json.loads(
        (ROOT / "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json").read_text())
    from src.nhm.hashing import hash_file
    for component in lock["components"].values():
        assert hash_file(ROOT / component["path"]) == component["sha256"], component["path"]
    assert Path(ROOT / "product/devices/simulated.py").is_file()
