#!/usr/bin/env python3
"""V2-003 Section 19: grouped permutation importance -- SECONDARY INTERPRETATION ONLY, does
not select the minimal subset. Uses only the ALL-29 RF already canonically fit per outer fold
(refit here deterministically -- same OPTIMISE data, same frozen random_state=20260927, same
fold-local imputer -- reproduces the exact canonical model, not a new one). For each outer
fold and each of {STAT, RR, QRS}, jointly permutes the ROW ASSIGNMENT of every column in that
group using one shared row permutation (preserves within-group correlation structure), 50
deterministic repetitions seeded from (20261003, outer_fold, group_index, repetition_index).
"""

from __future__ import annotations

import csv
import json

import numpy as np
from sklearn.metrics import average_precision_score

import scripts._v2_003_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_003"
BASE_SEED = 20261003
REPETITIONS = 50
GROUPS = ("STAT", "RR", "QRS")
GROUP_INDEX = {"STAT": 0, "RR": 1, "QRS": 2}


def _repetition_rng(outer_fold: int, group: str, repetition_index: int) -> np.random.Generator:
    seed_sequence = np.random.SeedSequence(
        [BASE_SEED, outer_fold, GROUP_INDEX[group], repetition_index]
    )
    return np.random.default_rng(seed_sequence)


def _fit_all_variant_for_fold(outer_fold: int) -> tuple:
    roles = lib.role_groups_for_fold(outer_fold)
    optimise = lib.load_role_population(
        role="OPTIMISE",
        stage_id="V2-003_FIT",
        requested_outer_fold=outer_fold,
        experiment_outer_fold=outer_fold,
        participant_group_ids=set(roles.optimise_groups),
        access_purpose="grouped permutation importance: refit canonical ALL-29 RF",
        fit_scope_finalized=False,
    )
    imputer, _scaler = lib.fit_fold_local_transform(optimise.features)
    x_opt_imputed = imputer.transform(optimise.features)
    forest = lib.create_random_forest()
    forest.fit(x_opt_imputed, optimise.labels)

    outer = lib.load_role_population(
        role="OUTER_TEST",
        stage_id="V2-003_EVAL",
        requested_outer_fold=outer_fold,
        experiment_outer_fold=outer_fold,
        participant_group_ids=set(roles.outer_groups),
        access_purpose="grouped permutation importance: baseline + permuted AUPRC",
        fit_scope_finalized=True,
    )
    return imputer, forest, outer


def _auprc_for_raw_features(imputer, forest, raw_features: np.ndarray, labels: np.ndarray) -> float:
    imputed = imputer.transform(raw_features)
    probs = forest.predict_proba(imputed)[:, list(forest.classes_).index(1)]
    return float(average_precision_score(labels, probs))


def main() -> None:
    csv_rows: list[dict] = []
    summary: dict[str, dict] = {}
    for outer_fold in lib.OUTER_FOLDS:
        imputer, forest, outer = _fit_all_variant_for_fold(outer_fold)
        baseline_auprc = _auprc_for_raw_features(
            imputer, forest, outer.features, outer.labels
        )

        for group in GROUPS:
            group_indices = list(lib.VARIANT_INDICES[group])
            permuted_auprcs: list[float] = []
            for repetition_index in range(REPETITIONS):
                rng = _repetition_rng(outer_fold, group, repetition_index)
                permutation = rng.permutation(outer.features.shape[0])
                permuted_features = outer.features.copy()
                permuted_features[:, group_indices] = outer.features[permutation][
                    :, group_indices
                ]
                permuted_auprc = _auprc_for_raw_features(
                    imputer, forest, permuted_features, outer.labels
                )
                permuted_auprcs.append(permuted_auprc)
                csv_rows.append(
                    {
                        "outer_fold": outer_fold,
                        "group": group,
                        "repetition": repetition_index,
                        "baseline_AUPRC": baseline_auprc,
                        "permuted_AUPRC": permuted_auprc,
                        "delta_AUPRC": permuted_auprc - baseline_auprc,
                    }
                )
            arr = np.asarray(permuted_auprcs)
            deltas = arr - baseline_auprc
            summary[f"F{outer_fold:02d}_{group}"] = {
                "outer_fold": outer_fold,
                "group": group,
                "baseline_AUPRC": baseline_auprc,
                "permuted_AUPRC_mean": float(np.mean(arr)),
                "permuted_AUPRC_median": float(np.median(arr)),
                "mean_delta_AUPRC": float(np.mean(deltas)),
                "median_delta_AUPRC": float(np.median(deltas)),
                "delta_AUPRC_percentile_2_5": float(np.percentile(deltas, 2.5)),
                "delta_AUPRC_percentile_97_5": float(np.percentile(deltas, 97.5)),
                "repetitions": REPETITIONS,
            }

    csv_path = OUT_DIR / "grouped_permutation_importance.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    group_overall = {}
    for group in GROUPS:
        mean_deltas = [summary[f"F{f:02d}_{group}"]["mean_delta_AUPRC"] for f in lib.OUTER_FOLDS]
        group_overall[group] = {
            "mean_delta_AUPRC_across_folds": float(np.mean(mean_deltas)),
            "per_fold_mean_delta_AUPRC": mean_deltas,
        }

    (OUT_DIR / "grouped_permutation_summary.json").write_text(
        json.dumps(
            {
                "base_seed": BASE_SEED,
                "repetitions_per_group_per_fold": REPETITIONS,
                "diagnostic_only": True,
                "shared_row_permutation_within_group": True,
                "model": "RF_ALL",
                "groups": list(GROUPS),
                "per_fold_group": summary,
                "group_overall": group_overall,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(group_overall, indent=2))


if __name__ == "__main__":
    main()
