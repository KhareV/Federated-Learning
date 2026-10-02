#!/usr/bin/env python3
"""V2-004 D2: for each D1-advanced architecture, reuse the exact V2-002 patient-cluster
bootstrap draws. For each replicate, compute the candidate's pooled AUPRC separately per seed
(20260927, 20260928, 20260929) on the SAME patient draw, then average those three seed-level
metrics (never predictions) into one replicate value; pair against MODEL_V1_CV_REFERENCE_V1's
own three-seed-mean replicate series (reused from reports/model_v2/v2_002/
bootstrap_seed_metrics.csv, never recomputed). Also computes the descriptive leave-one-
patient-out contribution diagnostic per architecture/seed (same definition as D0.6).
"""

from __future__ import annotations

import csv
import json
import sys

import numpy as np
from sklearn.metrics import average_precision_score

import scripts._v2_004_lib as lib

V2_002_DIR = lib.ROOT / "reports/model_v2/v2_002"
OUT_DIR = lib.ROOT / "reports/model_v2/v2_004"
B = 2000
BOOTSTRAP_SEED = 20261002


def load_bootstrap_draws() -> tuple[np.ndarray, list[str]]:
    draws = np.load(V2_002_DIR / "bootstrap_draws.npy")
    index = json.loads((V2_002_DIR / "bootstrap_patient_index.json").read_text())
    if index["bootstrap_seed"] != BOOTSTRAP_SEED or draws.shape != (B, 27):
        raise RuntimeError("V2-002 bootstrap draws do not match the expected identity")
    return draws, index["sorted_patient_index_mapping"]


def load_model_v1_three_seed_mean_replicates() -> list[float | None]:
    """Reused, never recomputed, from V2-002's own per-seed bootstrap replicates."""
    path = V2_002_DIR / "bootstrap_seed_metrics.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_replicate: dict[int, list[float | None]] = {i: [] for i in range(B)}
    for row in rows:
        replicate = int(row["replicate"])
        value = None if row["AUPRC"] == "" else float(row["AUPRC"])
        by_replicate[replicate].append(value)
    means: list[float | None] = []
    for replicate in range(B):
        values = by_replicate[replicate]
        if len(values) != 3 or any(v is None for v in values):
            means.append(None)
        else:
            means.append(float(np.mean(values)))
    return means


def load_architecture_three_seed_rows(architecture_id: str) -> dict[int, list[dict]]:
    with (OUT_DIR / "d2_oof_predictions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_seed: dict[int, list[dict]] = {}
    for seed in lib.ALL_SEEDS:
        by_seed[seed] = [
            r for r in rows if r["architecture_id"] == architecture_id and int(r["seed"]) == seed
        ]
    return by_seed


def replicate_metrics_per_seed(
    rows: list[dict], patient_universe: list[str], draws: np.ndarray
) -> list[float | None]:
    by_patient_labels: dict[str, list[int]] = {p: [] for p in patient_universe}
    by_patient_probs: dict[str, list[float]] = {p: [] for p in patient_universe}
    for row in rows:
        patient = row["participant_group_id"]
        by_patient_labels[patient].append(int(row["label"]))
        by_patient_probs[patient].append(float(row["raw_probability"]))

    values: list[float | None] = []
    for replicate_index in range(draws.shape[0]):
        sampled = [patient_universe[i] for i in draws[replicate_index]]
        labels_list: list[int] = []
        probs_list: list[float] = []
        for patient in sampled:
            labels_list.extend(by_patient_labels[patient])
            probs_list.extend(by_patient_probs[patient])
        labels_arr = np.asarray(labels_list)
        if len(np.unique(labels_arr)) < 2:
            values.append(None)
            continue
        values.append(float(average_precision_score(labels_arr, np.asarray(probs_list))))
    return values


def ci_from_values(values: list[float | None]) -> dict:
    valid = [v for v in values if v is not None]
    invalid = len(values) - len(valid)
    if not valid:
        return {"ci_lower_2_5": None, "ci_upper_97_5": None, "valid_B": 0, "invalid_B": invalid}
    lower, upper = np.percentile(np.asarray(valid), [2.5, 97.5])
    return {
        "ci_lower_2_5": float(lower),
        "ci_upper_97_5": float(upper),
        "valid_B": len(valid),
        "invalid_B": invalid,
    }


def patient_contribution(rows: list[dict]) -> dict[str, float | None]:
    labels = np.asarray([int(r["label"]) for r in rows], dtype=np.int64)
    probs = np.asarray([float(r["raw_probability"]) for r in rows], dtype=np.float64)
    groups = np.asarray([r["participant_group_id"] for r in rows], dtype=str)
    full = float(average_precision_score(labels, probs))
    deltas: dict[str, float | None] = {}
    for patient in sorted(set(groups.tolist())):
        mask = groups != patient
        if len(np.unique(labels[mask])) < 2:
            deltas[patient] = None
            continue
        without_p = float(average_precision_score(labels[mask], probs[mask]))
        deltas[patient] = full - without_p
    return deltas


def main(advanced_architectures: list[str]) -> None:
    draws, patient_universe = load_bootstrap_draws()
    v1_three_seed_mean_replicates = load_model_v1_three_seed_mean_replicates()

    bootstrap_summary: dict[str, dict] = {}
    contribution_rows: list[dict] = []

    for architecture_id in advanced_architectures:
        by_seed_rows = load_architecture_three_seed_rows(architecture_id)
        per_seed_replicates = {
            seed: replicate_metrics_per_seed(rows, patient_universe, draws)
            for seed, rows in by_seed_rows.items()
        }
        mean_replicates: list[float | None] = []
        for replicate_index in range(B):
            seed_values = [per_seed_replicates[seed][replicate_index] for seed in lib.ALL_SEEDS]
            mean_replicates.append(
                None if any(v is None for v in seed_values) else float(np.mean(seed_values))
            )
        delta_replicates = [
            None if a is None or b is None else a - b
            for a, b in zip(mean_replicates, v1_three_seed_mean_replicates, strict=True)
        ]
        delta_ci = ci_from_values(delta_replicates)

        candidate_point_means = []
        for rows in by_seed_rows.values():
            labels = np.asarray([int(r["label"]) for r in rows], dtype=np.int64)
            probs = np.asarray([float(r["raw_probability"]) for r in rows], dtype=np.float64)
            candidate_point_means.append(float(average_precision_score(labels, probs)))
        candidate_point_mean = float(np.mean(candidate_point_means))
        v1_point_mean = 0.4138882608052527

        bootstrap_summary[architecture_id] = {
            "candidate_three_seed_mean_point_AUPRC": candidate_point_mean,
            "V1_three_seed_mean_point_AUPRC": v1_point_mean,
            "point_delta_AUPRC": candidate_point_mean - v1_point_mean,
            "delta_AUPRC_ci": [delta_ci["ci_lower_2_5"], delta_ci["ci_upper_97_5"]],
            "valid_B": delta_ci["valid_B"],
            "invalid_B": delta_ci["invalid_B"],
        }

        for seed, rows in by_seed_rows.items():
            deltas = patient_contribution(rows)
            for patient, delta in deltas.items():
                contribution_rows.append(
                    {
                        "architecture_id": architecture_id,
                        "seed": seed,
                        "participant_group_id": patient,
                        "contribution_delta": delta,
                    }
                )

    (OUT_DIR / "d2_candidate_vs_v1_bootstrap_summary.json").write_text(
        json.dumps(
            {
                "bootstrap_id": "MODEL_V2_BOOTSTRAP_DRAWS_V1",
                "reused_from": "V2-002",
                "note": (
                    "mean of three independently trained seed models on the SAME patient "
                    "draw, paired against MODEL_V1_CV_REFERENCE_V1's own three-seed-mean "
                    "replicate series (also reused, never recomputed); not an ensemble, not "
                    "a p-value or t-test."
                ),
                "per_architecture": bootstrap_summary,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if contribution_rows:
        with (OUT_DIR / "d2_patient_contribution.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(
                handle, lineterminator="\n", fieldnames=list(contribution_rows[0].keys())
            )
            writer.writeheader()
            writer.writerows(contribution_rows)

    print(json.dumps(bootstrap_summary, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
