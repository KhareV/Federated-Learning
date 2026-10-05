"""Build the CAP-001 component registry and the CAPSTONE_PRODUCT_PROTOCOL_V1 freeze lock.

The lock binds the frozen CAP-001 contract/interface/test files by SHA-256 plus the upstream frozen
system identity. Task/gate registry hashes are recorded as informational ``freeze_time_state``
only: those two registries legitimately transition (CAP-001/CAPG0 -> PASS) at the result commit.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json"
def _c(cid, ctype, status, path, note, lock_path=None):
    return (cid, ctype, status, path, lock_path or path, note)


COMPONENTS = (
    _c("CAPSTONE_PRODUCT_PROTOCOL_V1", "PRODUCT_PROTOCOL", "FROZEN_PRE_IMPLEMENTATION_PROTOCOL",
       "configs/capstone/capstone_product_protocol_v1.json",
       "FL-first product protocol: five planes; does not change the frozen NHM science.", LOCK),
    _c("DEVICE_SOURCE_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/device_source_v1.json",
       "DeviceSource protocol, device lifecycle, descriptor/events; reuses ObservedRecord."),
    _c("EDGE_NODE_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/edge_node_v1.json",
       "Edge node: wearable != FL client; live vs training flows; SIM_FL_SITE cohort reuse."),
    _c("LOCAL_TRAINING_BUFFER_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/local_training_buffer_v1.json",
       "Local buffer schema; SimulationTruth only via SIMULATION_LABEL_ADAPTER_V1."),
    _c("CAPSTONE_FL_CLIENT_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/fl_client_v1.json",
       "FL client adapter over the existing V2 federated modules; no new FL implementation."),
    _c("CAPSTONE_FEDERATION_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/federation_v1.json",
       "Round lifecycle, algorithms (FedAvg/FedProx), SecAgg scope, data locality, events."),
    _c("CAPSTONE_FL_RUN_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/fl_run_v1.json",
       "Federation run; 8 clients/3 rounds/24 updates (V2-FL-005 compatible); engineering only."),
    _c("CAPSTONE_MODEL_REGISTRY_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/model_registry_v1.json",
       "Released scientific models vs CAPSTONE_FL_CANDIDATE namespace; production_deployed=false."),
    _c("CAPSTONE_MODEL_GOVERNANCE_V1", "PRODUCT_POLICY", "FROZEN_PRODUCT_POLICY",
       "contracts/capstone/model_governance_v1.json",
       "Candidate lifecycle; no PRODUCTION_DEPLOYED state; sandbox acceptance != promotion."),
    _c("PRODUCT_API_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/product_api_v1.json",
       "/product/v1 REST + 2 WebSockets; separate from the frozen /v1/infer-window API."),
    _c("PRODUCT_LIVE_EVENT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/live_event_v1.json",
       "Typed monitoring + federation event unions; authority product/events.py."),
    _c("CAPSTONE_SESSION_CONTRACT_V1", "INTERFACE_CONTRACT", "FROZEN_INTERFACE_CONTRACT",
       "contracts/capstone/session_v1.json",
       "Monitoring-session lifecycle and immutable identity."),
    _c("CAPSTONE_AUTH_POLICY_V1", "PRODUCT_POLICY", "FROZEN_PRODUCT_POLICY",
       "contracts/capstone/auth_policy_v1.json",
       "AuthProvider: Clerk (planned) + explicit Demo; identity never affects ML."),
    _c("CAPSTONE_STORAGE_POLICY_V1", "PRODUCT_POLICY", "FROZEN_PRODUCT_POLICY",
       "contracts/capstone/storage_policy_v1.json",
       "SQLite entities incl. federation/candidates; no per-sample rows."),
    _c("CAPSTONE_DEMO_SCENARIOS_V1", "DEMO_CONTRACT", "FROZEN_DEMO_CONTRACT",
       "contracts/capstone/demo_scenarios_v1.json",
       "13 deterministic engineering scenarios (monitoring, alert fixture, federation)."),
    _c("REAL_HARDWARE_REPLACEMENT_BOUNDARY_V1", "PRODUCT_PROTOCOL",
       "FROZEN_PRE_IMPLEMENTATION_PROTOCOL", "contracts/capstone/real_hardware_replacement_v1.json",
       "Source + edge-gateway swap boundary; unknown hardware facts VERIFICATION_REQUIRED."),
)
AUXILIARY = (
    "contracts/capstone/live_event_v1.schema.json", "contracts/capstone/connection_table_v1.json",
    "docs/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.md",
    "docs/capstone/REAL_HARDWARE_REPLACEMENT_BOUNDARY_V1.md",
    "reports/capstone/cap_001/architecture_graph.md",
    "product/__init__.py", "product/contracts.py", "product/events.py", "product/session.py",
    "product/devices/__init__.py", "product/devices/base.py", "product/auth/__init__.py",
    "product/auth/base.py", "product/edge/__init__.py", "product/edge/base.py",
    "product/edge/buffer.py", "product/federation/__init__.py", "product/federation/base.py",
    "product/models/__init__.py", "product/models/registry_contract.py",
    "tests/test_capstone_contracts.py", "tests/test_capstone_federation_contracts.py",
    "scripts/cap_001_generate_contracts.py", "scripts/cap_001_protected_audit.py",
)
UPSTREAM = (
    "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
    "artifacts/ROLLBACK_RUNTIME_BINDING_V1.lock.json", "contracts/API_SCHEMA_V1.json",
    "contracts/openapi_v1.json", "contracts/sample_schema_v1.json", "checkpoints/MODEL_V2_FINAL.pt",
    "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts", "artifacts/CAL_V2.json", "api/schemas.py",
    "simulation/types.py", "simulation/stream_runtime_v2013.py",
)


def build_registry() -> None:
    header = ["component_id", "component_type", "owner_task", "status", "predecessor_id",
              "lock_path", "notes"]
    with (ROOT / "manifests/capstone/component_registry_v1.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for cid, ctype, status, _path, lock_path, notes in COMPONENTS:
            writer.writerow([cid, ctype, "CAP-001", status, "", lock_path, notes])


def build_lock() -> dict:
    entry_path = ROOT / "reports/capstone/cap_001/upstream_protection_entry.json"
    entry = json.loads(entry_path.read_text())
    lock = {
        "lock_id": "CAPSTONE_PRODUCT_PROTOCOL_V1",
        "owner_task": "CAP-001", "gate": "CAPG0",
        "status": "FROZEN_PRE_IMPLEMENTATION_PROTOCOL",
        "entry_sha": entry["entry_sha"],
        "freeze_basis": "method/contract freeze: bound files precede CAPG0 result evidence",
        "components": {
            cid: {"status": status, "path": path, "sha256": hash_file(ROOT / path)}
            for cid, _t, status, path, _lock, _n in COMPONENTS
        },
        "component_registry": {
            "path": "manifests/capstone/component_registry_v1.csv",
            "sha256": hash_file(ROOT / "manifests/capstone/component_registry_v1.csv"),
        },
        "bound_files": {p: hash_file(ROOT / p) for p in AUXILIARY},
        "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in UPSTREAM},
        "upstream_system": {
            "software_system": "SOFTWARE_SYSTEM_V2", "model": "MODEL_V2_FINAL",
            "calibration": "CAL_V2",
            "gateway": "GATEWAY_ARTIFACT_V2", "api": "API_SCHEMA_V1",
            "federated_checkpoint_deployed": False,
        },
        "freeze_time_state": {
            "note": "informational only; these registries transition at the result commit",
            "task_registry_sha256": hash_file(ROOT / "manifests/capstone/task_registry_v1.csv"),
            "gate_registry_sha256": hash_file(ROOT / "manifests/capstone/gate_registry_v1.csv"),
            "CAP-001": "IN_PROGRESS", "CAPG0": "NOT_STARTED",
        },
        "mutable_future_implementation_files_bound": False,
    }
    out = ROOT / LOCK
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return lock


def main() -> None:
    build_registry()
    lock = build_lock()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    print(json.dumps({"head": head, "components": len(lock["components"]),
                      "bound_files": len(lock["bound_files"])}))


if __name__ == "__main__":
    main()
