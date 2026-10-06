# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-001 entry/final protection audit. Entry: exact repository/tag/lock state. Final: the ONLY changes since entry are the authorised presentation
surface (protocol config) plus additive FER namespaces; backend/API/DB/FL/auth/scientific trees are byte-identical."""

from __future__ import annotations

import json
import sys

from scripts import final_eval_repair_lib as lib
from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_011_protected_audit import all_locks

ROOT, OUT, ENTRY = lib.ROOT, lib.ROOT / "reports/final_eval_repair/fer_001", lib.ENTRY
PROTOCOL = ROOT / "configs/final_eval_repair/fer_001_authorised_surface_v1.json"
ADDITIVE = ("manifests/final_eval_repair/", "configs/final_eval_repair/", "docs/final_eval_repair/", "artifacts/final_eval_repair/", "reports/final_eval_repair/", "scripts/final_eval_repair_", "tests/test_final_eval_repair_")
PROTECTED = ("api/", "product/", "capstone_persistence/", "federated/", "privacy/", "simulation/", "src/", "checkpoints/", "contracts/", "reports/model_v2/", "reports/capstone/", "reports/clerk_connected/", "reports/ufl_lite/", "release/", "configs/ufl_lite/", "configs/model_v2/", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/CAL_V2.json")


def _ufl_ok() -> bool:
    reg = lib.registry
    return (all(reg("manifests/ufl_lite/task_registry_v1.csv", "task_id").get(f"UFL-LITE-00{i}") == "PASS" for i in (1, 2, 3)) and all(reg("manifests/ufl_lite/gate_registry_v1.csv", "gate_id").get(g) == "PASS" for g in ("UFLG0", "UFLG1", "UFLG2"))
            and all(v["verified"] for v in lib.verify_all_ufl_locks().values()))


def _ui_ok(upto: int) -> bool:
    import importlib

    names = ["scripts.verify_capstone_ui_v1", "scripts.verify_capstone_ui_v1_1", "scripts.verify_capstone_ui_v1_2", "scripts.verify_capstone_ui_v1_3", "scripts.verify_capstone_ui_v1_4"] + (["scripts.verify_capstone_ui_v1_5"] if upto >= 5 else [])
    return all(importlib.import_module(n).verify()["status"] == "PASS" for n in names)


def _clerk_ok() -> bool:
    from scripts.verify_clerk_connected import verify

    return verify()["status"] == "PASS" and lib.registry("manifests/clerk_connected/gate_registry_v1.csv", "gate_id").get("CLERKG0") == "PASS"


def entry() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    head, origin = lib.git("rev-parse", "HEAD"), lib.git("rev-parse", "origin/main")
    dirty = [ln for ln in lib.git("status", "--porcelain").splitlines() if "final_eval_repair" not in ln]
    if head != ENTRY or origin != ENTRY or dirty:
        raise RuntimeError("ENTRY_DRIFT")
    locks = all_locks()
    audit = {"phase": "FINAL-EVAL-REPAIR-001", "gate": "FERG0", "entry_sha": head, "origin_main_sha": origin, "entry_is_expected": head == ENTRY, "working_tree_clean_before_entry": True, "tags": {t: lib.tag_target(t) for t in lib.TAGS}, "tags_ok": lib.tags_ok(),
             "ufl_acceptance_target_reachable": lib.git("merge-base", "--is-ancestor", "cf18cba4d7891c514553a1702e227f28dbe26f7c", "HEAD") == "", "ufl_tasks_gates_and_locks_ok": _ufl_ok(), "capstone_locks_verified": all(v["verified"] for v in locks.values()), "capstone_lock_count": len(locks),
             "ui_v1_through_v1_4_verified": _ui_ok(4), "clerk_connected_ok": _clerk_ok(), "ci_queried": False, "ci_triggered": False}
    if not (audit["tags_ok"] and audit["ufl_tasks_gates_and_locks_ok"] and audit["capstone_locks_verified"] and audit["ui_v1_through_v1_4_verified"] and audit["clerk_connected_ok"] and audit["ufl_acceptance_target_reachable"]):
        raise RuntimeError("ENTRY_STATE_CONFLICT:" + json.dumps({k: v for k, v in audit.items() if v is False}))
    files = tracked_hashes()
    snap = {"entry_sha": head, "tracked_file_count": len(files), "tracked_files_sha256": files, "named_components": named_components(), "frontend": {p: d for p, d in files.items() if p.startswith("frontend/")}}
    for name, value in (("entry_audit.json", audit), ("protected_artifact_entry.json", snap), ("prior_lock_verification.json", {"capstone": locks, "ufl": lib.verify_all_ufl_locks()})):
        (OUT / name).write_text(json.dumps(value, sort_keys=True, indent=1, default=str) + "\n", encoding="utf-8")
    return {"entry_sha": head, "tracked": len(files), "ok": True}


def final() -> int:
    base = json.loads((OUT / "protected_artifact_entry.json").read_text())
    cfg = json.loads(PROTOCOL.read_text())
    authorised = set(cfg["authorised_modifications"])
    now, before = tracked_hashes(), base["tracked_files_sha256"]
    changed = sorted(p for p, h in before.items() if p in now and now[p] != h)
    removed = sorted(p for p in before if p not in now)
    added = sorted(p for p in now if p not in before)
    illegal = [p for p in changed if p not in authorised]
    non_additive = [p for p in added if not p.startswith(ADDITIVE) and p not in set(cfg["authorised_new_files"]) and not (p.startswith("frontend/") and p in set(cfg["authorised_new_files"]))]
    protected_touched = [p for p in changed + removed + added if p.startswith(PROTECTED)]
    ui5 = json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json").read_text()) if (ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json").exists() else {}
    fe_changed = sorted(p for p in changed + added if p.startswith("frontend/"))
    fe_unaccounted = [p for p in fe_changed if p not in set(ui5.get("changed_from_predecessor", [])) and p != "frontend/build"]
    locks = all_locks()
    ufl = lib.verify_all_ufl_locks()
    result = {"entry_sha": base["entry_sha"], "head_sha": lib.git("rev-parse", "HEAD"), "modified_since_entry": changed, "modified_outside_authorised": illegal, "removed_since_entry": removed, "added_count": len(added), "added_outside_authorised": non_additive,
              "protected_tree_touched": protected_touched, "frontend_changed": fe_changed, "frontend_unaccounted_by_ui_v1_5": fe_unaccounted, "capstone_locks_verified": {k: v["verified"] for k, v in locks.items()}, "ufl_locks_verified": {k: v["verified"] for k, v in ufl.items()},
              "tags_unchanged": lib.tags_ok(), "ui_chain_verified": _ui_ok(5), "clerk_ok": _clerk_ok(), "ufl_ok": _ufl_ok()}
    result["protected_artifact_drift"] = bool(illegal or removed or non_additive or protected_touched or fe_unaccounted or not all(result["capstone_locks_verified"].values()) or not all(result["ufl_locks_verified"].values()) or not result["tags_unchanged"] or not result["ui_chain_verified"] or not result["clerk_ok"] or not result["ufl_ok"])
    (OUT / "protected_artifact_final.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("protected_artifact_drift", "modified_outside_authorised", "added_outside_authorised", "protected_tree_touched", "frontend_unaccounted_by_ui_v1_5")}))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        print(json.dumps(entry()))
    elif mode == "final":
        sys.exit(final())
