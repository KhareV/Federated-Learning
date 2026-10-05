"""CAP-002 entry/final protection audit (same methodology as CAP-001, plus CAP-001 frozen files).

``entry`` records SHA-256 of every git-tracked file, the CAP-001 frozen components/bound files, the
frozen scientific/runtime component hashes and the frontend tree. ``final`` requires zero
modification/removal of any of them: only brand-new CAP-002 files and the explicit control-plane
transition files may change.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_002"
CAP001_LOCK = ROOT / "artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json"
EXPECTED_ENTRY = "44939378e7aee3baa2e92fefdd42fa9d75640a8a"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/", "artifacts/capstone/", "reports/capstone/cap_002/",
    "product/", "tests/test_capstone_", "tests/capstone_device_support.py", "scripts/cap_002_",
    "scripts/run_capstone_device_demo.py", "scripts/verify_capstone_device_edge.py",
)
# the ONLY already-tracked files CAP-002 may modify (control plane + its lifecycle test)
MODIFIABLE = (
    "manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv",
    "tests/test_capstone_lifecycle.py",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def verify_cap001_lock() -> dict:
    lock = json.loads(CAP001_LOCK.read_text())
    mismatches = []
    checked = 0
    for cid, entry in lock["components"].items():
        checked += 1
        if hash_file(ROOT / entry["path"]) != entry["sha256"]:
            mismatches.append(cid)
    for group in ("bound_files", "upstream_frozen_identity"):
        for path, digest in lock[group].items():
            checked += 1
            if hash_file(ROOT / path) != digest:
                mismatches.append(path)
    registry = lock["component_registry"]
    checked += 1
    if hash_file(ROOT / registry["path"]) != registry["sha256"]:
        mismatches.append(registry["path"])
    return {"lock": str(CAP001_LOCK.relative_to(ROOT)), "lock_sha256": hash_file(CAP001_LOCK),
            "status": lock["status"], "entries_checked": checked, "mismatches": mismatches,
            "verified": not mismatches}


def snapshot() -> dict:
    tree = tracked_hashes()
    lock = json.loads(CAP001_LOCK.read_text())
    return {
        "tracked_file_count": len(tree), "tracked_files_sha256": tree,
        "named_components": named_components(),
        "cap001_frozen": {"components": {k: v["sha256"] for k, v in lock["components"].items()},
                          "bound_files": lock["bound_files"]},
        "frontend": {p: h for p, h in tree.items() if p.startswith("frontend/")},
    }


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
    illegal_changes = [p for p in changed if p not in MODIFIABLE]
    non_additive = [p for p in added if not p.startswith(ADDITIVE_PREFIXES)]
    comps = named_components()
    comp_drift = sorted(k for k, v in comps.items()
                        if base["named_components"][k]["sha256"] != v["sha256"])
    frontend_drift = sorted(p for p, h in base["frontend"].items() if now.get(p) != h)
    cap001 = verify_cap001_lock()
    result = {
        "entry_sha": base["entry_sha"], "head_sha": _git("rev-parse", "HEAD"),
        "baseline_file_count": len(before), "modified_since_entry": changed,
        "modified_outside_allowed_control_plane": illegal_changes, "removed_since_entry": removed,
        "added_count": len(added), "added_outside_additive_namespace": non_additive,
        "named_component_drift": comp_drift, "named_components_checked": len(comps),
        "frontend_files_checked": len(base["frontend"]), "frontend_drift": frontend_drift,
        "cap001_lock_verification": cap001,
        "protected_artifact_drift": bool(illegal_changes or removed or non_additive or comp_drift
                                         or frontend_drift or not cap001["verified"]),
    }
    (OUT / "protected_artifact_final.json").write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "cap001_lock_verification"},
                     indent=1))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        entry()
    elif mode == "final":
        sys.exit(final())
    else:
        raise SystemExit("usage: cap_002_protected_audit.py entry|final")
