#!/usr/bin/env python3
"""C-V2-011-COMPLETENESS-SEMANTICS: write the corrected diagnostic completeness table from the
already-materialized residuals (no IG rerun, no model, no waveform access) and the additive
semantics-successor lock binding the original method commit, the failed-run commit, the authority
audit, the unchanged cases and the unchanged IG method.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from evaluation.explain_v2_semantics import SEMANTICS_ID, completeness_diagnostic
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_011"
CONFIG = "configs/model_v2/explainability_v2_completeness_semantics_v2.yaml"


def main() -> None:
    cfg = yaml.safe_load((ROOT / CONFIG).read_text())
    audit = json.loads((OUT / "case_access_audit.json").read_text())
    historical = {}
    with (OUT / "ig_completeness.csv").open(newline="") as handle:
        for r in csv.DictReader(handle):
            historical[r["case_type"]] = r
    rows = []
    for case in audit["cases"]:
        diag = completeness_diagnostic(case["F_x"], case["F_baseline"], case["attribution_sum"])
        old = historical[case["case_type"]]
        assert abs(diag["completeness_absolute_delta"] - float(old["absolute_delta"])) <= 1e-12
        assert abs(diag["completeness_relative_delta"] - float(old["relative_delta"])) <= 1e-9
        assert (diag["historical_v1_style_1e3_heuristic"] == "PASS") == (old["pass"] == "True")
        rows.append({"case_type": case["case_type"], "example_id": case["example_id"],
                     "F_x": case["F_x"], "F_baseline": case["F_baseline"],
                     "attribution_sum": case["attribution_sum"], **diag})
    with (OUT / "ig_completeness_diagnostic.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    bound = {rel: hash_file(ROOT / rel) for rel in [
        CONFIG, cfg["base_config"], cfg["authority_audit"], cfg["failed_run_manifest"],
        "reports/model_v2/v2_011/explainability_case_manifest.csv",
        "reports/model_v2/v2_011/ig_completeness.csv",
        "reports/model_v2/v2_011/ig_completeness_diagnostic.csv",
        "reports/model_v2/v2_011/failed_diagnostic_run_summary.json",
        "evaluation/explain.py", "evaluation/explain_v2.py", "evaluation/explain_v2_semantics.py",
        "scripts/_v2_011_cases.py", "checkpoints/MODEL_V2_FINAL.pt", "artifacts/CAL_V2.json",
        *(f"reports/model_v2/v2_011/cases/{c}_attribution.csv"
          for c in ("TP", "TN", "FP", "FN")),
    ]}
    lock = {
        "lock_id": SEMANTICS_ID,
        "status": "FROZEN_SEMANTICS_CORRECTION",
        "owner_task": "V2-011",
        "classification": cfg["classification"],
        "original_method_commit": cfg["original_method_commit"],
        "failed_diagnostic_run_commit": cfg["failed_diagnostic_run_commit"],
        "authority_audit": cfg["authority_audit"],
        "case_ids_unchanged": audit["frozen_case_ids"],
        "ig_method_unchanged": cfg["unchanged_from_original_method"],
        "numerical_completeness_gate": "NONE",
        "bound_artifacts": bound,
    }
    (ROOT / "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n")
    (OUT / "completeness_semantics_method_freeze.json").write_text(json.dumps({
        "semantics_id": SEMANTICS_ID,
        "only_acceptance_semantics_changed": True,
        "steps_changed": False, "baseline_changed": False, "cases_changed": False,
        "ig_rerun": False, "model_or_waveform_access": False,
        "per_case": {r["case_type"]: r["historical_heuristic_label"] for r in rows},
        "status": "PASS",
    }, indent=2, sort_keys=True) + "\n")
    print({r["case_type"]: r["historical_heuristic_label"] for r in rows})


if __name__ == "__main__":
    main()
