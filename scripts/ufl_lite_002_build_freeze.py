# ruff: noqa: E501
"""Freeze the UFL-LITE-002 method (lock) before the gate evaluation: implementation, evaluator, audits, tests and the UI successor lock."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.lock.json"
BOUND = (
    "configs/ufl_lite/uflg1_protocol_v1.json", "frontend/src/lib/product/federation/participation.ts", "frontend/src/lib/components/product/federation/ClientGrid.svelte", "frontend/src/routes/app/federation/live/+page.svelte",
    "frontend/src/routes/app/federation/rounds/+page.svelte", "frontend/src/lib/product/federation/__tests__/participation.test.ts", "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json", "scripts/freeze_capstone_ui_v1_4.py", "scripts/verify_capstone_ui_v1_4.py",
    "scripts/ufl_lite_002_lib.py", "scripts/ufl_lite_002_evaluate_gate.py", "scripts/ufl_lite_002_mutation_controls.py", "scripts/ufl_lite_002_build_evidence.py", "scripts/ufl_lite_002_build_freeze.py", "scripts/ufl_lite_002_protected_audit.py", "tests/test_ufl_lite_presentation.py",
)


def freeze() -> dict[str, object]:
    cfg = json.loads((ROOT / "configs/ufl_lite/uflg1_protocol_v1.json").read_text())
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock = {"lock_id": "UFL_LITE_002_PROTOCOL_V1", "status": "FROZEN_IMPLEMENTATION_PROTOCOL", "owner_phase": "UFL-LITE-002", "gate": "UFLG1", "entry_sha": cfg["entry"]["entry_sha"], "criteria_count": cfg["criteria_count"],
            "bound_files": {p: lib.sha(ROOT / p) for p in BOUND}, "freeze_basis": "implementation, UI successor lock and evaluator frozen before the final evidence run; Phase 3 not implemented"}
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return {"bound_files": len(BOUND), "lock_sha256": lib.sha(LOCK)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
