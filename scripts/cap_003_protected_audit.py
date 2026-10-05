"""CAP-003 entry/final protection audit (CAP-001/CAP-002 methodology + CAP-002 amendment chain).

``entry`` records SHA-256 of every tracked file, the CAP-001 and CAP-002 frozen files, named frozen
components and the frontend tree. ``final`` requires zero modification/removal of any of them: only
brand-new CAP-003 files and the explicit control-plane transition files may change.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_002_protected_audit import verify_cap001_lock
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_003"
CAP002_LOCK = ROOT / "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json"
EXPECTED_ENTRY = "9f49b0c52fd93f7a28aff9ef67407fa9c56976df"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/", "artifacts/capstone/", "docs/capstone/",
    "reports/capstone/cap_003/", "product/", "api/product_app.py", "tests/test_capstone_",
    "tests/capstone_", "scripts/cap_003_", "scripts/capstone_cap003_",
    "scripts/run_capstone_monitoring_e2e.py", "scripts/verify_capstone_monitoring.py",
)
# the ONLY already-tracked files CAP-003 may modify (control plane + its lifecycle test)
MODIFIABLE = (
    "manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv",
    "tests/test_capstone_lifecycle.py",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def verify_cap002_lock() -> dict:
    """Verify the CAP-002 lock INCLUDING the full amendment hash chain."""
    lock = json.loads(CAP002_LOCK.read_text())
    expected = {c["path"]: c["sha256"] for c in lock["components"].values()}
    expected.update(lock["bound_files"])
    expected.update(lock["upstream_frozen_identity"])
    chain = []
    for amendment in sorted((ROOT / "artifacts/capstone").glob(
            "CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.amendment_*.json")):
        data = json.loads(amendment.read_text())
        for path, change in data["files"].items():
            chain.append({"amendment": amendment.name, "path": path,
                          "old_matches_previous_link": expected.get(path) == change["old_sha256"]})
            expected[path] = change["new_sha256"]
    mismatches = [p for p, d in expected.items() if hash_file(ROOT / p) != d]
    registry = lock["component_registry"]
    if hash_file(ROOT / registry["path"]) != registry["sha256"]:
        mismatches.append(registry["path"])
    broken = [c for c in chain if not c["old_matches_previous_link"]]
    return {"lock": str(CAP002_LOCK.relative_to(ROOT)), "lock_sha256": hash_file(CAP002_LOCK),
            "status": lock["status"], "entries_checked": len(expected) + 1,
            "amendment_chain": chain, "broken_chain_links": broken, "mismatches": mismatches,
            "verified": not mismatches and not broken and len(chain) >= 1}


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
    changed = sorted(p for p, h in before.items() if p in now and now[p] != h)
    removed = sorted(p for p in before if p not in now)
    added = sorted(p for p in now if p not in before)
    illegal = [p for p in changed if p not in MODIFIABLE]
    non_additive = [p for p in added if not p.startswith(ADDITIVE_PREFIXES)]
    comps = named_components()
    comp_drift = sorted(k for k, v in comps.items()
                        if base["named_components"][k]["sha256"] != v["sha256"])
    frontend_drift = sorted(p for p, h in base["frontend"].items() if now.get(p) != h)
    lock1, lock2 = verify_cap001_lock(), verify_cap002_lock()
    result = {
        "entry_sha": base["entry_sha"], "head_sha": _git("rev-parse", "HEAD"),
        "baseline_file_count": len(before), "modified_since_entry": changed,
        "modified_outside_allowed_control_plane": illegal, "removed_since_entry": removed,
        "added_count": len(added), "added_outside_additive_namespace": non_additive,
        "named_component_drift": comp_drift, "named_components_checked": len(comps),
        "frontend_files_checked": len(base["frontend"]), "frontend_drift": frontend_drift,
        "cap001_lock_verified": lock1["verified"], "cap002_lock_verified": lock2["verified"],
        "cap002_amendment_chain_verified": not lock2["broken_chain_links"],
        "protected_artifact_drift": bool(illegal or removed or non_additive or comp_drift
                                         or frontend_drift or not lock1["verified"]
                                         or not lock2["verified"]),
    }
    (OUT / "protected_artifact_final.json").write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps(result, indent=1))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        entry()
    elif mode == "final":
        sys.exit(final())
    else:
        raise SystemExit("usage: cap_003_protected_audit.py entry|final")
