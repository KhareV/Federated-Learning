# ruff: noqa: E501
"""Build the CAPSTONE_UI_V1_1 successor lock (``ui``) or the CAP-008 component registry + CAPSTONE_FEDERATION_UX_PROTOCOL_V1
lock (``protocol``)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from scripts.verify_capstone_ui_v1_1 import frontend_files
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
UI_LOCK = "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json"
UI_V1 = "artifacts/capstone/CAPSTONE_UI_V1.lock.json"
LOCK = "artifacts/capstone/CAPSTONE_FEDERATION_UX_PROTOCOL_V1.lock.json"
REGISTRY = "manifests/capstone/component_registry_cap_008_v1.csv"
PROTOCOL = "configs/capstone/cap_008_federation_ux_protocol_v1.json"
IMPL = "FROZEN_ENGINEERING_IMPLEMENTATION"
COMPONENTS = (
    ("CAPSTONE_FEDERATION_UX_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_ENGINEERING_PROTOCOL", PROTOCOL, "", "CAP-008 method protocol incl. the frozen CAPG7 criteria."),
    ("CAPSTONE_UI_V1_1", "UI_SUCCESSOR_LOCK", "FROZEN_ENGINEERING_INTERFACE", UI_LOCK, "CAPSTONE_UI_V1", "Successor of CAPSTONE_UI_V1 binding the complete CAP-008 frontend."),
    ("CAPSTONE_FEDERATION_FRONTEND_V1", "IMPLEMENTATION_BINDING", "FROZEN_IMPLEMENTATION_BINDING", "docs/capstone/CAPSTONE_FEDERATION_FRONTEND_V1.md", "", "The federation/model pages and components over the CAP-007 backend."),
    ("CAPSTONE_FEDERATION_PRODUCT_CLIENT_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "frontend/src/lib/product/api.ts", "CAPSTONE_PRODUCT_CLIENT_V1", "Typed client extension: the nine CAP-007 methods and the token-free federation WebSocket URL."),
    ("CAPSTONE_FEDERATION_LIVE_MODEL_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "frontend/src/lib/product/federation/live-model.ts", "", "Event-derived federation state with strict sequence integrity (parser: federation/events.ts)."),
    ("CAPSTONE_FEDERATION_STORE_UI_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "frontend/src/lib/product/federation/state.svelte.ts", "", "Federation product store, separate from the monitoring store."),
    ("CAPSTONE_MODEL_GOVERNANCE_UI_V1", "ENGINEERING_IMPLEMENTATION", IMPL, "frontend/src/lib/components/product/federation/CandidateCard.svelte", "", "Candidate/governance presentation: sandbox-only, never deployed."),
)
BOUND = (
    "scripts/cap_008_protected_audit.py", "scripts/cap_008_build_freeze.py", "scripts/cap_008_build_evidence.py", "scripts/cap_008_mutation_controls.py",
    "scripts/run_capstone_federation_ui_e2e.py", "scripts/cap_008_cdp_driver.mjs", "scripts/verify_capstone_ui_v1_1.py", "scripts/verify_capstone_ui_v1.py",
    "tests/test_capstone_federation_ui.py", "tests/test_capstone_frontend.py", "reports/capstone/cap_008/frontend_entry_inventory.json",
)
UPSTREAM = (
    "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json", UI_V1,
    "artifacts/capstone/CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_FEDERATION_PROTOCOL_V1.lock.json",
    "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "artifacts/FEDPROX_MU_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
    "api/product_app_v1_2.py", "api/product_app_v1_1.py", "capstone_persistence/federation_store.py", "capstone_persistence/store.py",
    "product/federation/service.py", "product/federation/client_v2.py", "product/federation/events.py", "product/federation/journal.py", "product/federation/recovery.py", "product/federation/replay.py",
    "product/federation/secagg_shadow.py", "product/federation/artifact_store.py", "product/models/registry.py", "product/models/governance.py", "product/models/candidate_artifacts.py",
    "contracts/capstone/federation_v2.json", "contracts/capstone/federation_execution_binding_v1.json", "reports/model_v2/v2_fl_005/federation_run.json",
)


def build_ui() -> None:
    v1 = json.loads((ROOT / UI_V1).read_text())
    expected = dict(v1["bound_artifacts"])
    for a in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_*.json")):
        d = json.loads(a.read_text())
        for p, c in d.get("files", {}).items():
            if p in expected:
                expected[p] = c["new_sha256"]
        expected.update(d.get("added_files", {}))
    files = frontend_files()
    bound = {p: hash_file(ROOT / p) for p in files}
    changed = sorted(p for p in files if expected.get(p) != bound[p])
    lock = {"lock_id": "CAPSTONE_UI_V1_1", "status": "FROZEN_ENGINEERING_INTERFACE", "owner_phase": "CAP-008", "predecessor_id": "CAPSTONE_UI_V1", "predecessor_sha256": hash_file(ROOT / UI_V1),
            "reason": "CAP-008: the federation/model placeholders of CAPSTONE_UI_V1 are replaced by real CAP-007-backed product UX (federation overview, clients, rounds, live, privacy, models). The CAPSTONE_UI_V1 lock file is preserved byte-identical.",
            "backend_modified": False, "api_contract_changed": False, "scientific_state_semantics_changed": False, "public_runtime_model_selector_added": False, "second_frontend_created": False, "npm_dependencies_added": [],
            "repository_path": "frontend/", "change_control": "Any change to a bound frontend file requires a recorded amendment (artifacts/capstone/CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_N.json) with the old->new sha chain; unaccounted frontend drift fails scripts/verify_capstone_ui_v1_1.py.",
            "bound_artifacts": bound, "changed_from_predecessor": changed}
    (ROOT / UI_LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"bound": len(bound), "changed_from_predecessor": len(changed)}))


def build_protocol() -> None:
    with (ROOT / REGISTRY).open("w", newline="") as handle:
        w = csv.writer(handle, lineterminator="\n")
        w.writerow(["component_id", "component_type", "owner_task", "status", "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, path, pred, notes in COMPONENTS:
            w.writerow([cid, ctype, "CAP-008", status, pred, LOCK if cid.endswith("UX_PROTOCOL_V1") else path, notes])
    lock = {"lock_id": "CAPSTONE_FEDERATION_UX_PROTOCOL_V1", "owner_task": "CAP-008", "gate": "CAPG7", "status": "FROZEN_ENGINEERING_PROTOCOL", "entry_sha": "711a4a0a1233765d6f1200fc2b6d8f3aa62d4743",
            "freeze_basis": "UI/method freeze: bound files precede CAPG7 result evidence",
            "components": {cid: {"status": status, "path": path, "sha256": hash_file(ROOT / path)} for cid, _t, status, path, _p, _n in COMPONENTS},
            "component_registry": {"path": REGISTRY, "sha256": hash_file(ROOT / REGISTRY)}, "bound_files": {p: hash_file(ROOT / p) for p in BOUND},
            "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in UPSTREAM},
            "freeze_time_state": {"note": "informational; these registries transition at the result commit", "task_registry_sha256": hash_file(ROOT / "manifests/capstone/task_registry_v1.csv"), "gate_registry_sha256": hash_file(ROOT / "manifests/capstone/gate_registry_v1.csv"), "CAP-008": "IN_PROGRESS", "CAPG7": "NOT_STARTED"},
            "mutable_future_implementation_files_bound": False, "frontend_bound_by": UI_LOCK}
    (ROOT / LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"components": len(lock["components"]), "bound": len(lock["bound_files"]), "upstream": len(lock["upstream_frozen_identity"])}))


if __name__ == "__main__":
    build_ui() if sys.argv[1] == "ui" else build_protocol()
