#!/usr/bin/env python3
"""V2-003: reuse the frozen V2-002 patient-cluster bootstrap draws (MODEL_V2_BOOTSTRAP_DRAWS_V1,
B=2000, 27 patient slots, seed 20261002) -- never regenerate a new RNG sequence. For every
(feature_variant, model_family) combination, compute bootstrap replicate AUPRC/AUROC with
patient multiplicity preserved. Then: (a) for RF, pair each reduced variant against ALL on the
SAME replicate patient draw to get delta distributions; (b) compare every classical reference
of interest against MODEL_V1_CV_REFERENCE_V1's three-seed mean on the SAME replicate draw,
reusing V2-002's own per-seed bootstrap replicate values (never recomputed) for the MODEL_V1
side. No p-values, no t-tests -- percentile CIs only.
"""

from __future__ import annotations

import csv
import json

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

import scripts._v2_003_lib as lib

V2_002_DIR = lib.ROOT / "reports/model_v2/v2_002"
OUT_DIR = lib.ROOT / "reports/model_v2/v2_003"
B = 2000
BOOTSTRAP_SEED = 20261002


def load_bootstrap_draws() -> tuple[np.ndarray, list[str]]:
    draws = np.load(V2_002_DIR / "bootstrap_draws.npy")
    index = json.loads((V2_002_DIR / "bootstrap_patient_index.json").read_text())
    if index["bootstrap_seed"] != BOOTSTRAP_SEED or draws.shape != (B, 27):
        raise RuntimeError("V2-002 bootstrap draws do not match the expected identity")
    return draws, index["sorted_patient_index_mapping"]


def load_oof_predictions() -> list[dict]:
    with (OUT_DIR / "oof_predictions.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _pooled_metric(labels: np.ndarray, probs: np.ndarray) -> tuple[float, float | None]:
    auprc = float(average_precision_score(labels, probs))
    auroc = float(roc_auc_score(labels, probs)) if len(np.unique(labels)) == 2 else None
    return auprc, auroc


def replicate_metrics_for_combo(
    rows: list[dict], patient_universe: list[str], draws: np.ndarray
) -> dict[str, list[float | None]]:
    by_patient_labels: dict[str, list[int]] = {p: [] for p in patient_universe}
    by_patient_probs: dict[str, list[float]] = {p: [] for p in patient_universe}
    for row in rows:
        patient = row["participant_group_id"]
        by_patient_labels[patient].append(int(row["label"]))
        by_patient_probs[patient].append(float(row["probability"]))

    auprc_values: list[float | None] = []
    auroc_values: list[float | None] = []
    for replicate_index in range(draws.shape[0]):
        sampled = [patient_universe[i] for i in draws[replicate_index]]
        labels_list: list[int] = []
        probs_list: list[float] = []
        for patient in sampled:
            labels_list.extend(by_patient_labels[patient])
            probs_list.extend(by_patient_probs[patient])
        labels_arr = np.asarray(labels_list)
        probs_arr = np.asarray(probs_list)
        if len(np.unique(labels_arr)) < 2:
            auprc_values.append(None)
            auroc_values.append(None)
            continue
        auprc, auroc = _pooled_metric(labels_arr, probs_arr)
        auprc_values.append(auprc)
        auroc_values.append(auroc)
    return {"AUPRC": auprc_values, "AUROC": auroc_values}


def main() -> None:
    draws, patient_universe = load_bootstrap_draws()
    rows = load_oof_predictions()

    combo_replicates: dict[str, dict[str, list[float | None]]] = {}
    combo_point: dict[str, dict[str, float]] = {}
    csv_rows: list[dict] = []
    for variant in lib.VARIANT_IDS:
        for model_family in lib.MODEL_FAMILIES:
            key = f"{variant}_{model_family}"
            combo_rows = [
                r for r in rows if r["feature_variant"] == variant
                and r["model_family"] == model_family
            ]
            labels = np.asarray([int(r["label"]) for r in combo_rows])
            probs = np.asarray([float(r["probability"]) for r in combo_rows])
            point_auprc, point_auroc = _pooled_metric(labels, probs)
            combo_point[key] = {"AUPRC": point_auprc, "AUROC": point_auroc}
            replicates = replicate_metrics_for_combo(combo_rows, patient_universe, draws)
            combo_replicates[key] = replicates
            for replicate_index in range(B):
                csv_rows.append(
                    {
                        "feature_variant": variant,
                        "model_family": model_family,
                        "replicate": replicate_index,
                        "AUPRC": replicates["AUPRC"][replicate_index],
                        "AUROC": replicates["AUROC"][replicate_index],
                    }
                )

    bootstrap_csv_path = OUT_DIR / "paired_variant_bootstrap.csv"
    with bootstrap_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(csv_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    per_combo_summary = {}
    for variant in lib.VARIANT_IDS:
        for model_family in lib.MODEL_FAMILIES:
            key = f"{variant}_{model_family}"
            auprc_ci = lib.ci_from_values(combo_replicates[key]["AUPRC"])
            auroc_ci = lib.ci_from_values(combo_replicates[key]["AUROC"])
            per_combo_summary[key] = {
                "feature_variant": variant,
                "model_family": model_family,
                "AUPRC_point": combo_point[key]["AUPRC"],
                "AUPRC_ci": [auprc_ci["ci_lower_2_5"], auprc_ci["ci_upper_97_5"]],
                "AUROC_point": combo_point[key]["AUROC"],
                "AUROC_ci": [auroc_ci["ci_lower_2_5"], auroc_ci["ci_upper_97_5"]],
                "valid_B": auprc_ci["valid_B"],
                "invalid_B": auprc_ci["invalid_B"],
            }

    reduced_variants = [v for v in lib.VARIANT_IDS if v != "ALL"]
    rf_vs_all: dict[str, dict] = {}
    all_rf_auprc_replicates = combo_replicates["ALL_RF"]["AUPRC"]
    all_rf_auroc_replicates = combo_replicates["ALL_RF"]["AUROC"]
    all_rf_point = combo_point["ALL_RF"]
    for variant in reduced_variants:
        key = f"{variant}_RF"
        delta_auprc_values: list[float | None] = []
        delta_auroc_values: list[float | None] = []
        for replicate_index in range(B):
            reduced_auprc = combo_replicates[key]["AUPRC"][replicate_index]
            all_auprc = all_rf_auprc_replicates[replicate_index]
            delta_auprc_values.append(
                None if reduced_auprc is None or all_auprc is None
                else reduced_auprc - all_auprc
            )
            reduced_auroc = combo_replicates[key]["AUROC"][replicate_index]
            all_auroc = all_rf_auroc_replicates[replicate_index]
            delta_auroc_values.append(
                None if reduced_auroc is None or all_auroc is None
                else reduced_auroc - all_auroc
            )
        auprc_ci = lib.ci_from_values(delta_auprc_values)
        auroc_ci = lib.ci_from_values(delta_auroc_values)
        rf_vs_all[variant] = {
            "delta_AUPRC_point": combo_point[key]["AUPRC"] - all_rf_point["AUPRC"],
            "delta_AUPRC_ci": [auprc_ci["ci_lower_2_5"], auprc_ci["ci_upper_97_5"]],
            "delta_AUROC_point": combo_point[key]["AUROC"] - all_rf_point["AUROC"],
            "delta_AUROC_ci": [auroc_ci["ci_lower_2_5"], auroc_ci["ci_upper_97_5"]],
            "valid_B": auprc_ci["valid_B"],
            "invalid_B": auprc_ci["invalid_B"],
        }

    (OUT_DIR / "paired_variant_bootstrap_summary.json").write_text(
        json.dumps(
            {
                "bootstrap_id": "MODEL_V2_BOOTSTRAP_DRAWS_V1",
                "reused_from": "V2-002",
                "bootstrap_seed": BOOTSTRAP_SEED,
                "replicates": B,
                "note": (
                    "Descriptive uncertainty around fixed, predeclared ablations; no "
                    "p-values, no t-tests."
                ),
                "per_combo": per_combo_summary,
                "rf_reduced_vs_all": rf_vs_all,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps({"rf_reduced_vs_all": rf_vs_all}, indent=2))


if __name__ == "__main__":
    main()
