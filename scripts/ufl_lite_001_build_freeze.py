# ruff: noqa: E501
"""Freeze the UFL-LITE-001 method (lock) before the gate evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/ufl_lite/UFL_LITE_001_PROTOCOL_V1.lock.json"
BOUND = ("contracts/ufl_lite/user_bound_fl_participation_v1.json", "docs/ufl_lite/USER_BOUND_FL_PARTICIPATION_V1.md", "configs/ufl_lite/uflg0_protocol_v1.json", "reports/ufl_lite/ufl_lite_001/zero_drift_baseline.json",
         "reports/ufl_lite/ufl_lite_001/architecture_audit.json", "reports/ufl_lite/ufl_lite_001/change_surface.json", "scripts/ufl_lite_lib.py", "scripts/ufl_lite_001_evaluate_gate.py", "scripts/ufl_lite_001_mutation_controls.py",
         "scripts/ufl_lite_001_build_evidence.py", "scripts/ufl_lite_001_build_freeze.py", "scripts/ufl_lite_001_protected_audit.py", "tests/test_ufl_lite_contract.py")


def freeze() -> dict[str, object]:
    cfg = json.loads((ROOT / "configs/ufl_lite/uflg0_protocol_v1.json").read_text())
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock = {"lock_id": "UFL_LITE_001_PROTOCOL_V1", "status": "FROZEN_ARCHITECTURE_PROTOCOL", "owner_phase": "UFL-LITE-001", "gate": "UFLG0", "entry_sha": cfg["entry"]["entry_sha"], "criteria_count": cfg["criteria_count"],
            "bound_files": {p: lib.sha(ROOT / p) for p in BOUND}, "freeze_basis": "before UFLG0 evaluation; architecture/contract only; Phase 2 not implemented"}
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return {"bound_files": len(BOUND), "lock_sha256": lib.sha(LOCK)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
