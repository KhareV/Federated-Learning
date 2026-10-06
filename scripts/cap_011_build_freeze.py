# ruff: noqa: E501
"""Freeze the CAP-011 release layer (lock + component registry) BEFORE the release-target commit and any clean clone."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.cap_011_protected_audit import all_locks

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/capstone/CAPSTONE_RELEASE_PROTOCOL_V1.lock.json"
REGISTRY = ROOT / "manifests/capstone/component_registry_cap_011_v1.csv"
CONFIG = ROOT / "configs/capstone/cap_011_release_protocol_v1.json"
ENTRY = ROOT / "reports/capstone/cap_011/entry_audit.json"
METHOD_FILES = (
    "configs/capstone/cap_011_release_policy_v1.json", "configs/capstone/cap_011_clean_clone_protocol_v1.json", "configs/capstone/cap_011_release_protocol_v1.json",
    "artifacts/capstone/CAPSTONE_RELEASE_MANIFEST_V1.json", "docs/capstone/CAPSTONE_RELEASE_GUIDE_V1.md",
    "scripts/capstone_release_lib.py", "scripts/verify_capstone_release_v1.py", "scripts/run_capstone_clean_release.py", "scripts/cap_011_evaluate_gate.py", "scripts/cap_011_mutation_controls.py",
    "scripts/cap_011_build_manifest.py", "scripts/cap_011_build_freeze.py", "scripts/cap_011_protected_audit.py", "scripts/cap_011_test_report.py", "scripts/cap_011_build_evidence.py",
    "tests/test_capstone_release_lib.py", "tests/test_capstone_release_harness.py", "tests/test_capstone_release_guide.py", "tests/test_capstone_release_target.py",
)
COMPONENTS = (
    ("CAPSTONE_RELEASE_PROTOCOL_V1", "ENGINEERING_PROTOCOL", "FROZEN_PRE_RELEASE_PROTOCOL", "configs/capstone/cap_011_release_protocol_v1.json", "136 CAPG10 criteria, 20 mutation controls; lock binds the whole release layer."),
    ("CAPSTONE_RELEASE_POLICY_V1", "RELEASE_POLICY", "FROZEN_PRE_RELEASE_POLICY", "configs/capstone/cap_011_release_policy_v1.json", "23 hard blockers; manual_override_allowed=false; claim, limitations, test gating."),
    ("CAPSTONE_CLEAN_CLONE_PROTOCOL_V1", "CLEAN_CLONE_PROTOCOL", "FROZEN_PRE_RELEASE_PROTOCOL", "configs/capstone/cap_011_clean_clone_protocol_v1.json", "Remote-only source, prohibitions, ordered command set."),
    ("CAPSTONE_RELEASE_MANIFEST_V1", "RELEASE_MANIFEST", "FROZEN_PRE_RELEASE_MANIFEST", "artifacts/capstone/CAPSTONE_RELEASE_MANIFEST_V1.json", "Key artifact and dependency-lock hashes; no model bytes."),
    ("CAPSTONE_RELEASE_VERIFIER_V1", "RELEASE_VERIFIER", "FROZEN_ENGINEERING_IMPLEMENTATION", "scripts/verify_capstone_release_v1.py", "No training/inference/FL/science; library in capstone_release_lib.py."),
    ("CAPSTONE_RELEASE_GUIDE_V1", "DOCUMENTATION", "FROZEN_PRE_RELEASE_GUIDE", "docs/capstone/CAPSTONE_RELEASE_GUIDE_V1.md", "Commands equal the tested clean-clone commands."),
    ("CAPSTONE_RELEASE_V1", "RELEASE", "PROSPECTIVE_UNTIL_CAPG10", "reports/capstone/cap_011/release_decision.json", "The release is the exact RELEASE_TARGET_SHA; decision recorded as evidence only."),
)
PROTECTED_UPSTREAM = (
    "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json", "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json",
    "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/ROLLBACK_RUNTIME_BINDING_V1.lock.json", "api/product_app_v1_3.py",
    "scripts/run_capstone_faculty_demo.py", "scripts/capstone_demo_preflight.py", "requirements-dev.lock", "requirements-capstone-auth.lock", "pyproject.toml", "frontend/package-lock.json", "frontend/clerk-sdk/package-lock.json",
)


def write_registry() -> None:
    with REGISTRY.open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle, lineterminator="\n")
        w.writerow(["component_id", "component_type", "owner_task", "status", "predecessor_id", "lock_path", "notes"])
        for cid, ctype, status, path, notes in COMPONENTS:
            w.writerow([cid, ctype, "CAP-011", status, "", path, notes])


def freeze() -> dict[str, object]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if len(config["capg10_criteria"]) != 136 or len(config["mutation_controls"]) != 20:
        raise RuntimeError("CAPG10_PROTOCOL_COUNT_MISMATCH")
    LOCK.unlink(missing_ok=True)
    prior = all_locks()
    if not all(item["verified"] for item in prior.values()):
        raise RuntimeError("PRIOR_LOCK_CHAIN_FAILED")
    write_registry()
    prior_files = [item["lock"] for item in prior.values() if "lock" in item]
    upstream = {p: hash_file(ROOT / p) for p in sorted(set(prior_files + list(PROTECTED_UPSTREAM)))}
    lock = {
        "lock_id": "CAPSTONE_RELEASE_PROTOCOL_V1", "status": "FROZEN_PRE_RELEASE_PROTOCOL", "owner_phase": "CAP-011", "gate": "CAPG10", "entry_sha": config["entry"]["entry_sha"],
        "entry_audit_sha256": hash_file(ENTRY), "prior_locks_verified": sorted(prior), "criteria_count": 136, "mutation_controls": 20, "hard_blockers": 23,
        "bound_files": {p: hash_file(ROOT / p) for p in sorted(METHOD_FILES)}, "upstream_frozen_identity": upstream,
        "components": {cid: {"path": path, "sha256": hash_file(ROOT / path), "status": status} for cid, _t, status, path, _n in COMPONENTS if (ROOT / path).exists()},
        "component_registry": {"path": REGISTRY.relative_to(ROOT).as_posix(), "sha256": hash_file(REGISTRY)}, "unbound_prospective_components": ["CAPSTONE_RELEASE_V1"],
        "freeze_basis": "before the RELEASE_TARGET commit and any canonical clean clone; the clean-clone harness, the CAPG10 evaluator, the verifier and the criteria are frozen here",
        "claim_boundary": "CLEAN_CLONE_SOFTWARE_ARTIFACT_PRODUCT_DEMO_REPRODUCIBILITY_ONE_LAPTOP",
    }
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": lock["status"], "sha256": hash_file(LOCK), "bound_files": len(lock["bound_files"]), "upstream": len(upstream)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
