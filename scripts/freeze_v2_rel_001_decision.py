#!/usr/bin/env python3
"""V2-REL-001: freeze SYSTEM_V2_RELEASE_DECISION_V1 (lock binding the evaluator output) BEFORE any
cutover change. Refuses to write an ACCEPT lock unless the decision file itself says ACCEPT."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_rel_001"


def main() -> None:
    decision = json.loads((OUT / "system_v2_release_decision.json").read_text())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    lock = {
        "lock_id": "SYSTEM_V2_RELEASE_DECISION_V1", "status": "FROZEN_RELEASE_DECISION",
        "owner_task": "V2-REL-001",
        "policy_lock": "artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json",
        "policy_lock_sha256": hash_file(ROOT / "artifacts/SYSTEM_V2_RELEASE_POLICY_V1.lock.json"),
        "SYSTEM_V2_RELEASE_DECISION": decision["SYSTEM_V2_RELEASE_DECISION"],
        "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED": decision["SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED"],
        "manual_override": decision["manual_override"],
        "decision_sha256": hash_file(OUT / "system_v2_release_decision.json"),
        "evidence_matrix_sha256": hash_file(OUT / "system_v2_release_evidence_matrix.json"),
        "criteria_passed": sum(r["status"] == "PASS" for r in decision["criteria"]),
        "criteria_total": len(decision["criteria"]),
        "historical_model_promotion_disposition": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "new_system_release_disposition": decision["new_system_release_disposition"],
        "head_at_decision_freeze": head, "frozen_before_cutover": True,
        "operational_default_at_freeze": "MODEL_V1"}
    (ROOT / "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: lock[k] for k in ("SYSTEM_V2_RELEASE_DECISION", "criteria_passed",
                                           "criteria_total")}))


if __name__ == "__main__":
    main()
