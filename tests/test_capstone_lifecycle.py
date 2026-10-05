"""STRICT current-state test for the capstone control plane (manifests/capstone). Exact statuses;
this is the single capstone test updated at each phase transition. It also re-verifies the CAP-001
freeze lock byte-for-byte."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TASKS = {
    "CAP-001": "PASS",
    "CAP-002": "PASS",
    **{f"CAP-{n:03d}": "NOT_STARTED" for n in range(3, 12)},
}
EXPECTED_GATES = {"CAPG0": "PASS", "CAPG1": "PASS"}
EXPECTED_COMPONENTS = {
    "CAPSTONE_PRODUCT_PROTOCOL_V1": "FROZEN_PRE_IMPLEMENTATION_PROTOCOL",
    "DEVICE_SOURCE_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "EDGE_NODE_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "LOCAL_TRAINING_BUFFER_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "CAPSTONE_FL_CLIENT_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "CAPSTONE_FEDERATION_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "CAPSTONE_FL_RUN_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "CAPSTONE_MODEL_REGISTRY_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "CAPSTONE_MODEL_GOVERNANCE_V1": "FROZEN_PRODUCT_POLICY",
    "PRODUCT_API_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "PRODUCT_LIVE_EVENT_V1": "FROZEN_INTERFACE_CONTRACT",
    "CAPSTONE_SESSION_CONTRACT_V1": "FROZEN_INTERFACE_CONTRACT",
    "CAPSTONE_AUTH_POLICY_V1": "FROZEN_PRODUCT_POLICY",
    "CAPSTONE_STORAGE_POLICY_V1": "FROZEN_PRODUCT_POLICY",
    "CAPSTONE_DEMO_SCENARIOS_V1": "FROZEN_DEMO_CONTRACT",
    "REAL_HARDWARE_REPLACEMENT_BOUNDARY_V1": "FROZEN_PRE_IMPLEMENTATION_PROTOCOL",
}
LOCK = ROOT / "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json"


def _rows(name: str) -> list[dict]:
    with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_capstone_task_registry_is_exactly_the_current_state() -> None:
    assert {r["task_id"]: r["status"] for r in _rows("task")} == EXPECTED_TASKS


def test_capstone_gate_registry_is_exactly_the_current_state() -> None:
    assert {r["gate_id"]: r["status"] for r in _rows("gate")} == EXPECTED_GATES


def test_capstone_components_are_exactly_the_sixteen_cap_001_components() -> None:
    assert {r["component_id"]: r["status"] for r in _rows("component")} == EXPECTED_COMPONENTS


def test_task_prerequisite_chain_is_linear_and_later_phases_have_no_evidence() -> None:
    tasks = {r["task_id"]: r for r in _rows("task")}
    for n in range(3, 12):
        assert tasks[f"CAP-{n:03d}"]["prerequisites"] == f"CAP-{n - 1:03d}"
        assert tasks[f"CAP-{n:03d}"]["evidence_path"] == ""
        assert tasks[f"CAP-{n:03d}"]["implemented_at_commit"] == ""


def test_freeze_lock_binds_every_listed_file_byte_for_byte() -> None:
    lock = json.loads(LOCK.read_text())
    assert lock["status"] == "FROZEN_PRE_IMPLEMENTATION_PROTOCOL"
    assert lock["mutable_future_implementation_files_bound"] is False
    for cid, entry in lock["components"].items():
        assert entry["status"] == EXPECTED_COMPONENTS[cid]
        assert hash_file(ROOT / entry["path"]) == entry["sha256"], cid
    for path, digest in {**lock["bound_files"], **lock["upstream_frozen_identity"]}.items():
        assert hash_file(ROOT / path) == digest, path
    registry = lock["component_registry"]
    assert hash_file(ROOT / registry["path"]) == registry["sha256"]
    assert lock["upstream_system"]["federated_checkpoint_deployed"] is False


def test_v2_control_plane_is_untouched_by_the_capstone_lineage() -> None:
    entry = json.loads(
        (ROOT / "reports/capstone/cap_001/upstream_protection_entry.json").read_text())
    for path, digest in entry["tracked_files_sha256"].items():
        if path.startswith(("manifests/model_v2/", "artifacts/", "api/", "checkpoints/")):
            assert hash_file(ROOT / path) == digest, path


CAP002_LOCK = ROOT / "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json"
EXPECTED_CAP002_COMPONENTS = {
    "CAPSTONE_DEVICE_EDGE_PROTOCOL_V1": "FROZEN_ENGINEERING_PROTOCOL",
    "SIMULATED_WEARABLE_SOURCE_V1": "FROZEN_ENGINEERING_IMPLEMENTATION",
    "VIRTUAL_EDGE_NODE_V1": "FROZEN_ENGINEERING_IMPLEMENTATION",
    "CAPSTONE_DEVICE_SCENARIO_RUNTIME_V1": "FROZEN_ENGINEERING_IMPLEMENTATION",
    "CAPSTONE_DEVICE_REPLAY_V1": "FROZEN_ENGINEERING_REPLAY",
}


def test_cap_002_components_are_exactly_the_five_registered_components() -> None:
    with (ROOT / "manifests/capstone/component_registry_cap_002_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {r["component_id"]: r["status"] for r in rows} == EXPECTED_CAP002_COMPONENTS
    assert {r["owner_task"] for r in rows} == {"CAP-002"}


def test_cap_002_freeze_lock_binds_every_listed_file_byte_for_byte() -> None:
    lock = json.loads(CAP002_LOCK.read_text())
    assert lock["status"] == "FROZEN_ENGINEERING_PROTOCOL"
    for cid, entry in lock["components"].items():
        assert entry["status"] == EXPECTED_CAP002_COMPONENTS[cid]
        assert hash_file(ROOT / entry["path"]) == entry["sha256"], cid
    bound = {**lock["bound_files"], **lock["upstream_frozen_identity"]}
    amendments = sorted((ROOT / "artifacts/capstone").glob(
        "CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.amendment_*.json"))
    assert len(amendments) >= 1
    for amendment in amendments:
        for path, change in json.loads(amendment.read_text())["files"].items():
            assert bound[path] == change["old_sha256"]  # supersedes exactly the previous hash
            bound[path] = change["new_sha256"]
    for path, digest in bound.items():
        assert hash_file(ROOT / path) == digest, path
    registry = lock["component_registry"]
    assert hash_file(ROOT / registry["path"]) == registry["sha256"]


def test_cap_001_components_and_lock_are_unchanged_by_cap_002() -> None:
    from scripts.cap_002_protected_audit import verify_cap001_lock
    assert verify_cap001_lock()["verified"] is True
    with (ROOT / "manifests/capstone/component_registry_v1.csv").open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 16
