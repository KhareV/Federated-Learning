#!/usr/bin/env python3
"""Verify frozen T027 FedProx evidence without rerunning training."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from nhm.hashing import hash_file  # noqa: E402
from scripts.verify_fl_config_t026 import verify as verify_f12  # noqa: E402


def verify() -> dict[str, object]:
    verify_f12(ROOT)
    method = json.loads((ROOT / "artifacts/FEDPROX_METHOD_V1.lock.json").read_text())
    for path, expected in method["bound_artifacts"].items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"FEDPROX_METHOD_TAMPER: {path}")
    mu_lock = json.loads((ROOT / "artifacts/FEDPROX_MU_V1.lock.json").read_text())
    if mu_lock["selected_mu"] != 0.01 or mu_lock["status"] != "FROZEN_ENGINEERING_METHOD":
        raise RuntimeError("FEDPROX_MU_LOCK_MISMATCH")
    if mu_lock["F12_lock_sha256"] != hash_file(ROOT / "artifacts/FL_CONFIG_V1.lock.json"):
        raise RuntimeError("F12_BINDING_MISMATCH")
    zero = json.loads((ROOT / "reports/t027/mu_zero_equivalence.json").read_text())
    if zero["status"] != "PASS" or zero["full_round"]["maximum_absolute_difference"] != 0:
        raise RuntimeError("FEDPROX_MU_ZERO_MISMATCH")
    with (ROOT / "reports/t027/mu_candidates.csv").open(newline="") as handle:
        candidates = list(csv.DictReader(handle))
    if [float(row["mu"]) for row in candidates] != [0.001, 0.01, 0.1]:
        raise RuntimeError("FEDPROX_CANDIDATE_DRIFT")
    for stem in ("mu_0p001", "mu_0p01", "mu_0p1"):
        with (ROOT / f"reports/t027/candidates/{stem}_rounds.csv").open(newline="") as handle:
            if len(list(csv.DictReader(handle))) != 51:
                raise RuntimeError("FEDPROX_CANDIDATE_ROUND_COUNT")
        with (ROOT / f"reports/t027/candidates/{stem}_client_rounds.csv").open(
            newline=""
        ) as handle:
            if len(list(csv.DictReader(handle))) != 400:
                raise RuntimeError("FEDPROX_CANDIDATE_CLIENT_COUNT")
    report = json.loads((ROOT / "reports/fedprox.json").read_text())
    if report["status"] != "PASS" or len(report["comparisons"]) != 5:
        raise RuntimeError("FEDPROX_REPORT_INVALID")
    if any(float(row["selected_mu"]) != 0.01 for row in report["comparisons"]):
        raise RuntimeError("CROSS_CONDITION_MU_MISMATCH")
    replay = json.loads((ROOT / "reports/t027/reproducibility.json").read_text())
    if replay["status"] != "PASS":
        raise RuntimeError("FEDPROX_REPRODUCIBILITY_FAILURE")
    inventory = json.loads((ROOT / "reports/t027/artifact_hashes.json").read_text())
    for path, expected in inventory.items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"T027_ARTIFACT_HASH_MISMATCH: {path}")
    return {
        "status": "PASS",
        "selected_mu": 0.01,
        "conditions": 5,
        "candidate_rounds": 150,
        "comparison_rounds": 250,
        "F12": "FROZEN",
        "FEDPROX_MU_V1": "FROZEN_ENGINEERING_METHOD",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
