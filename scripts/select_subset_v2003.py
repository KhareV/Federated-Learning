#!/usr/bin/env python3
"""V2-003: apply the two frozen selection rules (minimal adequate feature subset, best reduced
RF) to the canonical oof_metrics.json, then compute the V1_reference_comparison.json for RF
ALL, LOGISTIC ALL, BEST_REDUCED_RF, and the minimal adequate subset's RF, reusing the
per-replicate values already written to paired_variant_bootstrap.csv (never recomputed) and
MODEL_V1_CV_REFERENCE_V1's own bootstrap replicates (also never recomputed).
"""

from __future__ import annotations

import csv
import json

import scripts._v2_003_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_003"
REDUCED_VARIANTS = ("STAT", "RR", "QRS", "RR_QRS", "STAT_RR", "STAT_QRS")
MARGIN = 0.02


def load_oof_metrics() -> dict:
    return json.loads((OUT_DIR / "oof_metrics.json").read_text(encoding="utf-8"))


def select_minimal_adequate_subset(metrics: dict) -> dict:
    rf_all_auprc = metrics["per_variant_model"]["ALL_RF"]["pooled_OOF_AUPRC"]
    adequate = []
    for variant in REDUCED_VARIANTS:
        entry = metrics["per_variant_model"][f"{variant}_RF"]
        is_adequate = entry["pooled_OOF_AUPRC"] >= rf_all_auprc - MARGIN
        adequate.append(
            {
                "variant": variant,
                "feature_count": entry["feature_count"],
                "RF_AUPRC": entry["pooled_OOF_AUPRC"],
                "distance_from_all": rf_all_auprc - entry["pooled_OOF_AUPRC"],
                "adequate": is_adequate,
            }
        )
    candidates = [row for row in adequate if row["adequate"]]
    if candidates:
        candidates.sort(key=lambda row: (row["feature_count"], -row["RF_AUPRC"], row["variant"]))
        selected = candidates[0]
        fallback_to_all = False
    else:
        selected = {
            "variant": "ALL",
            "feature_count": 29,
            "RF_AUPRC": rf_all_auprc,
            "distance_from_all": 0.0,
            "adequate": True,
        }
        fallback_to_all = True
    return {
        "component_id": "MODEL_V2_MINIMAL_ADEQUATE_FEATURE_SUBSET_V1",
        "rule": "SMALLEST_SUBSET_WITHIN_0.02_ABSOLUTE_RF_POOLED_OOF_AUPRC_OF_ALL_29",
        "margin_absolute_auprc": MARGIN,
        "RF_ALL_pooled_OOF_AUPRC": rf_all_auprc,
        "candidate_evaluation": adequate,
        "no_reduced_variant_adequate_fallback_to_all": fallback_to_all,
        "selected_variant": selected["variant"],
        "selected_feature_count": selected["feature_count"],
        "selected_RF_AUPRC": selected["RF_AUPRC"],
        "selected_distance_from_all": selected["distance_from_all"],
        "selection_rule_satisfied": True,
    }


def select_best_reduced_rf(metrics: dict) -> dict:
    rows = []
    for variant in REDUCED_VARIANTS:
        entry = metrics["per_variant_model"][f"{variant}_RF"]
        rows.append(
            {
                "variant": variant,
                "feature_count": entry["feature_count"],
                "AUPRC": entry["pooled_OOF_AUPRC"],
                "AUROC": entry["pooled_OOF_AUROC"],
            }
        )
    rows.sort(key=lambda row: (-row["AUPRC"], -row["AUROC"], row["feature_count"], row["variant"]))
    best = rows[0]
    return {
        "component_id": "BEST_REDUCED_RF_V1",
        "rule": "HIGHEST_POOLED_OOF_RF_AUPRC_AMONG_REDUCED_VARIANTS",
        "tie_rule": "higher_AUROC_then_fewer_features_then_lexical_id",
        "candidates_considered": rows,
        "selected_variant": best["variant"],
        "feature_count": best["feature_count"],
        "AUPRC": best["AUPRC"],
        "AUROC": best["AUROC"],
    }


def v1_reference_comparison(
    metrics: dict, minimal_subset: dict, best_reduced: dict
) -> dict:
    with (OUT_DIR / "paired_variant_bootstrap.csv").open(newline="", encoding="utf-8") as handle:
        bootstrap_rows = list(csv.DictReader(handle))
    by_combo: dict[str, list[float | None]] = {}
    for row in bootstrap_rows:
        key = f"{row['feature_variant']}_{row['model_family']}"
        by_combo.setdefault(key, [None] * lib.BOOTSTRAP_B)
        by_combo[key][int(row["replicate"])] = (
            None if row["AUPRC"] == "" else float(row["AUPRC"])
        )

    model_v1_replicate_means = lib.load_model_v1_replicate_means()

    comparisons = {}
    targets = {
        "RF_ALL": "ALL_RF",
        "LOGISTIC_ALL": "ALL_LOGISTIC",
        "BEST_REDUCED_RF": f"{best_reduced['selected_variant']}_RF",
        "MINIMAL_ADEQUATE_SUBSET_RF": f"{minimal_subset['selected_variant']}_RF",
    }
    for label, combo_key in targets.items():
        classical_point = metrics["per_variant_model"][combo_key]["pooled_OOF_AUPRC"]
        delta_values: list[float | None] = []
        for replicate_index in range(lib.BOOTSTRAP_B):
            classical = by_combo[combo_key][replicate_index]
            v1_mean = model_v1_replicate_means[replicate_index]
            delta_values.append(
                None if classical is None or v1_mean is None else classical - v1_mean
            )
        ci = lib.ci_from_values(delta_values)
        comparisons[label] = {
            "classical_combo": combo_key,
            "classical_AUPRC_point": classical_point,
            "model_v1_three_seed_mean_AUPRC_point": lib.MODEL_V1_THREE_SEED_MEAN_AUPRC,
            "delta_AUPRC_point": classical_point - lib.MODEL_V1_THREE_SEED_MEAN_AUPRC,
            "delta_AUPRC_ci": [ci["ci_lower_2_5"], ci["ci_upper_97_5"]],
            "valid_B": ci["valid_B"],
            "invalid_B": ci["invalid_B"],
        }
    return comparisons


def main() -> None:
    metrics = load_oof_metrics()
    minimal_subset = select_minimal_adequate_subset(metrics)
    best_reduced = select_best_reduced_rf(metrics)

    (OUT_DIR / "minimal_adequate_subset.json").write_text(
        json.dumps(minimal_subset, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "best_reduced_rf.json").write_text(
        json.dumps(best_reduced, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    comparisons = v1_reference_comparison(metrics, minimal_subset, best_reduced)
    (OUT_DIR / "v1_reference_comparison.json").write_text(
        json.dumps(
            {
                "note": (
                    "Descriptive paired patient-cluster comparison on the SAME V2-002 "
                    "bootstrap draw; MODEL_V1 side is the mean of its three independently "
                    "trained seeds on that draw, never an ensemble. No p-values, no t-tests."
                ),
                "comparisons": comparisons,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(minimal_subset, indent=2))
    print(json.dumps(best_reduced, indent=2))
    print(json.dumps(comparisons, indent=2))


if __name__ == "__main__":
    main()
