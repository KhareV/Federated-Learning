#!/usr/bin/env python3
"""V2-REL-001 POLICY freeze: artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json, written BEFORE the
deterministic decision evaluation and before any operational-default change. The mutable lifecycle
test is not bound."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "configs/model_v2/system_v2_release_policy_v1.yaml",
    "configs/model_v2/system_v2_release_evidence_matrix_schema_v1.json",
    "docs/SYSTEM_V2_RELEASE_POLICY_V1.md", "scripts/evaluate_system_v2_release.py",
    "tests/test_v2_rel_001_policy.py", "reports/model_v2/v2_rel_001/policy_disclosures.json",
    "api/app.py", "api/app_v2.py", "api/runtime.py", "api/runtime_v2.py", "api/schemas.py",
    "artifacts/API_RUNTIME_V2_1.lock.json", "artifacts/DASHBOARD_UI_V1_4.lock.json",
    "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json",
    "artifacts/MODEL_V2_COMPLETE_REPRO_V1.lock.json",
    "reports/model_v2/v2_007/promotion_decision.json",
    "reports/model_v2/v2_010/runtime_acceptance_decision.json",
]


def main() -> None:
    policy = yaml.safe_load((ROOT / FILES[0]).read_text())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    lock = {
        "lock_id": "SYSTEM_V2_RELEASE_POLICY_V1", "status": "FROZEN", "owner_task": "V2-REL-001",
        "gate": {"gate_id": "V2RELG0", **policy["v2relg0"]}, "entry_sha": policy["entry_sha"],
        "bound_artifacts": {p: hash_file(ROOT / p) for p in FILES},
        "release_level": policy["release_level"], "created_after_evidence": True,
        "scientific_preregistration_claim": False, "lifecycle_test_bound": False,
        "frozen_before_decision_evaluation": True, "frozen_before_default_change": True,
        "operational_default_at_freeze": "MODEL_V1", "head_at_freeze": head}
    (ROOT / "artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SYSTEM_V2_RELEASE_POLICY_V1 frozen on top of", head)


if __name__ == "__main__":
    main()
