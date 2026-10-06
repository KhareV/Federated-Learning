# ruff: noqa: E501
"""Freeze the FINAL-EVAL-REPAIR-001 method (lock) before ANY canonical evidence: protocol, surface, truth contract, route policy, guards, machinery, evaluator, mutation controls, tests and the UI successor."""

from __future__ import annotations

import json

from scripts import final_eval_repair_lib as lib

ROOT = lib.ROOT
LOCK = ROOT / "artifacts/final_eval_repair/FINAL_EVAL_REPAIR_001_PROTOCOL_V1.lock.json"
BOUND = (
    "configs/final_eval_repair/fer_001_protocol_v1.json", "configs/final_eval_repair/fer_001_authorised_surface_v1.json", "configs/final_eval_repair/evaluator_truth_v1.json", "configs/final_eval_repair/legacy_route_policy_v1.json",
    "scripts/final_eval_repair_lib.py", "scripts/final_eval_repair_presentation.py", "scripts/final_eval_repair_crawl_analysis.py", "scripts/final_eval_repair_crawl.mjs", "scripts/final_eval_repair_e2e.py", "scripts/final_eval_repair_clean_clone.py", "scripts/final_eval_repair_build_evidence.py",
    "scripts/final_eval_repair_mutation_controls.py", "scripts/final_eval_repair_evaluate_gate.py", "scripts/final_eval_repair_record_target.py", "scripts/final_eval_repair_build_freeze.py", "scripts/final_eval_repair_protected_audit.py", "scripts/final_eval_repair_amend.py", "scripts/final_eval_repair_entry_evidence.py",
    "tests/test_final_eval_repair_presentation.py", "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json", "scripts/freeze_capstone_ui_v1_5.py", "scripts/verify_capstone_ui_v1_5.py", "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1_1.md",
    "frontend/src/lib/product/route-policy.ts", "frontend/src/routes/+layout.ts", "frontend/src/routes/+page.svelte", "frontend/src/routes/app/about/+page.svelte",
    "scripts/ufl_lite_lib.py", "scripts/ufl_lite_002_lib.py", "scripts/ufl_lite_003_lib.py", "scripts/ufl_lite_003_e2e.py", "scripts/ufl_lite_003_cdp_driver.mjs", "scripts/run_capstone_clerk_connected_e2e.py", "scripts/run_capstone_clerk_connected_clean_clone.py",
)


def freeze() -> dict[str, object]:
    cfg = json.loads((ROOT / "configs/final_eval_repair/fer_001_protocol_v1.json").read_text())
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock = {"lock_id": "FINAL_EVAL_REPAIR_001_PROTOCOL_V1", "status": "FROZEN_REPAIR_PROTOCOL", "owner_phase": "FINAL-EVAL-REPAIR-001", "gate": "FERG0", "entry_sha": cfg["entry"]["entry_sha"], "criteria_count": cfg["criteria_count"], "mutation_control_count": cfg["mutation_control_count"],
            "bound_files": {p: lib.sha(ROOT / p) for p in BOUND}, "freeze_basis": "repair implementation, UI successor lock, guards, machinery, evaluator and mutation-control definitions frozen before any canonical evidence; zero backend/API/DB/FL/auth/scientific change"}
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return {"bound_files": len(BOUND), "lock_sha256": lib.sha(LOCK)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
