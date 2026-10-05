# ruff: noqa: E501
"""Build the CAP-004 component registry and the CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1 lock."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.lock.json"
REGISTRY = "manifests/capstone/component_registry_cap_004_v1.csv"
PROTOCOL = "configs/capstone/cap_004_auth_persistence_protocol_v1.json"
IMPL = "FROZEN_ENGINEERING_IMPLEMENTATION"
CONTRACT = "FROZEN_INTERFACE_CONTRACT"
# (component_id, type, status, path, predecessor, notes)
COMPONENTS = (
    ("CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_ENGINEERING_PROTOCOL",
     PROTOCOL, "", "CAP-004 method protocol incl. the frozen CAPG3 criteria."),
    ("CAPSTONE_STORAGE_POLICY_V2", "PRODUCT_POLICY", "FROZEN_PRODUCT_POLICY",
     "contracts/capstone/storage_policy_v2.json", "CAPSTONE_STORAGE_POLICY_V1",
     "Additive successor: devices.scenario_id, schema version, lifecycle clock, restart semantics."),
    ("PRODUCT_API_CONTRACT_V2", "INTERFACE_CONTRACT", CONTRACT,
     "contracts/capstone/product_api_v2.json", "PRODUCT_API_CONTRACT_V1",
     "Additive successor: system auth_provider/demo_mode/persistence_mode; /me and session routes."),
    ("CLERK_AUTH_PROVIDER_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/auth/clerk.py", "",
     "Clerk session auth through the official clerk-backend-api SDK; no custom JWT; no fallback."),
    ("DEMO_AUTH_PROVIDER_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/auth/demo.py", "",
     "Explicit offline faculty demo identity behind the exact acknowledgement."),
    ("CAPSTONE_SQLITE_STORE_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/persistence/store.py", "",
     "Stdlib SQLite store: 15 policy tables, WAL, foreign keys, schema version, immutability."),
    ("CAPSTONE_PERSISTENCE_BRIDGE_V1", "ENGINEERING_IMPLEMENTATION", IMPL,
     "product/persistence/bridge.py", "",
     "Observes the unchanged live stream; bounded writes; raw vs product context."),
    ("CAPSTONE_SESSION_SERVICE_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/sessions/service.py",
     "", "Public session create/list/get and persistent device service over the frozen services."),
    ("CAPSTONE_PRODUCT_API_V1_1", "ENGINEERING_IMPLEMENTATION", IMPL, "api/product_app_v1_1.py",
     "CAPSTONE_PRODUCT_API_V1", "Additive successor app: CAP-003 routes + /me + session routes, CORS, recovery."),
    ("CAPSTONE_RESTART_RECOVERY_V1", "ENGINEERING_IMPLEMENTATION", IMPL,
     "product/persistence/recovery.py", "",
     "Restart: devices reconstructed DETACHED; stale nonterminal sessions FAILED, never resumed."),
    ("CAPSTONE_WAVEFORM_PREVIEW_V1", "ENGINEERING_IMPLEMENTATION", IMPL,
     "product/persistence/preview.py", "", "Bounded (<=4000 point) ECG preview; not the raw stream."),
)
BOUND = (
    "product/auth/errors.py", "product/auth/factory.py", "product/auth/resolver.py",
    "product/persistence/__init__.py", "product/persistence/schema.py", "product/sessions/__init__.py",
    "product/api/models_v2.py", "scripts/run_capstone_product.py", "scripts/run_capstone_persistent_e2e.py",
    "scripts/cap_004_protected_audit.py", "scripts/cap_004_build_freeze.py",
    "scripts/cap_004_build_evidence.py", "scripts/cap_004_mutation_controls.py",
    "tests/capstone_persistent_support.py", "tests/test_capstone_auth.py",
    "tests/test_capstone_persistence.py", "tests/test_capstone_session_service.py",
    "tests/test_capstone_restart_recovery.py", ".env.example", "pyproject.toml", "requirements-dev.lock",
)
UPSTREAM = (
    "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json",
    "contracts/capstone/storage_policy_v1.json", "contracts/capstone/product_api_v1.json",
    "contracts/capstone/auth_policy_v1.json", "api/product_app.py", "product/auth/base.py",
    "product/devices/manager.py", "product/inference/client.py", "product/monitoring/coordinator.py",
    "product/monitoring/event_adapter.py", "product/monitoring/event_journal.py",
    "product/monitoring/mux.py", "product/monitoring/runtime_state.py", "product/monitoring/waveform.py",
    "product/events.py", "product/session.py", "simulation/stream_runtime_v2013.py", "api/schemas.py",
    "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
)


def main() -> None:
    with (ROOT / REGISTRY).open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["component_id", "component_type", "owner_task", "status",
                         "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, path, predecessor, notes in COMPONENTS:
            lock_path = LOCK if cid.startswith("CAPSTONE_AUTH_PERSISTENCE") else path
            writer.writerow([cid, ctype, "CAP-004", status, predecessor, lock_path, notes])
    lock = {
        "lock_id": "CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1", "owner_task": "CAP-004", "gate": "CAPG3",
        "status": "FROZEN_ENGINEERING_PROTOCOL",
        "entry_sha": "56fc19f69566fd9ead6b509292449d5cd7540adb",
        "freeze_basis": "method/protocol freeze: bound files precede CAPG3 result evidence",
        "components": {cid: {"status": status, "path": path, "sha256": hash_file(ROOT / path)}
                       for cid, _t, status, path, _p, _n in COMPONENTS},
        "component_registry": {"path": REGISTRY, "sha256": hash_file(ROOT / REGISTRY)},
        "bound_files": {p: hash_file(ROOT / p) for p in BOUND},
        "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in UPSTREAM},
        "freeze_time_state": {
            "note": "informational; these registries transition at the result commit",
            "task_registry_sha256": hash_file(ROOT / "manifests/capstone/task_registry_v1.csv"),
            "gate_registry_sha256": hash_file(ROOT / "manifests/capstone/gate_registry_v1.csv"),
            "CAP-004": "IN_PROGRESS", "CAPG3": "NOT_STARTED"},
        "mutable_future_implementation_files_bound": False,
    }
    (ROOT / LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"components": len(lock["components"]), "bound": len(lock["bound_files"])}))


if __name__ == "__main__":
    main()
