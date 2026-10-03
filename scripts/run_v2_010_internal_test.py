#!/usr/bin/env python3
"""V2-010 guarded V2-only second-look session #1: INTERNAL_TEST. Reuses the frozen
evaluation.internal_test window/population loader unchanged (generic I/O); runs
MODEL_V2_FINAL (never MODEL_V1) in eval/inference-only mode; applies CAL_V2 (never CAL_V1).
Prints only closure/count/hash/guard-status -- never headline metrics -- during exposure.
Guarded by nhm.model_v2_second_look_guard: a second invocation after COMPLETED raises
V2_INTERNAL_TEST_SECOND_LOOK_ALREADY_CONSUMED before any data is touched.
"""

from __future__ import annotations

import csv
import json

import numpy as np

import scripts._v2_010_lib as lib
from evaluation.calibration import (
    apply_operating_threshold,
    raw_probability_from_logit,
    source_domain_calibrated_probability,
)
from models.cal_v2_verify import load_cal_v2
from nhm.hashing import hash_file
from nhm.model_v2_second_look_guard import (
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
)

ROOT = lib.ROOT
DATASET = "INTERNAL_TEST"
OUT_DIR = ROOT / "reports/model_v2/v2_010"
PREDICTIONS_PATH = OUT_DIR / "internal_v2_predictions.csv"

FIELDS = [
    "example_id", "participant_group_id", "record_id", "prediction_timestamp_us",
    "ecg_quality", "label", "raw_logit", "raw_probability",
    "source_domain_calibrated_probability", "threshold", "thresholded_prediction",
    "model_id", "model_sha", "calibration_id",
]


def main() -> None:
    observed = lib.observed_preconditions(ROOT, DATASET)
    check_and_begin_session(ROOT, DATASET, observed_preconditions=observed)

    try:
        population = lib.load_internal_test_population(ROOT)
        v1_rows = lib.read_v1_internal_predictions(ROOT)
        v1_ids = {row["example_id"] for row in v1_rows}
        v2_ids = {row["example_id"] for row in population.rows}
        if v2_ids != v1_ids:
            raise lib.V2SecondLookError(
                f"INTERNAL_TEST_V2_CLOSURE_MISMATCH: missing={len(v1_ids - v2_ids)} "
                f"extra={len(v2_ids - v1_ids)}"
            )

        logits = lib.extract_logits_v2_internal(population, ROOT, batch_size=64)
        raw = raw_probability_from_logit(logits)
        cal = load_cal_v2(ROOT)
        calibrated = source_domain_calibrated_probability(logits, cal)
        predictions = apply_operating_threshold(calibrated, cal)
        cal_sha = hash_file(ROOT / "artifacts/CAL_V2.json")
        model_sha = hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt")

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with PREDICTIONS_PATH.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            for row, label, logit, raw_p, cal_p, prediction in zip(
                population.rows, population.labels, logits, raw, calibrated, predictions,
                strict=True,
            ):
                writer.writerow({
                    "example_id": row["example_id"],
                    "participant_group_id": row["participant_group_id"],
                    "record_id": row["record_id"],
                    "prediction_timestamp_us": row["prediction_timestamp_us"],
                    "ecg_quality": row["ecg_quality"],
                    "label": int(label),
                    "raw_logit": format(float(logit), ".17g"),
                    "raw_probability": format(float(raw_p), ".17g"),
                    "source_domain_calibrated_probability": format(float(cal_p), ".17g"),
                    "threshold": format(float(cal["threshold"]), ".17g"),
                    "thresholded_prediction": int(prediction),
                    "model_id": "MODEL_V2_FINAL",
                    "model_sha": model_sha,
                    "calibration_id": "CAL_V2",
                })

        summary = {
            "dataset": DATASET,
            "closure_exact": True,
            "row_count": len(population.rows),
            "positive_count": int(np.sum(population.labels == 1)),
            "negative_count": int(np.sum(population.labels == 0)),
            "prediction_table_sha256": hash_file(PREDICTIONS_PATH),
            "model_sha256": model_sha,
            "calibration_sha256": cal_sha,
        }
    except Exception as exc:
        mark_partially_consumed(ROOT, DATASET, failure_summary={"error": str(exc)})
        raise

    complete_session(ROOT, DATASET, completion_summary=summary)
    (OUT_DIR / "internal_access_audit.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"dataset": DATASET, "status": "COMPLETED", "rows": summary["row_count"]}))


if __name__ == "__main__":
    main()
