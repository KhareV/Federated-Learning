#!/usr/bin/env python3
"""Verify API_RUNTIME_V2_1: predecessor preserved byte-identical, every bound file unchanged, V2
upstream freezes re-verified, quality/preproc claimed unchanged."""

from __future__ import annotations

import json

from nhm.hashing import hash_file
from scripts._v2_013_lib import ROOT


def verify() -> dict[str, object]:
    path = ROOT / "artifacts/API_RUNTIME_V2_1.lock.json"
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock["lock_id"] != "API_RUNTIME_V2_1" or lock["status"] != "FROZEN_RESEARCH_RUNTIME":
        raise RuntimeError("API_RUNTIME_V2_1_IDENTITY_MISMATCH")
    if lock["quality_v1_changed"] is not False or lock["preproc_v1_changed"] is not False:
        raise RuntimeError("API_RUNTIME_V2_1_CLAIM_VIOLATION")
    if hash_file(ROOT / "artifacts/API_RUNTIME_V2.lock.json") != lock["predecessor_sha256"]:
        raise RuntimeError("API_RUNTIME_V2_1_PREDECESSOR_WAS_MUTATED")
    for relative, expected in lock["bound_artifacts"].items():
        if hash_file(ROOT / relative) != expected:
            raise RuntimeError(f"API_RUNTIME_V2_1_TAMPER:{relative}")
    from models.cal_v2_verify import verify_cal_v2
    from models.gateway_artifact_v2_verify import verify_gateway_artifact_v2
    from preprocessing.freeze import verify_preproc_freeze

    verify_cal_v2(ROOT)
    verify_gateway_artifact_v2(ROOT)
    verify_preproc_freeze(ROOT)
    return {"status": "PASS", "lock_id": "API_RUNTIME_V2_1", "lock_sha256": hash_file(path),
            "bound_artifacts": len(lock["bound_artifacts"])}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
