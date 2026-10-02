#!/usr/bin/env python3
"""V2-004 D2: apply the frozen instability rule to select the learned-only survivor set, pick
BEST_LEARNED_ONLY_V2_CV_V1, and compute the (not-run) V2-005 hybrid trigger. No manual
selection -- this is the only code path permitted to decide the D2 outcome.
"""

from __future__ import annotations

import json
import sys

import scripts._v2_004_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_004"
RUNS_DIR = OUT_DIR / "runs"

BEST_REDUCED_RF_V1_AUPRC = 0.713140103147974
HYBRID_THRESHOLD = 0.03


def _v1_cv_reference_sample_sd() -> float:
    lock = json.loads(
        (lib.ROOT / "manifests/model_v2/MODEL_V1_CV_REFERENCE_V1.lock.json").read_text()
    )
    return float(lock["three_seed_summary"]["AUPRC_sample_sd"])


def _check_non_instability_disqualifiers(architecture_id: str) -> list[str]:
    reasons: list[str] = []
    for seed in lib.D2_SEEDS:
        for fold in lib.OUTER_FOLDS:
            exp_id = lib.experiment_id("D2", architecture_id, fold, seed)
            summary = json.loads(
                (RUNS_DIR / exp_id / "fit_summary.json").read_text(encoding="utf-8")
            )
            if summary.get("non_finite_detected"):
                reasons.append(f"{exp_id}: non_finite_detected=true")
            if summary["parameter_count"] != lib.EXPECTED_PARAMETER_COUNTS[architecture_id]:
                reasons.append(f"{exp_id}: parameter_count mismatch")
    closure = json.loads((OUT_DIR / "d2_oof_closure_audit.json").read_text())
    if closure["status"] != "PASS":
        reasons.append("D2 OOF closure not PASS")
    return reasons


def main(advanced_architectures: list[str]) -> None:
    instability_limit = 2.0 * _v1_cv_reference_sample_sd()
    summary = json.loads((OUT_DIR / "d2_architecture_summary.json").read_text())

    per_architecture: dict[str, dict] = {}
    for architecture_id in advanced_architectures:
        entry = summary[architecture_id]
        unstable = entry["AUPRC_sample_sd"] > instability_limit
        non_instability_reasons = _check_non_instability_disqualifiers(architecture_id)
        per_architecture[architecture_id] = {
            "AUPRC_mean": entry["AUPRC_mean"],
            "AUPRC_sample_sd": entry["AUPRC_sample_sd"],
            "AUPRC_minimum": entry["AUPRC_minimum"],
            "AUROC_mean": entry["AUROC_mean"],
            "parameter_count": entry["parameter_count"],
            "instability_limit": instability_limit,
            "unstable": unstable,
            "non_instability_disqualification_reasons": non_instability_reasons,
            "non_instability_disqualified": len(non_instability_reasons) > 0,
        }

    multi_candidate = len(advanced_architectures) == 2
    survivors = []
    for architecture_id, entry in per_architecture.items():
        if entry["non_instability_disqualified"]:
            entry["disposition"] = "DISQUALIFIED_NON_INSTABILITY"
            continue
        if entry["unstable"] and multi_candidate:
            entry["disposition"] = "DISQUALIFIED_UNSTABLE_MULTI_CANDIDATE"
            continue
        if entry["unstable"] and not multi_candidate:
            entry["disposition"] = "ONLY_SURVIVOR_WITH_INSTABILITY_FLAG"
            survivors.append(architecture_id)
            continue
        entry["disposition"] = "SURVIVOR"
        survivors.append(architecture_id)

    best_learned_only = None
    hybrid = {
        "best_reduced_rf_v1_auprc": BEST_REDUCED_RF_V1_AUPRC,
        "threshold": HYBRID_THRESHOLD,
        "comparator": ">=",
    }

    if not survivors:
        v2_004_outcome = "NO_D2_LEARNED_ONLY_SURVIVOR"
        hybrid["status"] = "NOT_EVALUABLE_NEURAL_SEARCH_STOPPED"
        hybrid["trigger"] = None
        hybrid["gap"] = None
        hybrid["best_learned_only_mean_auprc"] = None
    else:
        ranked = sorted(
            survivors,
            key=lambda a: (
                -per_architecture[a]["AUPRC_mean"],
                per_architecture[a]["AUPRC_sample_sd"],
                per_architecture[a]["parameter_count"],
                a,
            ),
        )
        best_learned_only = ranked[0]
        v2_004_outcome = "D2_ONE_SURVIVOR" if len(survivors) == 1 else "D2_TWO_SURVIVORS"
        best_entry = per_architecture[best_learned_only]
        gap = BEST_REDUCED_RF_V1_AUPRC - best_entry["AUPRC_mean"]
        hybrid["best_learned_only_mean_auprc"] = best_entry["AUPRC_mean"]
        hybrid["gap"] = gap
        hybrid["trigger"] = gap >= HYBRID_THRESHOLD
        hybrid["status"] = "TRUE" if hybrid["trigger"] else "FALSE"

    decision = {
        "stage": "D2",
        "advanced_architectures": advanced_architectures,
        "instability_limit": instability_limit,
        "per_architecture": per_architecture,
        "multi_candidate": multi_candidate,
        "survivors": survivors,
        "v2_004_outcome": v2_004_outcome,
        "best_learned_only_architecture_id": best_learned_only,
        "hybrid_trigger": hybrid,
    }
    (OUT_DIR / "d2_stability_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if best_learned_only is not None:
        best_entry = per_architecture[best_learned_only]
        (OUT_DIR / "best_learned_only.json").write_text(
            json.dumps(
                {
                    "component_id": "BEST_LEARNED_ONLY_V2_CV_V1",
                    "architecture_id": best_learned_only,
                    "AUPRC_mean": best_entry["AUPRC_mean"],
                    "AUPRC_sample_sd": best_entry["AUPRC_sample_sd"],
                    "AUPRC_minimum": best_entry["AUPRC_minimum"],
                    "AUROC_mean": best_entry["AUROC_mean"],
                    "parameter_count": best_entry["parameter_count"],
                    "instability_status": best_entry["disposition"],
                    "paired_bootstrap_vs_v1": json.loads(
                        (OUT_DIR / "d2_candidate_vs_v1_bootstrap_summary.json").read_text()
                    )["per_architecture"][best_learned_only],
                    "not_a_canonical_freeze": True,
                    "not_a_checkpoint_promotion": True,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        (OUT_DIR / "best_learned_only.json").write_text(
            json.dumps(
                {"component_id": "BEST_LEARNED_ONLY_V2_CV_V1", "status": "NOT_AVAILABLE"},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    (OUT_DIR / "hybrid_trigger.json").write_text(
        json.dumps(hybrid, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
