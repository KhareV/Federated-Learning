#!/usr/bin/env python3
"""V2-006: apply the predeclared corrected-schedule adoption rule (POINT_DELTA strictly
greater than BOOTSTRAP_SE_DELTA, AND challenger seed SD <= control seed SD), compute
mechanism diagnostics, and freeze the finalist shortlist. Never re-opens the decision after
inspecting results; this script applies the rule exactly as frozen in
configs/model_v2/optimizer_correction_v1.yaml."""

from __future__ import annotations

import csv
import json

import numpy as np

import scripts._v2_006_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_006"
RUNS_DIR = OUT_DIR / "runs"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def mechanism_diagnostics() -> dict:
    rows = []
    for seed in lib.ALL_SEEDS:
        for fold in lib.OUTER_FOLDS:
            exp_id = lib.experiment_id(fold, seed)
            fit_summary = load_json(RUNS_DIR / exp_id / "fit_summary.json")
            rows.append(
                {
                    "experiment_id": exp_id,
                    "role": "CHALLENGER",
                    "seed": seed,
                    "outer_fold": fold,
                    "selected_epoch": fit_summary["selected_epoch"],
                    "stop_epoch": fit_summary["stop_epoch"],
                    "lr_reductions": fit_summary["lr_reductions"],
                    "first_lr_reduction_epoch": fit_summary.get("first_lr_reduction_epoch"),
                    "final_learning_rate": fit_summary["final_learning_rate"],
                    "best_inner_validation_auprc": fit_summary["best_inner_validation_auprc"],
                    "outer_auprc": fit_summary["outer_auprc"],
                    "outer_auroc": fit_summary["outer_auroc"],
                    "wall_clock_seconds": fit_summary["wall_clock_seconds"],
                }
            )

    v2_004_runs = lib.ROOT / "reports/model_v2/v2_004/runs"
    control_specs = [("D1", 20260927, f) for f in lib.OUTER_FOLDS] + [
        ("D2", seed, f) for seed in (20260928, 20260929) for f in lib.OUTER_FOLDS
    ]
    for stage, seed, fold in control_specs:
        exp_id = f"V2-004-{stage}-MEANMAX-F{fold:02d}-S{seed}"
        fit_summary = load_json(v2_004_runs / exp_id / "fit_summary.json")
        rows.append(
            {
                "experiment_id": exp_id,
                "role": "CONTROL",
                "seed": seed,
                "outer_fold": fold,
                "selected_epoch": fit_summary["selected_epoch"],
                "stop_epoch": fit_summary["stop_epoch"],
                "lr_reductions": fit_summary["lr_reductions"],
                "first_lr_reduction_epoch": None,
                "final_learning_rate": fit_summary["final_learning_rate"],
                "best_inner_validation_auprc": fit_summary["best_inner_validation_auprc"],
                "outer_auprc": fit_summary["outer_auprc"],
                "outer_auroc": fit_summary["outer_auroc"],
                "wall_clock_seconds": fit_summary["wall_clock_seconds"],
            }
        )

    with (OUT_DIR / "optimizer_mechanism_diagnostics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for role in ("CONTROL", "CHALLENGER"):
        role_rows = [r for r in rows if r["role"] == role]
        lr_reduced = [r for r in role_rows if r["lr_reductions"] >= 1]
        summary[role] = {
            "fraction_fits_with_ge_1_lr_reduction": len(lr_reduced) / len(role_rows),
            "median_lr_reduction_count": float(
                np.median([r["lr_reductions"] for r in role_rows])
            ),
            "median_selected_epoch": float(np.median([r["selected_epoch"] for r in role_rows])),
            "median_stop_epoch": float(np.median([r["stop_epoch"] for r in role_rows])),
        }
    (OUT_DIR / "optimizer_mechanism_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    control = load_json(OUT_DIR / "control_seed_metrics.json")
    challenger_metrics_rows = []
    with (OUT_DIR / "challenger_seed_metrics.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            challenger_metrics_rows.append(
                {"seed": int(row["seed"]), "AUPRC": float(row["pooled_OOF_AUPRC"])}
            )
    challenger_sorted = sorted(challenger_metrics_rows, key=lambda r: r["seed"])
    challenger_auprcs = [r["AUPRC"] for r in challenger_sorted]
    control_auprcs = [
        control["per_seed"][str(seed)]["pooled_OOF_AUPRC"] for seed in lib.ALL_SEEDS
    ]

    control_mean = float(np.mean(control_auprcs))
    challenger_mean = float(np.mean(challenger_auprcs))
    point_delta = challenger_mean - control_mean
    control_seed_sd = float(np.std(control_auprcs, ddof=1))
    challenger_seed_sd = float(np.std(challenger_auprcs, ddof=1))

    bootstrap = load_json(OUT_DIR / "paired_bootstrap_summary.json")
    bootstrap_se_delta = bootstrap["BOOTSTRAP_SE_DELTA"]
    sufficient_replicates = bootstrap["sufficient_valid_replicates_for_adoption_decision"]

    oof_closure = load_json(OUT_DIR / "oof_closure_audit.json")
    oof_closure_exact = oof_closure["status"] == "PASS"

    improvement_gt_one_se = (
        sufficient_replicates and bootstrap_se_delta is not None
        and point_delta > bootstrap_se_delta
    )
    seed_sd_not_worse = challenger_seed_sd <= control_seed_sd

    if not oof_closure_exact or not sufficient_replicates:
        decision = "ORIGINAL_SCHEDULE_RETAINED_INVALID_CHALLENGER"
        adopted = False
    elif improvement_gt_one_se and seed_sd_not_worse:
        decision = "CORRECTED_SCHEDULE_ADOPTED"
        adopted = True
    elif not improvement_gt_one_se and not seed_sd_not_worse:
        decision = "ORIGINAL_SCHEDULE_RETAINED_BOTH_CRITERIA_FAILED"
        adopted = False
    elif not improvement_gt_one_se:
        decision = "ORIGINAL_SCHEDULE_RETAINED_INSUFFICIENT_IMPROVEMENT"
        adopted = False
    else:
        decision = "ORIGINAL_SCHEDULE_RETAINED_SEED_VARIANCE_WORSE"
        adopted = False

    optimizer_comparison = {
        "control_architecture": lib.ARCHITECTURE_ID,
        "control_schedule_id": lib.CONTROL_SCHEDULE_ID,
        "challenger_architecture": lib.ARCHITECTURE_ID,
        "challenger_schedule_id": lib.CHALLENGER_SCHEDULE_ID,
        "unchanged_parameters": [
            "architecture", "parameter_count", "preprocessing", "augmentation",
            "dataset_rows", "outer_folds", "inner_roles", "loss", "pos_weight_rule",
            "optimizer_family_AdamW", "learning_rate_0.001", "weight_decay_0.0001",
            "batch_size_64", "max_epochs_50", "checkpoint_metric",
        ],
        "changed_parameters": {
            "scheduler_patience": {"control": 10, "challenger": 3},
            "scheduler_factor": {"control": 0.1, "challenger": 0.3},
            "early_stopping_patience": {"control": 7, "challenger": 8},
        },
        "control_seed_metrics": control["per_seed"],
        "challenger_seed_metrics": {
            str(r["seed"]): {"AUPRC": r["AUPRC"]} for r in challenger_metrics_rows
        },
        "control_mean_AUPRC": control_mean,
        "challenger_mean_AUPRC": challenger_mean,
        "POINT_DELTA": point_delta,
        "control_seed_SD": control_seed_sd,
        "challenger_seed_SD": challenger_seed_sd,
        "bootstrap_valid_B": bootstrap["valid_B"],
        "BOOTSTRAP_SE_DELTA": bootstrap_se_delta,
        "paired_95_percentile_CI": bootstrap["delta_AUPRC_ci_95_percentile"],
        "improvement_gt_one_SE": improvement_gt_one_se,
        "seed_SD_not_worse": seed_sd_not_worse,
        "corrected_schedule_adopted": adopted,
        "decision_reason": decision,
    }
    (OUT_DIR / "optimizer_comparison.json").write_text(
        json.dumps(optimizer_comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    adoption_decision = {
        "decision": decision,
        "corrected_schedule_adopted": adopted,
        "point_delta": point_delta,
        "bootstrap_se_delta": bootstrap_se_delta,
        "improvement_gt_one_se": improvement_gt_one_se,
        "seed_sd_not_worse": seed_sd_not_worse,
        "oof_closure_exact": oof_closure_exact,
        "sufficient_valid_bootstrap_replicates": sufficient_replicates,
        "auroc_used_as_adoption_gate": False,
        "p_value_used": False,
        "ci_alone_used_for_decision": False,
    }
    (OUT_DIR / "adoption_decision.json").write_text(
        json.dumps(adoption_decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    finalist_b_schedule = (
        "CONFIG_V2_TCN_MEANMAX_OPT_CORR_V1" if adopted else "CONFIG_V2_TCN_MEANMAX_ORIGINAL_V1"
    )
    shortlist = {
        "shortlist_id": "MODEL_V2_FINALIST_SHORTLIST_V1",
        "max_official_validation_configurations": 2,
        "finalists": [
            {
                "finalist": "A",
                "architecture_id": "MODEL_V2_TCN_MEAN",
                "schedule_id": "CONFIG_V2_TCN_MEAN_ORIGINAL_V1",
                "optimizer_challenged": False,
            },
            {
                "finalist": "B",
                "architecture_id": "MODEL_V2_TCN_MEANMAX",
                "schedule_id": finalist_b_schedule,
                "optimizer_challenged": True,
                "adoption_decision": decision,
            },
        ],
        "shortlist_count": 2,
        "rejected_schedule_variant_excluded": True,
        "model_v2_final_selected": False,
        "bindings": {
            "protocol_v3_lock_sha256": (
                "287aff4ff3fcf583524f06e6af51f23bd65949a75abef14cde80ff0936873db8"
            ),
            "arch_causality_lock_sha256": (
                "79c423fdcbd5c9dee1743ec60f704e56a48af201b6357499990cd54fa35729c3"
            ),
            "final_inner_manifest_for_v2_007": "MITDB_TRAIN_FINAL_INNER_V2_V1",
            "v2_006_optimizer_correction_result": (
                "reports/model_v2/v2_006/optimizer_comparison.json"
            ),
        },
        "seeds_for_v2_007": [20260927, 20260928, 20260929],
    }
    (OUT_DIR / "finalist_shortlist.json").write_text(
        json.dumps(shortlist, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    mechanism_diagnostics()

    print(json.dumps(adoption_decision, indent=2))
    print(json.dumps(shortlist, indent=2))


if __name__ == "__main__":
    main()
