#!/usr/bin/env python3
"""V2-011: serialize EXPLAINABILITY_V2 (final report + additive method lock) from the frozen
case outputs, the error-analysis tables and the controlled noise-type run. Pure assembly:
every number is read back from already-frozen result files.
"""

from __future__ import annotations

import json
import subprocess

import yaml

import scripts._v2_011_cases as cases
from evaluation.explain_v2_semantics import SEMANTICS_ID, completeness_diagnostic
from nhm.hashing import hash_file

ROOT = cases.ROOT
OUT = cases.OUT
CLAIM = (
    "Integrated Gradients identifies normalized input regions that contribute to "
    "MODEL_V2_FINAL's pre-sigmoid logit under the specified zero baseline. Engineering "
    "model-contribution diagnostic only: not a causal physiological explanation, not a "
    "clinical explanation, and not proof of model trustworthiness. Error-analysis "
    "associations are descriptive. Authorizes parallel research artifacts only, not a "
    "runtime switch."
)
CLAIM_FIELDS = {
    "causal_physiological_explanation": False,
    "clinical_explanation": False,
    "model_trustworthiness_proof": False,
    "runtime_switch_authorized": False,
}


def method_commit() -> str:
    log = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", "scripts/freeze_v2_011_method.py"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.split()
    if not log:
        raise RuntimeError("V2_011_METHOD_COMMIT_NOT_FOUND")
    return log[-1]


def corrective_commit() -> str:
    log = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--",
         "configs/model_v2/explainability_v2_completeness_semantics_v2.yaml"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.split()
    if not log:
        raise RuntimeError("V2_011_CORRECTIVE_METHOD_COMMIT_NOT_FOUND")
    return log[-1]


def main() -> None:
    config = cases.load_config(ROOT)
    sem_cfg = yaml.safe_load((ROOT / "configs/model_v2/explainability_v2_completeness_semantics_v2"
                              ".yaml").read_text())
    repro = json.loads((OUT / "ig_reproducibility.json").read_text())
    manifest_rows = cases.read_csv(cases.CASE_MANIFEST_PATH)
    recomputed, _ = cases.build_case_manifest_rows(ROOT)
    audit = json.loads((OUT / "case_access_audit.json").read_text())
    commit = method_commit()
    noise_protocol = json.loads((OUT / "noise_type_protocol_audit.json").read_text())
    pred = {
        "internal": hash_file(ROOT / "reports/model_v2/v2_010/internal_v2_predictions.csv"),
        "incart": hash_file(ROOT / "reports/model_v2/v2_010/incart_v2_predictions.csv"),
        "nstdb": hash_file(ROOT / "reports/model_v2/v2_010/nstdb_v2_predictions.csv"),
    }
    case_fields = ["case_type", "example_id", "record_id", "F_x", "F_baseline",
                   "output_difference", "attribution_sum", "max_abs_attribution_index",
                   "window_start_s", "window_end_s", "attribution_sha256", "raw_sha256",
                   "annotations_sha256", "figure_sha256"]
    case_entries = []
    for c in audit["cases"]:
        entry = {k: c[k] for k in case_fields}
        entry["completeness_diagnostic"] = completeness_diagnostic(
            c["F_x"], c["F_baseline"], c["attribution_sum"])
        case_entries.append(entry)
    diagnostics = [e["completeness_diagnostic"] for e in case_entries]
    compliance = {
        "target_exact": config["target"] == "MODEL_V2_FINAL_PRE_SIGMOID_LOGIT",
        "baseline_exact": config["baseline"] == "ALL_ZERO_NORMALIZED_INPUT",
        "gauss_legendre_64_exact": config["integration"] == "GAUSS_LEGENDRE"
        and config["steps"] == 64,
        "eval_mode": audit["model_mutated"] is False and "eval" in config["model_mode"],
        "signed_export": all("signed_ig" in cases.read_csv(
            OUT / f"cases/{c['case_type']}_attribution.csv")[0] for c in audit["cases"]),
        "per_window_absolute_overlay": config["visual_overlay"]
        == "PER_WINDOW_ABSOLUTE_ATTRIBUTION_NORMALIZED_BY_WINDOW_MAX",
        "cases_predeclared_and_unchanged": [dict(r) for r in manifest_rows]
        == [{k: str(v) for k, v in r.items()} for r in recomputed],
        "completeness_diagnostic_saved": all(
            "completeness_absolute_delta" in d for d in diagnostics),
        "raw_ecg_and_annotations_present": all(
            len(cases.read_csv(OUT / f"cases/{c['case_type']}_raw_ecg.csv")) == 3600
            and len(cases.read_csv(OUT / f"cases/{c['case_type']}_annotations.csv")) > 0
            for c in audit["cases"]),
        "reproducible": repro["status"] == "PASS",
        "non_mutating": audit["model_mutated"] is False,
        "logits_consistent_with_v2_010": audit["all_logits_consistent_with_v2_010"] is True,
    }
    compliance["status"] = "PASS" if all(compliance.values()) else "FAIL"
    largest_abs = max(d["completeness_absolute_delta"] for d in diagnostics)
    largest_rel = max(d["completeness_relative_delta"] for d in diagnostics)
    report = {
        "method_id": "EXPLAINABILITY_V2",
        "owner_task": "V2-011",
        "status": "FROZEN_EXPLAINABILITY",
        "model_id": "MODEL_V2_FINAL",
        "MODEL_V2_FINAL_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
        "CAL_V2_sha256": hash_file(ROOT / "artifacts/CAL_V2.json"),
        "protocol_v3_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"),
        "PREPROC_V1_lock_sha256": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
        "v2_010_prediction_sha256": pred,
        "case_manifest_sha256": hash_file(cases.CASE_MANIFEST_PATH),
        "target": config["target"],
        "baseline": config["baseline"],
        "integration": config["integration"],
        "steps": config["steps"],
        "attribution": config["attribution"],
        "overlay_normalization": config["visual_overlay"],
        "case_selection": config["case_selection"],
        "tie_rule": config["tie_rule"],
        "completeness_rule": "DIAGNOSTIC_METADATA_NO_NUMERICAL_GATE",
        "completeness_semantics": {
            "semantics_id": SEMANTICS_ID,
            "numerical_completeness_gate": "NONE",
            "gates_v2g10": False,
            "historical_heuristic_role": "DESCRIPTIVE_ONLY",
            "historical_heuristic_absolute": 0.001,
            "historical_heuristic_relative": 0.001,
            "largest_observed_absolute_residual": largest_abs,
            "largest_observed_relative_residual": largest_rel,
            "cases_exceeding_historical_heuristic": sorted(
                e["case_type"] for e in case_entries
                if e["completeness_diagnostic"]["historical_v1_style_1e3_heuristic"]
                == "EXCEEDS_HEURISTIC"),
            "report_statement": " ".join(sem_cfg["required_report_wording"].split()),
            "quadrature_steps_baseline_model_or_cases_changed": False,
        },
        "locked_method_compliance": compliance,
        "cases": case_entries,
        "error_analysis_config_sha256": hash_file(ROOT / "configs/model_v2/error_analysis_v2.yaml"),
        "c031_noise_protocol_lock_sha256": hash_file(
            ROOT / "artifacts/C031_ERROR_ANALYSIS_V1.lock.json"),
        "noise_type_protocol_checks_pass": noise_protocol["status"] == "PASS",
        "noise_type_v2_predictions_sha256": hash_file(OUT / "noise_type_v2_predictions.csv"),
        "claim_boundary": CLAIM,
        "claim_boundary_fields": CLAIM_FIELDS,
        "method_commit": commit,
        "original_method_commit": sem_cfg["original_method_commit"],
        "failed_diagnostic_run_commit": sem_cfg["failed_diagnostic_run_commit"],
        "corrective_method_commit": corrective_commit(),
        "runtime_acceptance_changed_by_this_phase": False,
        "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED",
        "official_validation_promotion": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "operational_lineage": "MODEL_V1",
    }
    cases.write_json(OUT / "explainability_v2.json", report)

    ea = json.loads((OUT / "error_analysis_v2.json").read_text())
    metrics = cases.read_csv(OUT / "noise_type_metrics.csv")
    ea["noise_type"] = {
        "protocol_id": "NOISE_TYPE_ERROR_ANALYSIS_V1",
        "claim_boundary": "CONTROLLED_TWO_SOURCE_RECORD_NOISE_TYPE_ROBUSTNESS_ANALYSIS_"
        "NOT_POPULATION_ROBUSTNESS",
        "pooled_cells": len([m for m in metrics if m["scope"] == "POOLED_BOTH_SOURCE_RECORDS"]),
        "predictions": "reports/model_v2/v2_011/noise_type_v2_predictions.csv",
        "metrics": "reports/model_v2/v2_011/noise_type_metrics.csv",
        "comparison": "reports/model_v2/v2_011/noise_type_comparison_v1_v2.csv",
        "new_acceptance_gate": False,
        "v1_inference_rerun": False,
        "limitations": [
            "two source ECG records (118 and 119) only",
            "pure-noise bw/em/ma recordings carry no AAMI labels; labels come from the clean "
            "MIT-BIH base windows",
            "official 118e*/119e* provider-generated stress and controlled em injection use "
            "different generation procedures; equality is not expected",
            "not population robustness; no tuning or acceptance decision derives from it",
        ],
    }
    cases.write_json(OUT / "error_analysis_v2.json", ea)

    bound = {
        rel: hash_file(ROOT / rel)
        for rel in [
            *cases.METHOD_PATHS,
            "checkpoints/MODEL_V2_FINAL.pt",
            "artifacts/CAL_V2.json",
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
            "manifests/preprocessing/PREPROC_V1.lock.json",
            "reports/model_v2/v2_010/internal_v2_predictions.csv",
            "reports/model_v2/v2_010/incart_v2_predictions.csv",
            "reports/model_v2/v2_010/nstdb_v2_predictions.csv",
            "reports/t031/hr_bins.json",
            "artifacts/C031_ERROR_ANALYSIS_V1.lock.json",
            "configs/c031_error_analysis_v1.yaml",
            "reports/t031/c031_noise_base_manifest.csv",
            "reports/model_v2/v2_011/noise_type_v2_predictions.csv",
            "reports/model_v2/v2_011/hr_bins.json",
            "configs/model_v2/explainability_v2_completeness_semantics_v2.yaml",
            "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json",
            "evaluation/explain_v2_semantics.py",
            "reports/model_v2/v2_011/completeness_semantics_authority_audit.json",
            "reports/model_v2/v2_011/failed_diagnostic_run_manifest.json",
            "reports/model_v2/v2_011/ig_completeness_diagnostic.csv",
            "data/raw/nstdb/1.0.0/bw.dat",
            "data/raw/nstdb/1.0.0/em.dat",
            "data/raw/nstdb/1.0.0/ma.dat",
        ]
    }
    cases.write_json(
        ROOT / "artifacts/EXPLAINABILITY_V2_METHOD.lock.json",
        {
            "lock_id": "EXPLAINABILITY_V2_METHOD",
            "owner_task": "V2-011",
            "status": "FROZEN_EXPLAINABILITY",
            "target": config["target"],
            "baseline": config["baseline"],
            "integration": "64_POINT_GAUSS_LEGENDRE",
            "steps": config["steps"],
            "overlay": "PER_WINDOW_NORMALIZED_ABSOLUTE_IG_WITH_SIGNED_IG_PRESERVED",
            "case_selection": "TP high; TN low; FP high; FN low calibrated probability",
            "tie_rule": config["tie_rule"],
            "completeness_rule": config["completeness_acceptance"],
            "claim_boundary": CLAIM,
            "method_commit": commit,
            "original_method_commit": sem_cfg["original_method_commit"],
            "failed_diagnostic_run_commit": sem_cfg["failed_diagnostic_run_commit"],
            "corrective_method_commit": corrective_commit(),
            "completeness_semantics": SEMANTICS_ID,
            "bound_artifacts": bound,
        },
    )
    print("EXPLAINABILITY_V2 serialized")


if __name__ == "__main__":
    main()
