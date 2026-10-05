#!/usr/bin/env python3
"""Verify the V2-REL-001 release locks: DEFAULT_RUNTIME_BINDING_V2, ROLLBACK_RUNTIME_BINDING_V1,
SOFTWARE_SYSTEM_V2 and the frozen release decision/policy chain (every bound hash recomputed)."""

from __future__ import annotations

import json
from pathlib import Path

from api.app_default import (
    DEFAULT_LOCK,
    ROLLBACK_LOCK,
    verify_binding,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    default = verify_binding(ROOT, DEFAULT_LOCK, "default")
    rollback = verify_binding(ROOT, ROLLBACK_LOCK, "rollback")
    system = json.loads((ROOT / "artifacts/SOFTWARE_SYSTEM_V2.lock.json").read_text())
    decision = json.loads((ROOT / "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json").read_text())
    policy_lock = ROOT / "artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json"
    checks = {
        "system_status": system["status"] == "FROZEN_RESEARCH_SOFTWARE_DEFAULT",
        "decision_accept": decision["SYSTEM_V2_RELEASE_DECISION"] == "ACCEPT"
        and decision["manual_override"] is False,
        "decision_binds_policy": decision["policy_lock_sha256"] == hash_file(policy_lock),
        "historical_disposition": system["historical_model_promotion_disposition"]
        == "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "fl_checkpoint_not_deployed": system["federated_checkpoint_deployed"] is False
        and default["federated_checkpoint_deployed"] is False,
        "default_selector_false": default["public_model_selector"] is False,
        "rollback_operator_only": rollback["operator_only"] is True}
    drift = [p for p, h in system["bound_artifacts"].items() if hash_file(ROOT / p) != h]
    if drift or not all(checks.values()):
        raise RuntimeError(f"RELEASE_BINDING_VERIFY_FAILED:{drift}:{checks}")
    return {"status": "PASS", "checks": checks, "bound_system_artifacts": len(
        system["bound_artifacts"]), "default_lock_sha256": hash_file(ROOT / DEFAULT_LOCK),
        "rollback_lock_sha256": hash_file(ROOT / ROLLBACK_LOCK)}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
