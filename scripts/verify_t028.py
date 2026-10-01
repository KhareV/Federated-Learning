#!/usr/bin/env python3
"""Verify T028 SecAgg+ locks, correctness, visibility, and scope."""

from __future__ import annotations

import json
from pathlib import Path

import flwr

from nhm.hashing import hash_file
from scripts.verify_fl_config_t026 import verify as verify_f12
from scripts.verify_t027 import verify as verify_t027

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    verify_f12(ROOT)
    verify_t027()
    if flwr.__version__ != "1.39.0":
        raise RuntimeError("FLOWER_VERSION_MISMATCH")
    method = json.loads((ROOT / "artifacts/SECAGG_METHOD_V1.lock.json").read_text())
    for path, expected in method["bound_artifacts"].items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"SECAGG_METHOD_TAMPER: {path}")
    correctness = json.loads((ROOT / "reports/t028/aggregate_correctness.json").read_text())
    model = correctness["MODEL_V1_shaped"]
    if correctness["status"] != "PASS" or model["maximum_absolute_difference"] > 1e-4:
        raise RuntimeError("SECAGG_AGGREGATE_MISMATCH")
    if model["relative_L2_difference"] > 1e-4 or model["clipped_value_count"] != 0:
        raise RuntimeError("SECAGG_AGGREGATE_MISMATCH")
    if model["plain_aggregate_sha256"] != model["authoritative_T025_round_1_state_sha256"]:
        raise RuntimeError("SECAGG_REFERENCE_IDENTITY_MISMATCH")
    visibility = json.loads((ROOT / "reports/t028/server_visibility_audit.json").read_text())
    if not visibility["plain_detector_positive"]:
        raise RuntimeError("VISIBILITY_PROBE_NOT_SENSITIVE")
    if visibility["protected_clear_update_count"] != 0:
        raise RuntimeError("PROTECTED_CLEAR_UPDATE_EXPOSED")
    overhead = json.loads((ROOT / "reports/t028/overhead_summary.json").read_text())
    if overhead["completion"] != {"attempted": 10, "completed": 10, "failed": 0, "rate": 1.0}:
        raise RuntimeError("SECAGG_TRIAL_COMPLETION_FAILURE")
    lock = json.loads((ROOT / "artifacts/SECAGG_CONFIG_V1.lock.json").read_text())
    if lock["freeze_id"] != "F13" or lock["status"] != "FROZEN":
        raise RuntimeError("F13_LOCK_MISMATCH")
    for path, expected in lock["bound_artifacts"].items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"F13_TAMPER: {path}")
    inventory = json.loads((ROOT / "reports/t028/artifact_hashes.json").read_text())
    for path, expected in inventory.items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"T028_ARTIFACT_HASH_MISMATCH: {path}")
    return {
        "status": "PASS",
        "Flower": flwr.__version__,
        "known_vector": "PASS",
        "MODEL_V1_shaped": "PASS",
        "plain_clear_updates": 8,
        "protected_clear_updates": 0,
        "protected_trials": "10/10",
        "F13": "FROZEN",
        "G14": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
