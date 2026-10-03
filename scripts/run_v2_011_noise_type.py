#!/usr/bin/env python3
"""V2-011 guarded session 2: the single controlled C031-derived V2 noise-type run (720 source
windows x 3 noise types x 6 SNRs = 18 cells). No V1 inference; V1 comparator values come only
from the frozen C031 evidence. Guarded by V2_NOISE_TYPE_ERROR_ANALYSIS_ONCE. Does not touch
V2-010 runtime acceptance.
"""

from __future__ import annotations

import json

import scripts._v2_011_analysis as analysis
import scripts._v2_011_cases as cases
from nhm.hashing import hash_file
from nhm.model_v2_explainability_guard import (
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
)

ROOT = cases.ROOT
OUT = cases.OUT
GUARD = "NOISE_TYPE"


def main() -> None:
    protocol = analysis.verify_noise_protocol(ROOT)
    if protocol["status"] != "PASS":
        raise RuntimeError("V2_011_C031_NOISE_PROTOCOL_NOT_REPRODUCIBLE")
    check_and_begin_session(
        ROOT, GUARD, observed_preconditions=cases.observed_preconditions(ROOT, GUARD)
    )
    try:
        rows, fixtures, mutated = analysis.run_noise_matrix_v2(ROOT)
        if mutated:
            raise RuntimeError("MODEL_V2_FINAL_STATE_MUTATED_DURING_NOISE_TYPE_RUN")
        pred_path = OUT / "noise_type_v2_predictions.csv"
        cases.write_csv(pred_path, rows, analysis.NOISE_PRED_FIELDS)
    except Exception as exc:
        mark_partially_consumed(ROOT, GUARD, failure_summary={"error": str(exc)})
        raise
    summary = {
        "prediction_rows": len(rows),
        "cells": len({(r["noise_type"], r["snr_db"]) for r in rows}),
        "source_windows": len({r["base_window_id"] for r in rows}),
        "prediction_table_sha256": hash_file(pred_path),
        "v1_inference_rerun": False,
        "standalone_noise_labels_fabricated": False,
        "model_mutated": mutated,
        "model_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
        "cal_sha256": hash_file(ROOT / "artifacts/CAL_V2.json"),
        "fixture_count": len(fixtures),
        "fixtures_all_pass": all(f["status"] == "PASS" for f in fixtures),
    }
    complete_session(ROOT, GUARD, completion_summary=summary)
    cases.write_json(OUT / "noise_type_access_audit.json", {**summary, "fixtures": fixtures})

    metrics = analysis.aggregate_noise(analysis.read_noise_predictions(pred_path))
    cases.write_csv(OUT / "noise_type_metrics.csv", metrics, list(metrics[0]))
    comparison = analysis.compare_noise_to_v1(metrics, ROOT)
    cases.write_csv(OUT / "noise_type_comparison_v1_v2.csv", comparison, list(comparison[0]))
    print(json.dumps({"status": "COMPLETED", "rows": summary["prediction_rows"],
                      "cells": summary["cells"]}))


if __name__ == "__main__":
    main()
