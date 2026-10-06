# ruff: noqa: E501
"""Freeze the UFL-LITE-003 verification method (lock) before ANY canonical evidence: protocol, driver, analyzers, orchestrators, evaluator, mutation controls, builders, tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/ufl_lite/UFL_LITE_003_PROTOCOL_V1.lock.json"
BOUND = (
    "configs/ufl_lite/uflg2_protocol_v1.json", "scripts/ufl_lite_003_cdp_driver.mjs", "scripts/ufl_lite_003_lib.py", "scripts/ufl_lite_003_e2e.py", "scripts/ufl_lite_003_clean_clone.py", "scripts/ufl_lite_003_build_evidence.py", "scripts/ufl_lite_003_mutation_controls.py",
    "scripts/ufl_lite_003_evaluate_gate.py", "scripts/ufl_lite_003_record_target.py", "scripts/ufl_lite_003_build_freeze.py", "scripts/ufl_lite_003_protected_audit.py", "tests/test_ufl_lite_003_machinery.py",
    "scripts/run_capstone_clerk_connected_e2e.py", "scripts/run_capstone_clerk_connected_clean_clone.py", "scripts/ufl_lite_lib.py", "scripts/ufl_lite_002_lib.py",
)


def freeze() -> dict[str, object]:
    cfg = json.loads((ROOT / "configs/ufl_lite/uflg2_protocol_v1.json").read_text())
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock = {"lock_id": "UFL_LITE_003_PROTOCOL_V1", "status": "FROZEN_VERIFICATION_PROTOCOL", "owner_phase": "UFL-LITE-003", "gate": "UFLG2", "entry_sha": cfg["entry"]["entry_sha"], "criteria_count": cfg["criteria_count"], "mutation_control_count": cfg["mutation_control_count"],
            "bound_files": {p: lib.sha(ROOT / p) for p in BOUND}, "freeze_basis": "verification protocol, machinery, evaluator and mutation-control definitions frozen before any canonical evidence; zero product-feature delta"}
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return {"bound_files": len(BOUND), "lock_sha256": lib.sha(LOCK)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
