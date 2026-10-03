#!/usr/bin/env python3
"""V2-006: verify challenger OOF closure (9660 rows/seed x 3 seeds = 28980), compute pooled
per-seed/three-seed challenger metrics, and extract the matched CONTROL evidence READ-ONLY
from the frozen V2-004 MODEL_V2_TCN_MEANMAX result (D1 seed 20260927 + D2 seeds 20260928/
20260929) -- never re-run, never copied/modified in place."""

from __future__ import annotations

import csv
import json

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

import scripts._v2_006_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_006"
RUNS_DIR = OUT_DIR / "runs"
V2_004_DIR = lib.ROOT / "reports/model_v2/v2_004"
V2_004_RUNS_DIR = V2_004_DIR / "runs"


def _eligible_train_example_ids() -> set[str]:
    with lib.WINDOW_MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["example_id"]
        for row in rows
        if row["partition"] == "TRAIN" and row["core_eligible"].upper() == "TRUE"
    }


def _verify_closure(rows: list[dict], eligible_ids: set[str]) -> dict:
    ids = [r["example_id"] for r in rows]
    duplicates = len(ids) - len(set(ids))
    missing = sorted(eligible_ids - set(ids))
    extra = sorted(set(ids) - eligible_ids)
    status = len(rows) == len(eligible_ids) and duplicates == 0 and not missing and not extra
    return {
        "rows": len(rows),
        "expected_rows": len(eligible_ids),
        "duplicates": duplicates,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "closure_exact": status,
    }


def _pooled(labels: np.ndarray, probs: np.ndarray) -> tuple[float, float | None]:
    auprc = float(average_precision_score(labels, probs))
    auroc = float(roc_auc_score(labels, probs)) if len(np.unique(labels)) == 2 else None
    return auprc, auroc


def load_challenger_predictions() -> dict[int, list[dict]]:
    by_seed: dict[int, list[dict]] = {seed: [] for seed in lib.ALL_SEEDS}
    for seed in lib.ALL_SEEDS:
        for fold in lib.OUTER_FOLDS:
            exp_id = lib.experiment_id(fold, seed)
            path = RUNS_DIR / exp_id / "outer_predictions.csv"
            with path.open(newline="", encoding="utf-8") as handle:
                by_seed[seed].extend(csv.DictReader(handle))
    return by_seed


def load_control_predictions() -> dict[int, list[dict]]:
    """Read-only extraction from the already-frozen V2-004 MODEL_V2_TCN_MEANMAX result.
    D1 contributes seed 20260927 (folds 0-4); D2 contributes seeds 20260928/20260929
    (folds 0-4). Never re-run; never copies canonical V2-004 files, only reads them."""
    by_seed: dict[int, list[dict]] = {seed: [] for seed in lib.ALL_SEEDS}
    for fold in lib.OUTER_FOLDS:
        exp_id = f"V2-004-D1-MEANMAX-F{fold:02d}-S20260927"
        path = V2_004_RUNS_DIR / exp_id / "outer_predictions.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            by_seed[20260927].extend(csv.DictReader(handle))
    for seed in (20260928, 20260929):
        for fold in lib.OUTER_FOLDS:
            exp_id = f"V2-004-D2-MEANMAX-F{fold:02d}-S{seed}"
            path = V2_004_RUNS_DIR / exp_id / "outer_predictions.csv"
            with path.open(newline="", encoding="utf-8") as handle:
                by_seed[seed].extend(csv.DictReader(handle))
    return by_seed


def _seed_metrics(rows_by_seed: dict[int, list[dict]], eligible_ids: set[str]) -> dict:
    closure: dict[int, dict] = {}
    metrics: dict[int, dict] = {}
    for seed, rows in rows_by_seed.items():
        closure[seed] = _verify_closure(rows, eligible_ids)
        if not closure[seed]["closure_exact"]:
            continue
        labels = np.asarray([int(r["label"]) for r in rows], dtype=np.int64)
        probs = np.asarray([float(r["raw_probability"]) for r in rows], dtype=np.float64)
        auprc, auroc = _pooled(labels, probs)
        metrics[seed] = {"seed": seed, "pooled_OOF_AUPRC": auprc, "pooled_OOF_AUROC": auroc}
    return {"closure": closure, "metrics": metrics}


def _three_seed_summary(metrics: dict[int, dict]) -> dict:
    auprcs = [metrics[seed]["pooled_OOF_AUPRC"] for seed in sorted(metrics)]
    aurocs = [metrics[seed]["pooled_OOF_AUROC"] for seed in sorted(metrics)]
    return {
        "AUPRC_mean": float(np.mean(auprcs)),
        "AUPRC_sample_sd": float(np.std(auprcs, ddof=1)),
        "AUPRC_minimum": float(np.min(auprcs)),
        "AUROC_mean": float(np.mean(aurocs)),
        "AUROC_sample_sd": float(np.std(aurocs, ddof=1)),
    }


def main() -> None:
    eligible_ids = _eligible_train_example_ids()
    if len(eligible_ids) != 9660:
        raise RuntimeError(f"expected 9660 eligible TRAIN examples, found {len(eligible_ids)}")

    challenger_rows_by_seed = load_challenger_predictions()
    control_rows_by_seed = load_control_predictions()

    challenger_result = _seed_metrics(challenger_rows_by_seed, eligible_ids)
    control_result = _seed_metrics(control_rows_by_seed, eligible_ids)

    overall_status = "PASS" if (
        all(c["closure_exact"] for c in challenger_result["closure"].values())
        and all(c["closure_exact"] for c in control_result["closure"].values())
    ) else "FAIL"

    (OUT_DIR / "oof_closure_audit.json").write_text(
        json.dumps(
            {
                "challenger": challenger_result["closure"],
                "control": control_result["closure"],
                "total_challenger_rows": sum(
                    c["rows"] for c in challenger_result["closure"].values()
                ),
                "expected_total_challenger_rows": 28980,
                "status": overall_status,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if overall_status != "PASS":
        raise RuntimeError(f"V2-006 OOF closure FAILED: {challenger_result['closure']}")

    all_challenger_rows = []
    for seed in lib.ALL_SEEDS:
        all_challenger_rows.extend(challenger_rows_by_seed[seed])
    all_challenger_rows.sort(key=lambda r: (int(r["seed"]), r["example_id"]))
    with (OUT_DIR / "challenger_oof_predictions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(all_challenger_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(all_challenger_rows)

    with (OUT_DIR / "challenger_seed_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["seed", "pooled_OOF_AUPRC", "pooled_OOF_AUROC"])
        for seed in sorted(challenger_result["metrics"]):
            m = challenger_result["metrics"][seed]
            writer.writerow([seed, m["pooled_OOF_AUPRC"], m["pooled_OOF_AUROC"]])

    challenger_summary = _three_seed_summary(challenger_result["metrics"])
    control_summary = _three_seed_summary(control_result["metrics"])

    (OUT_DIR / "control_seed_metrics.json").write_text(
        json.dumps(
            {
                "architecture_id": lib.ARCHITECTURE_ID,
                "schedule_id": lib.CONTROL_SCHEDULE_ID,
                "source": "reports/model_v2/v2_004 (read-only, never re-run)",
                "per_seed": control_result["metrics"],
                "three_seed_summary": control_summary,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    (OUT_DIR / "control_reference_inventory.json").write_text(
        json.dumps(
            {
                "architecture_id": lib.ARCHITECTURE_ID,
                "schedule_id": lib.CONTROL_SCHEDULE_ID,
                "control_retrained": False,
                "source_experiment_ids": (
                    [f"V2-004-D1-MEANMAX-F{f:02d}-S20260927" for f in lib.OUTER_FOLDS]
                    + [
                        f"V2-004-D2-MEANMAX-F{f:02d}-S{seed}"
                        for seed in (20260928, 20260929)
                        for f in lib.OUTER_FOLDS
                    ]
                ),
                "per_seed_row_counts": {
                    seed: control_result["closure"][seed]["rows"] for seed in lib.ALL_SEEDS
                },
                "three_seed_summary": control_summary,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print("CONTROL three-seed summary:", json.dumps(control_summary, indent=2))
    print("CHALLENGER three-seed summary:", json.dumps(challenger_summary, indent=2))


if __name__ == "__main__":
    main()
