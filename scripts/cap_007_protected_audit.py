# ruff: noqa: E501
"""CAP-007 entry/final protection audit (strict). Every tracked file present at entry must be
byte-identical at final except the explicit control-plane allow-list; every NEW file must live in an
explicit CAP-007 additive namespace (no blanket 'anything under product/')."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_006_protected_audit import all_locks as locks_001_005
from scripts.cap_006_protected_audit import verify_amended_lock
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_007"
CAP006_LOCK = ROOT / "artifacts/capstone/CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1.lock.json"
EXPECTED_ENTRY = "651bfa61022cf699a43c0a91cbc43a6486943bc"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/", "artifacts/capstone/", "docs/capstone/",
    "contracts/capstone/", "reports/capstone/cap_007/", "tests/test_capstone_", "tests/capstone_",
    "scripts/cap_007_", "scripts/run_capstone_product_v1_2.py", "scripts/run_capstone_federation.py",
    "scripts/verify_capstone_federation.py",
    "product/federation/client_v2.py", "product/federation/service.py", "product/federation/events.py",
    "product/federation/journal.py", "product/federation/recovery.py",
    "product/federation/execution_binding.py", "product/federation/artifact_store.py",
    "product/federation/secagg_shadow.py", "product/federation/replay.py",
    "product/models/", "capstone_persistence/federation_store.py", "api/product_app_v1_2.py",
)
MODIFIABLE = (
    "manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv",
    "tests/test_capstone_lifecycle.py",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def _hash_map_lock(path: Path, key: str) -> dict:
    lock = json.loads(path.read_text())
    bad = [p for p, d in lock[key].items() if hash_file(ROOT / p) != d]
    return {"lock": str(path.relative_to(ROOT)), "entries_checked": len(lock[key]),
            "mismatches": bad, "broken_chain_links": [], "verified": not bad}


def fl_locks() -> dict:
    fl = _hash_map_lock(ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json",
                        "bound_artifacts")
    mu = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
    init = json.loads((ROOT / "reports/model_v2/v2_fl_005/federation_run.json").read_text())
    return {
        "v2_fl_wearable_system": fl,
        "fedprox_mu_v2": {"selected_mu": mu["selected_mu"], "broken_chain_links": [],
                          "verified": mu["selected_mu"] == 0.1},
        "fl_init_v2": {"broken_chain_links": [], "verified": init["state_progression"]["0"][
            "sha256" if "sha256" in init["state_progression"]["0"] else "global_state_sha256"]
            == mu["FL_INIT_V2_round_0_state_sha256"]},
    }


def all_locks() -> dict:
    locks = locks_001_005()
    locks["cap006"] = verify_amended_lock(
        CAP006_LOCK, "CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1.amendment_*.json")
    locks.update(fl_locks())
    return locks


def snapshot() -> dict:
    tree = tracked_hashes()
    return {"tracked_file_count": len(tree), "tracked_files_sha256": tree,
            "named_components": named_components(),
            "frontend": {p: h for p, h in tree.items() if p.startswith("frontend/")}}


def entry() -> None:
    snap = snapshot()
    snap["entry_sha"] = _git("rev-parse", "HEAD")
    snap["expected_entry_sha_prefix"] = EXPECTED_ENTRY
    (OUT / "protected_artifact_entry.json").write_text(
        json.dumps(snap, indent=1, sort_keys=True) + "\n")
    locks = all_locks()
    (OUT / "prior_lock_verification.json").write_text(
        json.dumps(locks, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"entry_sha": snap["entry_sha"], "tracked": snap["tracked_file_count"],
                      "locks": {k: v["verified"] for k, v in locks.items()}}))


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
    result = {
        "entry_sha": base["entry_sha"], "head_sha": _git("rev-parse", "HEAD"),
        "baseline_file_count": len(before), "modified_since_entry": changed,
        "modified_outside_allowed_control_plane": illegal, "removed_since_entry": removed,
        "added_count": len(added), "added_outside_additive_namespace": non_additive,
        "named_component_drift": comp_drift, "named_components_checked": len(comps),
        "frontend_files_checked": len(base["frontend"]), "frontend_drift": fe_drift,
        "released_runtime_untouched": not [p for p in changed + removed if p.startswith((
            "api/", "src/", "checkpoints/", "simulation/", "federated/", "privacy/",
            "capstone_persistence/store.py", "reports/model_v2/", "product/monitoring/",
            "product/persistence/", "product/auth/", "product/sessions/"))],
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
        raise SystemExit("usage: cap_007_protected_audit.py entry|final")
