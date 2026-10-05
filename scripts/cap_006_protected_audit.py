# ruff: noqa: E501
"""CAP-006 entry/final protection audit. Unlike CAP-005, the frontend is PROTECTED again: every tracked
file present at entry must be byte-identical at final except the explicit allow-list (capstone registries and
the lifecycle test); every new file must live in an additive CAP-006 namespace."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_005_protected_audit import all_locks as locks_001_004
from scripts.verify_capstone_ui_v1 import verify as verify_ui
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_006"
CAP005_LOCK = ROOT / "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json"
EXPECTED_ENTRY = "b8a6c70ed6b77a38273cb8bdb6659452dfe26f83"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/", "artifacts/capstone/", "docs/capstone/",
    "reports/capstone/cap_006/", "tests/test_capstone_", "tests/capstone_", "scripts/cap_006_",
    "scripts/run_capstone_local_training.py", "scripts/verify_capstone_local_training.py",
    "product/edge/label_adapter.py", "product/edge/local_training_buffer.py",
    "product/federation/client.py", "product/federation/update_bridge.py",
    "product/federation/local_cohort.py",
)
MODIFIABLE = (
    "manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv",
    "tests/test_capstone_lifecycle.py",
    "tests/test_capstone_frontend.py",  # CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1 amendment 6 (CAP-006 adds files)
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def verify_amended_lock(lock_path: Path, glob: str) -> dict:
    lock = json.loads(lock_path.read_text())
    expected = {**lock["bound_files"], **lock["upstream_frozen_identity"]}
    expected.update({c["path"]: c["sha256"] for c in lock["components"].values()})
    registry = dict(lock["component_registry"])
    chain = []
    for amendment in sorted((ROOT / "artifacts/capstone").glob(glob)):
        data = json.loads(amendment.read_text())
        for path, change in data["files"].items():
            chain.append({"amendment": amendment.name, "path": path,
                          "old_matches_previous_link": expected.get(path) == change["old_sha256"]})
            expected[path] = change["new_sha256"]
        expected.update(data.get("added_files", {}))
        if "component_registry" in data:
            registry["sha256"] = data["component_registry"]["new_sha256"]
    mismatches = [p for p, d in expected.items() if hash_file(ROOT / p) != d]
    if hash_file(ROOT / registry["path"]) != registry["sha256"]:
        mismatches.append(registry["path"])
    broken = [c for c in chain if not c["old_matches_previous_link"]]
    return {"lock": str(lock_path.relative_to(ROOT)), "lock_sha256": hash_file(lock_path),
            "entries_checked": len(expected) + 1, "amendment_chain": chain,
            "broken_chain_links": broken, "mismatches": mismatches,
            "amendments": len({c["amendment"] for c in chain}),
            "verified": not mismatches and not broken and len(chain) >= 1}


def all_locks() -> dict:
    locks = locks_001_004()
    locks["cap005"] = verify_amended_lock(
        CAP005_LOCK, "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_*.json")
    ui = verify_ui()
    locks["capstone_ui_v1"] = {"verified": ui["status"] == "PASS", **ui, "broken_chain_links": []}
    return locks


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
    fe_drift = sorted(p for p, h in base["frontend"].items() if now.get(p) != h)
    locks = all_locks()
    protected_prefixes = ("api/", "product/api/", "product/monitoring/", "product/auth/",
                          "product/persistence/", "product/sessions/", "capstone_persistence/",
                          "simulation/", "src/", "checkpoints/", "federated/", "privacy/")
    result = {
        "entry_sha": base["entry_sha"], "head_sha": _git("rev-parse", "HEAD"),
        "baseline_file_count": len(before), "modified_since_entry": changed,
        "modified_outside_allowed_control_plane": illegal, "removed_since_entry": removed,
        "added_count": len(added), "added_outside_additive_namespace": non_additive,
        "named_component_drift": comp_drift, "named_components_checked": len(comps),
        "frontend_files_checked": len(base["frontend"]), "frontend_drift": fe_drift,
        "backend_and_fl_dirs_untouched": not [p for p in changed + removed
                                              if p.startswith(protected_prefixes)],
        "v2_fl_evidence_unchanged": not [p for p in changed + removed
                                         if p.startswith("reports/model_v2/")],
        "locks_verified": {k: v["verified"] for k, v in locks.items()},
        "amendment_chains_verified": not any(v.get("broken_chain_links") for v in locks.values()),
        "protected_artifact_drift": bool(
            illegal or removed or non_additive or comp_drift or fe_drift
            or not all(v["verified"] for v in locks.values())),
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
        raise SystemExit("usage: cap_006_protected_audit.py entry|final")
