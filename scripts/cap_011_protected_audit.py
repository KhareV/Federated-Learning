# ruff: noqa: E501
"""CAP-011 entry/final protection audit. CAP-011 is release-layer only: every file tracked at entry must be
byte-identical at final except the control-plane registries; every new file must live in an explicit CAP-011
release namespace. The historical RELEASE_V1 / T036 / G22 / F15 lineage rows are hashed and must not move."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_010_protected_audit import all_locks as locks_to_cap010

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_011"
EXPECTED_PRIOR_RESULT = "f0bcc1693a75155b41ec9a3cd2abd994c5e88029"
AUTHORISED_INTERVENING = {
    "7360cee": "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1 amendment 1 (successor-compatible phase-state predicate)",
    "af60c1e": "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1 amendment 9_2 (lifecycle guard governs CAP-011/CAPG10)",
}
CAP011_LOCK = ROOT / "artifacts/capstone/CAPSTONE_RELEASE_PROTOCOL_V1.lock.json"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/cap_011_", "artifacts/capstone/CAPSTONE_RELEASE", "artifacts/capstone/CAPSTONE_CLEAN_CLONE",
    "docs/capstone/CAPSTONE_RELEASE", "reports/capstone/cap_011/", "scripts/cap_011_", "scripts/run_capstone_clean_release.py",
    "scripts/verify_capstone_release_v1.py", "scripts/capstone_release_", "tests/test_capstone_release_", "tests/capstone_release_",
)
MODIFIABLE = ("manifests/capstone/task_registry_v1.csv", "manifests/capstone/gate_registry_v1.csv")
PROTECTED_PREFIXES = ("api/", "product/", "capstone_persistence/", "federated/", "privacy/", "simulation/", "src/", "checkpoints/", "contracts/",
                      "frontend/", "reports/model_v2/", "reports/capstone/cap_00", "reports/capstone/cap_010/", "release/")
HISTORICAL_ROOT_REGISTRIES = ("manifests/task_registry_v1.csv", "manifests/gate_registry_v1.csv", "manifests/freeze_registry_v1.csv", "manifests/evidence_registry_v1.csv", "manifests/do_not_start_v1.csv")
HISTORICAL_KEYS = ("T036", "G22", "F15", "RELEASE_V1")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def statuses() -> dict[str, dict[str, str]]:
    out = {}
    for name, key in (("task", "task_id"), ("gate", "gate_id")):
        with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
            out[name] = {r[key]: r["status"] for r in csv.DictReader(h)}
    return out


def historical_state() -> dict:
    rows = {}
    for rel in HISTORICAL_ROOT_REGISTRIES:
        text = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        rows[rel] = {"file_sha256": sha(rel), "rows": {k: hashlib.sha256("\n".join(line for line in text if line.startswith(k + ",")).encode()).hexdigest() for k in HISTORICAL_KEYS},
                     "matching_row_counts": {k: sum(1 for line in text if line.startswith(k + ",")) for k in HISTORICAL_KEYS}}
    tracked = git("ls-files").splitlines()
    rel_files = sorted(p for p in tracked if "RELEASE_V1" in p and "CAPSTONE" not in p)
    rows["historical_release_v1_files"] = {p: sha(p) for p in rel_files}
    return rows


UPSTREAM_NAMED = ("FL_INIT_V2", "FEDPROX_MU_V2", "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1", "WEARABLE_SIM_FL_SECAGG_COMPAT_V1", "MODEL_V2_COMPLETE_REPRO_V1",
                  "SOFTWARE_SYSTEM_V2", "DEFAULT_RUNTIME_BINDING_V2", "ROLLBACK_RUNTIME_BINDING_V1")


def upstream_inventory() -> dict:
    out = {}
    for name in UPSTREAM_NAMED:
        paths = sorted(p for p in git("ls-files", "artifacts").splitlines() if Path(p).name.startswith(name) and p.endswith(".json"))
        out[name] = {p: sha(p) for p in paths}
    # identities that live in a config / inside another lock rather than in their own artifact file
    out["WEARABLE_SIM_FL_SECAGG_COMPAT_V1"] = {"configs/model_v2/wearable_sim_fl_secagg_compat_v1.yaml": sha("configs/model_v2/wearable_sim_fl_secagg_compat_v1.yaml")}
    out["FL_INIT_V2"] = {"artifacts/FEDPROX_MU_V2.lock.json#FL_INIT_V2_round_0_state_sha256": json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())["FL_INIT_V2_round_0_state_sha256"]}
    return out


def all_locks() -> dict:
    locks = locks_to_cap010()
    if CAP011_LOCK.exists():
        from scripts.cap_006_protected_audit import verify_amended_lock

        r = verify_amended_lock(CAP011_LOCK, "CAPSTONE_RELEASE_PROTOCOL_V1.amendment_*.json")
        r["verified"] = not r["mismatches"] and not r["broken_chain_links"]
        locks["cap011"] = r
    return locks


def entry() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    dirty = [ln for ln in git("status", "--porcelain").splitlines() if "cap_011" not in ln]
    if origin != head or dirty:
        raise RuntimeError("CAP011_ENTRY_STATE_CONFLICT")
    intervening = [ln for ln in git("log", "--format=%h %s", f"{EXPECTED_PRIOR_RESULT}..HEAD").splitlines()]
    unexplained = [ln for ln in intervening if ln.split()[0] not in AUTHORISED_INTERVENING]
    if unexplained:
        raise RuntimeError(f"CAP011_UNEXPLAINED_INTERVENING_COMMITS:{unexplained}")
    changed = git("diff", "--name-only", EXPECTED_PRIOR_RESULT, "HEAD").splitlines()
    st = statuses()
    exp_t = {f"CAP-{i:03d}": "PASS" for i in range(1, 11)} | {"CAP-011": "NOT_STARTED"}
    exp_g = {f"CAPG{i}": "PASS" for i in range(10)}
    if any(st["task"].get(k) != v for k, v in exp_t.items()) or any(st["gate"].get(k) != v for k, v in exp_g.items()) or "CAPG10" in st["gate"]:
        raise RuntimeError("CAP011_STATUS_CONFLICT")
    locks = all_locks()
    if not all(v["verified"] for v in locks.values()):
        raise RuntimeError("CAP011_PRIOR_LOCK_FAILURE")
    files, comps = tracked_hashes(), named_components()
    hist = historical_state()
    audit = {"phase": "CAP-011", "gate": "CAPG10", "entry_sha": head, "origin_main_sha": origin, "expected_prior_result_sha": EXPECTED_PRIOR_RESULT,
             "entry_is_expected_prior_result": head == EXPECTED_PRIOR_RESULT, "working_tree_clean_before_entry": True,
             "intervening_commits_since_expected": intervening, "intervening_commits_authorised_explanation": AUTHORISED_INTERVENING,
             "intervening_files_changed": changed,
             "intervening_scope_note": "Only the user-authorised release-enabling compatibility amendments (CAP-010 preflight phase-state predicate; historical lifecycle guard) separate this entry from the expected f0bcc16; no scientific, runtime, frontend, API, monitoring, history/research, FL or governance file changed.",
             "prior_tasks": exp_t, "prior_gates": exp_g, "cap_011_not_started": True, "capg10_absent": True, "prior_locks_verified": True, "locks": sorted(locks),
             "protected_tracked_file_count": len(files), "upstream_named_lock_inventory": upstream_inventory(), "historical_release_lineage_snapshot_sha256": hashlib.sha256(json.dumps(hist, sort_keys=True).encode()).hexdigest(),
             "ci_queried": False, "ci_triggered": False, "remote": git("remote", "get-url", "origin")}
    snap = {"entry_sha": head, "tracked_file_count": len(files), "tracked_files_sha256": files, "named_components": comps,
            "frontend": {p: d for p, d in files.items() if p.startswith("frontend/")}, "historical_release_lineage": hist}
    for name, value in (("entry_audit.json", audit), ("protected_artifact_entry.json", snap), ("prior_lock_verification.json", locks)):
        (OUT / name).write_text(json.dumps(value, sort_keys=True, indent=1, default=str) + "\n", encoding="utf-8")
    return {"entry_sha": head, "tracked": len(files), "locks": {k: v["verified"] for k, v in locks.items()}, "intervening": intervening}


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
    hist_now = historical_state()
    result = {"entry_sha": base["entry_sha"], "head_sha": git("rev-parse", "HEAD"), "modified_since_entry": changed, "modified_outside_allowed": illegal, "removed_since_entry": removed,
              "added_count": len(added), "added_outside_additive_namespace": non_additive, "named_component_drift": comp_drift,
              "protected_tree_modified": [p for p in changed + removed if p.startswith(PROTECTED_PREFIXES)],
              "frontend_drift": [p for p, h in base["frontend"].items() if now.get(p) != h],
              "historical_release_lineage_unchanged": hist_now == base["historical_release_lineage"],
              "locks_verified": {k: v["verified"] for k, v in locks.items()}, "amendment_chains_verified": not any(v.get("broken_chain_links") for v in locks.values())}
    result["protected_artifact_drift"] = bool(illegal or removed or non_additive or comp_drift or result["protected_tree_modified"] or result["frontend_drift"]
                                              or not result["historical_release_lineage_unchanged"] or not all(v["verified"] for v in locks.values()))
    (OUT / "protected_artifact_final.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("protected_artifact_drift", "modified_outside_allowed", "added_outside_additive_namespace", "historical_release_lineage_unchanged")}))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        print(json.dumps(entry()))
    elif mode == "final":
        sys.exit(final())
    else:
        sys.exit("usage: entry|final")
