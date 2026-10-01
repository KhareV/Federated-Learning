#!/usr/bin/env python3
"""Verify corrective checkpoint C031-EA without reopening G17."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from evaluation.metrics import pooled_binary_metrics
from nhm.hashing import hash_file
from scripts.verify_t031 import verify as verify_t031

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify() -> dict[str, object]:
    verify_t031()
    lock = json.loads((ROOT / "artifacts/C031_ERROR_ANALYSIS_V1.lock.json").read_text())
    for path, expected in lock["bound_artifacts"].items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"C031_METHOD_TAMPER:{path}")
    base = read_csv(ROOT / "reports/t031/c031_noise_base_manifest.csv")
    matrix = read_csv(ROOT / "reports/t031/noise_type_snr_slice_v2.csv")
    predictions = read_csv(ROOT / "reports/t031/noise_type_predictions_v2.csv")
    if len(base) != 720 or sum(int(row["label"]) for row in base) != 469:
        raise RuntimeError("NOISE_TYPE_BASE_WINDOW_CONFLICT")
    if len(matrix) != 18 or len(predictions) != 12960:
        raise RuntimeError("C031_MATRIX_CLOSURE_FAILURE")
    for metric in matrix:
        selected = [
            row
            for row in predictions
            if row["noise_type"] == metric["noise_type"] and row["snr_db"] == metric["snr_db"]
        ]
        labels = np.asarray([int(row["label"]) for row in selected])
        probabilities = np.asarray([float(row["calibrated_probability"]) for row in selected])
        decisions = np.asarray([int(row["thresholded_prediction"]) for row in selected])
        recomputed = pooled_binary_metrics(
            labels,
            probabilities,
            decisions,
            np.asarray([row["base_record_id"] for row in selected]),
            allow_undefined=False,
        )
        if abs(float(metric["AUPRC"]) - float(recomputed["AUPRC"])) > 1e-12:
            raise RuntimeError("C031_METRIC_RECOMPUTATION_FAILURE")
    fixtures = json.loads((ROOT / "reports/t031/c031_noise_fixture_audit.json").read_text())
    if fixtures["status"] != "PASS" or not fixtures["same_segment_across_snr"]:
        raise RuntimeError("C031_NOISE_FIXTURE_FAILURE")
    inventory = json.loads((ROOT / "reports/t031/c031_artifact_hashes.json").read_text())
    for path, expected in inventory.items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"C031_ARTIFACT_HASH_MISMATCH:{path}")
    return {
        "checkpoint": "C031-EA",
        "status": "PASS",
        "patients": 6,
        "base_windows": 720,
        "matrix_rows": 18,
        "G17": "PASS",
        "T031": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
