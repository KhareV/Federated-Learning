#!/usr/bin/env python3
"""V2-003: execute the 70 canonical classical fits (7 feature variants x 2 model families x 5
outer folds). For each outer fold: load OPTIMISE once, fit all 14 variant/model combinations
on OPTIMISE only (fresh fold-local imputer/scaler per variant, never the full-TRAIN frozen
T014 transformer), mark fit-scope finalized for that fold, then load OUTER_TEST once and
evaluate all 14 combinations. Writes reports/model_v2/v2_003/fold_predictions.csv (one row per
example per variant per model family) and fit_scope_audit.csv (one row per fold).
"""

from __future__ import annotations

import csv
import time

import numpy as np

import scripts._v2_003_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_003"
DECISION_THRESHOLD = 0.5


def _probabilities(model, features: np.ndarray) -> np.ndarray:
    classes = list(model.classes_)
    positive_index = classes.index(1)
    return np.asarray(model.predict_proba(features)[:, positive_index], dtype=np.float64)


def run_fold(outer_fold: int) -> tuple[list[dict], dict]:
    roles = lib.role_groups_for_fold(outer_fold)
    lib.verify_role_closure(roles)

    optimise = lib.load_role_population(
        role="OPTIMISE",
        stage_id="V2-003_FIT",
        requested_outer_fold=outer_fold,
        experiment_outer_fold=outer_fold,
        participant_group_ids=set(roles.optimise_groups),
        access_purpose="fit LOGISTIC and RF for all 7 feature variants (fold-local transforms)",
        fit_scope_finalized=False,
    )

    fitted: dict[str, dict] = {}
    for variant in lib.VARIANT_IDS:
        idx = list(lib.VARIANT_INDICES[variant])
        x_opt = optimise.features[:, idx]
        imputer, scaler = lib.fit_fold_local_transform(x_opt)
        x_opt_imputed = imputer.transform(x_opt)
        x_opt_scaled = scaler.transform(x_opt_imputed)

        logistic = lib.create_logistic_regression()
        logistic.fit(x_opt_scaled, optimise.labels)
        forest = lib.create_random_forest()
        forest.fit(x_opt_imputed, optimise.labels)

        fitted[variant] = {
            "imputer": imputer,
            "scaler": scaler,
            "LOGISTIC": logistic,
            "RF": forest,
        }

    outer = lib.load_role_population(
        role="OUTER_TEST",
        stage_id="V2-003_EVAL",
        requested_outer_fold=outer_fold,
        experiment_outer_fold=outer_fold,
        participant_group_ids=set(roles.outer_groups),
        access_purpose="evaluate all 7 feature variants x 2 model families, probability only",
        fit_scope_finalized=True,
    )

    rows: list[dict] = []
    for variant in lib.VARIANT_IDS:
        idx = list(lib.VARIANT_INDICES[variant])
        x_out = outer.features[:, idx]
        state = fitted[variant]
        x_out_imputed = state["imputer"].transform(x_out)
        x_out_scaled = state["scaler"].transform(x_out_imputed)

        for model_family, x_eval in (("LOGISTIC", x_out_scaled), ("RF", x_out_imputed)):
            model = state[model_family]
            probabilities = _probabilities(model, x_eval)
            exp_id = lib.experiment_id(variant, model_family, outer_fold)
            for index, example_id in enumerate(outer.example_ids):
                probability = float(probabilities[index])
                rows.append(
                    {
                        "example_id": example_id,
                        "participant_group_id": outer.participant_group_ids[index],
                        "record_id": outer.record_ids[index],
                        "outer_fold": outer_fold,
                        "label": int(outer.labels[index]),
                        "feature_variant": variant,
                        "model_family": model_family,
                        "probability": probability,
                        "prediction_at_0_5": int(probability >= DECISION_THRESHOLD),
                        "experiment_id": exp_id,
                    }
                )

    fit_scope_row = {
        "outer_fold": outer_fold,
        "optimise_patients": len(roles.optimise_groups),
        "optimise_windows": int(optimise.labels.size),
        "outer_test_patients": len(roles.outer_groups),
        "outer_test_windows": int(outer.labels.size),
        "inner_validation_loaded": False,
        "imputer_fit_scope": "OPTIMISE_ONLY_FOLD_LOCAL",
        "scaler_fit_scope": "OPTIMISE_ONLY_FOLD_LOCAL",
        "full_train_frozen_transformer_reused": False,
        "variants_fit": len(lib.VARIANT_IDS),
        "model_families_fit": len(lib.MODEL_FAMILIES),
    }
    return rows, fit_scope_row


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    fit_scope_rows: list[dict] = []
    start = time.monotonic()
    for outer_fold in lib.OUTER_FOLDS:
        rows, fit_scope_row = run_fold(outer_fold)
        all_rows.extend(rows)
        fit_scope_rows.append(fit_scope_row)
        print(f"fold {outer_fold}: {len(rows)} prediction rows")

    predictions_path = OUT_DIR / "fold_predictions.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(all_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(all_rows)

    fit_scope_path = OUT_DIR / "fit_scope_audit.csv"
    with fit_scope_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(fit_scope_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(fit_scope_rows)

    elapsed = time.monotonic() - start
    print(f"V2-003: 70 canonical fits complete in {elapsed:.1f}s, {len(all_rows)} total rows")


if __name__ == "__main__":
    main()
