#!/usr/bin/env python3
"""V2-011 guarded session 1: the four frozen Integrated-Gradients cases. Only the four frozen
example IDs may be materialized; no bulk INTERNAL_TEST scoring and no new performance table.
Guarded by V2_EXPLAINABILITY_CASE_ACCESS_ONCE.
"""

from __future__ import annotations

import json
import sys

import scripts._v2_011_cases as cases
from nhm.hashing import hash_file
from nhm.model_v2_explainability_guard import (
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
)

ROOT = cases.ROOT
OUT = cases.OUT
GUARD = "CASE_ACCESS"


def main() -> None:
    check_and_begin_session(
        ROOT, GUARD, observed_preconditions=cases.observed_preconditions(ROOT, GUARD)
    )
    try:
        result = cases.run_all_cases(ROOT)
    except Exception as exc:
        mark_partially_consumed(ROOT, GUARD, failure_summary={"error": str(exc)})
        raise
    rows = result["cases"]
    fields = ["case_type", "example_id", "F_x", "F_baseline", "output_difference",
              "attribution_sum", "signed_delta", "absolute_delta", "relative_delta", "pass"]
    cases.write_csv(OUT / "ig_completeness.csv", [{k: r[k] for k in fields} for r in rows], fields)
    max_diff = max(r["reproducibility"]["signed_max_abs_difference"] for r in rows)
    cases.write_json(
        OUT / "ig_reproducibility.json",
        {
            "runs_per_case": 2,
            "per_case": {r["case_type"]: r["reproducibility"] for r in rows},
            "maximum_absolute_attribution_difference": max_diff,
            "all_within_tolerance": all(r["reproducibility"]["within_tolerance"] for r in rows),
            "better_looking_run_selected": False,
            "status": "PASS" if all(r["reproducibility"]["within_tolerance"] for r in rows)
            else "FAIL",
        },
    )
    opened = sorted({p for r in rows for p in r["cache_paths_opened"]})
    summary = {
        "frozen_case_ids": {r["case_type"]: r["example_id"] for r in rows},
        "materialized_windows": len(rows),
        "windows_materialized_outside_frozen_manifest": 0,
        "bulk_internal_test_scoring": False,
        "new_internal_test_performance_table": False,
        "source_record_caches_opened": opened,
        "source_records_read_for_raw_ecg_and_annotations": sorted({r["record_id"] for r in rows}),
        "all_completeness_pass": all(r["pass"] for r in rows),
        "all_logits_consistent_with_v2_010": all(r["logit_consistent_with_v2_010"] for r in rows),
        "model_mutated": result["model_mutated"],
        "checkpoint_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
    }
    complete_session(ROOT, GUARD, completion_summary=summary)
    cases.write_json(OUT / "case_access_audit.json", {**summary, "cases": rows})
    print(json.dumps({"status": "COMPLETED", "completeness": summary["all_completeness_pass"],
                      "model_mutated": summary["model_mutated"]}))
    if not summary["all_completeness_pass"]:
        sys.exit("V2_011_IG_COMPLETENESS_FAILURE")
    if summary["model_mutated"] or not summary["all_logits_consistent_with_v2_010"]:
        sys.exit("V2_011_IG_INTEGRITY_FAILURE")


if __name__ == "__main__":
    main()
