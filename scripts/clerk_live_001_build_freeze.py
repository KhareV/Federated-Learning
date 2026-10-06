# ruff: noqa: E501
"""Freeze the CLERK-LIVE-001 method (lock + component registry) BEFORE the canonical real-Clerk E2E."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.cap_011_protected_audit import all_locks

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/clerk_connected/CLERK_LIVE_001_PROTOCOL_V1.lock.json"
REGISTRY = ROOT / "manifests/clerk_connected/component_registry_v1.csv"
CONFIG = ROOT / "configs/clerk_connected/clerk_live_001_protocol_v1.json"
ENTRY = ROOT / "reports/clerk_connected/clerk_live_001/entry_audit.json"
METHOD_FILES = (
    "configs/clerk_connected/clerk_live_001_protocol_v1.json", "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1.md", "frontend/src/lib/product/auth.ts", "frontend/src/lib/product/__tests__/clerk-ui-loader.test.ts",
    "scripts/run_capstone_clerk_connected.py", "scripts/run_capstone_clerk_connected_e2e.py", "scripts/clerk_connected_cdp_driver.mjs", "scripts/run_capstone_clerk_connected_clean_clone.py",
    "scripts/clerk_connected_lib.py", "scripts/clerk_live_001_evaluate_gate.py", "scripts/clerk_live_001_mutation_controls.py", "scripts/clerk_live_001_build_evidence.py", "scripts/clerk_live_001_build_freeze.py",
    "scripts/clerk_live_001_protected_audit.py", "scripts/verify_clerk_connected.py", "tests/test_clerk_connected_launcher.py", "tests/test_clerk_connected_lib.py",
)
COMPONENTS = (
    ("CLERK_LIVE_001_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_PRE_RESULT_PROTOCOL", "configs/clerk_connected/clerk_live_001_protocol_v1.json", "88 CLERKG0 criteria, 20 mutation controls; lock binds the connected layer."),
    ("CAPSTONE_UI_V1_3", "UI_SUCCESSOR_LOCK", "FROZEN_ENGINEERING_INTERFACE", "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json", "Whole-frontend successor lock; V1/V1_1/V1_2 lock bytes unchanged."),
    ("CAPSTONE_FRONTEND_AUTH_V2", "ENGINEERING_IMPLEMENTATION", "FROZEN_ENGINEERING_IMPLEMENTATION", "frontend/src/lib/product/auth.ts", "Official ClerkJS 6.x @clerk/ui bundle loader (CLERK mode only); no new dependency."),
    ("CAPSTONE_CLERK_CONNECTED_LAUNCHER_V1", "ENGINEERING_IMPLEMENTATION", "FROZEN_ENGINEERING_IMPLEMENTATION", "scripts/run_capstone_clerk_connected.py", "Same three services as the faculty launcher; CLERK auth; env-only credentials; no DemoAuth fallback."),
    ("CAPSTONE_CLERK_CONNECTED_E2E_V1", "ENGINEERING_IMPLEMENTATION", "FROZEN_ENGINEERING_IMPLEMENTATION", "scripts/run_capstone_clerk_connected_e2e.py", "Real Chrome + real Clerk TEST sign-in; two users; WebSockets; ownership; logout/refresh/restart."),
    ("CAPSTONE_CLERK_CONNECTED_RUNBOOK_V1", "DOCUMENTATION", "FROZEN_ENGINEERING_INTERFACE", "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1.md", "Placeholders only; offline DemoAuth distinction."),
    ("CAPSTONE_CLERK_CONNECTED_V1", "CONNECTED_SYSTEM", "PROSPECTIVE_UNTIL_CLERKG0", "reports/clerk_connected/clerk_live_001/connected_decision.json", "Successor of CAPSTONE_RELEASE_V1; decision recorded as evidence only."),
)
UPSTREAM = (
    "artifacts/capstone/CAPSTONE_UI_V1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "artifacts/capstone/CAPSTONE_RELEASE_MANIFEST_V1.json",
    "artifacts/capstone/CAPSTONE_RELEASE_PROTOCOL_V1.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "api/product_app_v1_3.py", "product/auth/clerk.py", "product/auth/resolver.py",
    "requirements-dev.lock", "requirements-capstone-auth.lock", "pyproject.toml", "frontend/package-lock.json", "frontend/clerk-sdk/package-lock.json", "frontend/clerk-sdk/package.json",
)


def write_registry() -> None:
    with REGISTRY.open("w", newline="", encoding="utf-8") as h:
        w = csv.writer(h, lineterminator="\n")
        w.writerow(["component_id", "component_type", "owner_task", "status", "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, path, notes in COMPONENTS:
            w.writerow([cid, ctype, "CLERK-LIVE-001", status, "", path, notes])


def freeze() -> dict[str, object]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if len(config["clerkg0_criteria"]) != config["criteria_count"] or len(config["mutation_controls"]) != 20:
        raise RuntimeError("CLERKG0_PROTOCOL_COUNT_MISMATCH")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.unlink(missing_ok=True)
    prior = all_locks()
    if not all(i["verified"] for i in prior.values()):
        raise RuntimeError("PRIOR_LOCK_CHAIN_FAILED")
    write_registry()
    prior_files = [i["lock"] for i in prior.values() if "lock" in i]
    lock = {
        "lock_id": "CLERK_LIVE_001_PROTOCOL_V1", "status": "FROZEN_PRE_RESULT_PROTOCOL", "owner_phase": "CLERK-LIVE-001", "gate": "CLERKG0", "entry_sha": config["entry"]["entry_sha"], "entry_audit_sha256": hash_file(ENTRY),
        "criteria_count": config["criteria_count"], "mutation_controls": 20, "bound_files": {p: hash_file(ROOT / p) for p in sorted(METHOD_FILES)}, "upstream_frozen_identity": {p: hash_file(ROOT / p) for p in sorted(set(prior_files + list(UPSTREAM)))},
        "components": {cid: {"path": path, "sha256": hash_file(ROOT / path), "status": status} for cid, _t, status, path, _n in COMPONENTS if (ROOT / path).exists()},
        "component_registry": {"path": REGISTRY.relative_to(ROOT).as_posix(), "sha256": hash_file(REGISTRY)}, "unbound_prospective_components": ["CAPSTONE_CLERK_CONNECTED_V1"],
        "freeze_basis": "before the canonical real-Clerk E2E; the connected evaluator, E2E orchestrator/driver, launcher, mutation controls and criteria are frozen here",
        "claim_boundary": "REAL_CLERK_TEST_INSTANCE_INTEGRATION_ONLY",
    }
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": lock["status"], "sha256": hash_file(LOCK), "bound_files": len(lock["bound_files"])}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
