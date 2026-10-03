#!/usr/bin/env python3
"""C-V2-011-COMPLETENESS-SEMANTICS step 2: preserve exactly what happened in the first V2-011
case-access session (the run that tripped the prompt-introduced 1e-3 completeness gate).
Pure provenance: reads already-written outputs, never recomputes IG, never touches the model.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_011"
METHOD_COMMIT = "1bb81d52876ff70dbc1eba742a2b1f1909b8523d"


def main() -> None:
    audit = json.loads((OUT / "case_access_audit.json").read_text())
    with (OUT / "ig_completeness.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    cases = {}
    for r in rows:
        absolute, relative = float(r["absolute_delta"]), float(r["relative_delta"])
        cases[r["case_type"]] = {
            "example_id": r["example_id"],
            "completeness_signed_delta": float(r["signed_delta"]),
            "completeness_absolute_delta": absolute,
            "completeness_relative_delta": relative,
            "prompt_rule_abs_lt_1e-3_or_rel_lt_1e-3": "PASS" if r["pass"] == "True" else "FAIL",
        }
    summary = {
        "classification": "FAILED_DIAGNOSTIC_RUN_PRESERVED_AS_IMMUTABLE_HISTORY",
        "method_commit": METHOD_COMMIT,
        "stop_code_raised_at_the_time": "V2_011_IG_COMPLETENESS_FAILURE",
        "stop_code_basis": "prompt-introduced hard rule absolute_delta<1e-3 OR relative_delta<1e-3",
        "ig_method_unchanged_since_method_commit": True,
        "cases": cases,
        "cases_exceeding_prompt_rule": sorted(
            k for k, v in cases.items() if v["prompt_rule_abs_lt_1e-3_or_rel_lt_1e-3"] == "FAIL"),
        "largest_absolute_residual": max(v["completeness_absolute_delta"] for v in cases.values()),
        "logits_consistent_with_v2_010": audit["all_logits_consistent_with_v2_010"],
        "repeat_runs_within_tolerance": json.loads(
            (OUT / "ig_reproducibility.json").read_text())["status"] == "PASS",
        "model_mutated": audit["model_mutated"],
        "v2_011_status_marked_pass": False,
        "v2g10_status_marked_pass": False,
        "explainability_v2_frozen": False,
        "scratch_note": (
            "Before the method commit, prediction-table error-analysis code was executed "
            "interactively for development/testing only; it wrote no result files and its "
            "console output is NON_AUTHORITATIVE_PRELOCK_SCRATCH. The authoritative tables are "
            "regenerated after the corrective semantics lock."
        ),
    }
    (OUT / "failed_diagnostic_run_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    files = [
        "case_access_audit.json", "case_access_guard.json", "ig_completeness.csv",
        "ig_reproducibility.json", "failed_diagnostic_run_summary.json",
        *(f"cases/{c}_{s}" for c in ("TP", "TN", "FP", "FN")
          for s in ("attribution.csv", "raw_ecg.csv", "annotations.csv", "figure.svg")),
    ]
    manifest = {
        "run": "V2-011 first case-access session (failed diagnostic run)",
        "method_commit": METHOD_COMMIT,
        "guard_state": json.loads((OUT / "case_access_guard.json").read_text())["state"],
        "frozen_case_ids": audit["frozen_case_ids"],
        "artifact_sha256": {f"reports/model_v2/v2_011/{f}": hash_file(OUT / f) for f in files},
    }
    (OUT / "failed_diagnostic_run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["cases_exceeding_prompt_rule"]))


if __name__ == "__main__":
    main()
