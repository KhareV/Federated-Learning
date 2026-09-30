#!/usr/bin/env python3
"""Verify T024 entirely from toy/model-vector artifacts; no real data access."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from federated.server_app import run_toy_flower_round  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from scripts.generate_t024_evidence import adapter_run, analytical_run  # noqa: E402


def verify() -> dict[str, object]:
    toy = json.loads((ROOT / "reports/t024/toy_aggregation.json").read_text())
    if toy != analytical_run() or toy["status"] != "PASS":
        raise RuntimeError("TOY_AGGREGATION_MISMATCH")
    smoke = json.loads((ROOT / "reports/t024/fl_smoke.json").read_text())
    current_smoke = run_toy_flower_round()
    if smoke["run_1"] != current_smoke or smoke["flower_output"] != [14.0, 26.0]:
        raise RuntimeError("FLOWER_REFERENCE_MISMATCH")
    adapter = json.loads((ROOT / "reports/t024/model_adapter_audit.json").read_text())
    if adapter != adapter_run() or adapter["maximum_logit_difference"] != 0.0:
        raise RuntimeError("MODEL_ADAPTER_PREDICTION_DRIFT")
    inventory = json.loads((ROOT / "reports/t024/artifact_hashes.json").read_text())
    for path, expected in inventory["artifacts"].items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"T024_ARTIFACT_HASH_MISMATCH: {path}")
    with (ROOT / "manifests/freeze_registry_v1.csv").open(newline="", encoding="utf-8") as handle:
        freezes = {row["freeze_id"]: row for row in csv.DictReader(handle)}
    if (
        freezes["F12"]["version_id"] != "FL_CONFIG_V1"
        or freezes["F12"]["current_status"] != "NOT_FROZEN"
    ):
        raise RuntimeError("T024_FEDERATED_FREEZE_MISMATCH")
    return {
        "status": "PASS",
        "analytical_aggregation": "PASS",
        "Flower_reference_equivalence": "PASS",
        "MODEL_V1_adapter": "PASS",
        "artifact_hashes": "PASS",
        "federated_freeze_id": "F12",
        "federated_freeze_status": "NOT_FROZEN",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
