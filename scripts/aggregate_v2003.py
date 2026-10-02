#!/usr/bin/env python3
"""V2-003: verify OOF closure per (feature_variant, model_family) against the 9660 eligible
TRAIN examples, then write the canonical sorted oof_predictions.csv and pooled OOF AUPRC/AUROC
(+ descriptive 0.5-threshold metrics, + fold-level diagnostics never averaged into the
canonical estimate) for every variant x model family.
"""

from __future__ import annotations

import csv
import json

import numpy as np

import scripts._v2_003_lib as lib
from models.baselines import descriptive_metrics

OUT_DIR = lib.ROOT / "reports/model_v2/v2_003"


def _eligible_train_example_ids() -> set[str]:
    with lib.FEATURE_MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {row["example_id"] for row in rows if row["partition"] == "TRAIN"}


def load_fold_predictions() -> list[dict]:
    with (OUT_DIR / "fold_predictions.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify_closure(rows: list[dict], eligible_ids: set[str]) -> dict:
    per_combo = {}
    all_pass = True
    for variant in lib.VARIANT_IDS:
        for model_family in lib.MODEL_FAMILIES:
            key = f"{variant}_{model_family}"
            combo_rows = [
                r for r in rows if r["feature_variant"] == variant
                and r["model_family"] == model_family
            ]
            ids = [r["example_id"] for r in combo_rows]
            duplicates = len(ids) - len(set(ids))
            missing = sorted(eligible_ids - set(ids))
            extra = sorted(set(ids) - eligible_ids)
            status = (
                len(combo_rows) == len(eligible_ids)
                and duplicates == 0
                and not missing
                and not extra
            )
            all_pass = all_pass and status
            per_combo[key] = {
                "rows": len(combo_rows),
                "expected_rows": len(eligible_ids),
                "duplicates": duplicates,
                "missing_count": len(missing),
                "extra_count": len(extra),
                "closure_exact": status,
            }
    return {"status": "PASS" if all_pass else "FAIL", "per_combo": per_combo}


def compute_metrics(rows: list[dict]) -> dict:
    metrics: dict[str, dict] = {}
    for variant in lib.VARIANT_IDS:
        for model_family in lib.MODEL_FAMILIES:
            combo_rows = [
                r for r in rows if r["feature_variant"] == variant
                and r["model_family"] == model_family
            ]
            labels = np.asarray([int(r["label"]) for r in combo_rows], dtype=np.int64)
            probs = np.asarray([float(r["probability"]) for r in combo_rows], dtype=np.float64)
            groups = np.asarray([r["participant_group_id"] for r in combo_rows], dtype=str)
            descriptive = descriptive_metrics(labels, probs, groups)

            fold_diagnostics = []
            for fold in lib.OUTER_FOLDS:
                fold_rows = [r for r in combo_rows if int(r["outer_fold"]) == fold]
                fold_labels = np.asarray([int(r["label"]) for r in fold_rows], dtype=np.int64)
                fold_probs = np.asarray(
                    [float(r["probability"]) for r in fold_rows], dtype=np.float64
                )
                fold_metrics = descriptive_metrics(
                    fold_labels,
                    fold_probs,
                    np.asarray([r["participant_group_id"] for r in fold_rows], dtype=str),
                )
                fold_diagnostics.append(
                    {
                        "outer_fold": fold,
                        "AUPRC": fold_metrics["AUPRC"],
                        "AUROC": fold_metrics["AUROC"],
                        "windows": fold_metrics["windows"],
                    }
                )

            key = f"{variant}_{model_family}"
            metrics[key] = {
                "feature_variant": variant,
                "model_family": model_family,
                "feature_count": len(lib.VARIANT_INDICES[variant]),
                "pooled_OOF_AUPRC": descriptive["AUPRC"],
                "pooled_OOF_AUROC": descriptive["AUROC"],
                "descriptive_0_5_threshold": descriptive,
                "fold_level_diagnostics_not_averaged": fold_diagnostics,
            }
    return metrics


def main() -> None:
    rows = load_fold_predictions()
    eligible_ids = _eligible_train_example_ids()
    if len(eligible_ids) != 9660:
        raise RuntimeError(f"expected 9660 eligible TRAIN examples, found {len(eligible_ids)}")

    closure = verify_closure(rows, eligible_ids)
    (OUT_DIR / "oof_closure_audit.json").write_text(
        json.dumps(closure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if closure["status"] != "PASS":
        raise RuntimeError(f"V2-003 OOF closure FAILED: {closure}")

    rows_sorted = sorted(
        rows, key=lambda r: (r["feature_variant"], r["model_family"], r["example_id"])
    )
    oof_path = OUT_DIR / "oof_predictions.csv"
    with oof_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(rows_sorted[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows_sorted)

    metrics = compute_metrics(rows)
    (OUT_DIR / "oof_metrics.json").write_text(
        json.dumps(
            {
                "canonical_metric_definition": (
                    "pooled AUPRC/AUROC computed on the concatenation of all 5 outer-fold "
                    "OUTER_TEST predictions for that (feature_variant, model_family) -- "
                    "fold-level metrics are diagnostics only and are never averaged into the "
                    "canonical estimate; patient-average AUPRC is never computed."
                ),
                "per_variant_model": metrics,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    metrics_csv_path = OUT_DIR / "oof_metrics.csv"
    with metrics_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["feature_variant", "model_family", "feature_count", "pooled_OOF_AUPRC",
             "pooled_OOF_AUROC"]
        )
        for variant in lib.VARIANT_IDS:
            for model_family in lib.MODEL_FAMILIES:
                entry = metrics[f"{variant}_{model_family}"]
                writer.writerow(
                    [variant, model_family, entry["feature_count"],
                     entry["pooled_OOF_AUPRC"], entry["pooled_OOF_AUROC"]]
                )

    print(json.dumps({"closure": closure["status"]}, indent=2))
    for variant in lib.VARIANT_IDS:
        for model_family in lib.MODEL_FAMILIES:
            entry = metrics[f"{variant}_{model_family}"]
            print(
                f"{variant:10s} {model_family:8s} AUPRC={entry['pooled_OOF_AUPRC']:.6f} "
                f"AUROC={entry['pooled_OOF_AUROC']:.6f}"
            )


if __name__ == "__main__":
    main()
