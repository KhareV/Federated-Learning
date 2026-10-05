"""CAP-002: VIRTUAL_EDGE_NODE_V1, live/training separation, truth firewall and hardware swap."""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from product.contracts import ROOT, load_contract
from product.devices.base import AdapterType, DeviceSource, DeviceState
from product.devices.simulated import SimulatedWearableSource
from product.edge import base as edge_base
from product.edge.base import EdgeNode, EdgeNodeIdentity, EdgeNodeKind
from product.edge.buffer import LocalTrainingBuffer, TrainingBufferRecord
from product.edge.virtual import (
    DisabledTrainingBuffer,
    TrainingBufferDisabledError,
    VirtualEdgeNode,
    edge_identity_for_site,
    monitoring_edge_identity,
)
from simulation.types import ObservedRecord
from tests.capstone_device_support import drain, scan_source_for_truth
from tests.test_capstone_contracts import _descriptor
from tests.test_capstone_simulated_device import SHORT

CAP002_FILES = ("product/devices/simulated.py", "product/devices/scenarios.py",
                "product/devices/replay.py", "product/edge/virtual.py")


def _node() -> VirtualEdgeNode:
    source = SimulatedWearableSource(SHORT)
    return VirtualEdgeNode(monitoring_edge_identity(source.descriptor.device_id), source)


def test_virtual_edge_node_implements_the_frozen_edge_contract() -> None:
    node = _node()
    assert isinstance(node, EdgeNode)
    contract = load_contract("edge_node")
    for name, spec in contract["methods"].items():
        member = getattr(VirtualEdgeNode, name)
        assert inspect.iscoroutinefunction(member) is spec["async"]
        assert [p for p in inspect.signature(member).parameters if p != "self"] == spec["args"]
    for prop in contract["properties"]:
        assert isinstance(getattr(VirtualEdgeNode, prop), property)
    assert list(EdgeNodeIdentity.model_fields) == contract["identity_fields"]
    assert node.identity.kind is EdgeNodeKind.VIRTUAL_EDGE_NODE and node.identity.simulation
    assert node.identity.edge_node_id == "VIRTUAL_EDGE_NODE_00"
    assert node.identity.device_id == node.device_source.descriptor.device_id
    assert isinstance(node.device_source, DeviceSource)


def test_edge_identities_reuse_the_frozen_eight_client_cohort_mapping() -> None:
    from simulation.fl_cohort_v1 import client_profile
    mapping = load_contract("edge_node")["simulated_cohort_mapping"]["mapping"]
    assert len(mapping) == 8
    for index in range(8):
        identity = edge_identity_for_site(index, device_id=f"DEV{index}")
        profile = client_profile(index)
        assert identity.fl_client_id == profile.client_id == f"SIM_FL_SITE_{index:02d}"
        assert identity.participant_id == profile.participant_id == f"SIM_P{101 + index:06d}"
        assert identity.edge_node_id == f"VIRTUAL_EDGE_NODE_{index:02d}"
        assert identity.simulation is True
    with pytest.raises(ValueError, match="OUT_OF_RANGE"):
        edge_identity_for_site(8)
    assert monitoring_edge_identity("D").fl_client_id is None  # no second client universe


def test_virtual_edge_node_rejects_real_identities_and_non_sources() -> None:
    real = EdgeNodeIdentity(edge_node_id="GW", kind=EdgeNodeKind.REAL_EDGE_GATEWAY,
                            simulation=False)
    with pytest.raises(ValueError, match="SIMULATED_IDENTITY"):
        VirtualEdgeNode(real, SimulatedWearableSource(SHORT))
    with pytest.raises(TypeError, match="PROTOCOL"):
        VirtualEdgeNode(monitoring_edge_identity("D"), object())  # type: ignore[arg-type]


def test_live_flow_runs_the_attachment_then_streams_observed_records() -> None:
    node = _node()

    async def go() -> list:
        await node.start_live_monitoring("EDGE_S1")
        return [r async for r in node.live_records()]

    records = asyncio.run(go())
    assert records and all(type(r) is ObservedRecord for r in records)
    events = drain(node.live_events())
    assert [e.event_type.value for e in events][:5] == [
        "SCAN_STARTED", "DEVICE_DISCOVERED", "PAIRING_STARTED", "DEVICE_CONNECTED",
        "STREAM_STARTED"]
    assert node.device_source.connection_state is DeviceState.STOPPED
    assert all(e.session_id == "EDGE_S1" for e in events[4:])


def test_edge_stop_and_reattach_follow_the_device_lifecycle() -> None:
    node = _node()

    async def go() -> None:
        await node.start_live_monitoring("A")
        await node.stop_live_monitoring()
        assert node.device_source.connection_state is DeviceState.STOPPED
        await node.start_live_monitoring("B")  # STOPPED -> CONNECTED -> STREAMING
        assert node.device_source.connection_state is DeviceState.STREAMING

    asyncio.run(go())


def test_training_boundary_is_a_disabled_placeholder_that_persists_nothing() -> None:
    node = _node()
    buffer = node.training_buffer
    assert isinstance(buffer, LocalTrainingBuffer) and isinstance(buffer, DisabledTrainingBuffer)
    assert buffer.batch_ids() == () and buffer.eligible_count() == 0
    record = TrainingBufferRecord(
        client_id="SIM_FL_SITE_00", participant_id="SIM_P000101", source="WEARABLE_SIM_V1",
        window_id="w", model_input_ref="r", label=0, label_source="SIMULATION_TRUTH_ENGINEERING",
        quality_eligible=True, timestamp_us=1, simulation=True, provenance_id="P",
        buffer_batch_id="b")
    with pytest.raises(TrainingBufferDisabledError, match="CAP_006"):
        buffer.append_batch([record])
    assert buffer.batch_ids() == () and buffer.eligible_count() == 0

    async def stream() -> None:
        await node.start_live_monitoring("S")
        async for _ in node.live_records():
            pass

    asyncio.run(stream())  # live monitoring never feeds the buffer
    assert buffer.batch_ids() == () and buffer.eligible_count() == 0


def test_edge_node_has_no_fl_or_training_surface() -> None:
    node = _node()
    names = {n for n in dir(node) if not n.startswith("_")}
    assert not {"local_train", "produce_update", "train", "fit", "submit_update"} & names
    live = {"attach", "start_live_monitoring", "stop_live_monitoring", "live_records",
            "live_events", "identity", "device_source", "training_buffer"}
    assert names == live
    assert not any(hasattr(edge_base, n) for n in ("Coordinator", "FLClient", "local_train"))


def _fresh_modules_after(code: str) -> set[str]:
    out = subprocess.run([sys.executable, "-c", code + "\nimport sys,json;print(json.dumps("
                          "sorted(sys.modules)))"], cwd=ROOT, check=True, capture_output=True,
                         text=True, env={"PYTHONPATH": "src:.", "PATH": ""}).stdout
    return set(json.loads(out.strip().splitlines()[-1]))


def test_live_edge_path_does_not_import_fl_server_truth_or_inference_modules() -> None:
    modules = _fresh_modules_after(
        "import product.edge.virtual, product.devices.simulated, product.devices.replay\n"
        "from product.devices.replay import run_replay\n"
        "from product.devices.scenarios import ScenarioSpec, ScenarioSegment\n"
        "run_replay(ScenarioSpec('T',1,16,(ScenarioSegment('a',0,16,None,'VALID'),)))")
    top = {m.split(".")[0] for m in modules}
    assert not top & {"federated", "privacy", "flwr", "torch", "api", "fastapi", "deployment",
                      "fusion"}, sorted(top & {"federated", "privacy", "flwr", "torch", "api"})
    assert not modules & {"simulation.truth_v2013", "simulation.fl_cohort_truth_v1",
                          "simulation.fl_cohort_v1"}


def test_simulation_truth_is_never_imported_by_the_cap_002_modules() -> None:
    for path in CAP002_FILES:
        assert not scan_source_for_truth((ROOT / path).read_text()), path
    for path in ("product/devices/base.py", "product/edge/base.py", "product/edge/buffer.py"):
        assert not scan_source_for_truth((ROOT / path).read_text()), path


def test_truth_scanner_negative_controls_detect_planted_leakage() -> None:
    planted = "from simulation.fl_cohort_truth_v1 import scheduled_event_times_us"
    assert scan_source_for_truth(planted)
    assert scan_source_for_truth("from simulation.types import SimulationTruth")
    assert scan_source_for_truth("from simulation.wearable import get_truth")
    assert scan_source_for_truth("import simulation.truth_v2013")
    assert scan_source_for_truth("from simulation import fl_cohort_truth_v1")
    assert not scan_source_for_truth("from simulation.types import ObservedRecord")


def test_cap_001_truth_boundary_still_holds_with_the_new_modules() -> None:
    from tests.test_capstone_federation_contracts import _truth_importers
    boundary = load_contract("training_buffer")["simulation_truth_boundary"]
    importers = set(_truth_importers())
    assert not [p for p in importers if p.startswith("product/")]
    sanctioned = {p for g in boundary["sanctioned_importers"].values() for p in g}
    assert importers <= sanctioned


def test_live_records_expose_no_truth_label_or_model_fields() -> None:
    node = _node()

    async def go() -> list:
        await node.start_live_monitoring("S")
        return [r async for r in node.live_records()]

    records = asyncio.run(go())
    fields = set(records[0].to_canonical_dict())
    assert fields == set(json.loads((ROOT / "contracts/sample_schema_v1.json").read_text())[
        "required"])
    assert not [r for r in records if hasattr(r, "truth") or hasattr(r, "label")]


# ---- hardware replacement compatibility -------------------------------------------------------
class _FutureRealDouble:
    """Interface-shape double only. It does not talk to hardware and implements no transport."""

    @property
    def descriptor(self):
        return _descriptor(AdapterType.FUTURE_REAL)

    @property
    def connection_state(self) -> DeviceState:
        return DeviceState.DETACHED

    async def scan(self, timeout_s: float):
        return [self.descriptor]

    async def connect(self, device_id: str) -> None: ...
    async def disconnect(self) -> None: ...
    async def start_stream(self, session_id: str) -> None: ...
    async def stop_stream(self) -> None: ...

    async def records(self):
        if False:
            yield  # pragma: no cover

    async def events(self):
        if False:
            yield  # pragma: no cover


def test_simulated_source_and_future_real_double_share_one_interface_boundary() -> None:
    simulated, future = SimulatedWearableSource(SHORT), _FutureRealDouble()
    assert isinstance(simulated, DeviceSource) and isinstance(future, DeviceSource)
    protocol_members = {n for n in dir(DeviceSource) if not n.startswith("_")}
    assert protocol_members <= set(dir(simulated)) and protocol_members <= set(dir(future))
    for name in ("scan", "connect", "disconnect", "start_stream", "stop_stream"):
        assert inspect.signature(getattr(SimulatedWearableSource, name)).parameters.keys() == (
            inspect.signature(getattr(_FutureRealDouble, name)).parameters.keys())
    # the same edge host accepts either source: only the adapter differs
    assert VirtualEdgeNode(monitoring_edge_identity("D"), simulated).device_source is simulated
    assert VirtualEdgeNode(monitoring_edge_identity("D"), future).device_source is future
    assert future.descriptor.hardware_specific_fields_status == "VERIFICATION_REQUIRED"
    assert simulated.descriptor.hardware_specific_fields_status == "NOT_APPLICABLE"
    assert future.descriptor.capabilities.nominal_source_rates_hz is None  # not invented


def test_no_real_hardware_adapter_or_wearable_v1_artifact_exists() -> None:
    source = "".join(p.read_text() for p in Path(ROOT / "product").rglob("*.py"))
    for forbidden in ("class FutureRealWearableSource", "class RealWearableSource",
                      "import serial", "import bleak", "import bluetooth", "WEARABLE_V1_MANIFEST"):
        assert forbidden not in source, forbidden
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True,
                             text=True).stdout.split()
    assert not [p for p in tracked if "wearable_v1" in p.lower() and "wearable_sim" not in p.lower()
                and p.startswith(("reports/capstone", "manifests/capstone", "product"))]
    hardware = load_contract("hardware_replacement")
    assert all(v == "VERIFICATION_REQUIRED"
               for v in hardware["verification_required_fields"].values())
