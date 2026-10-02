#!/usr/bin/env python3
"""V2-002: aggregate the 15 per-fit outer-fold prediction CSVs into one canonical OOF table,
verify closure, and compute the canonical pooled-OOF metrics per seed (never averaging fold
metrics, never averaging per-patient AUPRC). No model re-inference -- reads only the already-
saved per-fit prediction CSVs.
"""

from __future__ import annotations

import csv
import json

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

import scripts._v2_002_lib as lib
from nhm.hashing import hash_file

OUT_DIR = lib.ROOT / "reports/model_v2/v2_002"
RUNS_DIR = OUT_DIR / "runs"
EXPECTED_WINDOWS_PER_SEED = 9660
EXPECTED_TOTAL_ROWS = 28980


def load_all_predictions() -> list[dict]:
    rows: list[dict] = []
    for fold in lib.OUTER_FOLDS:
        for seed in lib.SEEDS:
            exp_id = lib.experiment_id(fold, seed)
            path = RUNS_DIR / exp_id / "outer_predictions.csv"
            if not path.exists():
                raise RuntimeError(f"missing per-fit predictions for {exp_id}: {path}")
            with path.open(newline="", encoding="utf-8") as handle:
                rows.extend(csv.DictReader(handle))
    return rows


def verify_closure(rows: list[dict]) -> dict:
    train_groups = {
        row["participant_group_id"]
        for row in lib._read_csv(lib.SPLIT_CSV)
        if row["partition"] == "TRAIN"
    }
    eligible_train_example_ids = {
        row["example_id"]
        for row in lib._read_csv(lib.WINDOW_MANIFEST)
        if row["partition"] == "TRAIN" and row["core_eligible"].upper() == "TRUE"
    }

    per_seed_audit = {}
    for seed in lib.SEEDS:
        seed_rows = [r for r in rows if int(r["seed"]) == seed]
        example_ids = [r["example_id"] for r in seed_rows]
        example_id_set = set(example_ids)
        duplicates = len(example_ids) - len(example_id_set)
        missing = eligible_train_example_ids - example_id_set
        extra = example_id_set - eligible_train_example_ids
        non_train = {
            r["participant_group_id"]
            for r in seed_rows
            if r["participant_group_id"] not in train_groups
        }
        per_seed_audit[str(seed)] = {
            "rows": len(seed_rows),
            "expected_rows": EXPECTED_WINDOWS_PER_SEED,
            "duplicates": duplicates,
            "missing_count": len(missing),
            "extra_count": len(extra),
            "non_train_participant_groups": sorted(non_train),
            "closure_exact": (
                len(seed_rows) == EXPECTED_WINDOWS_PER_SEED
                and duplicates == 0
                and not missing
                and not extra
                and not non_train
            ),
        }

    total_rows = len(rows)
    overall = {
        "total_rows": total_rows,
        "expected_total_rows": EXPECTED_TOTAL_ROWS,
        "per_seed": per_seed_audit,
        "all_seeds_closure_exact": all(v["closure_exact"] for v in per_seed_audit.values()),
        "total_rows_exact": total_rows == EXPECTED_TOTAL_ROWS,
    }
    overall["status"] = (
        "PASS" if overall["all_seeds_closure_exact"] and overall["total_rows_exact"] else "FAIL"
    )
    return overall


def compute_metrics(rows: list[dict]) -> dict:
    per_seed_metrics = {}
    for seed in lib.SEEDS:
        seed_rows = [r for r in rows if int(r["seed"]) == seed]
        labels = np.array([int(r["label"]) for r in seed_rows])
        probabilities = np.array([float(r["raw_probability"]) for r in seed_rows])
        auprc = float(average_precision_score(labels, probabilities))
        auroc = (
            float(roc_auc_score(labels, probabilities)) if len(np.unique(labels)) == 2 else None
        )

        fold_diagnostics = []
        for fold in lib.OUTER_FOLDS:
            fold_rows = [r for r in seed_rows if int(r["outer_fold"]) == fold]
            fold_labels = np.array([int(r["label"]) for r in fold_rows])
            fold_probs = np.array([float(r["raw_probability"]) for r in fold_rows])
            fold_auprc = float(average_precision_score(fold_labels, fold_probs))
            fold_auroc = (
                float(roc_auc_score(fold_labels, fold_probs))
                if len(np.unique(fold_labels)) == 2
                else None
            )
            fold_diagnostics.append(
                {
                    "outer_fold": fold,
                    "windows": len(fold_rows),
                    "AUPRC": fold_auprc,
                    "AUROC": fold_auroc,
                }
            )

        per_seed_metrics[str(seed)] = {
            "pooled_OOF_AUPRC": auprc,
            "pooled_OOF_AUROC": auroc,
            "windows": len(seed_rows),
            "positives": int(labels.sum()),
            "negatives": int(labels.size - labels.sum()),
            "fold_level_diagnostics_not_averaged": fold_diagnostics,
        }

    auprcs = np.array([per_seed_metrics[str(s)]["pooled_OOF_AUPRC"] for s in lib.SEEDS])
    auroc_values = [per_seed_metrics[str(s)]["pooled_OOF_AUROC"] for s in lib.SEEDS]
    auroc_arr = np.array([v for v in auroc_values if v is not None])

    three_seed = {
        "AUPRC_mean": float(np.mean(auprcs)),
        "AUPRC_sample_sd": float(np.std(auprcs, ddof=1)),
        "AUPRC_minimum": float(np.min(auprcs)),
        "AUROC_mean": float(np.mean(auroc_arr)) if auroc_arr.size == len(lib.SEEDS) else None,
        "AUROC_sample_sd": (
            float(np.std(auroc_arr, ddof=1)) if auroc_arr.size == len(lib.SEEDS) else None
        ),
        "AUROC_minimum": float(np.min(auroc_arr)) if auroc_arr.size == len(lib.SEEDS) else None,
        "note": (
            "This is a summary of three independently trained models (one per seed), "
            "never an ensemble prediction and never a fourth model."
        ),
    }
    return {
        "per_seed": per_seed_metrics,
        "three_seed_summary": three_seed,
        "canonical_metric_definition": (
            "pooled AUPRC/AUROC computed on the concatenation of all 5 outer-fold OOF "
            "predictions for that seed -- fold-level metrics are diagnostics only and are "
            "never averaged into the canonical per-seed estimate; patient-average AUPRC is "
            "never computed."
        ),
    }


def main() -> None:
    rows = load_all_predictions()
    closure = verify_closure(rows)
    if closure["status"] != "PASS":
        raise RuntimeError(f"OOF closure FAILED: {json.dumps(closure, indent=2)}")
    metrics = compute_metrics(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_sorted = sorted(rows, key=lambda r: (int(r["seed"]), r["example_id"]))
    oof_path = OUT_DIR / "oof_predictions.csv"
    with oof_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_sorted[0].keys()))
        writer.writeheader()
        writer.writerows(rows_sorted)

    (OUT_DIR / "oof_closure_audit.json").write_text(
        json.dumps(closure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    metrics["oof_predictions_sha256"] = hash_file(oof_path)
    (OUT_DIR / "oof_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    metrics_csv_path = OUT_DIR / "oof_metrics.csv"
    with metrics_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["seed", "pooled_OOF_AUPRC", "pooled_OOF_AUROC", "windows"])
        for seed in lib.SEEDS:
            entry = metrics["per_seed"][str(seed)]
            writer.writerow(
                [seed, entry["pooled_OOF_AUPRC"], entry["pooled_OOF_AUROC"], entry["windows"]]
            )

    summary = {"closure": closure["status"], "three_seed_summary": metrics["three_seed_summary"]}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
