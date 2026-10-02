#!/usr/bin/env python3
"""V2-004 D1: verify OOF closure (9660 rows per architecture, seed 20260927 only) and compute
pooled OOF AUPRC/AUROC for each of the three architectures. Fold-level metrics are diagnostics
only, never averaged into the canonical per-architecture estimate."""

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


def load_d1_predictions() -> dict[str, list[dict]]:
    by_architecture: dict[str, list[dict]] = {arch: [] for arch in lib.ARCHITECTURE_IDS}
    for architecture_id in lib.ARCHITECTURE_IDS:
        for fold in lib.OUTER_FOLDS:
            exp_id = lib.experiment_id("D1", architecture_id, fold, lib.D1_SEED)
            path = RUNS_DIR / exp_id / "outer_predictions.csv"
            with path.open(newline="", encoding="utf-8") as handle:
                by_architecture[architecture_id].extend(csv.DictReader(handle))
    return by_architecture


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


def main() -> None:
    eligible_ids = _eligible_train_example_ids()
    if len(eligible_ids) != 9660:
        raise RuntimeError(f"expected 9660 eligible TRAIN examples, found {len(eligible_ids)}")

    by_architecture = load_d1_predictions()
    closure: dict[str, dict] = {}
    metrics: dict[str, dict] = {}
    all_rows: list[dict] = []
    for architecture_id, rows in by_architecture.items():
        closure[architecture_id] = verify_closure(rows, eligible_ids)
        if not closure[architecture_id]["closure_exact"]:
            continue
        labels = np.asarray([int(r["label"]) for r in rows], dtype=np.int64)
        probs = np.asarray([float(r["raw_probability"]) for r in rows], dtype=np.float64)
        pooled_auprc, pooled_auroc = _pooled(labels, probs)

        fold_diagnostics = []
        for fold in lib.OUTER_FOLDS:
            fold_rows = [r for r in rows if int(r["outer_fold"]) == fold]
            fold_labels = np.asarray([int(r["label"]) for r in fold_rows], dtype=np.int64)
            fold_probs = np.asarray(
                [float(r["raw_probability"]) for r in fold_rows], dtype=np.float64
            )
            fold_auprc, fold_auroc = _pooled(fold_labels, fold_probs)
            fold_diagnostics.append(
                {
                    "outer_fold": fold,
                    "AUPRC": fold_auprc,
                    "AUROC": fold_auroc,
                    "windows": len(fold_rows),
                }
            )

        metrics[architecture_id] = {
            "architecture_id": architecture_id,
            "seed": lib.D1_SEED,
            "pooled_OOF_AUPRC": pooled_auprc,
            "pooled_OOF_AUROC": pooled_auroc,
            "fold_level_diagnostics_not_averaged": fold_diagnostics,
            "parameter_count": lib.EXPECTED_PARAMETER_COUNTS[architecture_id],
        }
        all_rows.extend(rows)

    overall_status = "PASS" if all(c["closure_exact"] for c in closure.values()) else "FAIL"
    (OUT_DIR / "oof_closure_audit.json").write_text(
        json.dumps(
            {
                "stage": "D1",
                "per_architecture": closure,
                "total_rows_all_architectures": sum(c["rows"] for c in closure.values()),
                "expected_total_rows": 28980,
                "status": overall_status,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if overall_status != "PASS":
        raise RuntimeError(f"D1 OOF closure FAILED: {closure}")

    rows_sorted = sorted(all_rows, key=lambda r: (r["architecture_id"], r["example_id"]))
    with (OUT_DIR / "d1_oof_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows_sorted[0].keys()))
        writer.writeheader()
        writer.writerows(rows_sorted)

    (OUT_DIR / "d1_oof_metrics.json").write_text(
        json.dumps(
            {
                "canonical_metric_definition": (
                    "pooled AUPRC/AUROC on the concatenation of all 5 outer-fold predictions "
                    "for that architecture at seed 20260927 -- fold-level metrics are "
                    "diagnostics only, never averaged into the canonical estimate."
                ),
                "per_architecture": metrics,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with (OUT_DIR / "d1_fold_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["architecture_id", "outer_fold", "AUPRC", "AUROC", "windows"])
        for architecture_id, entry in metrics.items():
            for fold_row in entry["fold_level_diagnostics_not_averaged"]:
                writer.writerow(
                    [
                        architecture_id,
                        fold_row["outer_fold"],
                        fold_row["AUPRC"],
                        fold_row["AUROC"],
                        fold_row["windows"],
                    ]
                )

    print(json.dumps({"closure": overall_status}, indent=2))
    for architecture_id, entry in metrics.items():
        print(
            f"{architecture_id:20s} AUPRC={entry['pooled_OOF_AUPRC']:.6f} "
            f"AUROC={entry['pooled_OOF_AUROC']:.6f}"
        )


if __name__ == "__main__":
    main()
