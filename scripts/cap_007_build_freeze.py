# ruff: noqa: E501
"""Build the CAP-007 component registry and the CAPSTONE_FEDERATION_PROTOCOL_V1 lock."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_FEDERATION_PROTOCOL_V1.lock.json"
REGISTRY = "manifests/capstone/component_registry_cap_007_v1.csv"
PROTOCOL = "configs/capstone/cap_007_federation_protocol_v1.json"
IMPL = "FROZEN_ENGINEERING_IMPLEMENTATION"
COMPONENTS = (
    ("CAPSTONE_FEDERATION_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_ENGINEERING_PROTOCOL", PROTOCOL, "", "CAP-007 method protocol incl. the frozen CAPG6 criteria."),
    ("CAPSTONE_FEDERATION_CONTRACT_V2", "INTERFACE_CONTRACT_SUCCESSOR", "FROZEN_INTERFACE_CONTRACT_SUCCESSOR", "contracts/capstone/federation_v2.json", "CAPSTONE_FEDERATION_CONTRACT_V1", "Additive successor: one candidate per run (AGGREGATING -> COMPLETED for non-final rounds)."),
    ("CAPSTONE_FEDERATION_EXECUTION_BINDING_V1", "IMPLEMENTATION_BINDING", "FROZEN_IMPLEMENTATION_BINDING", "contracts/capstone/federation_execution_binding_v1.json", "", "Binds the orchestrator to the unchanged V2 FL stack (lineage, replay, resume, concurrency, SecAgg shadow)."),
    ("CAPSTONE_FL_CLIENT_ADAPTER_V2", "ENGINEERING_IMPLEMENTATION", IMPL, "product/federation/client_v2.py", "CAPSTONE_FL_CLIENT_ADAPTER_V1", "Round-lineage-verified successor of the CAP-006 client adapter (V1 unchanged)."),
    ("CAPSTONE_FEDERATION_SERVICE_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/federation/service.py", "", "Live orchestrator: runs, rounds, coordinator, events, checkpoints, candidate, governance, replay, recovery."),
    ("CAPSTONE_FEDERATION_EVENT_JOURNAL_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/federation/journal.py", "", "Per-run append-only federation event journal (12 kinds, contiguous sequence, replay then tail)."),
    ("CAPSTONE_FEDERATION_STORE_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "capstone_persistence/federation_store.py", "", "SQLite rows for the five federation policy tables over its own connection."),
    ("CAPSTONE_FEDERATION_ARTIFACT_STORE_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/federation/artifact_store.py", "", "Run metadata, event JSONL and round checkpoints (never committed)."),
    ("CAPSTONE_FEDERATION_RECOVERY_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/federation/recovery.py", "", "Round-boundary restart recovery: resume from a valid checkpoint or mark FAILED."),
    ("CAPSTONE_MODEL_REGISTRY_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/models/registry.py", "", "Released vs CAPSTONE_FL_CANDIDATE namespaces; atomic candidate allocation."),
    ("CAPSTONE_MODEL_GOVERNANCE_RUNTIME_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/models/governance.py", "", "Five structural validation checks and the sandbox-only governance decision."),
    ("CAPSTONE_PRODUCT_API_V1_2", "ENGINEERING_IMPLEMENTATION", IMPL, "api/product_app_v1_2.py", "CAPSTONE_PRODUCT_API_V1_1", "Product API successor: composes V1_1 and adds exactly the ten CAP-007 routes."),
)
BOUND = (
    "docs/capstone/CAPSTONE_FEDERATION_EXECUTION_BINDING_V1.md", "reports/capstone/cap_007/federation_contract_reconciliation.json",
    "product/federation/execution_binding.py", "product/federation/events.py", "product/federation/secagg_shadow.py", "product/federation/replay.py",
    "product/models/candidate_artifacts.py", "product/models/views.py",
    "scripts/cap_007_protected_audit.py", "scripts/cap_007_build_freeze.py", "scripts/cap_007_build_evidence.py", "scripts/cap_007_mutation_controls.py",
    "scripts/run_capstone_federation.py", "scripts/run_capstone_product_v1_2.py", "scripts/verify_capstone_federation.py",
    "tests/capstone_federation_support.py", "tests/test_capstone_federation_service.py", "tests/test_capstone_federation_multiround.py", "tests/test_capstone_federation_api.py",
    "tests/test_capstone_federation_websocket.py", "tests/test_capstone_candidate_registry.py", "tests/test_capstone_candidate_governance.py",
    "tests/test_capstone_federation_recovery.py", "tests/test_capstone_federation_replay.py", "tests/test_capstone_secagg_integration.py", "tests/test_capstone_federation_isolation.py",
)
UPSTREAM = (
    "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1.lock.json", "artifacts/capstone/CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1.lock.json",
    "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "artifacts/FEDPROX_MU_V2.lock.json",
    "reports/model_v2/v2_fl_005/cohort_manifest_run.json", "reports/model_v2/v2_fl_005/federation_run.json",
    "federated/model_v2_fl.py", "federated/model_v2_fedprox.py", "federated/aggregation.py", "federated/model_adapter.py", "federated/wearable_fl_system_v1.py",
    "federated/wearable_fl_runner_v1.py", "federated/wearable_fl_secagg_shadow_v1.py", "privacy/secagg_app.py", "configs/model_v2/wearable_sim_fl_secagg_compat_v1.yaml",
    "product/federation/base.py", "product/federation/client.py", "product/federation/local_cohort.py", "product/federation/update_bridge.py", "product/edge/local_training_buffer.py",
    "product/events.py", "product/models/registry_contract.py", "product/session.py",
    "contracts/capstone/federation_v1.json", "contracts/capstone/fl_run_v1.json", "contracts/capstone/model_registry_v1.json", "contracts/capstone/model_governance_v1.json",
    "contracts/capstone/storage_policy_v2.json", "contracts/capstone/product_api_v1.json", "contracts/capstone/product_api_v2.json",
    "api/product_app.py", "api/product_app_v1_1.py", "capstone_persistence/store.py",
    "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
)


def main() -> None:
    with (ROOT / REGISTRY).open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["component_id", "component_type", "owner_task", "status", "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, path, predecessor, notes in COMPONENTS:
            writer.writerow([cid, ctype, "CAP-007", status, predecessor, LOCK if cid.startswith("CAPSTONE_FEDERATION_PROTOCOL") else path, notes])
    lock = {
        "lock_id": "CAPSTONE_FEDERATION_PROTOCOL_V1", "owner_task": "CAP-007", "gate": "CAPG6", "status": "FROZEN_ENGINEERING_PROTOCOL",
        "entry_sha": "651bfa61022cf699a43c0a91cbc43a6486943bcb", "freeze_basis": "method/federation freeze: bound files precede CAPG6 result evidence",
        "components": {cid: {"status": status, "path": path, "sha256": hash_file(ROOT / path)} for cid, _t, status, path, _p, _n in COMPONENTS},
        "component_registry": {"path": REGISTRY, "sha256": hash_file(ROOT / REGISTRY)},
        "bound_files": {p: hash_file(ROOT / p) for p in BOUND},
        "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in UPSTREAM},
        "freeze_time_state": {"note": "informational; these registries transition at the result commit", "task_registry_sha256": hash_file(ROOT / "manifests/capstone/task_registry_v1.csv"),
                              "gate_registry_sha256": hash_file(ROOT / "manifests/capstone/gate_registry_v1.csv"), "CAP-007": "IN_PROGRESS", "CAPG6": "NOT_STARTED"},
        "mutable_future_implementation_files_bound": False,
    }
    (ROOT / LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"components": len(lock["components"]), "bound": len(lock["bound_files"]), "upstream": len(lock["upstream_frozen_identity"])}))


if __name__ == "__main__":
    main()
