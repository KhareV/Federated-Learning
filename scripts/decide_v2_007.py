#!/usr/bin/env python3
"""V2-007 Sections 39-42: finalist selection, release candidate, paired promotion bootstraps
vs MODEL_V1, and the frozen promotion-rule evaluation. Reads only already-frozen prediction/
bootstrap artifacts -- no model inference, no waveform access.
"""

from __future__ import annotations

import csv
import json

import numpy as np

import scripts._v2_007_lib as lib
import scripts._v2_007_stats as stats

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"
RELEASE_SEED = lib.RELEASE_SEED


def _read(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def finalist_selection() -> dict:
    summary_rows = _read(OUT_DIR / "finalist_validation_summary.csv")
    finalist_summary = {r["architecture_id"]: r for r in summary_rows}
    a = finalist_summary["MODEL_V2_TCN_MEAN"]
    b = finalist_summary["MODEL_V2_TCN_MEANMAX"]

    dists = np.load(OUT_DIR / "finalist_rep_mean_distributions.npz")
    a_rep_mean = dists["A"]
    b_rep_mean = dists["B"]

    comparison = stats.finalist_comparison(
        a_three_seed_mean=float(a["mean_auprc"]),
        b_three_seed_mean=float(b["mean_auprc"]),
        a_rep_mean_distribution=a_rep_mean,
        b_rep_mean_distribution=b_rep_mean,
        a_params=int(a["parameter_count"]),
        b_params=int(b["parameter_count"]),
        a_seed_sd=float(a["sd_auprc"]),
        b_seed_sd=float(b["sd_auprc"]),
        a_config_id=a["schedule_id"],
        b_config_id=b["schedule_id"],
    )
    selected_row = a if comparison["selected"] == "A" else b

    data = {
        "a_mean_auprc": float(a["mean_auprc"]),
        "b_mean_auprc": float(b["mean_auprc"]),
        "delta_b_minus_a": comparison["delta_b_minus_a"],
        "bootstrap_se": comparison["bootstrap_se"],
        "within_one_se": comparison["within_one_se"],
        "a_params": int(a["parameter_count"]),
        "b_params": int(b["parameter_count"]),
        "a_seed_sd": float(a["sd_auprc"]),
        "b_seed_sd": float(b["sd_auprc"]),
        "tie_break_path": comparison["tie_break_path"],
        "selected_finalist": comparison["selected"],
        "selected_architecture_id": selected_row["architecture_id"],
        "selected_schedule_id": selected_row["schedule_id"],
        "selected_three_seed_mean_auprc": float(selected_row["mean_auprc"]),
        "selection_reason": (
            "higher_three_seed_mean_AUPRC_not_within_one_SE"
            if not comparison["within_one_se"]
            else f"within_one_SE_tie_break:{comparison['tie_break_path']}"
        ),
    }
    (OUT_DIR / "finalist_selection.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def _config_id(architecture_id: str, seed: int) -> str:
    return lib.experiment_id(architecture_id, seed)


def paired_promotion_bootstraps(selected_architecture_id: str) -> tuple[dict, dict]:
    dists = np.load(OUT_DIR / "finalist_rep_mean_distributions.npz")

    release_v2 = dists[f"{selected_architecture_id}_S{RELEASE_SEED}"]
    release_v1 = dists[f"V1_S{RELEASE_SEED}"]
    release_delta_rep = release_v2 - release_v1
    release_ci = stats.percentile_ci(release_delta_rep)
    release_point_delta = float(np.nanmean(release_v2) - np.nanmean(release_v1))

    selected_key = "A" if selected_architecture_id == "MODEL_V2_TCN_MEAN" else "B"
    three_seed_v2 = dists[selected_key]
    three_seed_v1 = dists["V1"]
    three_seed_delta_rep = three_seed_v2 - three_seed_v1
    three_seed_ci = stats.percentile_ci(three_seed_delta_rep)
    three_seed_point_delta = float(np.nanmean(three_seed_v2) - np.nanmean(three_seed_v1))

    release_rows = [
        {"replicate": i, "v2_auprc": float(release_v2[i]), "v1_auprc": float(release_v1[i]),
         "delta": float(release_delta_rep[i])}
        for i in range(len(release_delta_rep))
    ]
    with (OUT_DIR / "v1_release_paired_bootstrap.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        release_fields = list(release_rows[0].keys())
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=release_fields)
        writer.writeheader()
        writer.writerows(release_rows)

    three_seed_rows = [
        {"replicate": i, "v2_auprc": float(three_seed_v2[i]), "v1_auprc": float(three_seed_v1[i]),
         "delta": float(three_seed_delta_rep[i])}
        for i in range(len(three_seed_delta_rep))
    ]
    with (OUT_DIR / "v1_three_seed_paired_bootstrap.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(three_seed_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(three_seed_rows)

    release_summary = {
        "point_delta": release_point_delta, "ci": release_ci,
        "lower_gt_0": release_ci["lower"] > 0,
    }
    three_seed_summary = {
        "point_delta": three_seed_point_delta, "ci": three_seed_ci,
        "lower_gt_0": three_seed_ci["lower"] > 0,
    }
    return release_summary, three_seed_summary


def promotion(
    selection: dict, release_summary: dict, three_seed_summary: dict
) -> dict:
    decision = stats.promotion_decision(
        selected_three_seed_mean_auprc=selection["selected_three_seed_mean_auprc"],
        release_delta_ci=release_summary["ci"],
        three_seed_delta_ci=three_seed_summary["ci"],
    )
    data = {
        **decision,
        "selected_finalist": selection["selected_finalist"],
        "selected_architecture_id": selection["selected_architecture_id"],
        "selected_schedule_id": selection["selected_schedule_id"],
        "release_seed": RELEASE_SEED,
        "release_point_delta_vs_v1": release_summary["point_delta"],
        "release_ci": release_summary["ci"],
        "three_seed_point_delta_vs_v1": three_seed_summary["point_delta"],
        "three_seed_ci": three_seed_summary["ci"],
        "no_auroc_hard_gate": True,
        "no_p_value_gate": True,
        "no_rf_or_lr_gate": True,
    }
    (OUT_DIR / "promotion_decision.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def main() -> None:
    selection = finalist_selection()
    release_summary, three_seed_summary = paired_promotion_bootstraps(
        selection["selected_architecture_id"]
    )
    decision = promotion(selection, release_summary, three_seed_summary)
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
