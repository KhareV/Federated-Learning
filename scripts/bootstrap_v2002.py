#!/usr/bin/env python3
"""V2-002: patient-cluster bootstrap over the frozen OOF predictions (MODEL_V2_BOOTSTRAP_
DRAWS_V1). No model re-inference -- reads only reports/model_v2/v2_002/oof_predictions.csv.
Deterministic: numpy.random.default_rng(20261002), 2000 draws of 27 patient slots with
replacement, multiplicity preserved (never converted to a set). Designed to be run twice from
the frozen predictions and produce byte-identical draw arrays/replicate metrics/summary.
"""

from __future__ import annotations

import csv
import json

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

import scripts._v2_002_lib as lib
from nhm.hashing import hash_file

OUT_DIR = lib.ROOT / "reports/model_v2/v2_002"
B = 2000
BOOTSTRAP_SEED = 20261002


def load_oof_predictions() -> list[dict]:
    path = OUT_DIR / "oof_predictions.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def patient_cluster_universe(rows: list[dict]) -> list[str]:
    groups = sorted({r["participant_group_id"] for r in rows})
    if len(groups) != 27:
        raise RuntimeError(f"expected exactly 27 TRAIN patient clusters, got {len(groups)}")
    return groups


def generate_draws(patient_universe: list[str]) -> np.ndarray:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(patient_universe)
    draws = rng.integers(0, n, size=(B, n))
    return draws


def _pooled_metric(labels: np.ndarray, probabilities: np.ndarray) -> tuple[float, float | None]:
    auprc = float(average_precision_score(labels, probabilities))
    auroc = float(roc_auc_score(labels, probabilities)) if len(np.unique(labels)) == 2 else None
    return auprc, auroc


def compute_replicate_metrics(
    rows: list[dict], patient_universe: list[str], draws: np.ndarray
) -> dict:
    by_patient: dict[str, dict[int, list[int]]] = {p: {} for p in patient_universe}
    for seed in lib.SEEDS:
        for p in patient_universe:
            by_patient[p][seed] = []
    labels_by_seed_patient: dict[int, dict[str, list[int]]] = {s: {} for s in lib.SEEDS}
    probs_by_seed_patient: dict[int, dict[str, list[float]]] = {s: {} for s in lib.SEEDS}
    for row in rows:
        seed = int(row["seed"])
        patient = row["participant_group_id"]
        labels_by_seed_patient[seed].setdefault(patient, []).append(int(row["label"]))
        probs_by_seed_patient[seed].setdefault(patient, []).append(float(row["raw_probability"]))

    per_seed_replicates: dict[int, dict[str, list[float | None]]] = {
        s: {"AUPRC": [], "AUROC": []} for s in lib.SEEDS
    }
    three_seed_replicate_auprc: list[float | None] = []
    three_seed_replicate_auroc: list[float | None] = []
    unique_patient_counts: list[int] = []

    for replicate_index in range(draws.shape[0]):
        patient_indices = draws[replicate_index]
        sampled_patients = [patient_universe[i] for i in patient_indices]
        unique_patient_counts.append(len(set(sampled_patients)))

        seed_metric_values: dict[int, tuple[float, float | None]] = {}
        for seed in lib.SEEDS:
            labels_list: list[int] = []
            probs_list: list[float] = []
            for patient in sampled_patients:
                labels_list.extend(labels_by_seed_patient[seed].get(patient, []))
                probs_list.extend(probs_by_seed_patient[seed].get(patient, []))
            labels_arr = np.asarray(labels_list)
            probs_arr = np.asarray(probs_list)
            if len(np.unique(labels_arr)) < 2:
                per_seed_replicates[seed]["AUPRC"].append(None)
                per_seed_replicates[seed]["AUROC"].append(None)
                seed_metric_values[seed] = (float("nan"), None)
                continue
            auprc, auroc = _pooled_metric(labels_arr, probs_arr)
            per_seed_replicates[seed]["AUPRC"].append(auprc)
            per_seed_replicates[seed]["AUROC"].append(auroc)
            seed_metric_values[seed] = (auprc, auroc)

        auprc_values = [seed_metric_values[s][0] for s in lib.SEEDS]
        auroc_values = [seed_metric_values[s][1] for s in lib.SEEDS]
        if any(np.isnan(v) for v in auprc_values):
            three_seed_replicate_auprc.append(None)
        else:
            three_seed_replicate_auprc.append(float(np.mean(auprc_values)))
        if any(v is None for v in auroc_values):
            three_seed_replicate_auroc.append(None)
        else:
            three_seed_replicate_auroc.append(float(np.mean(auroc_values)))

    return {
        "per_seed_replicates": per_seed_replicates,
        "three_seed_replicate_auprc": three_seed_replicate_auprc,
        "three_seed_replicate_auroc": three_seed_replicate_auroc,
        "unique_patient_counts": unique_patient_counts,
    }


def _ci(values: list[float | None]) -> dict:
    valid = [v for v in values if v is not None]
    invalid = len(values) - len(valid)
    if not valid:
        return {"ci_lower_2_5": None, "ci_upper_97_5": None, "valid_B": 0, "invalid_B": invalid}
    arr = np.asarray(valid)
    lower, upper = np.percentile(arr, [2.5, 97.5])
    return {
        "ci_lower_2_5": float(lower),
        "ci_upper_97_5": float(upper),
        "valid_B": len(valid),
        "invalid_B": invalid,
    }


def main() -> None:
    rows = load_oof_predictions()
    patient_universe = patient_cluster_universe(rows)
    draws = generate_draws(patient_universe)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    draws_path = OUT_DIR / "bootstrap_draws.npy"
    np.save(draws_path, draws)

    index_path = OUT_DIR / "bootstrap_patient_index.json"
    index_path.write_text(
        json.dumps(
            {
                "bootstrap_id": "MODEL_V2_BOOTSTRAP_DRAWS_V1",
                "bootstrap_seed": BOOTSTRAP_SEED,
                "rng": "numpy.random.default_rng",
                "numpy_version": np.__version__,
                "replicates": B,
                "slots_per_replicate": len(patient_universe),
                "sorted_patient_index_mapping": patient_universe,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    replicate_metrics = compute_replicate_metrics(rows, patient_universe, draws)

    seed_metrics_csv_rows = []
    per_seed_summary = {}
    for seed in lib.SEEDS:
        seed_rows = [r for r in rows if int(r["seed"]) == seed]
        labels = np.array([int(r["label"]) for r in seed_rows])
        probs = np.array([float(r["raw_probability"]) for r in seed_rows])
        point_auprc, point_auroc = _pooled_metric(labels, probs)
        auprc_ci = _ci(replicate_metrics["per_seed_replicates"][seed]["AUPRC"])
        auroc_ci = _ci(replicate_metrics["per_seed_replicates"][seed]["AUROC"])
        per_seed_summary[str(seed)] = {
            "AUPRC_point": point_auprc,
            "AUPRC_ci": [auprc_ci["ci_lower_2_5"], auprc_ci["ci_upper_97_5"]],
            "AUPRC_valid_B": auprc_ci["valid_B"],
            "AUPRC_invalid_B": auprc_ci["invalid_B"],
            "AUROC_point": point_auroc,
            "AUROC_ci": [auroc_ci["ci_lower_2_5"], auroc_ci["ci_upper_97_5"]],
            "AUROC_valid_B": auroc_ci["valid_B"],
            "AUROC_invalid_B": auroc_ci["invalid_B"],
        }
        for replicate_index in range(B):
            seed_metrics_csv_rows.append(
                {
                    "seed": seed,
                    "replicate": replicate_index,
                    "AUPRC": replicate_metrics["per_seed_replicates"][seed]["AUPRC"][
                        replicate_index
                    ],
                    "AUROC": replicate_metrics["per_seed_replicates"][seed]["AUROC"][
                        replicate_index
                    ],
                }
            )

    seed_metrics_path = OUT_DIR / "bootstrap_seed_metrics.csv"
    with seed_metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=["seed", "replicate", "AUPRC", "AUROC"]
        )
        writer.writeheader()
        writer.writerows(seed_metrics_csv_rows)

    three_seed_auprc_ci = _ci(replicate_metrics["three_seed_replicate_auprc"])
    three_seed_auroc_ci = _ci(replicate_metrics["three_seed_replicate_auroc"])
    auprcs_point = np.array([per_seed_summary[str(s)]["AUPRC_point"] for s in lib.SEEDS])
    auroc_point_vals = [per_seed_summary[str(s)]["AUROC_point"] for s in lib.SEEDS]

    unique_counts = np.array(replicate_metrics["unique_patient_counts"])
    summary = {
        "bootstrap_id": "MODEL_V2_BOOTSTRAP_DRAWS_V1",
        "bootstrap_seed": BOOTSTRAP_SEED,
        "rng": "numpy.random.default_rng",
        "bit_generator": "PCG64",
        "replicates": B,
        "source_patient_clusters": len(patient_universe),
        "patient_slots_per_replicate": len(patient_universe),
        "unique_patient_count_min": int(unique_counts.min()),
        "unique_patient_count_median": float(np.median(unique_counts)),
        "unique_patient_count_max": int(unique_counts.max()),
        "window_bootstrap_used": False,
        "stratified_bootstrap_used": False,
        "rejection_redraw_used": False,
        "multiplicity_preserved": True,
        "per_seed": per_seed_summary,
        "three_seed_mean": {
            "AUPRC_point": float(np.mean(auprcs_point)),
            "AUPRC_ci": [three_seed_auprc_ci["ci_lower_2_5"], three_seed_auprc_ci["ci_upper_97_5"]],
            "AUPRC_valid_B": three_seed_auprc_ci["valid_B"],
            "AUPRC_invalid_B": three_seed_auprc_ci["invalid_B"],
            "AUROC_point": float(np.mean(auroc_point_vals)),
            "AUROC_ci": [three_seed_auroc_ci["ci_lower_2_5"], three_seed_auroc_ci["ci_upper_97_5"]],
            "AUROC_valid_B": three_seed_auroc_ci["valid_B"],
            "AUROC_invalid_B": three_seed_auroc_ci["invalid_B"],
            "note": (
                "mean of three independently trained seed models on the SAME patient draw; "
                "not an ensemble, not a fourth model, not a p-value or t-test"
            ),
        },
        "point_estimate_source": "ORIGINAL_POOLED_OOF_METRIC_NOT_BOOTSTRAP_MEAN",
        "oof_predictions_sha256": hash_file(OUT_DIR / "oof_predictions.csv"),
        "bootstrap_draws_sha256": hash_file(draws_path),
    }
    summary_path = OUT_DIR / "bootstrap_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["three_seed_mean"], indent=2))


if __name__ == "__main__":
    main()
