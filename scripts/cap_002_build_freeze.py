"""Build the CAP-002 component registry and the CAPSTONE_DEVICE_EDGE_PROTOCOL_V1 freeze lock."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json"
REGISTRY = "manifests/capstone/component_registry_cap_002_v1.csv"
PROTOCOL = "configs/capstone/cap_002_device_edge_protocol_v1.json"
COMPONENTS = (
    ("CAPSTONE_DEVICE_EDGE_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_ENGINEERING_PROTOCOL",
     PROTOCOL, LOCK, "CAP-002 method protocol incl. the 53 frozen CAPG1 criteria."),
    ("SIMULATED_WEARABLE_SOURCE_V1", "ENGINEERING_IMPLEMENTATION",
     "FROZEN_ENGINEERING_IMPLEMENTATION", "product/devices/simulated.py",
     "product/devices/simulated.py",
     "Concrete DeviceSource over the existing WEARABLE_SIM generator; not WEARABLE_V1."),
    ("VIRTUAL_EDGE_NODE_V1", "ENGINEERING_IMPLEMENTATION", "FROZEN_ENGINEERING_IMPLEMENTATION",
     "product/edge/virtual.py", "product/edge/virtual.py",
     "EdgeNode (live path only; disabled training-buffer boundary)."),
    ("CAPSTONE_DEVICE_SCENARIO_RUNTIME_V1", "ENGINEERING_IMPLEMENTATION",
     "FROZEN_ENGINEERING_IMPLEMENTATION", "product/devices/scenarios.py",
     "product/devices/scenarios.py",
     "Five frozen monitoring scenarios -> existing IntegrationProfile."),
    ("CAPSTONE_DEVICE_REPLAY_V1", "ENGINEERING_REPLAY", "FROZEN_ENGINEERING_REPLAY",
     "product/devices/replay.py", "product/devices/replay.py",
     "Deterministic semantic replay + existing WearableStreamRuntime compatibility summary."),
)
BOUND = (
    "tests/test_capstone_simulated_device.py", "tests/test_capstone_virtual_edge.py",
    "tests/test_capstone_device_replay.py", "tests/capstone_device_support.py",
    "scripts/run_capstone_device_demo.py", "scripts/verify_capstone_device_edge.py",
    "scripts/cap_002_protected_audit.py", "scripts/cap_002_build_evidence.py",
    "scripts/cap_002_mutation_controls.py",
)
UPSTREAM = (
    "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json",
    "simulation/stream_runtime_v2013.py", "simulation/profile_v2013.py", "simulation/types.py",
    "simulation/wearable.py", "simulation/fl_cohort_v1.py", "contracts/sample_schema_v1.json",
    "contracts/API_SCHEMA_V1.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
    "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "product/devices/base.py", "product/edge/base.py",
)


def main() -> None:
    with (ROOT / REGISTRY).open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["component_id", "component_type", "owner_task", "status",
                         "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, _path, lock_path, notes in COMPONENTS:
            writer.writerow([cid, ctype, "CAP-002", status, "", lock_path, notes])
    lock = {
        "lock_id": "CAPSTONE_DEVICE_EDGE_PROTOCOL_V1", "owner_task": "CAP-002", "gate": "CAPG1",
        "status": "FROZEN_ENGINEERING_PROTOCOL",
        "entry_sha": "44939378e7aee3baa2e92fefdd42fa9d75640a8a",
        "freeze_basis": "method/protocol freeze: bound files precede CAPG1 result evidence",
        "components": {cid: {"status": status, "path": path, "sha256": hash_file(ROOT / path)}
                       for cid, _t, status, path, _l, _n in COMPONENTS},
        "component_registry": {"path": REGISTRY, "sha256": hash_file(ROOT / REGISTRY)},
        "bound_files": {p: hash_file(ROOT / p) for p in BOUND},
        "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in UPSTREAM},
        "freeze_time_state": {
            "note": "informational; these registries transition at the result commit",
            "task_registry_sha256": hash_file(ROOT / "manifests/capstone/task_registry_v1.csv"),
            "gate_registry_sha256": hash_file(ROOT / "manifests/capstone/gate_registry_v1.csv"),
            "CAP-002": "IN_PROGRESS", "CAPG1": "NOT_STARTED"},
        "mutable_future_implementation_files_bound": False,
    }
    (ROOT / LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"components": len(lock["components"]), "bound": len(lock["bound_files"])}))


if __name__ == "__main__":
    main()
