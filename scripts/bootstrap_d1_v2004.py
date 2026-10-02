#!/usr/bin/env python3
"""V2-004 D1: reuse the frozen V2-002 patient-cluster bootstrap draws (MODEL_V2_BOOTSTRAP_
DRAWS_V1, B=2000, 27 patient slots, seed 20261002) -- never regenerate a new RNG sequence. For
each architecture (seed 20260927), compute bootstrap replicate AUPRC/AUROC with patient
multiplicity preserved; pair against MODEL_V1_CV_REFERENCE_V1's seed-20260927 OOF predictions
(not the three-seed mean -- D1 itself uses seed 20260927 only) on the SAME replicate draw; and
compute the three causal pairwise comparisons (H0/H1/H2) on the SAME draws. No p-values, no
t-tests -- percentile CIs only.
"""

from __future__ import annotations

import csv
import json

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

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


def load_v1_seed_20260927_predictions() -> list[dict]:
    with (V2_002_DIR / "oof_predictions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [r for r in rows if int(r["seed"]) == lib.D1_SEED]


def load_d1_predictions(architecture_id: str) -> list[dict]:
    with (OUT_DIR / "d1_oof_predictions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [r for r in rows if r["architecture_id"] == architecture_id]


def _pooled(labels: np.ndarray, probs: np.ndarray) -> tuple[float, float | None]:
    auprc = float(average_precision_score(labels, probs))
    auroc = float(roc_auc_score(labels, probs)) if len(np.unique(labels)) == 2 else None
    return auprc, auroc


def replicate_metrics(
    rows: list[dict], probability_field: str, patient_universe: list[str], draws: np.ndarray
) -> dict[str, list[float | None]]:
    by_patient_labels: dict[str, list[int]] = {p: [] for p in patient_universe}
    by_patient_probs: dict[str, list[float]] = {p: [] for p in patient_universe}
    for row in rows:
        patient = row["participant_group_id"]
        by_patient_labels[patient].append(int(row["label"]))
        by_patient_probs[patient].append(float(row[probability_field]))

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
        auprc, auroc = _pooled(labels_arr, probs_arr)
        auprc_values.append(auprc)
        auroc_values.append(auroc)
    return {"AUPRC": auprc_values, "AUROC": auroc_values}


def ci(values: list[float | None]) -> dict:
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


def paired_delta(a_values: list[float | None], b_values: list[float | None]) -> list[float | None]:
    out: list[float | None] = []
    for a, b in zip(a_values, b_values, strict=True):
        out.append(None if a is None or b is None else a - b)
    return out


def main() -> None:
    draws, patient_universe = load_bootstrap_draws()
    v1_rows = load_v1_seed_20260927_predictions()
    v1_replicates = replicate_metrics(v1_rows, "raw_probability", patient_universe, draws)
    v1_labels = np.asarray([int(r["label"]) for r in v1_rows])
    v1_probs = np.asarray([float(r["raw_probability"]) for r in v1_rows])
    v1_point_auprc, v1_point_auroc = _pooled(v1_labels, v1_probs)

    architecture_replicates: dict[str, dict[str, list[float | None]]] = {}
    architecture_points: dict[str, dict[str, float]] = {}
    csv_rows: list[dict] = []

    for architecture_id in lib.ARCHITECTURE_IDS:
        rows = load_d1_predictions(architecture_id)
        labels = np.asarray([int(r["label"]) for r in rows])
        probs = np.asarray([float(r["raw_probability"]) for r in rows])
        point_auprc, point_auroc = _pooled(labels, probs)
        architecture_points[architecture_id] = {"AUPRC": point_auprc, "AUROC": point_auroc}
        replicates = replicate_metrics(rows, "raw_probability", patient_universe, draws)
        architecture_replicates[architecture_id] = replicates
        for replicate_index in range(B):
            csv_rows.append(
                {
                    "architecture_id": architecture_id,
                    "replicate": replicate_index,
                    "AUPRC": replicates["AUPRC"][replicate_index],
                    "AUROC": replicates["AUROC"][replicate_index],
                    "V1_seed_20260927_AUPRC": v1_replicates["AUPRC"][replicate_index],
                    "V1_seed_20260927_AUROC": v1_replicates["AUROC"][replicate_index],
                }
            )

    with (OUT_DIR / "d1_candidate_vs_v1_bootstrap.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    candidate_vs_v1_summary: dict[str, dict] = {}
    for architecture_id in lib.ARCHITECTURE_IDS:
        delta_auprc = paired_delta(
            architecture_replicates[architecture_id]["AUPRC"], v1_replicates["AUPRC"]
        )
        delta_auroc = paired_delta(
            architecture_replicates[architecture_id]["AUROC"], v1_replicates["AUROC"]
        )
        auprc_ci = ci(delta_auprc)
        auroc_ci = ci(delta_auroc)
        own_ci = ci(architecture_replicates[architecture_id]["AUPRC"])
        valid_own = [v for v in architecture_replicates[architecture_id]["AUPRC"] if v is not None]
        candidate_vs_v1_summary[architecture_id] = {
            "candidate_point_AUPRC": architecture_points[architecture_id]["AUPRC"],
            "candidate_point_AUROC": architecture_points[architecture_id]["AUROC"],
            "candidate_bootstrap_sd_AUPRC": float(np.std(np.asarray(valid_own), ddof=1))
            if len(valid_own) > 1
            else None,
            "candidate_bootstrap_ci_AUPRC": [own_ci["ci_lower_2_5"], own_ci["ci_upper_97_5"]],
            "V1_seed_20260927_point_AUPRC": v1_point_auprc,
            "V1_seed_20260927_point_AUROC": v1_point_auroc,
            "delta_AUPRC_point": architecture_points[architecture_id]["AUPRC"] - v1_point_auprc,
            "delta_AUPRC_ci": [auprc_ci["ci_lower_2_5"], auprc_ci["ci_upper_97_5"]],
            "delta_AUROC_point": architecture_points[architecture_id]["AUROC"] - v1_point_auroc,
            "delta_AUROC_ci": [auroc_ci["ci_lower_2_5"], auroc_ci["ci_upper_97_5"]],
            "valid_B": auprc_ci["valid_B"],
            "invalid_B": auprc_ci["invalid_B"],
            "bootstrap_qualified": auprc_ci["ci_lower_2_5"] is not None
            and auprc_ci["ci_lower_2_5"] > 0.0,
        }

    (OUT_DIR / "d1_candidate_vs_v1_bootstrap_summary.json").write_text(
        json.dumps(
            {
                "bootstrap_id": "MODEL_V2_BOOTSTRAP_DRAWS_V1",
                "reused_from": "V2-002",
                "bootstrap_seed": BOOTSTRAP_SEED,
                "replicates": B,
                "reference": (
                    "MODEL_V1_CV_REFERENCE_V1 seed 20260927 OOF predictions "
                    "(not three-seed mean)"
                ),
                "qualification_rule": (
                    "paired_95_percentile_lower_bound_of_delta_AUPRC_strictly_greater_than_0"
                ),
                "per_architecture": candidate_vs_v1_summary,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # ---- causal pairwise comparisons (H0/H1/H2), same bootstrap draws -----------------------
    causal_pairs = {
        "H0": ("MODEL_V2_CAPCTRL", None),  # None => compare against V1 seed 20260927
        "H1": ("MODEL_V2_TCN_MEAN", "MODEL_V2_CAPCTRL"),
        "H2": ("MODEL_V2_TCN_MEANMAX", "MODEL_V2_TCN_MEAN"),
    }
    causal_rows: list[dict] = []
    causal_summary: dict[str, dict] = {}
    for hypothesis, (left, right) in causal_pairs.items():
        left_replicates = architecture_replicates[left]["AUPRC"]
        right_replicates = (
            v1_replicates["AUPRC"] if right is None else architecture_replicates[right]["AUPRC"]
        )
        left_point = architecture_points[left]["AUPRC"]
        right_point = v1_point_auprc if right is None else architecture_points[right]["AUPRC"]
        delta_values = paired_delta(left_replicates, right_replicates)
        delta_ci = ci(delta_values)
        left_auroc_replicates = architecture_replicates[left]["AUROC"]
        right_auroc_replicates = (
            v1_replicates["AUROC"] if right is None else architecture_replicates[right]["AUROC"]
        )
        delta_auroc_values = paired_delta(left_auroc_replicates, right_auroc_replicates)
        delta_auroc_ci = ci(delta_auroc_values)
        for replicate_index in range(B):
            causal_rows.append(
                {
                    "hypothesis": hypothesis,
                    "left": left,
                    "right": right or "MODEL_V1_CV_REFERENCE_V1_seed_20260927",
                    "replicate": replicate_index,
                    "delta_AUPRC": delta_values[replicate_index],
                    "delta_AUROC": delta_auroc_values[replicate_index],
                }
            )
        point_delta = left_point - right_point
        if delta_ci["ci_lower_2_5"] is not None and delta_ci["ci_lower_2_5"] > 0:
            verdict = "SUPPORTED"
        elif delta_ci["ci_upper_97_5"] is not None and delta_ci["ci_upper_97_5"] < 0:
            verdict = "CONTRADICTED"
        else:
            verdict = "INCONCLUSIVE"
        causal_summary[hypothesis] = {
            "left": left,
            "right": right or "MODEL_V1_CV_REFERENCE_V1_seed_20260927",
            "point_delta_AUPRC": point_delta,
            "delta_AUPRC_ci": [delta_ci["ci_lower_2_5"], delta_ci["ci_upper_97_5"]],
            "point_delta_AUROC": (
                architecture_points[left]["AUROC"]
                - (v1_point_auroc if right is None else architecture_points[right]["AUROC"])
            ),
            "delta_AUROC_ci": [delta_auroc_ci["ci_lower_2_5"], delta_auroc_ci["ci_upper_97_5"]],
            "verdict": verdict,
            "valid_B": delta_ci["valid_B"],
            "invalid_B": delta_ci["invalid_B"],
        }

    with (OUT_DIR / "d1_causal_pairwise_bootstrap.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(causal_rows[0].keys()))
        writer.writeheader()
        writer.writerows(causal_rows)

    (OUT_DIR / "d1_causal_hypothesis_summary.json").write_text(
        json.dumps(
            {
                "note": (
                    "Controlled software/model ablation comparisons, not biological "
                    "causality. No clinical superiority or physiological-mechanism claim."
                ),
                "verdict_vocabulary": {
                    "SUPPORTED": "lower_95_CI_of_delta_AUPRC_greater_than_0",
                    "CONTRADICTED": "upper_95_CI_of_delta_AUPRC_less_than_0",
                    "INCONCLUSIVE": "CI_includes_0",
                },
                "hypotheses": causal_summary,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps({"candidate_vs_v1": candidate_vs_v1_summary}, indent=2))
    print(json.dumps({"causal": causal_summary}, indent=2))


if __name__ == "__main__":
    main()
