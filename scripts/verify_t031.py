#!/usr/bin/env python3
"""Verify T031 method bindings, canonical outputs, scope, and inventory."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.verify_t029 import verify as verify_t029

ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    verify_t029()
    lock = json.loads((ROOT / "artifacts/EXPLAINABILITY_V1_METHOD.lock.json").read_text())
    if lock["status"] != "FROZEN_COMPONENT_METHOD":
        raise RuntimeError("EXPLAINABILITY_METHOD_NOT_FROZEN")
    for path, expected in lock["bound_artifacts"].items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"EXPLAINABILITY_METHOD_TAMPER:{path}")
    with (ROOT / "reports/t031/ig_completeness.csv").open(newline="") as handle:
        complete = list(csv.DictReader(handle))
    if [row["case_type"] for row in complete] != ["TP", "TN", "FP", "FN"]:
        raise RuntimeError("EXPLAINABILITY_CASE_SET_MISMATCH")
    if not all(row["pass"] == "True" for row in complete):
        raise RuntimeError("IG_COMPLETENESS_FAILURE")
    wearable = json.loads((ROOT / "reports/t031/wearable_slice_status.json").read_text())
    if wearable["status"] != "DEFERRED_T030_HARDWARE":
        raise RuntimeError("WEARABLE_DEFERRAL_MISMATCH")
    scope = json.loads((ROOT / "reports/t031/scope_audit.json").read_text())
    if scope["status"] != "PASS" or any(
        scope[key]
        for key in (
            "MODEL_V1_modified",
            "model_training",
            "threshold_tuning",
            "CAL_fitting",
            "PREPROC_change",
            "INCART_adaptation",
            "hardware",
            "WEARABLE_V1_fabrication",
        )
    ):
        raise RuntimeError("T031_SCOPE_FAILURE")
    inventory = json.loads((ROOT / "reports/t031/artifact_hashes.json").read_text())
    for path, expected in inventory.items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"T031_ARTIFACT_HASH_MISMATCH:{path}")
    return {
        "status": "PASS",
        "method": "EXPLAINABILITY_V1",
        "cases": 4,
        "completeness": "PASS",
        "error_analysis": "PASS",
        "wearable": "DEFERRED_T030_HARDWARE",
        "G17": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
