"""Build the CAP-003 component registry and the CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1 lock."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json"
REGISTRY = "manifests/capstone/component_registry_cap_003_v1.csv"
PROTOCOL = "configs/capstone/cap_003_product_monitoring_protocol_v1.json"
IMPL = "FROZEN_ENGINEERING_IMPLEMENTATION"
COMPONENTS = (
    ("CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1", "ENGINEERING_PROTOCOL",
     "FROZEN_ENGINEERING_PROTOCOL", PROTOCOL, LOCK,
     "CAP-003 method protocol incl. the frozen CAPG2 criteria."),
    ("CAPSTONE_LIVE_STREAM_BINDING_V1", "IMPLEMENTATION_BINDING", "FROZEN_IMPLEMENTATION_BINDING",
     "configs/capstone/cap_003_live_stream_binding_v1.json",
     "configs/capstone/cap_003_live_stream_binding_v1.json",
     "Tee at the coordinator: 360 Hz UI vs unchanged 250 Hz scientific path."),
    ("CAPSTONE_PRODUCT_API_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "api/product_app.py",
     "api/product_app.py", "Separate product FastAPI app: 9 CAP-003 routes; fail-closed auth."),
    ("CAPSTONE_DEVICE_MANAGER_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "product/devices/manager.py",
     "product/devices/manager.py", "In-memory device service over the unchanged CAP-002 source."),
    ("CAPSTONE_MONITORING_COORDINATOR_V1", "ENGINEERING_IMPLEMENTATION", IMPL,
     "product/monitoring/coordinator.py", "product/monitoring/coordinator.py",
     "Sole live-source orchestrator (+ mux, waveform, ephemeral state)."),
    ("CAPSTONE_INFERENCE_CLIENT_V1", "ENGINEERING_IMPLEMENTATION", IMPL,
     "product/inference/client.py", "product/inference/client.py",
     "Async HTTP client to the released /v1/infer-window; no model import."),
    ("CAPSTONE_PRODUCT_EVENT_ADAPTER_V1", "ENGINEERING_IMPLEMENTATION", IMPL,
     "product/monitoring/event_adapter.py", "product/monitoring/event_adapter.py",
     "Real upstream values -> PRODUCT_LIVE_EVENT_V1 with one global sequencer."),
    ("CAPSTONE_MONITORING_EVENT_JOURNAL_V1", "ENGINEERING_IMPLEMENTATION", IMPL,
     "product/monitoring/event_journal.py", "product/monitoring/event_journal.py",
     "In-memory append-only journal; replay from 0 then tail."),
)
BOUND = (
    "docs/capstone/CAPSTONE_LIVE_STREAM_BINDING_V1.md", "product/api/__init__.py",
    "product/api/errors.py", "product/api/models.py", "product/inference/__init__.py",
    "product/monitoring/__init__.py", "product/monitoring/mux.py", "product/monitoring/waveform.py",
    "product/monitoring/runtime_state.py", "scripts/capstone_cap003_test_identity.py",
    "scripts/run_capstone_monitoring_e2e.py", "scripts/cap_003_protected_audit.py",
    "scripts/cap_003_build_evidence.py", "scripts/cap_003_mutation_controls.py",
    "tests/capstone_product_support.py", "tests/test_capstone_product_api.py",
    "tests/test_capstone_monitoring_coordinator.py", "tests/test_capstone_inference_client.py",
    "tests/test_capstone_monitoring_websocket.py", "tests/test_capstone_monitoring_e2e.py",
)
UPSTREAM = (
    "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json",
    "simulation/stream_runtime_v2013.py", "simulation/types.py", "api/schemas.py",
    "api/app_default.py", "api/app_v2.py", "contracts/API_SCHEMA_V1.json",
    "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json",
    "product/events.py", "product/session.py", "product/devices/simulated.py",
    "product/edge/virtual.py",
)


def main() -> None:
    with (ROOT / REGISTRY).open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["component_id", "component_type", "owner_task", "status",
                         "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, _path, lock_path, notes in COMPONENTS:
            writer.writerow([cid, ctype, "CAP-003", status, "", lock_path, notes])
    lock = {
        "lock_id": "CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1", "owner_task": "CAP-003",
        "gate": "CAPG2", "status": "FROZEN_ENGINEERING_PROTOCOL",
        "entry_sha": "9f49b0c52fd93f7a28aff9ef67407fa9c56976df",
        "freeze_basis": "method/protocol freeze: bound files precede CAPG2 result evidence",
        "components": {cid: {"status": status, "path": path, "sha256": hash_file(ROOT / path)}
                       for cid, _t, status, path, _l, _n in COMPONENTS},
        "component_registry": {"path": REGISTRY, "sha256": hash_file(ROOT / REGISTRY)},
        "bound_files": {p: hash_file(ROOT / p) for p in BOUND},
        "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in UPSTREAM},
        "freeze_time_state": {
            "note": "informational; these registries transition at the result commit",
            "task_registry_sha256": hash_file(ROOT / "manifests/capstone/task_registry_v1.csv"),
            "gate_registry_sha256": hash_file(ROOT / "manifests/capstone/gate_registry_v1.csv"),
            "CAP-003": "IN_PROGRESS", "CAPG2": "NOT_STARTED"},
        "mutable_future_implementation_files_bound": False,
    }
    (ROOT / LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"components": len(lock["components"]), "bound": len(lock["bound_files"])}))


if __name__ == "__main__":
    main()
