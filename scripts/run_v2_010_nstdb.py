#!/usr/bin/env python3
"""V2-010 guarded V2-only second-look session #3: NSTDB. Reuses the frozen
evaluation.noise stress-window builder/pairing (model-agnostic) unchanged; runs
MODEL_V2_FINAL (never MODEL_V1); applies CAL_V2 (never CAL_V1) via
scripts._v2_010_lib.infer_rows_v2_nstdb (a new function mirroring evaluation.noise.infer_rows,
never calling it). Prints only closure/count/hash/guard-status during exposure. Guarded: a
second invocation after COMPLETED raises V2_NSTDB_SECOND_LOOK_ALREADY_CONSUMED before any
data is touched.
"""

from __future__ import annotations

import csv
import json

import scripts._v2_010_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_second_look_guard import (
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
)

ROOT = lib.ROOT
DATASET = "NSTDB"
OUT_DIR = ROOT / "reports/model_v2/v2_010"
PREDICTIONS_PATH = OUT_DIR / "nstdb_v2_predictions.csv"

FIELDS = [
    "base_record_id", "nstdb_record_id", "snr_db", "source_right_edge_index", "pair_id",
    "label", "quality", "raw_logit", "raw_probability",
    "transferred_source_domain_probability", "frozen_threshold", "thresholded_prediction",
    "MODEL_V2_FINAL_sha256", "CAL_V2_sha256",
]


def main() -> None:
    observed = lib.observed_preconditions(ROOT, DATASET)
    check_and_begin_session(ROOT, DATASET, observed_preconditions=observed)

    try:
        paired = lib.nstdb_paired_population(ROOT)
        v2_rows = lib.infer_rows_v2_nstdb(paired, ROOT, batch_size=64)
        v1_rows = lib.read_v1_nstdb_predictions(ROOT)
        v1_pairs = {(row["pair_id"], row["snr_db"]) for row in v1_rows}
        v2_pairs = {(row["pair_id"], str(row["snr_db"])) for row in v2_rows}
        if v2_pairs != v1_pairs:
            raise lib.V2SecondLookError(
                f"NSTDB_V2_CLOSURE_MISMATCH: missing={len(v1_pairs - v2_pairs)} "
                f"extra={len(v2_pairs - v1_pairs)}"
            )

        v2_rows_sorted = sorted(v2_rows, key=lambda row: (row["pair_id"], row["snr_db"]))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with PREDICTIONS_PATH.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            for row in v2_rows_sorted:
                writer.writerow({
                    "base_record_id": row["base_record_id"],
                    "nstdb_record_id": row["nstdb_record_id"],
                    "snr_db": row["snr_db"],
                    "source_right_edge_index": row["source_right_edge_index"],
                    "pair_id": row["pair_id"],
                    "label": row["label"],
                    "quality": row["quality"],
                    "raw_logit": format(row["raw_logit"], ".17g"),
                    "raw_probability": format(row["raw_probability"], ".17g"),
                    "transferred_source_domain_probability": format(
                        row["transferred_source_domain_probability"], ".17g"
                    ),
                    "frozen_threshold": format(row["frozen_threshold"], ".17g"),
                    "thresholded_prediction": row["thresholded_prediction"],
                    "MODEL_V2_FINAL_sha256": row["MODEL_V2_FINAL_sha256"],
                    "CAL_V2_sha256": row["CAL_V2_sha256"],
                })

        summary = {
            "dataset": DATASET,
            "closure_exact": True,
            "row_count": len(v2_rows_sorted),
            "pair_id_count": len({row["pair_id"] for row in v2_rows_sorted}),
            "snr_levels": sorted({row["snr_db"] for row in v2_rows_sorted}, reverse=True),
            "prediction_table_sha256": hash_file(PREDICTIONS_PATH),
            "model_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
            "calibration_sha256": hash_file(ROOT / "artifacts/CAL_V2.json"),
        }
    except Exception as exc:
        mark_partially_consumed(ROOT, DATASET, failure_summary={"error": str(exc)})
        raise

    complete_session(ROOT, DATASET, completion_summary=summary)
    (OUT_DIR / "nstdb_access_audit.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"dataset": DATASET, "status": "COMPLETED", "rows": summary["row_count"]}))


if __name__ == "__main__":
    main()
