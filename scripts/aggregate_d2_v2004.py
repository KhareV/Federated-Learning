#!/usr/bin/env python3
"""V2-004 D2: for each D1-advanced architecture, combine its reused D1 seed-20260927 OOF
predictions with the two freshly-run D2 seeds (20260928, 20260929) into one three-seed OOF
table, verify closure per seed, and compute per-seed pooled metrics plus the architecture-level
three-seed scalar summary (mean/sample SD/minimum, never a "best seed").
"""

from __future__ import annotations

import csv
import json

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

import scripts._v2_004_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_004"
RUNS_DIR = OUT_DIR / "runs"


def _eligible_train_example_ids() -> set[str]:
    with lib.WINDOW_MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["example_id"]
        for row in rows
        if row["partition"] == "TRAIN" and row["core_eligible"].upper() == "TRUE"
    }


def load_d1_seed_predictions(architecture_id: str) -> list[dict]:
    with (OUT_DIR / "d1_oof_predictions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [r for r in rows if r["architecture_id"] == architecture_id]


def load_d2_seed_predictions(architecture_id: str, seed: int) -> list[dict]:
    rows: list[dict] = []
    for fold in lib.OUTER_FOLDS:
        exp_id = lib.experiment_id("D2", architecture_id, fold, seed)
        path = RUNS_DIR / exp_id / "outer_predictions.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def verify_closure(rows: list[dict], eligible_ids: set[str]) -> dict:
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


def main(advanced_architectures: list[str]) -> None:
    eligible_ids = _eligible_train_example_ids()
    closure: dict[str, dict] = {}
    seed_metrics: dict[str, dict] = {}
    all_rows: list[dict] = []
    architecture_summary: dict[str, dict] = {}

    for architecture_id in advanced_architectures:
        per_seed_rows: dict[int, list[dict]] = {
            lib.D1_SEED: load_d1_seed_predictions(architecture_id)
        }
        for seed in lib.D2_SEEDS:
            per_seed_rows[seed] = load_d2_seed_predictions(architecture_id, seed)

        auprcs = []
        aurocs = []
        for seed, rows in per_seed_rows.items():
            key = f"{architecture_id}_{seed}"
            closure[key] = verify_closure(rows, eligible_ids)
            if not closure[key]["closure_exact"]:
                continue
            labels = np.asarray([int(r["label"]) for r in rows], dtype=np.int64)
            probs = np.asarray([float(r["raw_probability"]) for r in rows], dtype=np.float64)
            auprc, auroc = _pooled(labels, probs)
            seed_metrics[key] = {
                "architecture_id": architecture_id,
                "seed": seed,
                "pooled_OOF_AUPRC": auprc,
                "pooled_OOF_AUROC": auroc,
                "windows": len(rows),
            }
            auprcs.append(auprc)
            aurocs.append(auroc)
            all_rows.extend(rows)

        if len(auprcs) == 3:
            architecture_summary[architecture_id] = {
                "AUPRC_mean": float(np.mean(auprcs)),
                "AUPRC_sample_sd": float(np.std(auprcs, ddof=1)),
                "AUPRC_minimum": float(np.min(auprcs)),
                "AUROC_mean": float(np.mean(aurocs)),
                "AUROC_sample_sd": float(np.std(aurocs, ddof=1)),
                "AUROC_minimum": float(np.min(aurocs)),
                "parameter_count": lib.EXPECTED_PARAMETER_COUNTS[architecture_id],
                "note": (
                    "Summary of three independently trained seeds, never an ensemble "
                    "prediction and never a fourth model."
                ),
            }

    overall_status = "PASS" if all(c["closure_exact"] for c in closure.values()) else "FAIL"
    (OUT_DIR / "d2_oof_closure_audit.json").write_text(
        json.dumps({"per_seed": closure, "status": overall_status}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    if overall_status != "PASS":
        raise RuntimeError(f"D2 OOF closure FAILED: {closure}")

    rows_sorted = sorted(
        all_rows, key=lambda r: (r["architecture_id"], int(r["seed"]), r["example_id"])
    )
    with (OUT_DIR / "d2_oof_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows_sorted[0].keys()))
        writer.writeheader()
        writer.writerows(rows_sorted)

    with (OUT_DIR / "d2_seed_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["architecture_id", "seed", "pooled_OOF_AUPRC", "pooled_OOF_AUROC", "windows"]
        )
        for entry in seed_metrics.values():
            writer.writerow(
                [
                    entry["architecture_id"],
                    entry["seed"],
                    entry["pooled_OOF_AUPRC"],
                    entry["pooled_OOF_AUROC"],
                    entry["windows"],
                ]
            )

    (OUT_DIR / "d2_architecture_summary.json").write_text(
        json.dumps(architecture_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps(architecture_summary, indent=2))


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
