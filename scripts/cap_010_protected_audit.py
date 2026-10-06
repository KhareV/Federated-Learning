"""CAP-010 entry/final protection audit. CAP-010 is integration/demonstration only: every file tracked at
entry must be byte-identical at final except the control-plane registries and the lifecycle test; every new
file must live in an explicit CAP-010 additive namespace. Frontend, API, backend and FL are protected."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_006_protected_audit import verify_amended_lock
from scripts.cap_008_protected_audit import all_locks as locks_to_cap008
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_010"
ENTRY = "be778d4ced186639155064e94516ff096751a81f"
CAP010_LOCK = ROOT / "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/cap_010_", "artifacts/capstone/", "docs/capstone/",
    "reports/capstone/cap_010/", "scripts/cap_010_", "scripts/run_capstone_faculty_demo.py",
    "scripts/capstone_demo_", "scripts/verify_capstone_faculty_demo.py", "scripts/run_capstone_full_demo_e2e.py",
    "tests/test_capstone_demo_", "tests/test_capstone_full_demo.py", "tests/capstone_demo_",
)
MODIFIABLE = ("manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv",
              "tests/test_capstone_lifecycle.py")
PROTECTED_PREFIXES = ("api/", "product/", "capstone_persistence/", "federated/", "privacy/", "simulation/", "src/",
                      "checkpoints/", "contracts/", "frontend/", "reports/model_v2/", "reports/capstone/cap_00")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def statuses() -> dict[str, dict[str, str]]:
    out = {}
    for name, key in (("task", "task_id"), ("gate", "gate_id")):
        with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
            out[name] = {r[key]: r["status"] for r in csv.DictReader(h)}
    return out


def all_locks() -> dict:
    from scripts.verify_capstone_history_evidence_protocol_v1 import verify as verify_history
    from scripts.verify_capstone_research_evidence_catalog import verify as verify_catalog
    from scripts.verify_capstone_ui_v1_2 import verify as verify_ui12

    locks = locks_to_cap008()
    h = verify_history()
    locks["cap009"] = {"verified": h["status"] == "PASS", **h, "broken_chain_links": []}
    locks["capstone_ui_v1_2"] = {"verified": verify_ui12()["status"] == "PASS", "broken_chain_links": []}
    locks["research_catalog"] = {"verified": verify_catalog()["status"] == "PASS", "broken_chain_links": []}
    if CAP010_LOCK.exists():
        r = verify_amended_lock(CAP010_LOCK, "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_*.json")
        r["verified"] = not r["mismatches"] and not r["broken_chain_links"]
        locks["cap010"] = r
    return locks


def entry() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    dirty = [l for l in git("status", "--porcelain").splitlines() if "cap_010" not in l]
    if head != ENTRY or origin != head or dirty:
        raise RuntimeError("CAP010_ENTRY_STATE_CONFLICT")
    st = statuses()
    exp_t = {f"CAP-{i:03d}": "PASS" for i in range(1, 10)} | {"CAP-010": "NOT_STARTED", "CAP-011": "NOT_STARTED"}
    exp_g = {f"CAPG{i}": "PASS" for i in range(9)}
    if any(st["task"].get(k) != v for k, v in exp_t.items()) or any(st["gate"].get(k) != v for k, v in exp_g.items()):
        raise RuntimeError("CAP010_STATUS_CONFLICT")
    locks = all_locks()
    if not all(v["verified"] for v in locks.values()):
        raise RuntimeError("CAP010_PRIOR_LOCK_FAILURE")
    files, comps = tracked_hashes(), named_components()
    audit = {"phase": "CAP-010", "gate": "CAPG9", "entry_sha": head, "origin_main_sha": origin, "expected_entry_sha": ENTRY,
             "working_tree_clean_before_entry": True, "intervening_commits": [], "prior_tasks": exp_t, "prior_gates": exp_g,
             "cap_011_not_started": True, "prior_locks_verified": True, "locks": sorted(locks), "protected_tracked_file_count": len(files),
             "ci_queried": False, "ci_triggered": False}
    snap = {"entry_sha": head, "tracked_file_count": len(files), "tracked_files_sha256": files, "named_components": comps,
            "frontend": {p: d for p, d in files.items() if p.startswith("frontend/")}}
    for name, value in (("entry_audit.json", audit), ("protected_artifact_entry.json", snap), ("prior_lock_verification.json", locks)):
        (OUT / name).write_text(json.dumps(value, sort_keys=True, indent=1, default=str) + "\n", encoding="utf-8")
    return {"entry_sha": head, "tracked": len(files), "locks": {k: v["verified"] for k, v in locks.items()}}


def final() -> int:
    base = json.loads((OUT / "protected_artifact_entry.json").read_text())
    now, before = tracked_hashes(), base["tracked_files_sha256"]
    changed = sorted(p for p, h in before.items() if p in now and now[p] != h)
    removed = sorted(p for p in before if p not in now)
    added = sorted(p for p in now if p not in before)
    illegal = [p for p in changed if p not in MODIFIABLE]
    non_additive = [p for p in added if not p.startswith(ADDITIVE_PREFIXES)]
    comps = named_components()
    comp_drift = sorted(k for k, v in comps.items() if base["named_components"][k]["sha256"] != v["sha256"])
    locks = all_locks()
    result = {"entry_sha": base["entry_sha"], "head_sha": git("rev-parse", "HEAD"), "modified_since_entry": changed,
              "modified_outside_allowed": illegal, "removed_since_entry": removed, "added_count": len(added),
              "added_outside_additive_namespace": non_additive, "named_component_drift": comp_drift,
              "protected_tree_modified": [p for p in changed + removed if p.startswith(PROTECTED_PREFIXES)],
              "frontend_drift": [p for p, h in base["frontend"].items() if now.get(p) != h],
              "locks_verified": {k: v["verified"] for k, v in locks.items()},
              "amendment_chains_verified": not any(v.get("broken_chain_links") for v in locks.values())}
    result["protected_artifact_drift"] = bool(illegal or removed or non_additive or comp_drift or result["protected_tree_modified"]
                                              or result["frontend_drift"] or not all(v["verified"] for v in locks.values()))
    (OUT / "protected_artifact_final.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("protected_artifact_drift", "modified_outside_allowed", "added_outside_additive_namespace")}))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        print(json.dumps(entry()))
    elif mode == "final":
        sys.exit(final())
    else:
        sys.exit("usage: entry|final")
