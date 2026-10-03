#!/usr/bin/env python3
"""V2-006: paired patient-cluster bootstrap of CHALLENGER vs CONTROL, reusing EXACTLY the
frozen V2-002 MODEL_V2_BOOTSTRAP_DRAWS_V1 identity (B=2000, 27 patient slots, bootstrap_seed
20261002) -- no new RNG sequence. For every replicate and each seed separately, compute
CONTROL and CHALLENGER pooled AUPRC on the SAME sampled patient multiset, then average each
model's three seed-level values into one replicate mean (never averaging probabilities).
BOOTSTRAP_SE_DELTA is frozen as the sample standard deviation (ddof=1) of the valid paired
delta_rep = challenger_rep_mean - control_rep_mean values."""

from __future__ import annotations

import csv
import json

import numpy as np
from sklearn.metrics import average_precision_score

import scripts._v2_006_lib as lib

V2_002_DIR = lib.ROOT / "reports/model_v2/v2_002"
OUT_DIR = lib.ROOT / "reports/model_v2/v2_006"
B = 2000
BOOTSTRAP_SEED = 20261002


def load_bootstrap_draws() -> tuple[np.ndarray, list[str]]:
    draws = np.load(V2_002_DIR / "bootstrap_draws.npy")
    index = json.loads((V2_002_DIR / "bootstrap_patient_index.json").read_text())
    if index["bootstrap_seed"] != BOOTSTRAP_SEED or draws.shape != (B, 27):
        raise RuntimeError("V2-002 bootstrap draws do not match the expected identity")
    return draws, index["sorted_patient_index_mapping"]


def _rows_by_seed(path, architecture_id: str | None = None) -> dict[int, list[dict]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_seed: dict[int, list[dict]] = {seed: [] for seed in lib.ALL_SEEDS}
    for row in rows:
        if architecture_id is not None and row["architecture_id"] != architecture_id:
            continue
        by_seed[int(row["seed"])].append(row)
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


def main() -> None:
    draws, patient_universe = load_bootstrap_draws()

    challenger_by_seed = _rows_by_seed(OUT_DIR / "challenger_oof_predictions.csv")

    v2_004_dir = lib.ROOT / "reports/model_v2/v2_004/runs"
    control_by_seed: dict[int, list[dict]] = {seed: [] for seed in lib.ALL_SEEDS}
    for fold in lib.OUTER_FOLDS:
        exp_id = f"V2-004-D1-MEANMAX-F{fold:02d}-S20260927"
        with (v2_004_dir / exp_id / "outer_predictions.csv").open(newline="") as handle:
            control_by_seed[20260927].extend(csv.DictReader(handle))
    for seed in (20260928, 20260929):
        for fold in lib.OUTER_FOLDS:
            exp_id = f"V2-004-D2-MEANMAX-F{fold:02d}-S{seed}"
            with (v2_004_dir / exp_id / "outer_predictions.csv").open(newline="") as handle:
                control_by_seed[seed].extend(csv.DictReader(handle))

    challenger_per_seed_replicates = {
        seed: replicate_metrics_per_seed(challenger_by_seed[seed], patient_universe, draws)
        for seed in lib.ALL_SEEDS
    }
    control_per_seed_replicates = {
        seed: replicate_metrics_per_seed(control_by_seed[seed], patient_universe, draws)
        for seed in lib.ALL_SEEDS
    }

    rows_out = []
    delta_reps: list[float | None] = []
    for replicate_index in range(B):
        challenger_seed_values = [
            challenger_per_seed_replicates[seed][replicate_index] for seed in lib.ALL_SEEDS
        ]
        control_seed_values = [
            control_per_seed_replicates[seed][replicate_index] for seed in lib.ALL_SEEDS
        ]
        challenger_valid = all(v is not None for v in challenger_seed_values)
        control_valid = all(v is not None for v in control_seed_values)
        if challenger_valid and control_valid:
            challenger_rep_mean = float(np.mean(challenger_seed_values))
            control_rep_mean = float(np.mean(control_seed_values))
            delta_rep = challenger_rep_mean - control_rep_mean
        else:
            challenger_rep_mean = None
            control_rep_mean = None
            delta_rep = None
        delta_reps.append(delta_rep)
        rows_out.append(
            {
                "replicate": replicate_index,
                "control_rep_mean_AUPRC": control_rep_mean,
                "challenger_rep_mean_AUPRC": challenger_rep_mean,
                "delta_rep": delta_rep,
            }
        )

    with (OUT_DIR / "paired_bootstrap_delta.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)

    valid_deltas = [d for d in delta_reps if d is not None]
    invalid_count = len(delta_reps) - len(valid_deltas)
    bootstrap_se_delta = (
        float(np.std(np.asarray(valid_deltas), ddof=1)) if len(valid_deltas) >= 2 else None
    )
    ci_lower, ci_upper = (
        (float(x) for x in np.percentile(np.asarray(valid_deltas), [2.5, 97.5]))
        if valid_deltas
        else (None, None)
    )

    summary = {
        "bootstrap_id": "MODEL_V2_BOOTSTRAP_DRAWS_V1",
        "bootstrap_seed": BOOTSTRAP_SEED,
        "B": B,
        "valid_B": len(valid_deltas),
        "invalid_B": invalid_count,
        "bootstrap_se_delta_definition": (
            "sample standard deviation (ddof=1) of all valid paired delta_rep values, where "
            "delta_rep = challenger_rep_mean_over_3_seeds - control_rep_mean_over_3_seeds, "
            "each seed's per-replicate AUPRC computed on the SAME sampled patient multiset"
        ),
        "BOOTSTRAP_SE_DELTA": bootstrap_se_delta,
        "delta_AUPRC_ci_95_percentile": [ci_lower, ci_upper],
        "sufficient_valid_replicates_for_adoption_decision": (
            bootstrap_se_delta is not None and len(valid_deltas) >= 2
        ),
    }
    (OUT_DIR / "paired_bootstrap_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
