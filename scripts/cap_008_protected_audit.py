# ruff: noqa: E501
"""CAP-008 entry/final protection audit. Backend, scientific, FL, CAP-006 and CAP-007 files are byte-identical
to the entry commit; the frontend may change ONLY through the CAPSTONE_UI_V1_1 successor (every changed or
added frontend file must be bound by that lock). New non-frontend files only in explicit CAP-008 namespaces."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_006_protected_audit import verify_amended_lock
from scripts.cap_007_protected_audit import all_locks as locks_to_cap007
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_008"
UI_V1_1_LOCK = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json"
UX_LOCK = ROOT / "artifacts/capstone/CAPSTONE_FEDERATION_UX_PROTOCOL_V1.lock.json"
EXPECTED_ENTRY = "711a4a0a1233765d6f1200fc2b6d8f3aa62d4743"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/", "artifacts/capstone/", "docs/capstone/",
    "reports/capstone/cap_008/", "tests/test_capstone_", "tests/capstone_", "scripts/cap_008_",
    "scripts/run_capstone_federation_ui_e2e.py", "scripts/verify_capstone_ui_v1_1.py",
    "frontend/",
)
MODIFIABLE = (
    "manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv",
    "tests/test_capstone_lifecycle.py",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def all_locks() -> dict:
    locks = locks_to_cap007()
    if UI_V1_1_LOCK.exists():
        from scripts.verify_capstone_ui_v1_1 import verify as verify_ui11
        r = verify_ui11()
        locks["capstone_ui_v1_1"] = {"verified": r["status"] == "PASS", **r, "broken_chain_links": []}
    if UX_LOCK.exists():
        locks["cap008"] = verify_amended_lock(UX_LOCK, "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_*.json")
        locks["cap008"]["verified"] = not locks["cap008"]["mismatches"] and not locks["cap008"]["broken_chain_links"]
    return locks


def snapshot() -> dict:
    tree = tracked_hashes()
    return {"tracked_file_count": len(tree), "tracked_files_sha256": tree, "named_components": named_components(),
            "frontend": {p: h for p, h in tree.items() if p.startswith("frontend/")}}


def entry() -> None:
    snap = snapshot()
    snap["entry_sha"] = _git("rev-parse", "HEAD")
    snap["expected_entry_sha"] = EXPECTED_ENTRY
    (OUT / "protected_artifact_entry.json").write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n")
    locks = all_locks()
    (OUT / "prior_lock_verification.json").write_text(json.dumps(locks, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"entry_sha": snap["entry_sha"], "tracked": snap["tracked_file_count"], "frontend_files": len(snap["frontend"]),
                      "locks": {k: v["verified"] for k, v in locks.items()}}))


def final() -> int:
    base = json.loads((OUT / "protected_artifact_entry.json").read_text())
    now = tracked_hashes()
    before = base["tracked_files_sha256"]
    changed = sorted(p for p, h in before.items() if p in now and now[p] != h)
    removed = sorted(p for p in before if p not in now)
    added = sorted(p for p in now if p not in before)
    nonfe_changed = [p for p in changed if not p.startswith("frontend/")]
    illegal = [p for p in nonfe_changed if p not in MODIFIABLE and p not in AMENDED_HISTORICAL]
    non_additive = [p for p in added if not p.startswith(ADDITIVE_PREFIXES)]
    comps = named_components()
    comp_drift = sorted(k for k, v in comps.items() if base["named_components"][k]["sha256"] != v["sha256"])
    ui = json.loads(UI_V1_1_LOCK.read_text())["bound_artifacts"] if UI_V1_1_LOCK.exists() else {}
    fe_changed = sorted(p for p in changed + added if p.startswith("frontend/"))
    fe_removed = sorted(p for p in removed if p.startswith("frontend/"))
    unaccounted = [p for p in fe_changed if p not in ui or hash_file(ROOT / p) != ui[p]]
    locks = all_locks()
    protected = ("api/", "src/", "checkpoints/", "simulation/", "federated/", "privacy/", "capstone_persistence/", "product/", "reports/model_v2/", "contracts/")
    result = {
        "entry_sha": base["entry_sha"], "head_sha": _git("rev-parse", "HEAD"), "baseline_file_count": len(before),
        "modified_since_entry_non_frontend": nonfe_changed, "modified_outside_allowed": illegal, "removed_since_entry": removed,
        "added_count": len(added), "added_outside_additive_namespace": non_additive, "named_component_drift": comp_drift,
        "named_components_checked": len(comps), "frontend_changed_or_added": len(fe_changed), "frontend_removed": fe_removed,
        "frontend_unaccounted_drift": unaccounted,
        "backend_scientific_fl_cap006_cap007_untouched": not [p for p in changed + removed if p.startswith(protected)],
        "locks_verified": {k: v["verified"] for k, v in locks.items()},
        "amendment_chains_verified": not any(v.get("broken_chain_links") for v in locks.values()),
        "protected_artifact_drift": bool(illegal or removed or non_additive or comp_drift or unaccounted or fe_removed
                                         or [p for p in changed + removed if p.startswith(protected)]
                                         or not all(v["verified"] for k, v in locks.items() if k != "capstone_ui_v1")),
    }
    (OUT / "protected_artifact_final.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps(result, indent=1))
    return 1 if result["protected_artifact_drift"] else 0


# historical guard tests amended through recorded amendments (CAP-008)
AMENDED_HISTORICAL = ("tests/test_capstone_frontend.py",)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    entry() if mode == "entry" else sys.exit(final()) if mode == "final" else sys.exit("usage: entry|final")
