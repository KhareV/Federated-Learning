# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-002 entry/final protection audit. Entry: exact repository/tag/lock state (FER-001 PASS preserved). Final: the ONLY changes since entry are the authorised
presentation surface (configs/final_eval_repair/fer_002_authorised_surface_v1.json) plus additive FER namespaces; backend/API/DB/FL/auth/scientific trees are byte-identical."""

from __future__ import annotations

import importlib
import json
import sys

from scripts import final_eval_repair_002_lib as l2
from scripts import final_eval_repair_lib as lib
from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_011_protected_audit import all_locks

ROOT, ENTRY = lib.ROOT, l2.ENTRY
OUT = ROOT / "reports/final_eval_repair/fer_002"
SURFACE = ROOT / "configs/final_eval_repair/fer_002_authorised_surface_v1.json"
ADDITIVE = ("manifests/final_eval_repair/", "configs/final_eval_repair/", "docs/final_eval_repair/", "artifacts/final_eval_repair/", "reports/final_eval_repair/", "scripts/final_eval_repair_", "tests/test_final_eval_repair_")
PROTECTED = ("api/", "product/", "capstone_persistence/", "federated/", "privacy/", "simulation/", "src/", "checkpoints/", "contracts/", "reports/model_v2/", "reports/capstone/", "reports/clerk_connected/", "reports/ufl_lite/", "release/", "configs/ufl_lite/", "configs/model_v2/",
             "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/CAL_V2.json", "docs/capstone/", "reports/final_eval_repair/fer_001/")


def _ui_ok(upto: int) -> bool:
    names = ["scripts.verify_capstone_ui_v1", "scripts.verify_capstone_ui_v1_1", "scripts.verify_capstone_ui_v1_2", "scripts.verify_capstone_ui_v1_3", "scripts.verify_capstone_ui_v1_4", "scripts.verify_capstone_ui_v1_5"] + (["scripts.verify_capstone_ui_v1_6"] if upto >= 6 else [])
    return all(importlib.import_module(n).verify()["status"] == "PASS" for n in names)


def _clerk_ok() -> bool:
    from scripts.verify_clerk_connected import verify

    return verify()["status"] == "PASS" and lib.registry("manifests/clerk_connected/gate_registry_v1.csv", "gate_id").get("CLERKG0") == "PASS"


def _prior_ok() -> bool:
    r = lib.registry
    return (all(r("manifests/ufl_lite/task_registry_v1.csv", "task_id").get(f"UFL-LITE-00{i}") == "PASS" for i in (1, 2, 3)) and all(r("manifests/ufl_lite/gate_registry_v1.csv", "gate_id").get(g) == "PASS" for g in ("UFLG0", "UFLG1", "UFLG2"))
            and r("manifests/final_eval_repair/task_registry_v1.csv", "task_id").get("FINAL-EVAL-REPAIR-001") == "PASS" and r("manifests/final_eval_repair/gate_registry_v1.csv", "gate_id").get("FERG0") == "PASS" and all(v["verified"] for v in l2.verify_all_locks().values()))


def entry() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    head, origin = lib.git("rev-parse", "HEAD"), lib.git("rev-parse", "origin/main")
    dirty = [ln for ln in lib.git("status", "--porcelain").splitlines() if "final_eval_repair" not in ln and "node_modules" not in ln]
    if head != ENTRY or origin != ENTRY or dirty:
        raise RuntimeError("ENTRY_DRIFT")
    locks = all_locks()
    audit = {"phase": "FINAL-EVAL-REPAIR-002", "gate": "FERG1", "entry_sha": head, "origin_main_sha": origin, "entry_is_expected": True, "working_tree_clean_before_entry": True, "tags": {t: lib.tag_target(t) for t in lib.TAGS}, "tags_ok": lib.tags_ok(),
             "fer1_target_reachable": lib.git("merge-base", "--is-ancestor", l2.FER1_TARGET, "HEAD") == "", "fer1_and_ufl_state_and_locks_ok": _prior_ok(), "capstone_locks_verified": all(v["verified"] for v in locks.values()), "capstone_lock_count": len(locks),
             "ui_v1_through_v1_5_verified": _ui_ok(5), "clerk_connected_ok": _clerk_ok(), "ci_queried": False, "ci_triggered": False}
    if not all(audit[k] for k in ("tags_ok", "fer1_target_reachable", "fer1_and_ufl_state_and_locks_ok", "capstone_locks_verified", "ui_v1_through_v1_5_verified", "clerk_connected_ok")):
        raise RuntimeError("ENTRY_STATE_CONFLICT:" + json.dumps({k: v for k, v in audit.items() if v is False}))
    files = tracked_hashes()
    snap = {"entry_sha": head, "tracked_file_count": len(files), "tracked_files_sha256": files, "named_components": named_components(), "frontend": {p: d for p, d in files.items() if p.startswith("frontend/")}}
    for name, value in (("entry_audit.json", audit), ("protected_artifact_entry.json", snap), ("prior_lock_verification.json", {"capstone": locks, "frozen_method_locks": l2.verify_all_locks()})):
        (OUT / name).write_text(json.dumps(value, sort_keys=True, indent=1, default=str) + "\n", encoding="utf-8")
    return {"entry_sha": head, "tracked": len(files), "ok": True}


def final() -> int:
    base = json.loads((OUT / "protected_artifact_entry.json").read_text())
    cfg = json.loads(SURFACE.read_text())
    ok_mod, ok_new = set(cfg["authorised_modifications"]), set(cfg["authorised_new_files"])
    now, before = tracked_hashes(), base["tracked_files_sha256"]
    changed = sorted(p for p, h in before.items() if p in now and now[p] != h)
    removed = sorted(p for p in before if p not in now)
    added = sorted(p for p in now if p not in before)
    illegal = [p for p in changed if p not in ok_mod]
    non_additive = [p for p in added if not p.startswith(ADDITIVE) and p not in ok_new]
    protected_touched = [p for p in changed + removed + added if p.startswith(PROTECTED) and p not in ok_mod and p not in ok_new and not p.startswith("reports/final_eval_repair/fer_002")]
    ui6 = json.loads((ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json").read_text()) if (ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json").exists() else {}
    fe_changed = sorted(p for p in changed + added if p.startswith("frontend/"))
    fe_unaccounted = [p for p in fe_changed if p not in set(ui6.get("changed_from_predecessor", []))]
    locks, frozen = all_locks(), l2.verify_all_locks()
    result = {"entry_sha": base["entry_sha"], "head_sha": lib.git("rev-parse", "HEAD"), "modified_since_entry": changed, "modified_outside_authorised": illegal, "removed_since_entry": removed, "added_count": len(added), "added_outside_authorised": non_additive, "protected_tree_touched": protected_touched,
              "frontend_changed": fe_changed, "frontend_unaccounted_by_ui_v1_6": fe_unaccounted, "capstone_locks_verified": {k: v["verified"] for k, v in locks.items()}, "frozen_method_locks_verified": {k: v["verified"] for k, v in frozen.items()}, "tags_unchanged": lib.tags_ok(), "ui_chain_verified": _ui_ok(6), "clerk_ok": _clerk_ok(), "prior_phases_ok": _prior_ok()}
    result["protected_artifact_drift"] = bool(illegal or removed or non_additive or protected_touched or fe_unaccounted or not all(result["capstone_locks_verified"].values()) or not all(result["frozen_method_locks_verified"].values()) or not result["tags_unchanged"] or not result["ui_chain_verified"] or not result["clerk_ok"] or not result["prior_phases_ok"])
    (OUT / "protected_artifact_final.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("protected_artifact_drift", "modified_outside_authorised", "added_outside_authorised", "protected_tree_touched", "frontend_unaccounted_by_ui_v1_6")}))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        print(json.dumps(entry()))
    elif mode == "final":
        sys.exit(final())
