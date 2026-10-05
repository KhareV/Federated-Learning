"""CAP-004 entry/final protection audit (CAP-003 methodology + CAP-003 lock/amendment chain).

``final`` requires zero modification/removal of any tracked file except the explicit allow-list:
the capstone task/gate registries, its lifecycle test, and ONLY the Clerk SDK dependency lines in
pyproject.toml / requirements-dev.lock (verified line-by-line: no existing pin may change).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_002_protected_audit import verify_cap001_lock
from scripts.cap_003_protected_audit import verify_cap002_lock
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_004"
CAP003_LOCK = ROOT / "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json"
EXPECTED_ENTRY = "56fc19f69566fd9ead6b509292449d5cd7540adb"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/", "artifacts/capstone/", "docs/capstone/",
    "contracts/capstone/", "reports/capstone/cap_004/", "product/", "api/product_app_v1_1.py",
    "tests/test_capstone_", "tests/capstone_", "scripts/cap_004_", "scripts/capstone_cap004_",
    "scripts/run_capstone_product.py", "scripts/run_capstone_persistent_e2e.py", ".env.example",
)
# existing tracked files CAP-004 may modify; dependency files are further checked line by line
MODIFIABLE = (
    "manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv",
    "tests/test_capstone_lifecycle.py", "pyproject.toml", "requirements-dev.lock",
)
ALLOWED_DEPENDENCY_ADDITIONS = ("clerk-backend-api==7.0.0", "PyJWT==2.15.1")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def verify_cap003_lock() -> dict:
    lock = json.loads(CAP003_LOCK.read_text())
    expected = {c["path"]: c["sha256"] for c in lock["components"].values()}
    expected.update(lock["bound_files"])
    expected.update(lock["upstream_frozen_identity"])
    chain = []
    for amendment in sorted((ROOT / "artifacts/capstone").glob(
            "CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.amendment_*.json")):
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
    return {"lock": str(CAP003_LOCK.relative_to(ROOT)), "lock_sha256": hash_file(CAP003_LOCK),
            "status": lock["status"], "entries_checked": len(expected) + 1,
            "amendment_chain": chain, "broken_chain_links": broken, "mismatches": mismatches,
            "verified": not mismatches and not broken and len(chain) >= 1}


def dependency_delta(path: str) -> dict:
    """Compare a dependency file with its entry-commit version line by line."""
    before = _git("show", f"{EXPECTED_ENTRY}:{path}").splitlines()
    after = (ROOT / path).read_text().splitlines()
    removed = [ln for ln in before if ln not in after]
    added = [ln for ln in after if ln not in before]
    return {"file": path, "removed_lines": removed, "added_lines": added}


def dependency_files_ok() -> tuple[bool, list[dict]]:
    deltas = [dependency_delta(p) for p in ("pyproject.toml", "requirements-dev.lock")]
    ok = True
    for delta in deltas:
        if delta["removed_lines"]:
            ok = False
        for line in delta["added_lines"]:
            stripped = line.strip().strip(",").strip('"')
            if line.startswith("#") or not stripped:
                continue
            if stripped not in ALLOWED_DEPENDENCY_ADDITIONS:
                ok = False
    return ok, deltas


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
    deps_ok, deltas = dependency_files_ok()
    locks = {"cap001": verify_cap001_lock(), "cap002": verify_cap002_lock(),
             "cap003": verify_cap003_lock()}
    result = {
        "entry_sha": base["entry_sha"], "head_sha": _git("rev-parse", "HEAD"),
        "baseline_file_count": len(before), "modified_since_entry": changed,
        "modified_outside_allowed_control_plane": illegal, "removed_since_entry": removed,
        "added_count": len(added), "added_outside_additive_namespace": non_additive,
        "named_component_drift": comp_drift, "named_components_checked": len(comps),
        "frontend_files_checked": len(base["frontend"]), "frontend_drift": frontend_drift,
        "dependency_file_changes_only_the_approved_clerk_sdk_lines": deps_ok,
        "dependency_deltas": deltas,
        "cap001_lock_verified": locks["cap001"]["verified"],
        "cap002_lock_verified": locks["cap002"]["verified"],
        "cap003_lock_verified": locks["cap003"]["verified"],
        "amendment_chains_verified": not (locks["cap002"]["broken_chain_links"]
                                          or locks["cap003"]["broken_chain_links"]),
        "protected_artifact_drift": bool(
            illegal or removed or non_additive or comp_drift or frontend_drift or not deps_ok
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
        raise SystemExit("usage: cap_004_protected_audit.py entry|final")
