# ruff: noqa: E501
"""Build the CAP-005 component registry, the CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1 lock and the
CAPSTONE_UI_V1 lock (successor of DASHBOARD_UI_V1_5)."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json"
UI_LOCK = "artifacts/capstone/CAPSTONE_UI_V1.lock.json"
REGISTRY = "manifests/capstone/component_registry_cap_005_v1.csv"
PROTOCOL = "configs/capstone/cap_005_frontend_product_protocol_v1.json"
IMPL = "FROZEN_ENGINEERING_IMPLEMENTATION"
FE = "frontend/src/"
# (component_id, type, status, path, predecessor, notes)
COMPONENTS = (
    ("CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_ENGINEERING_PROTOCOL", PROTOCOL, "", "CAP-005 method protocol incl. the frozen CAPG4 criteria."),
    ("CAPSTONE_UI_V1", "FRONTEND_INTERFACE", "FROZEN_ENGINEERING_INTERFACE", "docs/capstone/CAPSTONE_UI_V1.md", "DASHBOARD_UI_V1_5", "The existing SvelteKit frontend extended into the product UI; lock supersedes DASHBOARD_UI_V1_5."),
    ("CAPSTONE_FRONTEND_AUTH_V1", "ENGINEERING_IMPLEMENTATION", IMPL, FE + "lib/product/auth.ts", "", "Backend-decided DEMO/CLERK bootstrap; lazy official ClerkJS; no fallback."),
    ("CAPSTONE_PRODUCT_CLIENT_V1", "ENGINEERING_IMPLEMENTATION", IMPL, FE + "lib/product/api.ts", "", "Typed client for PRODUCT_API_CONTRACT_V2 (same-origin /product/v1)."),
    ("CAPSTONE_MONITORING_STORE_V1", "ENGINEERING_IMPLEMENTATION", IMPL, FE + "lib/product/state.svelte.ts", "", "Svelte 5 product store over the pure live model, strict event parser, bounded waveform and socket."),
    ("CAPSTONE_DEVICE_UI_V1", "ENGINEERING_IMPLEMENTATION", IMPL, FE + "routes/app/device/+page.svelte", "", "/app/device virtual-wearable lifecycle UI."),
    ("CAPSTONE_MONITORING_UI_V1", "ENGINEERING_IMPLEMENTATION", IMPL, FE + "routes/app/monitoring/+page.svelte", "", "/app/monitoring live session UI."),
)
BOUND = (
    "docs/capstone/CAPSTONE_UI_V1.md", "scripts/cap_005_protected_audit.py", "scripts/cap_005_build_freeze.py", "scripts/cap_005_build_evidence.py",
    "scripts/cap_005_mutation_controls.py", "scripts/cap_005_cdp_driver.mjs", "scripts/run_capstone_frontend_e2e.py", "scripts/verify_capstone_ui_v1.py",
    "tests/test_capstone_frontend.py", "tests/test_t035_lock_versioning.py", "tests/test_v2_rel_001_results.py",
)
UPSTREAM = (
    "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json",
    "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.lock.json",
    "artifacts/DASHBOARD_UI_V1_5.lock.json", "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json", "api/product_app_v1_1.py", "api/product_app.py",
    "capstone_persistence/store.py", "contracts/capstone/product_api_v2.json", "contracts/capstone/storage_policy_v2.json",
    "contracts/capstone/live_event_v1.schema.json", "scripts/run_capstone_product.py", "artifacts/SOFTWARE_SYSTEM_V2.lock.json",
    "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
)
UI_ROOT_FILES = ("frontend/package.json", "frontend/package-lock.json", "frontend/vite.config.ts", "frontend/vitest.config.ts", "frontend/svelte.config.js",
                 "frontend/tsconfig.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json", "frontend/clerk-sdk/.gitignore")


def frontend_files() -> list[str]:
    listing = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "frontend/src", "frontend/static"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split()
    return sorted(set(listing) | set(UI_ROOT_FILES))


def main() -> None:
    with (ROOT / REGISTRY).open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["component_id", "component_type", "owner_task", "status", "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, path, predecessor, notes in COMPONENTS:
            lock_path = LOCK if cid.startswith("CAPSTONE_FRONTEND_PRODUCT") else UI_LOCK if cid == "CAPSTONE_UI_V1" else path
            writer.writerow([cid, ctype, "CAP-005", status, predecessor, lock_path, notes])
    ui = {
        "lock_id": "CAPSTONE_UI_V1", "status": "FROZEN_ENGINEERING_INTERFACE", "logical_subsystem": "frontend", "repository_path": "frontend/",
        "predecessor_id": "DASHBOARD_UI_V1_5", "predecessor_sha256": hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_5.lock.json"),
        "reason": "CAP-005: the existing SvelteKit frontend becomes the capstone product interface (sign-in, /app shell, device, monitoring, persisted sessions, claim corrections, offline DEMO path). Files bound by DASHBOARD_UI_V1_5 that changed: routes/+page.svelte, routes/monitor/+page.svelte, vite.config.ts, vitest.config.ts. The V1_5 lock file is preserved byte-identical and reports drift by design.",
        "scientific_state_semantics_changed": False, "api_contract_changed": False, "backend_modified": False,
        "public_runtime_model_selector_added": False, "second_frontend_created": False,
        "clerk_sdk": {"package": "@clerk/clerk-js", "version": "6.37.0", "location": "frontend/clerk-sdk"},
        "bound_artifacts": {p: hash_file(ROOT / p) for p in frontend_files()},
        "change_control": "Any change to a bound frontend file requires a recorded amendment (artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_N.json) with the old->new sha chain.",
    }
    (ROOT / UI_LOCK).write_text(json.dumps(ui, indent=1, sort_keys=True) + "\n")
    lock = {
        "lock_id": "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1", "owner_task": "CAP-005", "gate": "CAPG4", "status": "FROZEN_ENGINEERING_PROTOCOL",
        "entry_sha": "9db76b482678114ac5c22f3f91a3f55ccb159e17", "freeze_basis": "method/UI freeze: bound files precede CAPG4 result evidence",
        "components": {cid: {"status": status, "path": path, "sha256": hash_file(ROOT / path)} for cid, _t, status, path, _p, _n in COMPONENTS},
        "component_registry": {"path": REGISTRY, "sha256": hash_file(ROOT / REGISTRY)},
        "ui_lock": {"path": UI_LOCK, "sha256": hash_file(ROOT / UI_LOCK), "bound_files": len(ui["bound_artifacts"])},
        "bound_files": {p: hash_file(ROOT / p) for p in (*BOUND, UI_LOCK)},
        "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in UPSTREAM},
        "freeze_time_state": {"note": "informational; these registries transition at the result commit", "task_registry_sha256": hash_file(ROOT / "manifests/capstone/task_registry_v1.csv"),
                              "gate_registry_sha256": hash_file(ROOT / "manifests/capstone/gate_registry_v1.csv"), "CAP-005": "IN_PROGRESS", "CAPG4": "NOT_STARTED"},
        "mutable_future_implementation_files_bound": False,
    }
    (ROOT / LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"components": len(lock["components"]), "bound": len(lock["bound_files"]), "ui_bound": len(ui["bound_artifacts"])}))


if __name__ == "__main__":
    main()
