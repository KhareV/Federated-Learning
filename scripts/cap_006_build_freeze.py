# ruff: noqa: E501
"""Build the CAP-006 component registry and the CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1 lock."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1.lock.json"
REGISTRY = "manifests/capstone/component_registry_cap_006_v1.csv"
PROTOCOL = "configs/capstone/cap_006_local_training_protocol_v1.json"
IMPL = "FROZEN_ENGINEERING_IMPLEMENTATION"
COMPONENTS = (
    ("CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_ENGINEERING_PROTOCOL", PROTOCOL, "", "CAP-006 method protocol incl. the frozen CAPG5 criteria."),
    ("CAPSTONE_LOCAL_BUFFER_BINDING_V1", "IMPLEMENTATION_BINDING", "FROZEN_IMPLEMENTATION_BINDING", "docs/capstone/CAPSTONE_LOCAL_BUFFER_BINDING_V1.md", "", "How the frozen LOCAL_TRAINING_BUFFER_CONTRACT_V1 is bound for the simulated capstone."),
    ("SIMULATION_LABEL_ADAPTER_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/edge/label_adapter.py", "", "Thin product wrapper over the existing client-local label adapter (WEARABLE_SIM_EVENT_WINDOW_V1)."),
    ("LOCAL_TRAINING_BUFFER_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/edge/local_training_buffer.py", "", "Client-local in-memory training buffer with private owner-only model-input store."),
    ("CAPSTONE_FL_CLIENT_ADAPTER_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/federation/client.py", "", "FLClient adapter over the existing V2 local FedAvg/FedProx epoch; local training only."),
    ("CAPSTONE_FL_UPDATE_BRIDGE_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/federation/update_bridge.py", "", "Exposes the EXISTING V2 update envelope after locality/validity checks."),
    ("CAPSTONE_FL_CLIENT_COHORT_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/federation/local_cohort.py", "", "The eight frozen V2-FL-005 clients as capstone FL clients (no second universe)."),
)
BOUND = (
    "scripts/cap_006_protected_audit.py", "scripts/cap_006_build_freeze.py", "scripts/cap_006_build_evidence.py",
    "scripts/cap_006_mutation_controls.py", "scripts/run_capstone_local_training.py",
    "tests/capstone_local_support.py", "tests/test_capstone_local_training_buffer.py",
    "tests/test_capstone_fl_client_adapter.py", "tests/test_capstone_local_update_bridge.py",
    "tests/test_capstone_local_training_repro.py",
)
UPSTREAM = (
    "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1.lock.json",
    "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "artifacts/FEDPROX_MU_V2.lock.json",
    "reports/model_v2/v2_fl_005/cohort_manifest_run.json", "reports/model_v2/v2_fl_005/federation_run.json",
    "federated/model_v2_fl.py", "federated/model_v2_fedprox.py", "federated/aggregation.py", "federated/virtual_client_source_v1.py",
    "federated/wearable_sim_local_labels.py", "federated/wearable_fl_system_v1.py", "federated/wearable_fl_runner_v1.py",
    "simulation/fl_cohort_v1.py", "simulation/fl_cohort_truth_v1.py", "product/edge/buffer.py", "product/edge/virtual.py", "product/federation/base.py",
    "contracts/capstone/fl_client_v1.json", "contracts/capstone/local_training_buffer_v1.json", "contracts/capstone/edge_node_v1.json",
    "contracts/capstone/fl_run_v1.json", "api/product_app.py", "api/product_app_v1_1.py", "capstone_persistence/store.py",
    "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
)


def main() -> None:
    with (ROOT / REGISTRY).open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["component_id", "component_type", "owner_task", "status", "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, path, predecessor, notes in COMPONENTS:
            writer.writerow([cid, ctype, "CAP-006", status, predecessor, LOCK if cid.startswith("CAPSTONE_LOCAL_TRAINING") else path, notes])
    lock = {
        "lock_id": "CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1", "owner_task": "CAP-006", "gate": "CAPG5", "status": "FROZEN_ENGINEERING_PROTOCOL",
        "entry_sha": "b8a6c70ed6b77a38273cb8bdb6659452dfe26f83", "freeze_basis": "method/local-training freeze: bound files precede CAPG5 result evidence",
        "components": {cid: {"status": status, "path": path, "sha256": hash_file(ROOT / path)} for cid, _t, status, path, _p, _n in COMPONENTS},
        "component_registry": {"path": REGISTRY, "sha256": hash_file(ROOT / REGISTRY)},
        "bound_files": {p: hash_file(ROOT / p) for p in BOUND},
        "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in UPSTREAM},
        "freeze_time_state": {"note": "informational; these registries transition at the result commit", "task_registry_sha256": hash_file(ROOT / "manifests/capstone/task_registry_v1.csv"),
                              "gate_registry_sha256": hash_file(ROOT / "manifests/capstone/gate_registry_v1.csv"), "CAP-006": "IN_PROGRESS", "CAPG5": "NOT_STARTED"},
        "mutable_future_implementation_files_bound": False,
    }
    (ROOT / LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"components": len(lock["components"]), "bound": len(lock["bound_files"]), "upstream": len(lock["upstream_frozen_identity"])}))


if __name__ == "__main__":
    main()
