#!/usr/bin/env python3
"""V2-004: generate the remaining required report-tree tables that are straightforward
derivations from already-existing per-fit artifacts: D1/D2 experiment matrices, aggregated
fit-summary and training-curve tables, and the raw per-replicate D2 candidate-vs-V1 bootstrap
CSV (the summary JSON already exists; this is its underlying long-format data)."""

from __future__ import annotations

import csv
import json
import sys

import numpy as np

import scripts._v2_004_lib as lib
import scripts.bootstrap_d2_v2004 as boot_d2

OUT_DIR = lib.ROOT / "reports/model_v2/v2_004"
RUNS_DIR = OUT_DIR / "runs"


def write_d1_experiment_matrix() -> None:
    rows = []
    index = 0
    for architecture_id in lib.ARCHITECTURE_IDS:
        for fold in lib.OUTER_FOLDS:
            rows.append(
                {
                    "experiment_id": lib.experiment_id("D1", architecture_id, fold, lib.D1_SEED),
                    "architecture_id": architecture_id,
                    "outer_fold": fold,
                    "seed": lib.D1_SEED,
                    "run_order_index": index,
                }
            )
            index += 1
    with (OUT_DIR / "d1_experiment_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_d2_experiment_matrix(advanced_architectures: list[str]) -> None:
    rows = []
    index = 0
    for architecture_id in advanced_architectures:
        for seed in lib.D2_SEEDS:
            for fold in lib.OUTER_FOLDS:
                rows.append(
                    {
                        "experiment_id": lib.experiment_id("D2", architecture_id, fold, seed),
                        "architecture_id": architecture_id,
                        "outer_fold": fold,
                        "seed": seed,
                        "run_order_index": index,
                    }
                )
                index += 1
    with (OUT_DIR / "d2_experiment_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _collect_fit_summaries(experiment_ids: list[str]) -> list[dict]:
    summaries = []
    for exp_id in experiment_ids:
        path = RUNS_DIR / exp_id / "fit_summary.json"
        summaries.append(json.loads(path.read_text(encoding="utf-8")))
    return summaries


def write_fit_summary_csv(name: str, experiment_ids: list[str]) -> None:
    summaries = _collect_fit_summaries(experiment_ids)
    rows = [
        {
            "experiment_id": s["experiment_id"],
            "architecture_id": s["architecture_id"],
            "stage": s["stage"],
            "outer_fold": s["outer_fold"],
            "seed": s["seed"],
            "selected_epoch": s["selected_epoch"],
            "best_inner_validation_auprc": s["best_inner_validation_auprc"],
            "checkpoint_sha256": s["checkpoint_sha256"],
            "parameter_count": s["parameter_count"],
            "outer_auprc": s["outer_auprc"],
            "outer_auroc": s["outer_auroc"],
            "lr_reductions": s["lr_reductions"],
            "epochs_completed": s["epochs_completed"],
            "stop_reason": s["stop_reason"],
            "non_finite_detected": s["non_finite_detected"],
            "wall_clock_seconds": s["wall_clock_seconds"],
            "pos_weight": s["pos_weight"],
        }
        for s in summaries
    ]
    with (OUT_DIR / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_training_curves_csv(name: str, experiment_ids: list[str]) -> None:
    rows = []
    for exp_id in experiment_ids:
        path = RUNS_DIR / exp_id / "training_curve.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    with (OUT_DIR / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_d2_candidate_vs_v1_bootstrap_csv(advanced_architectures: list[str]) -> None:
    draws, patient_universe = boot_d2.load_bootstrap_draws()
    v1_three_seed_mean_replicates = boot_d2.load_model_v1_three_seed_mean_replicates()
    rows = []
    for architecture_id in advanced_architectures:
        by_seed_rows = boot_d2.load_architecture_three_seed_rows(architecture_id)
        per_seed_replicates = {
            seed: boot_d2.replicate_metrics_per_seed(r, patient_universe, draws)
            for seed, r in by_seed_rows.items()
        }
        for replicate_index in range(boot_d2.B):
            seed_values = [per_seed_replicates[seed][replicate_index] for seed in lib.ALL_SEEDS]
            mean_value = (
                None if any(v is None for v in seed_values) else float(np.mean(seed_values))
            )
            v1_value = v1_three_seed_mean_replicates[replicate_index]
            delta = None if mean_value is None or v1_value is None else mean_value - v1_value
            rows.append(
                {
                    "architecture_id": architecture_id,
                    "replicate": replicate_index,
                    "candidate_three_seed_mean_AUPRC": mean_value,
                    "V1_three_seed_mean_AUPRC": v1_value,
                    "delta_AUPRC": delta,
                }
            )
    with (OUT_DIR / "d2_candidate_vs_v1_bootstrap.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(advanced_architectures: list[str]) -> None:
    write_d1_experiment_matrix()
    d1_ids = [
        lib.experiment_id("D1", architecture_id, fold, lib.D1_SEED)
        for architecture_id in lib.ARCHITECTURE_IDS
        for fold in lib.OUTER_FOLDS
    ]
    write_fit_summary_csv("d1_fit_summary.csv", d1_ids)
    write_training_curves_csv("d1_training_curves.csv", d1_ids)

    if advanced_architectures:
        write_d2_experiment_matrix(advanced_architectures)
        d2_ids = [
            lib.experiment_id("D2", architecture_id, fold, seed)
            for architecture_id in advanced_architectures
            for seed in lib.D2_SEEDS
            for fold in lib.OUTER_FOLDS
        ]
        write_fit_summary_csv("d2_fit_summary.csv", d2_ids)
        write_training_curves_csv("d2_training_curves.csv", d2_ids)
        write_d2_candidate_vs_v1_bootstrap_csv(advanced_architectures)

    print("V2-004 fit tables written")


if __name__ == "__main__":
    main(sys.argv[1:])
