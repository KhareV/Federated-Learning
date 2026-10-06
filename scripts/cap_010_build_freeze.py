# ruff: noqa: E501
"""Freeze the CAP-010 faculty-demo method before canonical demo runs and any result evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.cap_008_protected_audit import all_locks

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json"
CONFIG = ROOT / "configs/capstone/cap_010_faculty_demo_protocol_v1.json"
REGISTRY = ROOT / "manifests/capstone/component_registry_cap_010_v1.csv"
ENTRY = ROOT / "reports/capstone/cap_010/entry_audit.json"

METHOD_FILES = (
    "configs/capstone/cap_010_faculty_demo_protocol_v1.json",
    "configs/capstone/cap_010_full_demo_binding_v1.json",
    "docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md",
    "scripts/capstone_demo_preflight.py",
    "scripts/capstone_demo_workspace.py",
    "scripts/run_capstone_faculty_demo.py",
    "scripts/run_capstone_full_demo_e2e.py",
    "scripts/cap_010_cdp_driver.mjs",
    "scripts/cap_010_runbook_audit.py",
    "scripts/cap_010_protected_audit.py",
    "scripts/cap_010_mutation_controls.py",
    "scripts/cap_010_build_freeze.py",
    "scripts/verify_capstone_faculty_demo.py",
    "tests/capstone_demo_support.py",
    "tests/test_capstone_demo_orchestrator.py",
    "tests/test_capstone_demo_preflight.py",
    "tests/test_capstone_demo_workspace.py",
    "tests/test_capstone_full_demo.py",
)
PROTECTED_UPSTREAM = (
    "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json",
    "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json",
    "api/product_app_v1_3.py", "api/product_app_v1_2.py", "capstone_persistence/session_evidence_store.py",
    "capstone_persistence/federation_store.py", "product/federation/service.py", "product/research/service.py",
)
COMPONENTS = (
    ("CAPSTONE_FACULTY_DEMO_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_ENGINEERING_PROTOCOL",
     "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json", "104 consolidated CAPG9 criteria."),
    ("CAPSTONE_FULL_DEMO_BINDING_V1", "DEMO_BINDING", "FROZEN_ENGINEERING_INTERFACE",
     "configs/capstone/cap_010_full_demo_binding_v1.json", "FULL_CAPSTONE_DEMO scenario coverage + hero path binding."),
    ("CAPSTONE_DEMO_PREFLIGHT_V1", "ENGINEERING_IMPLEMENTATION", "FROZEN_ENGINEERING_IMPLEMENTATION",
     "scripts/capstone_demo_preflight.py", "Identity/artifact checks only; no science."),
    ("CAPSTONE_DEMO_WORKSPACE_V1", "ENGINEERING_IMPLEMENTATION", "FROZEN_ENGINEERING_IMPLEMENTATION",
     "scripts/capstone_demo_workspace.py", "Outside-Git workspace with sentinel; safe reset."),
    ("CAPSTONE_DEMO_ORCHESTRATOR_V1", "ENGINEERING_IMPLEMENTATION", "FROZEN_ENGINEERING_IMPLEMENTATION",
     "scripts/run_capstone_faculty_demo.py", "Exactly three services; readiness; reverse-order shutdown."),
    ("CAPSTONE_DEMO_RUNBOOK_V1", "DOCUMENTATION", "FROZEN_ENGINEERING_INTERFACE",
     "docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md", "Short and full paths; claim-audited."),
    ("CAPSTONE_DEMO_READINESS_V1", "READINESS_CLAIM", "PROSPECTIVE_UNTIL_CAPG9",
     "reports/capstone/cap_010/final_handoff.md", "Offline one-laptop faculty demonstration readiness only."),
)


def write_registry() -> None:
    with REGISTRY.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["component_id", "component_type", "owner_task", "status",
                         "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, path, notes in COMPONENTS:
            writer.writerow([cid, ctype, "CAP-010", status, "", path, notes])


def freeze() -> dict[str, object]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if len(config["capg9_criteria"]) != 104:
        raise RuntimeError("CAPG9_CRITERIA_COUNT_MISMATCH")
    LOCK.unlink(missing_ok=True)   # never bind (or verify against) a previous copy of this lock
    prior = all_locks()
    if not all(item["verified"] for item in prior.values()):
        raise RuntimeError("PRIOR_LOCK_CHAIN_FAILED")
    write_registry()
    prior_files = [item["lock"] for item in prior.values() if "lock" in item]
    upstream = {path: hash_file(ROOT / path)
                for path in sorted(set(prior_files + list(PROTECTED_UPSTREAM)))}
    binding = {path: hash_file(ROOT / path) for path in sorted(METHOD_FILES)}
    components = {cid: {"path": path, "sha256": hash_file(ROOT / path), "status": status}
                  for cid, _t, status, path, _n in COMPONENTS if (ROOT / path).exists()}
    lock = {
        "lock_id": "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1",
        "status": "FROZEN_ENGINEERING_PROTOCOL",
        "owner_phase": "CAP-010",
        "gate": "CAPG9",
        "entry_sha": config["entry"]["expected_entry_sha"],
        "entry_audit_sha256": hash_file(ENTRY),
        "prior_locks_verified": sorted(prior),
        "criteria_count": len(config["capg9_criteria"]),
        "mutation_controls": len(config["mutation_controls"]),
        "bound_files": binding,
        "upstream_frozen_identity": upstream,
        "components": components,
        "component_registry": {"path": REGISTRY.relative_to(ROOT).as_posix(), "sha256": hash_file(REGISTRY)},
        "unbound_prospective_components": ["CAPSTONE_DEMO_READINESS_V1"],
        "freeze_basis": "before CAP-010 canonical demo runs and gate-result execution",
        "claim_boundary": "OFFLINE_ONE_LAPTOP_FACULTY_DEMONSTRATION_READINESS_ONLY",
    }
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": lock["status"], "sha256": hash_file(LOCK), "bound_files": len(binding)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
