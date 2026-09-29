#!/usr/bin/env python3
"""Verify frozen T019 results without repeating NSTDB model inference."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.calibration import load_cal_v1, verify_cal_v1  # noqa: E402
from evaluation.internal_test import verify_internal_test_freeze  # noqa: E402
from evaluation.noise import SNR_LEVELS, summarize_prediction_rows, validate_pair_rows  # noqa: E402
from models.model_freeze import verify_frozen_model_v1  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402

EXPECTED_CONFIG_SHA = "66edae0c81fd409e479521321c420c1d578f2ecf1b52e06abe52083e8c08b50c"
EXPECTED_METHOD_SHA = "6e04f59ed00f53820a6db5179926f1f0c87e6c1f3ab80e3c41bdbd79c50e2d70"
EXPECTED_MODEL_SHA = "021352eb067932015b657f0570ac155f8ef00af2d43864e13a110d0252bc7bfe"
EXPECTED_CAL_SHA = "d225b20957913439fd532a4de4d23acf573a88d06366e71bf3b8a7673e63479b"
EXPECTED_INTERNAL_REPORT_SHA = "c2f48e80a7826eb4383151310c7b107f717a7e2bb71c2258a7c3a08ab922309e"
EXPECTED_INTERNAL_GUARD_SHA = "2fc3749b93357d5a3f93a4e8b2ae07ec742f7a78ebb7a238c734e9ae1e878e67"


def _load_rows(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        source = list(csv.DictReader(handle))
    integer_fields = {"snr_db", "source_right_edge_index", "label", "thresholded_prediction"}
    float_fields = {
        "raw_logit",
        "raw_probability",
        "transferred_source_domain_probability",
        "frozen_threshold",
    }
    rows: list[dict[str, object]] = []
    for item in source:
        row: dict[str, object] = dict(item)
        for key in integer_fields:
            row[key] = int(item[key])
        for key in float_fields:
            row[key] = float(item[key])
        rows.append(row)
    return rows


def _assert_metrics_equal(observed: list[dict], expected: list[dict]) -> None:
    if len(observed) != len(expected):
        raise RuntimeError("NSTDB_METRIC_ROW_COUNT_MISMATCH")
    for left, right in zip(observed, expected, strict=True):
        if left.keys() != right.keys():
            raise RuntimeError("NSTDB_METRIC_SCHEMA_MISMATCH")
        for key in left:
            if isinstance(left[key], float):
                if not math.isclose(left[key], float(right[key]), rel_tol=0.0, abs_tol=1e-15):
                    raise RuntimeError(f"NSTDB_METRIC_MISMATCH: {key}")
            elif left[key] != right[key]:
                raise RuntimeError(f"NSTDB_METRIC_MISMATCH: {key}")


def verify_noise_robustness(
    root: Path = ROOT,
    *,
    predictions_path: Path | None = None,
) -> dict[str, object]:
    verify_frozen_model_v1(root)
    verify_cal_v1(root)
    verify_internal_test_freeze(root)
    expected_hashes = {
        root / "configs/noise_robustness_v1.yaml": EXPECTED_CONFIG_SHA,
        root / "evaluation/noise.py": EXPECTED_METHOD_SHA,
        root / "checkpoints/MODEL_V1.pt": EXPECTED_MODEL_SHA,
        root / "artifacts/CAL_V1.json": EXPECTED_CAL_SHA,
        root / "reports/internal_test.json": EXPECTED_INTERNAL_REPORT_SHA,
        root / "artifacts/internal_test_access_v1.json": EXPECTED_INTERNAL_GUARD_SHA,
    }
    for path, expected in expected_hashes.items():
        if hash_file(path) != expected:
            raise RuntimeError(f"NSTDB_FROZEN_INPUT_HASH_MISMATCH: {path}")

    path = predictions_path or root / "reports/t019/nstdb_predictions.csv"
    rows = _load_rows(path)
    if len(rows) != 4320:
        raise RuntimeError("NSTDB_PREDICTION_ROW_COUNT_MISMATCH")
    validate_pair_rows(rows)
    cal = load_cal_v1(root)
    threshold = float(cal["threshold"])
    for row in rows:
        if row["MODEL_V1_sha256"] != EXPECTED_MODEL_SHA:
            raise RuntimeError("NSTDB_MODEL_BINDING_MISMATCH")
        if row["CAL_V1_sha256"] != EXPECTED_CAL_SHA:
            raise RuntimeError("NSTDB_CAL_BINDING_MISMATCH")
        if row["frozen_threshold"] != threshold:
            raise RuntimeError("NSTDB_THRESHOLD_BINDING_MISMATCH")
        probability = float(row["transferred_source_domain_probability"])
        expected_prediction = int(probability >= threshold)
        if row["thresholded_prediction"] != expected_prediction:
            raise RuntimeError("NSTDB_THRESHOLD_SEMANTICS_MISMATCH")

    pooled, by_record = summarize_prediction_rows(rows)
    report = json.loads((root / "reports/noise_robustness.json").read_text(encoding="utf-8"))
    _assert_metrics_equal(pooled, report["per_snr_pooled_results"])
    _assert_metrics_equal(by_record, report["per_record_results"])
    if [row["snr_db"] for row in pooled] != list(SNR_LEVELS):
        raise RuntimeError("NSTDB_SNR_ORDER_MISMATCH")
    if report["reference_is_clean"] is not False or report["no_tuning"] is not True:
        raise RuntimeError("NSTDB_CLAIM_OR_TUNING_CONTRACT_MISMATCH")
    pure = json.loads(
        (root / "reports/t019/pure_noise_source_audit.json").read_text(encoding="utf-8")
    )
    if pure["predictive_labels_fabricated"] or pure["used_for_AAMI_classification_metrics"]:
        raise RuntimeError("NSTDB_PURE_NOISE_LABEL_VIOLATION")
    return {
        "status": "PASS",
        "prediction_rows": len(rows),
        "pair_ids": len(rows) // 6,
        "SNR_levels": list(SNR_LEVELS),
        "method_config_sha256": EXPECTED_CONFIG_SHA,
        "method_code_sha256": EXPECTED_METHOD_SHA,
        "model_sha256": EXPECTED_MODEL_SHA,
        "calibration_sha256": EXPECTED_CAL_SHA,
        "model_inference_repeated": False,
    }


def main() -> None:
    print(json.dumps(verify_noise_robustness(ROOT), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
