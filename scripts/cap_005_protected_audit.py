"""CAP-005 entry/final protection audit.

The frontend is now legitimately mutable (CAP-005 owns it): its baseline is recorded at entry and
reported as a diff at final, but it is NOT counted as drift. Everything else is protected: only the
capstone task/gate registries and the lifecycle test may change; new files must be additive.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_002_protected_audit import verify_cap001_lock
from scripts.cap_003_protected_audit import verify_cap002_lock
from scripts.cap_004_protected_audit import verify_cap003_lock
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_005"
CAP004_LOCK = ROOT / "artifacts/capstone/CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.lock.json"
EXPECTED_ENTRY = "9db76b482678114ac5c22f3f91a3f55ccb159e17"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/", "artifacts/capstone/", "docs/capstone/",
    "contracts/capstone/", "reports/capstone/cap_005/", "tests/test_capstone_", "tests/capstone_",
    "scripts/cap_005_", "scripts/run_capstone_frontend_e2e.py", "scripts/verify_capstone_ui_v1.py",
    "frontend/",
)
# existing tracked non-frontend files CAP-005 may modify
MODIFIABLE = (
    "manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv",
    "tests/test_capstone_lifecycle.py",
    # DASHBOARD_UI_V1_5 supersession (same mechanism as V1_1..V1_5): predecessor-lock tests
    "tests/test_t035_lock_versioning.py", "tests/test_v2_rel_001_results.py",
    # CAPSTONE_PRODUCT_PROTOCOL_V1 amendment 1 / CAPSTONE_DEVICE_EDGE_PROTOCOL_V1 amendment 4
    "tests/test_capstone_federation_contracts.py", "scripts/cap_002_protected_audit.py",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def verify_cap004_lock() -> dict:
    lock = json.loads(CAP004_LOCK.read_text())
    expected = {**lock["bound_files"], **lock["upstream_frozen_identity"]}
    expected.update({c["path"]: c["sha256"] for c in lock["components"].values()})
    registry = dict(lock["component_registry"])
    chain = []
    for amendment in sorted((ROOT / "artifacts/capstone").glob(
            "CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.amendment_*.json")):
        data = json.loads(amendment.read_text())
        for path, change in data["files"].items():
            chain.append({"amendment": amendment.name, "path": path,
                          "old_matches_previous_link": expected.get(path) == change["old_sha256"]})
            expected[path] = change["new_sha256"]
        for path, move in data.get("moved_files", {}).items():
            chain.append({"amendment": amendment.name, "path": path, "moved_to": move["to"],
                          "old_matches_previous_link": expected.pop(path, None)
                          == move["old_sha256"]})
            expected[move["to"]] = move["new_sha256"]
        expected.update(data.get("added_files", {}))
        if "component_registry" in data:
            chain.append({"amendment": amendment.name, "path": registry["path"],
                          "old_matches_previous_link": registry["sha256"] == data[
                              "component_registry"]["old_sha256"]})
            registry["sha256"] = data["component_registry"]["new_sha256"]
    mismatches = [p for p, d in expected.items() if hash_file(ROOT / p) != d]
    if hash_file(ROOT / registry["path"]) != registry["sha256"]:
        mismatches.append(registry["path"])
    broken = [c for c in chain if not c["old_matches_previous_link"]]
    return {"lock": str(CAP004_LOCK.relative_to(ROOT)), "lock_sha256": hash_file(CAP004_LOCK),
            "status": lock["status"], "entries_checked": len(expected) + 1,
            "amendment_chain": chain, "broken_chain_links": broken, "mismatches": mismatches,
            "amendments": len(list((ROOT / "artifacts/capstone").glob(
                "CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.amendment_*.json"))),
            "verified": not mismatches and not broken and len(chain) >= 1}


def all_locks() -> dict:
    return {"cap001": verify_cap001_lock(), "cap002": verify_cap002_lock(),
            "cap003": verify_cap003_lock(), "cap004": verify_cap004_lock()}


def snapshot() -> dict:
    tree = tracked_hashes()
    return {"tracked_file_count": len(tree), "tracked_files_sha256": tree,
            "named_components": named_components(),
            "frontend": {p: h for p, h in tree.items() if p.startswith("frontend/")}}


def entry() -> None:
    snap = snapshot()
    snap["entry_sha"] = _git("rev-parse", "HEAD")
    snap["expected_entry_sha"] = EXPECTED_ENTRY
    (OUT / "protected_artifact_entry.json").write_text(
        json.dumps(snap, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"entry_sha": snap["entry_sha"], "tracked": snap["tracked_file_count"],
                      "frontend_files": len(snap["frontend"])}))


def final() -> int:
    base = json.loads((OUT / "protected_artifact_entry.json").read_text())
    now = tracked_hashes()
    before = base["tracked_files_sha256"]
    nonfront = {p: h for p, h in before.items() if not p.startswith("frontend/")}
    changed = sorted(p for p, h in nonfront.items() if p in now and now[p] != h)
    removed = sorted(p for p in nonfront if p not in now)
    added = sorted(p for p in now if p not in before)
    illegal = [p for p in changed if p not in MODIFIABLE]
    non_additive = [p for p in added if not p.startswith(ADDITIVE_PREFIXES)]
    comps = named_components()
    comp_drift = sorted(k for k, v in comps.items()
                        if base["named_components"][k]["sha256"] != v["sha256"])
    fe_before = base["frontend"]
    fe_changed = sorted(p for p, h in fe_before.items() if p in now and now[p] != h)
    fe_removed = sorted(p for p in fe_before if p not in now)
    fe_added = sorted(p for p in now if p.startswith("frontend/") and p not in fe_before)
    locks = all_locks()
    result = {
        "entry_sha": base["entry_sha"], "head_sha": _git("rev-parse", "HEAD"),
        "baseline_file_count": len(before), "nonfrontend_files_checked": len(nonfront),
        "modified_since_entry": changed, "modified_outside_allowed_control_plane": illegal,
        "removed_since_entry": removed, "added_count": len(added),
        "added_outside_additive_namespace": non_additive, "named_component_drift": comp_drift,
        "named_components_checked": len(comps),
        "frontend_baseline_files": len(fe_before), "frontend_modified": fe_changed,
        "frontend_removed": fe_removed, "frontend_added_count": len(fe_added),
        "backend_dirs_untouched": not [p for p in changed + removed if p.startswith((
            "api/", "product/", "capstone_persistence/", "simulation/", "src/", "checkpoints/"))],
        "cap001_lock_verified": locks["cap001"]["verified"],
        "cap002_lock_verified": locks["cap002"]["verified"],
        "cap003_lock_verified": locks["cap003"]["verified"],
        "cap004_lock_verified": locks["cap004"]["verified"],
        "amendment_chains_verified": not any(
            locks[k].get("broken_chain_links") for k in ("cap001", "cap002", "cap003", "cap004")),
        "protected_artifact_drift": bool(
            illegal or removed or non_additive or comp_drift
            or not all(v["verified"] for v in locks.values())),
    }
    (OUT / "protected_artifact_final.json").write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "frontend_modified"}, indent=1))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        entry()
    elif mode == "final":
        sys.exit(final())
    else:
        raise SystemExit("usage: cap_005_protected_audit.py entry|final")
