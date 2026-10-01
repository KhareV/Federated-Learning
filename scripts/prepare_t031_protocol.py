#!/usr/bin/env python3
"""Freeze T031 cases and descriptive-analysis rules before attribution inspection."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from datasets.labels import NOT_A_BEAT, map_annotation_symbol
from datasets.mitdb import DEFAULT_RAW_ROOT, EXPECTED_FS_HZ, load_annotations
from evaluation.error_analysis import (
    annotation_hr_seconds,
    derive_hr_quartiles,
    select_explainability_cases,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/t031"
PREDICTIONS = ROOT / "reports/internal_test_predictions.csv"
WINDOWS = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_yaml(path: Path, value: Any) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def record_beat_times(record_id: str) -> np.ndarray:
    annotations = load_annotations(record_id, ROOT / DEFAULT_RAW_ROOT)
    samples = [
        int(sample)
        for sample, symbol in zip(annotations.sample, annotations.symbol, strict=True)
        if map_annotation_symbol(str(symbol)).mapped_class != NOT_A_BEAT
    ]
    return np.asarray(samples, dtype=np.float64) / EXPECTED_FS_HZ


def main() -> None:
    REPORT.mkdir(parents=True, exist_ok=True)
    predictions = csv_rows(PREDICTIONS)
    windows = {row["example_id"]: row for row in csv_rows(WINDOWS)}
    selected = select_explainability_cases(predictions)
    pseudonyms = {
        value: f"INT_PATIENT_{index:03d}"
        for index, value in enumerate(
            sorted({row["participant_group_id"] for row in predictions}), 1
        )
    }
    manifest_fields = [
        "case_type",
        "window_id",
        "participant_pseudonym",
        "record_id",
        "prediction_timestamp_us",
        "label",
        "calibrated_probability",
        "frozen_threshold",
        "selection_rule",
        "tie_rule",
    ]
    manifest_rows = []
    for case_type in ("TP", "TN", "FP", "FN"):
        row = selected[case_type]
        manifest_rows.append(
            {
                "case_type": case_type,
                "window_id": row["example_id"],
                "participant_pseudonym": pseudonyms[row["participant_group_id"]],
                "record_id": row["record_id"],
                "prediction_timestamp_us": row["prediction_timestamp_us"],
                "label": row["label"],
                "calibrated_probability": row["source_domain_calibrated_probability"],
                "frozen_threshold": row["threshold"],
                "selection_rule": {
                    "TP": "highest_probability",
                    "TN": "lowest_probability",
                    "FP": "highest_probability",
                    "FN": "lowest_probability",
                }[case_type],
                "tie_rule": "lexicographically_smallest_window_id",
            }
        )
    manifest_path = REPORT / "explainability_case_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)

    counts = {case: 0 for case in ("TP", "TN", "FP", "FN")}
    for row in predictions:
        key = ("T" if row["label"] == row["thresholded_prediction"] else "F") + (
            "P" if row["thresholded_prediction"] == "1" else "N"
        )
        counts[key] += 1
    write_json(
        REPORT / "case_selection_audit.json",
        {
            "frozen_predictions_sha256": hash_file(PREDICTIONS),
            "frozen_threshold": float(predictions[0]["threshold"]),
            "confusion_counts": counts,
            "selection_rule": {
                "TP": "highest source-domain calibrated probability",
                "TN": "lowest source-domain calibrated probability",
                "FP": "highest source-domain calibrated probability",
                "FN": "lowest source-domain calibrated probability",
            },
            "tie_rule": "lexicographically smallest window_id",
            "selected_window_ids": {row["case_type"]: row["window_id"] for row in manifest_rows},
            "generated_before_attribution_rendering": True,
            "manual_selection": False,
            "status": "PASS",
        },
    )

    train_rows = [
        row
        for row in windows.values()
        if row["partition"] == "TRAIN" and row["core_eligible"].upper() == "TRUE"
    ]
    beats_by_record = {
        record: record_beat_times(record)
        for record in sorted({row["record_id"] for row in train_rows})
    }
    rates: list[float] = []
    for row in train_rows:
        end = int(row["prediction_timestamp_us"]) / 1_000_000.0
        times = beats_by_record[row["record_id"]]
        inside = times[(times > end - 10.0) & (times <= end)]
        rate = annotation_hr_seconds(inside.tolist())
        if rate is not None:
            rates.append(rate)
    edges = derive_hr_quartiles(rates)
    hr_report = {
        "id": "HR_ANALYSIS_BINS_V1",
        "derivation_partition": "TRAIN",
        "estimator": "60 / median consecutive annotation RR intervals wholly inside window",
        "minimum_intervals": 2,
        "defined_train_windows": len(rates),
        "total_train_windows": len(train_rows),
        "Q1_bpm": edges[0],
        "Q2_bpm": edges[1],
        "Q3_bpm": edges[2],
        "quantile_method": "linear",
        "status": "FROZEN_DESCRIPTIVE_METHOD",
    }
    write_json(REPORT / "hr_bins.json", hr_report)

    explain_config = {
        "id": "EXPLAINABILITY_V1",
        "MODEL_V1_sha256": hash_file(ROOT / "checkpoints/MODEL_V1.pt"),
        "PREPROC_V1_lock_sha256": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
        "CAL_V1_sha256": hash_file(ROOT / "artifacts/CAL_V1.json"),
        "internal_predictions_sha256": hash_file(PREDICTIONS),
        "target": "MODEL_V1_PRE_SIGMOID_LOGIT",
        "baseline": "ALL_ZERO_NORMALIZED_INPUT",
        "integration": "GAUSS_LEGENDRE",
        "steps": 64,
        "case_selection": "TP high; TN low; FP high; FN low calibrated probability",
        "tie_rule": "lexicographically_smallest_window_id",
        "overlay_normalization": "PER_WINDOW_ABS_DIVIDE_BY_WINDOW_MAX",
        "completeness": "sum(IG) - (F(x)-F(zero))",
        "completeness_acceptance": "absolute<=1e-3 OR relative<=1e-3",
        "claim_boundary": "engineering diagnostic only; non-causal and non-clinical",
    }
    write_yaml(ROOT / "configs/explainability_v1.yaml", explain_config)
    error_config = {
        "id": "ERROR_ANALYSIS_V1",
        "patient_metric": "frozen-threshold F1",
        "class_composition": "F first; else S/V dominance or tie",
        "HR_estimator": hr_report["estimator"],
        "HR_bins": {"Q1_bpm": edges[0], "Q2_bpm": edges[1], "Q3_bpm": edges[2]},
        "HR_derivation_partition": "TRAIN_ONLY",
        "threshold_region": {"id": "THRESHOLD_REGION_V1", "margin": 0.05},
        "dataset_sources": ["MITDB_INTERNAL_TEST", "INCART_FROZEN_EXTERNAL", "NSTDB_T019"],
        "wearable_status": "DEFERRED_T030_HARDWARE",
        "posthoc_only": True,
    }
    write_yaml(ROOT / "configs/error_analysis_v1.yaml", error_config)

    bound = [
        "checkpoints/MODEL_V1.pt",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "artifacts/CAL_V1.json",
        "reports/internal_test_predictions.csv",
        "reports/t031/explainability_case_manifest.csv",
        "evaluation/explain.py",
        "configs/explainability_v1.yaml",
        "configs/error_analysis_v1.yaml",
        "reports/t031/hr_bins.json",
    ]
    write_json(
        ROOT / "artifacts/EXPLAINABILITY_V1_METHOD.lock.json",
        {
            "lock_id": "EXPLAINABILITY_V1_METHOD",
            "status": "FROZEN_COMPONENT_METHOD",
            "target": "MODEL_V1_PRE_SIGMOID_LOGIT",
            "baseline": "ALL_ZERO_NORMALIZED_INPUT",
            "integration": "64_POINT_GAUSS_LEGENDRE",
            "overlay": "PER_WINDOW_NORMALIZED_ABSOLUTE_IG_WITH_SIGNED_IG_PRESERVED",
            "case_selection": explain_config["case_selection"],
            "claim_boundary": explain_config["claim_boundary"],
            "bound_artifacts": {path: hash_file(ROOT / path) for path in bound},
        },
    )


if __name__ == "__main__":
    main()
