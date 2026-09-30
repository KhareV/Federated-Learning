#!/usr/bin/env python3
"""Verification-only T025 audit from frozen logs, predictions, and locks."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from federated.fedavg_runner import choose_best_round  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify() -> dict[str, object]:
    method = json.loads((ROOT / "artifacts/FL_IID_METHOD_V1.lock.json").read_text())
    for name, path in method["paths"].items():
        if hash_file(ROOT / path) != method["hashes"][name]:
            raise RuntimeError(f"FL_IID_METHOD_LOCK_MISMATCH: {name}")
    result = json.loads((ROOT / "artifacts/FL_IID_V1.lock.json").read_text())
    for name, path in result["result_paths"].items():
        if hash_file(ROOT / path) != result["result_hashes"][name]:
            raise RuntimeError(f"FL_IID_RESULT_LOCK_MISMATCH: {name}")
    rounds = read_csv(ROOT / "reports/t025/fl_iid_rounds.csv")
    clients = read_csv(ROOT / "reports/t025/fl_iid_client_rounds.csv")
    if len(rounds) != 51 or len(clients) != 400:
        raise RuntimeError("FL_IID_ROUND_CLOSURE_FAILURE")
    if choose_best_round(rounds) != result["best_round"]:
        raise RuntimeError("FL_IID_BEST_ROUND_MISMATCH")
    stability = json.loads((ROOT / "reports/t025/stability_audit.json").read_text())
    if not stability["stable_convergence"] or stability["client_updates_received"] != 400:
        raise RuntimeError("FEDAVG_NO_LEARNING_SIGNAL")
    manifest = json.loads((ROOT / "reports/t025/client_manifest_audit.json").read_text())
    if (
        manifest["TRAIN_patient_groups"] != 27
        or manifest["total_windows"] != 9660
        or manifest["duplicate_patient_assignments"]
        or manifest["omitted_TRAIN_patients"]
    ):
        raise RuntimeError("CLIENTS_IID_V1_PATIENT_INTEGRITY_FAILURE")
    reproducibility = json.loads((ROOT / "reports/t025/reproducibility.json").read_text())
    if reproducibility["status"] != "PASS":
        raise RuntimeError("FL_IID_REPRODUCIBILITY_FAILURE")
    inventory = json.loads((ROOT / "reports/t025/artifact_hashes.json").read_text())
    for path, expected in inventory["artifacts"].items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"T025_ARTIFACT_HASH_MISMATCH: {path}")
    return {
        "status": "PASS",
        "rounds": 50,
        "client_updates": 400,
        "best_round": result["best_round"],
        "stable_convergence": True,
        "patient_integrity": "PASS",
        "reproducibility": "PASS",
        "canonical_F12_status": "NOT_FROZEN",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
