"""CAP-001 contract tests. Every test exercises the actual contract definitions (contracts/capstone
JSON + product/ interface code); none duplicates a hard-coded fixture of the thing it checks."""

from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from api.schemas import MonitoringState, QualityState
from product import events as ev
from product.auth import base as auth
from product.contracts import ROOT, IllegalTransitionError, load_contract, load_protocol
from product.devices import base as dev
from product.session import (
    MonitoringSession,
    RuntimeIdentity,
    SessionState,
    SimulationProvenance,
    advance_session,
    default_runtime_identity,
    session_transitions,
    validate_session_transition,
)
from scripts.cap_001_generate_contracts import render
from simulation import profile_v2013
from simulation.profiles import SMOKE_PARTICIPANT_INDEX, SMOKE_PARTICIPANT_SEED, SMOKE_SCENARIO
from simulation.types import ObservedRecord
from simulation.wearable import generate_participant, generate_session, iter_observed_records

CONTRACT_NAMES = (
    "device_source", "session", "live_event", "product_api", "auth_policy", "storage_policy",
    "demo_scenarios", "connection_table", "edge_node", "training_buffer", "fl_client",
    "federation", "fl_run", "model_registry", "model_governance", "hardware_replacement",
)


def test_all_contract_artifacts_exist_and_declare_frozen_status() -> None:
    for name in CONTRACT_NAMES:
        contract = load_contract(name)
        assert contract["contract_id"]
    assert len({load_contract(n)["contract_id"] for n in CONTRACT_NAMES}) == len(CONTRACT_NAMES)
    assert load_protocol()["status"] == "FROZEN_PRE_IMPLEMENTATION_PROTOCOL"
    assert load_protocol()["science_statement"].startswith("CAP-001 DOES NOT change")


# ---- device lifecycle -----------------------------------------------------------------------
def test_device_state_vocabulary_matches_contract_exactly() -> None:
    contract = load_contract("device_source")
    assert [s.value for s in dev.DeviceState] == contract["device_states"]
    table = dev.device_transitions()
    assert set(table) == set(contract["device_states"])
    for targets in table.values():
        assert set(targets) <= set(table)


@pytest.mark.parametrize(
    ("current", "new"),
    [("DETACHED", "SCANNING"), ("SCANNING", "FOUND"), ("SCANNING", "ERROR"), ("FOUND", "PAIRING"),
     ("PAIRING", "CONNECTED"), ("PAIRING", "ERROR"), ("CONNECTED", "STREAMING"),
     ("STREAMING", "DISCONNECTED"), ("STREAMING", "STOPPED"), ("DISCONNECTED", "RECONNECTING"),
     ("RECONNECTING", "CONNECTED"), ("RECONNECTING", "ERROR"), ("STOPPED", "DETACHED"),
     ("STOPPED", "CONNECTED")],
)
def test_prompt_mandated_device_transitions_are_legal(current: str, new: str) -> None:
    dev.validate_device_transition(dev.DeviceState(current), dev.DeviceState(new))


@pytest.mark.parametrize(
    ("current", "new"),
    [("DETACHED", "STREAMING"), ("DETACHED", "CONNECTED"), ("FOUND", "STREAMING"),
     ("STOPPED", "STREAMING"), ("ERROR", "CONNECTED"), ("CONNECTED", "SCANNING"),
     ("STREAMING", "CONNECTED"), ("DISCONNECTED", "STREAMING")],
)
def test_illegal_device_transitions_are_rejected(current: str, new: str) -> None:
    with pytest.raises(IllegalTransitionError, match="ILLEGAL_DEVICE_TRANSITION"):
        dev.validate_device_transition(dev.DeviceState(current), dev.DeviceState(new))


# ---- session lifecycle ----------------------------------------------------------------------
def _session(**override: object) -> MonitoringSession:
    base = {
        "session_id": "S1", "user_id": "demo:u1", "device_id": "D1",
        "device_adapter_type": dev.AdapterType.SIMULATED, "created_at_us": 1,
        "state": SessionState.CREATED, "runtime": default_runtime_identity(),
        "simulation_provenance": SimulationProvenance(
            scenario_id="NORMAL_MONITORING", seed=20261001, simulation_version="WEARABLE_SIM_V1"),
    }
    base.update(override)
    return MonitoringSession(**base)


def test_session_state_vocabulary_and_transitions_match_contract() -> None:
    contract = load_contract("session")
    assert [s.value for s in SessionState] == contract["session_states"]
    table = session_transitions()
    for terminal in contract["terminal_states"]:
        assert table[terminal] == ()
    assert "PAUSED" not in table


def test_session_lifecycle_walk_and_illegal_rejection() -> None:
    session = _session()
    for step, state in enumerate(
        (SessionState.DEVICE_READY, SessionState.MONITORING, SessionState.STOPPING,
         SessionState.COMPLETED), start=2):
        session = advance_session(session, state, step * 10)
    assert session.started_at_us == 30 and session.ended_at_us == 50
    with pytest.raises(IllegalTransitionError):
        validate_session_transition(SessionState.CREATED, SessionState.MONITORING)
    with pytest.raises(IllegalTransitionError):
        advance_session(session, SessionState.MONITORING, 99)


def test_session_runtime_identity_is_immutable_and_pinned_to_the_default_binding() -> None:
    lock = json.loads((ROOT / "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json").read_text())
    identity = lock["identity"]
    runtime = default_runtime_identity().model_dump()
    for key in ("model_id", "alert_policy_id", "alert_policy_binding_id", "gateway_artifact_id",
                "api_contract_version"):
        assert runtime[key] == identity[key]
    assert runtime["calibration_id"] == identity["calibration_id"]
    assert runtime["preprocess_id"] == identity["preprocess_id"]
    assert runtime["software_system_id"] == "SOFTWARE_SYSTEM_V2"
    with pytest.raises(ValidationError):
        RuntimeIdentity(**{**runtime, "model_id": "MODEL_V1"})
    session = _session()
    with pytest.raises(ValidationError):
        session.runtime = default_runtime_identity()  # frozen
    advanced = advance_session(session, SessionState.DEVICE_READY, 5)
    assert advanced.runtime == session.runtime
    changed = {k for k, v in advanced.model_dump().items() if v != session.model_dump()[k]}
    assert changed == {"state"}


def test_simulated_session_requires_provenance_and_real_must_not_carry_it() -> None:
    with pytest.raises(ValidationError, match="SIMULATION_PROVENANCE"):
        _session(simulation_provenance=None)
    with pytest.raises(ValidationError, match="MUST_NOT_CARRY"):
        _session(device_adapter_type=dev.AdapterType.FUTURE_REAL)
    assert _session(device_adapter_type=dev.AdapterType.FUTURE_REAL, simulation_provenance=None)


# ---- DeviceSource protocol / ObservedRecord reuse -------------------------------------------
def _descriptor(adapter: dev.AdapterType) -> dev.DeviceDescriptor:
    sim = adapter is dev.AdapterType.SIMULATED
    return dev.DeviceDescriptor(
        device_id="D1", display_name="NHM device", adapter_type=adapter,
        source_dataset_id="WEARABLE_SIM_V1" if sim else None,
        source_mode="SYNTHETIC_PHYSIOLOGY" if sim else None,
        connection_state=dev.DeviceState.DETACHED,
        capabilities=dev.DeviceCapabilities(
            supports_ecg=True, supports_ppg=True, supports_spo2_context=True,
            supports_device_events=True,
            nominal_source_rates_hz={"ecg": profile_v2013.SOURCE_RATE_HZ} if sim else None),
        simulation=sim, simulation_version="WEARABLE_SIM_V1" if sim else None,
        hardware_specific_fields_status="NOT_APPLICABLE" if sim else "VERIFICATION_REQUIRED")


class _FakeSource:
    """Minimal structural implementation, parameterised by adapter type."""

    def __init__(self, adapter: dev.AdapterType) -> None:
        self._descriptor = _descriptor(adapter)

    @property
    def descriptor(self) -> dev.DeviceDescriptor:
        return self._descriptor

    @property
    def connection_state(self) -> dev.DeviceState:
        return dev.DeviceState.DETACHED

    async def scan(self, timeout_s: float) -> Sequence[dev.DeviceDescriptor]:
        return [self._descriptor]

    async def connect(self, device_id: str) -> None: ...
    async def disconnect(self) -> None: ...
    async def start_stream(self, session_id: str) -> None: ...
    async def stop_stream(self) -> None: ...

    async def records(self) -> AsyncIterator[ObservedRecord]:
        participant = generate_participant(SMOKE_PARTICIPANT_INDEX, SMOKE_PARTICIPANT_SEED)
        session = generate_session(
            participant, SMOKE_SCENARIO, session_id="S", session_seed=1,
            profile="WEARABLE_SIM_SMOKE")
        for record in iter_observed_records(session):
            yield record

    async def events(self) -> AsyncIterator[dev.DeviceEvent]:
        return
        yield  # pragma: no cover


class _MissingStop(_FakeSource):
    stop_stream = None  # type: ignore[assignment]


def test_device_source_protocol_shape_matches_contract() -> None:
    contract = load_contract("device_source")
    proto = dev.DeviceSource
    for name, spec in contract["methods"].items():
        member = getattr(proto, name)
        assert (inspect.iscoroutinefunction(member)) == spec["async"], name
        params = [p for p in inspect.signature(member).parameters if p != "self"]
        assert params == spec["args"], name
    for prop in contract["properties"]:
        assert isinstance(getattr(proto, prop), property)
    hints = inspect.get_annotations(proto.records, eval_str=True)
    assert hints["return"] == AsyncIterator[ObservedRecord]
    assert inspect.get_annotations(proto.events, eval_str=True)["return"] == (
        AsyncIterator[dev.DeviceEvent])


@pytest.mark.parametrize("adapter", list(dev.AdapterType))
def test_simulated_and_future_real_sources_satisfy_the_same_interface(
        adapter: dev.AdapterType) -> None:
    source = _FakeSource(adapter)
    assert isinstance(source, dev.DeviceSource)
    assert source.descriptor.adapter_type is adapter

    async def first() -> ObservedRecord:
        async for record in source.records():
            return record
        raise AssertionError("no records")

    record = asyncio.run(first())
    assert isinstance(record, ObservedRecord)


def test_source_missing_a_contract_method_is_not_a_device_source() -> None:
    assert not isinstance(_MissingStop(dev.AdapterType.SIMULATED), dev.DeviceSource)


def test_observed_record_reference_is_the_existing_canonical_type() -> None:
    binding = load_contract("device_source")["observed_record_binding"]
    assert binding["new_record_type_allowed"] is False
    assert (binding["module"], binding["class"]) == (ObservedRecord.__module__, "ObservedRecord")
    schema = json.loads((ROOT / binding["schema"]).read_text())
    participant = generate_participant(SMOKE_PARTICIPANT_INDEX, SMOKE_PARTICIPANT_SEED)
    session = generate_session(participant, SMOKE_SCENARIO, session_id="S", session_seed=1,
                               profile="WEARABLE_SIM_SMOKE")
    records = list(iter_observed_records(session))
    assert records
    for record in records:
        jsonschema.validate(record.to_canonical_dict(), schema)
    from simulation.stream_runtime_v2013 import WearableStreamRuntime
    hints = inspect.get_annotations(WearableStreamRuntime.ingest, eval_str=True)
    assert hints["records"] == Sequence[ObservedRecord]
    assert "ObservedRecordV2" not in "".join(
        p.read_text() for p in (ROOT / "product").rglob("*.py"))


def test_descriptor_rules_and_no_clinical_or_hardware_availability_claims() -> None:
    assert _descriptor(dev.AdapterType.SIMULATED).simulation is True
    real = _descriptor(dev.AdapterType.FUTURE_REAL)
    assert real.hardware_specific_fields_status == "VERIFICATION_REQUIRED"
    assert real.simulation is False and real.capabilities.nominal_source_rates_hz is None
    with pytest.raises(ValidationError):
        real.model_copy(update={"simulation": True}).model_validate(
            real.model_copy(update={"simulation": True}).model_dump())
    with pytest.raises(ValidationError):
        dev.DeviceDescriptor(**{**real.model_dump(), "hardware_specific_fields_status":
                                "NOT_APPLICABLE"})
    banned = ("certif", "clinical", "fda", "ce_mark", "diagnos")
    names = list(dev.DeviceDescriptor.model_fields) + list(dev.DeviceCapabilities.model_fields)
    assert not [n for n in names if any(b in n for b in banned)]
    contract = load_contract("device_source")
    assert list(dev.DeviceDescriptor.model_fields) == contract["descriptor_fields"]
    assert list(dev.DeviceCapabilities.model_fields) == contract["capability_fields"]
    assert list(dev.DeviceEvent.model_fields) == contract["device_event_fields"]
    assert all(v == "VERIFICATION_REQUIRED"
               for v in contract["hardware_specific_fields"]["fields"].values())


def _event(event_type: str, state: str, **kw: object) -> dev.DeviceEvent:
    return dev.DeviceEvent(
        event_id="E1", device_id="D1", sequence_index=0, event_type=event_type, device_state=state,
        source="SIMULATED", product_timestamp_us=1, recoverable=True, **kw)


def test_device_events_follow_the_contract_state_effects_and_carry_no_model_output() -> None:
    contract = load_contract("device_source")
    assert [e.value for e in dev.DeviceEventType] == contract["event_types"]
    for etype, state in contract["event_type_state_effects"].items():
        assert _event(etype, state).device_state.value == state
        assert dev.event_state_effect(dev.DeviceEventType(etype)).value == state
    with pytest.raises(ValidationError, match="EVENT_STATE_MISMATCH"):
        _event("DEVICE_CONNECTED", "STREAMING")
    with pytest.raises(ValidationError):
        _event("DEVICE_CONNECTED", "CONNECTED", metadata={"monitoring_state": "NORMAL"})
    forbidden = ("probability", "monitoring_state", "model", "threshold", "ecg_quality")
    names = list(dev.DeviceEvent.model_fields) + list(dev.DeviceEventMetadata.model_fields)
    assert not [n for n in names if any(b in n for b in forbidden)]


# ---- live events ----------------------------------------------------------------------------
FED_ENV = {"contract_version": "PRODUCT_LIVE_EVENT_V1", "event_id": "E1", "run_id": "R1",
           "sequence_index": 0, "emitted_at_us": 10}
ENVELOPE = {"contract_version": "PRODUCT_LIVE_EVENT_V1", "event_id": "E1", "session_id": "S1",
            "sequence_index": 0, "emitted_at_us": 10}
CONTEXT = {"hr_ecg_bpm": 72.0, "pr_ppg_bpm": 71.0, "spo2_pct": 97.0, "spo2_valid": True,
           "context_available": True, "ppg_quality": "VALID"}
CAND = "CAPSTONE_FL_CANDIDATE_0001"
SAMPLES = {
    "session.status": {"session_state": "MONITORING", "elapsed_ms": 5},
    "device.status": {"device_id": "D1", "device_state": "STREAMING", "adapter_type": "SIMULATED",
                      "recoverable": True},
    "waveform.chunk": {"channel": "ECG", "first_sample_index": 0, "first_sample_timestamp_us": 0,
                       "sample_count": 3, "samples": [1, 2, None]},
    "context.snapshot": CONTEXT,
    "quality.status": {"ecg_quality": "DEGRADED", "ui_label": "Signal Degraded"},
    "inference.result": {
        "timestamp_us": 1, "model_id": "MODEL_V2_FINAL", "calibration_id": "CAL_V2",
        "calibration_domain": "d", "preprocess_version": "PREPROC_V1",
        "alert_policy_id": "ALERT_POLICY_V1", "ecg_quality": "VALID",
        "monitoring_state": "NORMAL_MONITORED_PATTERN", "context": CONTEXT, "latency_ms": 3.2,
        "raw_probability": 0.1, "source_domain_calibrated_probability": 0.2, "threshold": 0.5},
    "monitoring.state": {"monitoring_state": "RECHECK_SENSOR"},
    "system.error": {"error_code": "X", "message": "m", "recoverable": False, "origin": "STREAM"},
    "federation.status": {"run_type": "LIVE_RUN", "run_status": "RUNNING", "algorithm": "FEDAVG",
                          "current_round": 1, "planned_rounds": 3, "client_count": 8},
    "round.status": {"round_id": 1, "round_state": "COLLECTING", "accepted_updates": 0,
                     "expected_updates": 8},
    "client.status": {"client_id": "SIM_FL_SITE_00", "client_state": "TRAINING",
                      "local_example_count": 10},
    "client.training_progress": {"client_id": "SIM_FL_SITE_00", "round_id": 1,
                                 "progress_fraction": 0.5, "examples_seen": 5},
    "client.update_ready": {"client_id": "SIM_FL_SITE_00", "round_id": 1, "update_digest": "abc",
                            "examples_seen": 10},
    "aggregation.status": {"round_id": 1, "algorithm": "FEDAVG", "aggregation_mode": "PLAIN",
                           "accepted_updates": 8},
    "secagg.status": {"round_id": 1, "mode": "SECAGG_SHADOW", "status": "SHADOW_VERIFIED"},
    "candidate.created": {"candidate_id": CAND, "parent_model_id": "FL_INIT_V2", "round_id": 3,
                          "state_digest": "d"},
    "candidate.validation": {"candidate_id": CAND, "validation_status": "PASSED",
                             "checks": ["STATE_FINITE"]},
    "candidate.governance": {"candidate_id": CAND, "governance_status": "ACCEPTED_TO_SANDBOX",
                             "sandbox_status": "IN_SANDBOX"},
    "federation.completed": {"rounds_completed": 3, "candidate_ids": [CAND]},
    "federation.error": {"error_code": "X", "message": "m", "recoverable": True},
}


def _make(kind: str, payload: dict | None = None, **env: object) -> dict:
    base = FED_ENV if kind in ev.FEDERATION_EVENT_KINDS else ENVELOPE
    return {**base, **env, "event_type": kind, "payload": payload or SAMPLES[kind]}


def test_live_event_kinds_match_contract_and_every_kind_validates() -> None:
    contract = load_contract("live_event")
    assert list(ev.EVENT_KINDS) == contract["event_kinds"]
    assert list(ev.MONITORING_EVENT_KINDS) == contract["monitoring_event_kinds"]
    assert list(ev.FEDERATION_EVENT_KINDS) == contract["federation_event_kinds"]
    assert set(SAMPLES) == set(ev.EVENT_KINDS) and len(ev.EVENT_KINDS) == 20
    for kind in ev.EVENT_KINDS:
        parsed = ev.parse_live_event(_make(kind))
        assert parsed.event_type == kind
        assert parsed.contract_version == "PRODUCT_LIVE_EVENT_V1"
        assert parsed.event_id and parsed.sequence_index == 0 and parsed.emitted_at_us == 10


def test_monitoring_and_federation_streams_do_not_accept_each_others_events() -> None:
    for kind in ev.MONITORING_EVENT_KINDS:
        ev.parse_monitoring_event(_make(kind))
        with pytest.raises(ValidationError):
            ev.parse_federation_event(_make(kind))
    for kind in ev.FEDERATION_EVENT_KINDS:
        ev.parse_federation_event(_make(kind))
        with pytest.raises(ValidationError):
            ev.parse_monitoring_event(_make(kind))
    contract = load_contract("live_event")
    assert contract["identity_fields"] == {"monitoring": "session_id (required)",
                                           "federation": "run_id (required)"}


def test_live_event_schema_is_generated_from_the_authoritative_python_union() -> None:
    committed = (ROOT / "contracts/capstone/live_event_v1.schema.json").read_text()
    assert committed == render()
    schema = json.loads(committed)
    jsonschema.Draft202012Validator.check_schema(schema)
    for kind in ev.EVENT_KINDS:
        jsonschema.validate(_make(kind), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_make("quality.status", {"ecg_quality": "NOPE", "ui_label": "x"}),
                            schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_make("candidate.created", {**SAMPLES["candidate.created"],
                                                        "production_deployed": True}), schema)


@pytest.mark.parametrize(
    "bad",
    [
        {**ENVELOPE, "event_type": "free.form", "payload": {"anything": 1}},
        {**ENVELOPE, "event_type": "heartbeat", "payload": {"server_time_us": 1}},
        _make("monitoring.state", {"monitoring_state": "RECHECK_SENSOR", "extra": 1}),
        {**_make("monitoring.state"), "surprise": 1},
        {**_make("monitoring.state"), "contract_version": "PRODUCT_LIVE_EVENT_V2"},
        {k: v for k, v in _make("monitoring.state").items() if k != "session_id"},
        {k: v for k, v in _make("round.status").items() if k != "run_id"},
        {k: v for k, v in _make("monitoring.state").items() if k != "event_id"},
        _make("monitoring.state", sequence_index=-1),
        _make("candidate.created", {**SAMPLES["candidate.created"], "production_deployed": True}),
        _make("candidate.created", {**SAMPLES["candidate.created"],
                                    "candidate_id": "MODEL_V2_FINAL"}),
        _make("candidate.governance", {**SAMPLES["candidate.governance"],
                                       "governance_status": "PRODUCTION_DEPLOYED"}),
        _make("candidate.governance", {**SAMPLES["candidate.governance"],
                                       "production_deployed": True}),
        _make("federation.completed", {**SAMPLES["federation.completed"],
                                       "production_deployed": True}),
        _make("secagg.status", {"round_id": 1, "mode": "PLAIN", "status": "SHADOW_VERIFIED"}),
        _make("secagg.status", {**SAMPLES["secagg.status"], "claim_scope": "DIFFERENTIAL_PRIVACY"}),
        _make("client.training_progress", {**SAMPLES["client.training_progress"],
                                           "progress_fraction": 1.5}),
        _make("federation.status", {**SAMPLES["federation.status"], "engineering_only": False}),
        _make("client.status", {**SAMPLES["client.status"], "raw_ecg": [1, 2, 3]}),
        _make("monitoring.state", {"monitoring_state": "ARRHYTHMIA_DETECTED"}),
        _make("monitoring.state", {"monitoring_state": "AFIB"}),
        _make("quality.status", {"ecg_quality": "VALID", "ui_label": "Recheck Sensor"}),
        _make("waveform.chunk", {**SAMPLES["waveform.chunk"], "sample_count": 4}),
        _make("waveform.chunk", {**SAMPLES["waveform.chunk"], "sample_count": 145,
                                 "samples": [0] * 145}),
        _make("waveform.chunk", {**SAMPLES["waveform.chunk"], "source_rate_hz": 250}),
        _make("context.snapshot", {**CONTEXT, "context_available": False}),
        _make("inference.result", {**SAMPLES["inference.result"], "raw_probability": 1.5}),
    ],
)
def test_invalid_live_events_are_rejected(bad: dict) -> None:
    with pytest.raises(ValidationError):
        ev.parse_live_event(bad)


def test_live_event_vocabularies_reuse_the_frozen_api_enums() -> None:
    contract = load_contract("live_event")
    assert [s.value for s in MonitoringState] == contract["monitoring_state_vocabulary"]
    assert set(contract["monitoring_state_ui_labels"]) == set(
        contract["monitoring_state_vocabulary"])
    assert not set(contract["forbidden_states"]) & {s.value for s in MonitoringState}
    mapping = {q.value: label for q, label in ev.QUALITY_UI_LABELS.items()}
    assert mapping == {k: v for k, v in contract["quality_mapping"].items()
                       if k in {q.value for q in QualityState}}
    unavailable = ev.ContextSnapshotPayload(spo2_valid=False, context_available=False)
    assert unavailable.pr_ppg_bpm is None and unavailable.spo2_pct is None


def test_waveform_transport_policy_is_ui_only_and_not_per_sample() -> None:
    policy = load_contract("live_event")["waveform_transport_policy"]
    assert policy["per_sample_websocket_messages_allowed"] is False
    assert policy["scientific_source_rate_hz"] == ev.WAVEFORM_SOURCE_RATE_HZ == (
        profile_v2013.SOURCE_RATE_HZ)
    assert (policy["ui_updates_per_second"]["min"], policy["ui_updates_per_second"]["max"]) == (
        ev.WAVEFORM_UI_UPDATES_PER_SECOND_MIN, ev.WAVEFORM_UI_UPDATES_PER_SECOND_MAX)
    assert policy["hard_max_samples_per_chunk"] == ev.WAVEFORM_MAX_SAMPLES_PER_CHUNK
    nominal = policy["nominal_samples_per_chunk"]
    assert nominal["min"] == ev.WAVEFORM_SOURCE_RATE_HZ // ev.WAVEFORM_UI_UPDATES_PER_SECOND_MAX
    assert nominal["max"] == ev.WAVEFORM_SOURCE_RATE_HZ // ev.WAVEFORM_UI_UPDATES_PER_SECOND_MIN
    assert nominal["max"] <= ev.WAVEFORM_MAX_SAMPLES_PER_CHUNK


def test_inference_event_mirrors_the_frozen_response_without_new_scientific_fields() -> None:
    from api.schemas import InferWindowResponse
    response_fields = set(InferWindowResponse.model_fields)
    payload_fields = set(ev.InferenceResultPayload.model_fields) - {"probability_role"}
    assert payload_fields <= response_fields
    assert list(ev.InferenceResultPayload.model_fields) == (
        load_contract("live_event")["inference_event_fields"])
    assert ev.InferenceResultPayload.model_fields["probability_role"].default == (
        "RESEARCH_TECHNICAL_METADATA")


# ---- product API ----------------------------------------------------------------------------
def test_product_api_routes_are_unique_additive_and_separate_from_the_frozen_api() -> None:
    api = load_contract("product_api")
    keys = [(r["method"], r["path"]) for r in api["routes"]]
    assert len(keys) == len(set(keys))
    assert len({r["route_id"] for r in api["routes"]}) == len(api["routes"])
    assert all(r["path"].startswith("/product/v1/") for r in api["routes"])
    assert not any(r["path"].startswith("/v1/") for r in api["routes"])
    required = {
        ("GET", "/product/v1/system"), ("GET", "/product/v1/me"), ("GET", "/product/v1/devices"),
        ("POST", "/product/v1/devices/simulated"), ("POST", "/product/v1/devices/{id}/scan"),
        ("POST", "/product/v1/devices/{id}/connect"),
        ("POST", "/product/v1/devices/{id}/disconnect"), ("POST", "/product/v1/sessions"),
        ("GET", "/product/v1/sessions"), ("GET", "/product/v1/sessions/{id}"),
        ("POST", "/product/v1/sessions/{id}/start"), ("POST", "/product/v1/sessions/{id}/stop"),
        ("GET", "/product/v1/sessions/{id}/summary"),
        ("GET", "/product/v1/sessions/{id}/timeline"),
        ("WS", "/product/v1/sessions/{id}/live"),
        ("GET", "/product/v1/federation"), ("GET", "/product/v1/federation/clients"),
        ("POST", "/product/v1/federation/runs"), ("GET", "/product/v1/federation/runs"),
        ("GET", "/product/v1/federation/runs/{id}"),
        ("POST", "/product/v1/federation/runs/{id}/start"),
        ("GET", "/product/v1/federation/runs/{id}/rounds"),
        ("WS", "/product/v1/federation/runs/{id}/live"),
        ("GET", "/product/v1/models"), ("GET", "/product/v1/models/{id}"),
        ("GET", "/product/v1/research/ml"), ("GET", "/product/v1/research/fl"),
    }
    assert set(keys) == required
    frozen = json.loads((ROOT / "contracts/openapi_v1.json").read_text())
    assert not [p for p in frozen["paths"] if "product" in p]
    assert set(frozen["paths"]) == {"/v1/infer-window"}
    assert api["frozen_inference_api"]["api_schema_v2_created"] is False
    assert not (ROOT / "contracts/API_SCHEMA_V2.json").exists()
    assert api["inference_boundary"]["direct_model_import_allowed"] is False
    assert api["inference_boundary"]["second_inference_implementation_allowed"] is False
    fragments = api["forbidden_route_fragments"]
    assert not [r for r in api["routes"] if any(f in r["path"] for f in fragments)]
    assert api["frontend_routes"]["successor_identity"] == "CAPSTONE_UI_V1"
    assert {"/app/federation", "/app/federation/live", "/app/models"} <= set(
        api["frontend_routes"]["routes"])


def test_no_public_model_selector_in_any_product_contract_surface() -> None:
    api = load_contract("product_api")
    forbidden = set(api["forbidden_request_field_names"])
    for route in api["routes"]:
        assert not forbidden & set(route["request_fields"]), route["route_id"]
        assert not forbidden & set(route["path"].strip("/").split("/"))
    # identity, descriptors and the session's top-level fields carry no selector; the session's
    # nested `runtime` block is the pinned, read-only default identity (validated elsewhere)
    for model in (auth.AuthIdentity, MonitoringSession, dev.DeviceDescriptor, dev.DeviceEvent):
        assert not forbidden & set(model.model_fields), model.__name__
    assert not forbidden & set(auth.AuthIdentity.model_fields)
    assert load_contract("auth_policy")["ml_independence"]["identity_affects_ml"] is False
    assert load_contract("session")["immutability"]["per_user_runtime_selection_allowed"] is False


# ---- auth -----------------------------------------------------------------------------------
class _FakeProvider:
    def __init__(self, kind: auth.AuthProviderType) -> None:
        self._kind = kind

    @property
    def provider_type(self) -> auth.AuthProviderType:
        return self._kind

    def describe(self) -> auth.AuthProviderDescription:
        demo = self._kind is auth.AuthProviderType.DEMO
        return auth.AuthProviderDescription(
            provider=self._kind, demo_mode=demo,
            ui_banner="OFFLINE DEMO IDENTITY - not Clerk authentication" if demo else None)

    async def authenticate(self, credential: str | None) -> auth.AuthIdentity:
        demo = self._kind is auth.AuthProviderType.DEMO
        return auth.AuthIdentity(
            user_id=("demo:" if demo else "user_") + "1", auth_provider=self._kind,
            auth_session_id="s", demo_mode=demo)


def test_auth_provider_contract_for_clerk_and_demo() -> None:
    policy = load_contract("auth_policy")
    assert set(policy["providers"]) == {p.value for p in auth.AuthProviderType}
    assert [f for f in policy["identity_fields"]] == list(auth.AuthIdentity.model_fields)
    for kind in auth.AuthProviderType:
        provider = _FakeProvider(kind)
        assert isinstance(provider, auth.AuthProvider)
        identity = asyncio.run(provider.authenticate(None))
        assert identity.demo_mode == (kind is auth.AuthProviderType.DEMO)
    assert _FakeProvider(auth.AuthProviderType.DEMO).describe().ui_banner
    assert _FakeProvider(auth.AuthProviderType.CLERK).describe().ui_banner is None


def test_demo_identity_is_visibly_distinct_and_cannot_masquerade_as_clerk() -> None:
    with pytest.raises(ValidationError, match="DEMO_MODE_FLAG"):
        auth.AuthIdentity(user_id="demo:x", auth_provider="DEMO", auth_session_id="s",
                          demo_mode=False)
    with pytest.raises(ValidationError, match="DEMO_USER_ID"):
        auth.AuthIdentity(user_id="user_x", auth_provider="DEMO", auth_session_id="s",
                          demo_mode=True)
    with pytest.raises(ValidationError, match="NON_DEMO_USER_ID"):
        auth.AuthIdentity(user_id="demo:x", auth_provider="CLERK", auth_session_id="s",
                          demo_mode=False)


def test_demo_auth_requires_explicit_configuration_and_never_silently_activates() -> None:
    ack = load_contract("auth_policy")["demo_provider"]["acknowledgement_value"]
    with pytest.raises(auth.AuthConfigError, match="NOT_CONFIGURED"):
        auth.resolve_auth_mode({})
    with pytest.raises(auth.AuthConfigError, match="INVALID"):
        auth.resolve_auth_mode({auth.ENV_AUTH_MODE: "ANONYMOUS"})
    with pytest.raises(auth.AuthConfigError, match="ACKNOWLEDGEMENT"):
        auth.resolve_auth_mode({auth.ENV_AUTH_MODE: "DEMO"})
    with pytest.raises(auth.AuthConfigError, match="ACKNOWLEDGEMENT"):
        auth.resolve_auth_mode({auth.ENV_AUTH_MODE: "DEMO", auth.ENV_DEMO_ACK: "true"})
    assert auth.resolve_auth_mode({auth.ENV_AUTH_MODE: "DEMO", auth.ENV_DEMO_ACK: ack}) is (
        auth.AuthProviderType.DEMO)
    assert auth.resolve_auth_mode({auth.ENV_AUTH_MODE: "CLERK"}) is auth.AuthProviderType.CLERK
    policy = load_contract("auth_policy")["demo_provider"]
    assert policy["silent_activation_allowed"] is False
    assert policy["described_as_clerk_allowed"] is False


def test_authorization_is_owner_only() -> None:
    me = asyncio.run(_FakeProvider(auth.AuthProviderType.CLERK).authenticate(None))
    assert auth.can_access_owned(me, me.user_id)
    assert not auth.can_access_owned(me, "user_other")
    api = load_contract("product_api")
    owned = {"devices", "sessions"}
    for route in api["routes"]:
        parts = route["path"].split("/")
        if len(parts) > 3 and parts[3] in owned:
            assert route["auth"] == "AUTHENTICATED" and route["ownership_scope"] == "OWN", (
                route["route_id"])


# ---- storage --------------------------------------------------------------------------------
_SQL_TYPES = {"TEXT": "TEXT", "INTEGER": "INTEGER", "REAL": "REAL", "BLOB": "BLOB"}


def _ddl(policy: dict) -> list[str]:
    statements = []
    for entity in policy["entities"]:
        cols = []
        for name, spec in entity["columns"].items():
            nullable = spec.endswith("?")
            sql = _SQL_TYPES[spec.rstrip("?")]
            cols.append(f"{name} {sql}" + ("" if nullable or name == entity["primary_key"]
                                           else " NOT NULL"))
        cols.append(f"PRIMARY KEY ({entity['primary_key']})")
        for fk in entity["foreign_keys"]:
            table, column = fk["references"].split(".")
            cols.append(f"FOREIGN KEY ({fk['column']}) REFERENCES {table}({column})")
        statements.append(f"CREATE TABLE {entity['table']} ({', '.join(cols)})")
        for index in entity["indexes"]:
            unique = "UNIQUE " if index["unique"] else ""
            statements.append(
                f"CREATE {unique}INDEX {index['name']} ON {entity['table']} "
                f"({', '.join(index['columns'])})")
    return statements


def test_storage_policy_schema_is_executable_sqlite_with_enforced_foreign_keys() -> None:
    policy = load_contract("storage_policy")
    assert policy["engine"] == "SQLITE" and policy["database_server_required"] is False
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys=ON")
    for statement in _ddl(policy):
        connection.execute(statement)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {e["table"] for e in policy["entities"]}
    assert {e["entity"] for e in policy["entities"]} == {
        "users", "devices", "device_connections", "monitoring_sessions", "inference_events",
        "monitoring_state_events", "signal_quality_events", "context_snapshots",
        "session_summaries", "waveform_previews", "federation_runs", "federation_rounds",
        "fl_client_statuses", "candidate_models", "governance_decisions"}
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO devices VALUES ('d','nobody','n','SIMULATED',NULL,NULL,NULL,'{}',1)")


def test_storage_policy_forbids_per_sample_relational_rows() -> None:
    policy = load_contract("storage_policy")
    high = policy["high_rate_policy"]
    assert high["per_sample_rows_allowed"] is False
    assert high["raw_360hz_sample_table_allowed"] is False
    for entity in policy["entities"]:
        assert not [f for f in high["forbidden_entity_name_fragments"] if f in entity["entity"]]
        assert not set(high["forbidden_column_names"]) & set(entity["columns"])
    sample_schema = json.loads((ROOT / "contracts/sample_schema_v1.json").read_text())
    raw_fields = {k for k in sample_schema["required"] if k.endswith("_raw")}
    for entity in policy["entities"]:
        assert not raw_fields & set(entity["columns"])
    assert policy["raw_session_artifact_policy"]["mandatory"] is False
    preview = next(e for e in policy["entities"] if e["entity"] == "waveform_previews")
    assert "point_count" in preview["columns"] and high["max_preview_points_per_channel"] <= 4000


def test_storage_ownership_resolves_to_a_user_and_no_ml_selection_is_persisted() -> None:
    policy = load_contract("storage_policy")
    by_name = {e["entity"]: e for e in policy["entities"]}

    def reaches_users(name: str, seen: frozenset[str] = frozenset()) -> bool:
        if name == "users":
            return True
        if name in seen:
            return False
        return any(reaches_users(fk["references"].split(".")[0], seen | {name})
                   for fk in by_name[name]["foreign_keys"])

    assert all(reaches_users(n) for n in by_name)
    session_cols = set(by_name["monitoring_sessions"]["columns"])
    assert {"model_id", "calibration_id", "software_system_id"} <= session_cols
    assert "checkpoint_id" not in session_cols and "user_model_id" not in session_cols
    assert by_name["federation_runs"]["columns"]["engineering_only"] == "INTEGER"
    assert "production_deployed" in by_name["candidate_models"]["columns"]
    for name in ("federation_runs", "federation_rounds", "fl_client_statuses",
                 "candidate_models", "governance_decisions"):
        columns = set(by_name[name]["columns"])
        assert not columns & {"raw_ecg", "labels", "label", "truth", "simulation_truth",
                              "minibatch", "weights", "ecg_raw", "ppg_red_raw"}, name
    assert policy["live_fl_separation"]["fl_checkpoints_stored_as_live_model"] is False
    assert policy["live_fl_separation"]["per_user_model_state_stored"] is False


# ---- live/FL separation + connection table --------------------------------------------------
def test_live_inference_and_fl_research_are_separated_and_nothing_is_deployed() -> None:
    protocol = load_protocol()
    separation = protocol["live_vs_fl"]
    assert separation["fl_replaces_live_model"] is False
    assert separation["fl_checkpoint_deployed"] is False
    assert separation["synthetic_trained_state_deployed"] is False
    assert separation["device_wearer_becomes_fl_client"] is False
    assert protocol["no_per_user_training"]["identity_modifies"] == []
    assert protocol["no_per_user_training"]["self_learning"] is False
    system = json.loads((ROOT / "artifacts/SOFTWARE_SYSTEM_V2.lock.json").read_text())
    assert system["federated_checkpoint_deployed"] is False
    table = load_contract("connection_table")
    released = {"Inference Client", "POST /v1/infer-window", "WearableStreamRuntime",
                "SOFTWARE_SYSTEM_V2", "inference response"}
    fed = {"FL Client", "Federation Coordinator", "FedAvg/FedProx", "SecAgg Path",
           "CAPSTONE_FL_CANDIDATE", "Model Governance", "Candidate Registry"}
    for edge in table["edges"]:
        pair = {edge["from_component"], edge["to_component"]}
        assert not (pair & released and pair & fed), edge["edge_id"]
    demo = {s["scenario_id"]: s for s in load_contract("demo_scenarios")["scenarios"]}
    for sid, scenario in demo.items():
        if sid.startswith(("FL_", "FULL_")):
            assert scenario["deploys_model"] is False and scenario["production_deployed"] is False
            assert scenario["synthetic_fl_accuracy_reported"] is False


def test_connection_table_has_no_paper_only_edges_and_covers_all_three_graphs() -> None:
    table = load_contract("connection_table")
    known = {load_contract(n)["contract_id"] for n in CONTRACT_NAMES} | {
        "API_SCHEMA_V1", "SAMPLE_SCHEMA_V1"}
    planes = set(table["planes"])
    for edge in table["edges"]:
        assert set(edge) == set(table["columns"]), edge["edge_id"]
        for key in ("contract_id", "owner", "implementation_phase", "test_strategy", "interface",
                    "plane", "data_type"):
            assert edge[key], (edge["edge_id"], key)
        assert edge["contract_id"] in known, edge["edge_id"]
        assert edge["plane"] in planes
        assert edge["scientific_or_engineering"] in ("engineering", "scientific_released")
        assert isinstance(edge["existing_component"], bool) and isinstance(
            edge["new_component"], bool)
        assert edge["existing_component"] or edge["new_component"]
    pairs = {(e["from_component"], e["to_component"]) for e in table["edges"]}
    required = {
        ("User", "Product Frontend"), ("Product Frontend", "Product API"),
        ("Product API", "AuthProvider"), ("Product API", "Device Manager"),
        ("Device Manager", "SimulatedWearableSource"),
        ("SimulatedWearableSource", "VirtualEdgeNode"), ("VirtualEdgeNode", "ObservedRecord"),
        ("ObservedRecord", "WearableStreamRuntime"),
        ("WearableStreamRuntime", "Inference Client"),
        ("Inference Client", "POST /v1/infer-window"),
        ("POST /v1/infer-window", "SOFTWARE_SYSTEM_V2"),
        ("inference response", "Product Event Adapter"),
        ("Product Event Adapter", "WebSocket (monitoring)"),
        ("WebSocket (monitoring)", "Frontend monitoring UI"),
        ("VirtualEdgeNode", "LocalTrainingBuffer"), ("LocalTrainingBuffer", "FL Client"),
        ("FL Client", "Federation Coordinator"), ("Federation Coordinator", "FedAvg/FedProx"),
        ("Federation Coordinator", "SecAgg Path"), ("FedAvg/FedProx", "CAPSTONE_FL_CANDIDATE"),
        ("CAPSTONE_FL_CANDIDATE", "Model Governance"), ("Model Governance", "Candidate Registry"),
        ("scientific evidence", "Research ML view"),
        ("scientific evidence", "Research FL view"),
        ("SimulationTruth", "SIMULATION_LABEL_ADAPTER_V1"),
        ("SIMULATION_LABEL_ADAPTER_V1", "LocalTrainingBuffer"),
    }
    assert required <= pairs
    assert len({e["edge_id"] for e in table["edges"]}) == len(table["edges"])
    frozen_targets = {"POST /v1/infer-window", "ObservedRecord", "SOFTWARE_SYSTEM_V2"}
    assert all(e["upstream_frozen"] is True for e in table["edges"]
               if e["to_component"] in frozen_targets or e["from_component"] in frozen_targets)
    # every non-frozen planned component edge names a phase of the frozen roadmap
    phases = {p["task"] for p in load_protocol()["phase_sequence"]}
    for edge in table["edges"]:
        assert edge["implementation_phase"].split(" ")[0] in phases, edge["edge_id"]


# ---- demo scenarios -------------------------------------------------------------------------
def test_demo_scenarios_are_deterministic_engineering_only_and_honest() -> None:
    contract = load_contract("demo_scenarios")
    scenarios = {s["scenario_id"]: s for s in contract["scenarios"]}
    assert set(scenarios) == {
        "NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT",
        "MIXED_MONITORING_SESSION", "ALERT_POLICY_ENGINEERING_FIXTURE", "FL_SINGLE_RUN",
        "FL_NEW_LOCAL_BATCH", "FL_MULTIRUN_CANDIDATE_HISTORY", "FL_RESTART_RESUME",
        "FL_REJECT_INVALID_UPDATE", "FL_SECAGG_SHADOW", "FULL_CAPSTONE_DEMO"}
    assert all(isinstance(s["seed"], int) for s in scenarios.values())
    for scenario in scenarios.values():
        for field in contract["required_scenario_fields"]:
            assert field in scenario, (scenario["scenario_id"], field)
        assert scenario["engineering_only"] is True and scenario["scientific_evidence"] is False
        assert scenario["outcome_tuning_forbidden"] is True
        assert scenario["classification"].startswith("ENGINEERING")
    monitoring_seeds = [scenarios[k]["seed"] for k in (
        "NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT",
        "MIXED_MONITORING_SESSION", "ALERT_POLICY_ENGINEERING_FIXTURE")]
    assert len(set(monitoring_seeds)) == len(monitoring_seeds)
    assert contract["genuine_fl_requirement"]["static_charts_or_animation_only_allowed"] is False
    assert contract["genuine_fl_requirement"]["replay_mode_may_coexist"] is True


def test_simulation_truth_usage_is_declared_per_scenario_and_confined() -> None:
    for scenario in load_contract("demo_scenarios")["scenarios"]:
        sid = scenario["scenario_id"]
        if scenario["local_fl_training_runs"]:
            assert scenario["simulation_truth_used"] is True
            assert "SIMULATION_LABEL_ADAPTER_V1" in scenario["simulation_truth_allowed_where"]
            assert "never on the live monitoring" in scenario["simulation_truth_allowed_where"]
        else:
            assert scenario["simulation_truth_used"] is False, sid
        if scenario["live_inference_runs"] and sid != "FULL_CAPSTONE_DEMO":
            assert scenario["local_fl_training_runs"] is False, sid


def test_fl_scenarios_reuse_the_existing_eight_client_cohort() -> None:
    from simulation.fl_cohort_v1 import client_id
    cohort = [client_id(i) for i in range(8)]
    for sid in ("FL_SINGLE_RUN", "FL_NEW_LOCAL_BATCH", "FL_MULTIRUN_CANDIDATE_HISTORY",
                "FL_RESTART_RESUME", "FL_REJECT_INVALID_UPDATE", "FL_SECAGG_SHADOW"):
        scenario = next(s for s in load_contract("demo_scenarios")["scenarios"]
                        if s["scenario_id"] == sid)
        assert scenario["clients"] == cohort, sid
        assert scenario["new_four_client_experiment_allowed"] is False
    single = next(s for s in load_contract("demo_scenarios")["scenarios"]
                  if s["scenario_id"] == "FL_SINGLE_RUN")
    assert single["execution_modes"] == ["LIVE_RUN", "REPLAY"]


def test_scenario_timelines_reuse_the_existing_fault_and_context_vocabulary() -> None:
    for scenario in load_contract("demo_scenarios")["scenarios"]:
        previous_end = 0
        for segment in scenario["segments"]:
            assert segment["start_s"] >= previous_end and segment["end_s"] > segment["start_s"]
            assert segment["end_s"] <= scenario["duration_s"]
            previous_end = segment["end_s"]
            assert segment["context_mode"] in profile_v2013.CONTEXT_MODES
            assert segment["ecg_fault"] in (None, *profile_v2013.ECG_FAULTS)
        connection = set(scenario["expected_connection_events"])
        assert connection <= {e.value for e in dev.DeviceEventType}


def test_alert_fixture_is_separated_from_model_efficacy_evidence() -> None:
    scenarios = {s["scenario_id"]: s for s in load_contract("demo_scenarios")["scenarios"]}
    fixture = scenarios["ALERT_POLICY_ENGINEERING_FIXTURE"]
    assert fixture["model_v2_live_inference_invoked"] is False
    assert fixture["model_efficacy_claim_allowed"] is False
    assert fixture["mandatory_label"] == (
        "ENGINEERING STATE-MACHINE DEMONSTRATION - NOT MODEL PERFORMANCE EVIDENCE")
    assert set(fixture["must_demonstrate"]) >= {
        "consecutive-window confirmation", "alert opening", "alert closing", "DEGRADED handling",
        "UNUSABLE handling", "recovery"}
    for sid in ("NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT",
                "MIXED_MONITORING_SESSION"):
        scenario = scenarios[sid]
        assert scenario["model_v2_live_inference_invoked"] is True
        assert scenario["model_output_expectation"].startswith("NOT_ASSERTED")
    assert "forbidden" in load_contract("demo_scenarios")["full_pipeline_rule"]


# ---- protocol, offline mode, claims ---------------------------------------------------------
def test_protocol_freezes_offline_mode_claims_and_phase_sequence() -> None:
    protocol = load_protocol()
    offline = protocol["offline_faculty_mode"]
    assert offline["hard_requirement"] is True and offline["single_laptop"] is True
    assert {"physical hardware", "cloud ML inference", "remote database", "Clerk availability",
            "remote federation server", "internet access"} == set(offline["must_not_depend_on"])
    assert protocol["hardware"]["physical_hardware_available"] is False
    claims = protocol["claim_boundary"]
    assert "diagnosis" in claims["forbidden"] and "differential privacy" in claims["forbidden"]
    assert not set(claims["allowed"]) & set(claims["forbidden"])
    assert [p["task"] for p in protocol["phase_sequence"]] == (
        [f"CAP-00{n}" for n in range(1, 10)] + ["CAP-010", "CAP-011"])
    assert protocol["only_next_phase_allowed_after_capg0"] == "CAP-002"
    assert protocol["architecture"]["frontend_foundation"].startswith(
        "existing frontend/ SvelteKit app is the ONLY frontend foundation")
    assert "internet access" in protocol["offline_faculty_mode"]["must_not_depend_on"]
    assert "remote federation server" in protocol["offline_faculty_mode"]["must_not_depend_on"]
    assert [p["id"] for p in protocol["planes"]] == [
        "PRODUCT_USER_PLANE", "EDGE_CLIENT_PLANE", "FEDERATION_PLANE", "MODEL_GOVERNANCE_PLANE",
        "RELEASED_MONITORING_PLANE"]
    assert protocol["planes"][4]["frozen"] is True
    assert protocol["planes"][3]["federated_output_replaces_released_model"] is False
    assert "API_SCHEMA_V2" in " ".join(protocol["architecture"]["forbidden_paths"])


def test_protocol_protected_components_cover_every_prompt_listed_component() -> None:
    protected = set(load_protocol()["protected_components"])
    assert {"MODEL_V2_FINAL", "CAL_V2", "GATEWAY_ARTIFACT_V2", "API_SCHEMA_V1",
            "SOFTWARE_SYSTEM_V2", "SECAGG_CONFIG_V2", "SYSTEM_V2_RELEASE_MANIFEST_V1"} <= protected
    assert len(protected) == 39 and "GAP_POLICY_V1" in protected


def test_product_package_is_pure_interface_code() -> None:
    source = "".join(p.read_text() for p in Path(ROOT / "product").rglob("*.py"))
    for forbidden in ("import torch", "from fastapi", "import fastapi", "sqlite3", "import clerk",
                      "import flwr", "uvicorn"):
        assert forbidden not in source, forbidden
