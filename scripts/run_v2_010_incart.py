#!/usr/bin/env python3
"""V2-010 guarded V2-only second-look session #2: INCART. Reuses the frozen
evaluation.external_incart record-window extractor and _infer_windows (model passed as a
parameter) unchanged; runs MODEL_V2_FINAL (never MODEL_V1); applies CAL_V2 (never CAL_V1).
Patient clusters are participant_group_id (one cluster per patient, multi-recording patients
remain one cluster, exactly as F11 defined). Prints only closure/count/hash/guard-status
during exposure. Guarded: a second invocation after COMPLETED raises
V2_INCART_SECOND_LOOK_ALREADY_CONSUMED before any data is touched.
"""

from __future__ import annotations

import csv
import json

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
DATASET = "INCART"
OUT_DIR = ROOT / "reports/model_v2/v2_010"
PREDICTIONS_PATH = OUT_DIR / "incart_v2_predictions.csv"

FIELDS = [
    "example_id", "participant_group_id", "source_patient_id", "record_id",
    "prediction_timestamp_us", "quality", "label", "raw_logit", "raw_probability",
    "source_domain_calibrated_probability", "calibration_domain", "threshold",
    "thresholded_prediction", "model_id", "model_sha", "calibration_id", "calibration_sha",
    "preproc_id", "map_id", "target_id",
]


def main() -> None:
    observed = lib.observed_preconditions(ROOT, DATASET)
    check_and_begin_session(ROOT, DATASET, observed_preconditions=observed)

    try:
        rows, accessed_paths = lib.extract_incart_v2_rows(ROOT, batch_size=64)
        v1_rows = lib.read_v1_incart_predictions(ROOT)
        v1_ids = {row["example_id"] for row in v1_rows}
        v2_ids = {row["example_id"] for row in rows}
        if v2_ids != v1_ids:
            raise lib.V2SecondLookError(
                f"INCART_V2_CLOSURE_MISMATCH: missing={len(v1_ids - v2_ids)} "
                f"extra={len(v2_ids - v1_ids)}"
            )

        cal = load_cal_v2(ROOT)
        cal_sha = hash_file(ROOT / "artifacts/CAL_V2.json")
        model_sha = hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt")
        rows = sorted(rows, key=lambda row: row["example_id"])

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with PREDICTIONS_PATH.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                logit = row["raw_logit"]
                raw_p = float(raw_probability_from_logit(logit))
                cal_p = float(source_domain_calibrated_probability(logit, cal))
                prediction = int(apply_operating_threshold(cal_p, cal))
                writer.writerow({
                    "example_id": row["example_id"],
                    "participant_group_id": row["participant_group_id"],
                    "source_patient_id": row["source_patient_id"],
                    "record_id": row["record_id"],
                    "prediction_timestamp_us": row["prediction_timestamp_us"],
                    "quality": row["ecg_quality"],
                    "label": row["label"],
                    "raw_logit": format(float(logit), ".17g"),
                    "raw_probability": format(raw_p, ".17g"),
                    "source_domain_calibrated_probability": format(cal_p, ".17g"),
                    "calibration_domain": cal["calibration_domain"],
                    "threshold": format(float(cal["threshold"]), ".17g"),
                    "thresholded_prediction": prediction,
                    "model_id": "MODEL_V2_FINAL",
                    "model_sha": model_sha,
                    "calibration_id": "CAL_V2",
                    "calibration_sha": cal_sha,
                    "preproc_id": row["preprocess_id"],
                    "map_id": row["map_id"],
                    "target_id": row["target_id"],
                })

        summary = {
            "dataset": DATASET,
            "closure_exact": True,
            "row_count": len(rows),
            "accessed_path_count": len(set(accessed_paths)),
            "patient_cluster_count": len({row["participant_group_id"] for row in rows}),
            "prediction_table_sha256": hash_file(PREDICTIONS_PATH),
            "model_sha256": model_sha,
            "calibration_sha256": cal_sha,
        }
    except Exception as exc:
        mark_partially_consumed(ROOT, DATASET, failure_summary={"error": str(exc)})
        raise

    complete_session(ROOT, DATASET, completion_summary=summary)
    (OUT_DIR / "incart_access_audit.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"dataset": DATASET, "status": "COMPLETED", "rows": summary["row_count"]}))


if __name__ == "__main__":
    main()
