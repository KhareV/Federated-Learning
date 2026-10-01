"""Deterministic post-hoc slicing utilities for ERROR_ANALYSIS_V1."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


def confusion(label: int, prediction: int) -> str:
    return ("T" if label == prediction else "F") + ("P" if prediction else "N")


def select_explainability_cases(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in ("TP", "TN", "FP", "FN")}
    for row in rows:
        grouped[confusion(int(row["label"]), int(row["thresholded_prediction"]))].append(row)
    if any(not values for values in grouped.values()):
        raise ValueError("TP/TN/FP/FN must all be represented")

    def probability(row: dict[str, Any]) -> float:
        return float(row["source_domain_calibrated_probability"])

    return {
        "TP": sorted(grouped["TP"], key=lambda row: (-probability(row), row["example_id"]))[0],
        "TN": sorted(grouped["TN"], key=lambda row: (probability(row), row["example_id"]))[0],
        "FP": sorted(grouped["FP"], key=lambda row: (-probability(row), row["example_id"]))[0],
        "FN": sorted(grouped["FN"], key=lambda row: (probability(row), row["example_id"]))[0],
    }


def patient_pseudonyms(group_ids: Iterable[str], prefix: str = "INT_PATIENT") -> dict[str, str]:
    return {value: f"{prefix}_{index:03d}" for index, value in enumerate(sorted(set(group_ids)), 1)}


def class_composition(s_count: int, v_count: int, f_count: int) -> str:
    if f_count > 0:
        return "F_CONTAINING"
    if s_count > v_count:
        return "S_DOMINANT"
    if v_count > s_count:
        return "V_DOMINANT"
    if s_count == v_count and s_count > 0:
        return "S_V_TIE"
    return "NO_SVF_COMPOSITION"


def annotation_hr_seconds(timestamps: Sequence[float]) -> float | None:
    values = np.asarray(timestamps, dtype=np.float64)
    if values.size < 3:
        return None
    intervals = np.diff(values)
    intervals = intervals[np.isfinite(intervals) & (intervals > 0)]
    if intervals.size < 2:
        return None
    return float(60.0 / np.median(intervals))


def derive_hr_quartiles(train_rates: Sequence[float]) -> tuple[float, float, float]:
    values = np.asarray(train_rates, dtype=np.float64)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("TRAIN HR values must be nonempty and finite")
    result = np.quantile(values, [0.25, 0.5, 0.75], method="linear")
    return tuple(float(value) for value in result)


def assign_hr_bin(rate: float | None, edges: Sequence[float]) -> str:
    if rate is None or not np.isfinite(rate):
        return "HR_UNDEFINED"
    q1, q2, q3 = edges
    if rate <= q1:
        return "HR_BIN_1"
    if rate <= q2:
        return "HR_BIN_2"
    if rate <= q3:
        return "HR_BIN_3"
    return "HR_BIN_4"


def threshold_region(probability: float, threshold: float, margin: float = 0.05) -> bool:
    if margin != 0.05:
        raise ValueError("THRESHOLD_REGION_V1 margin must be 0.05")
    return abs(probability - threshold) <= margin + 1e-12


def binary_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    labels = np.asarray([int(row["label"]) for row in rows], dtype=np.int64)
    predictions = np.asarray([int(row["thresholded_prediction"]) for row in rows], dtype=np.int64)
    probabilities = np.asarray(
        [float(row["source_domain_calibrated_probability"]) for row in rows], dtype=np.float64
    )
    tp = int(np.sum((labels == 1) & (predictions == 1)))
    tn = int(np.sum((labels == 0) & (predictions == 0)))
    fp = int(np.sum((labels == 0) & (predictions == 1)))
    fn = int(np.sum((labels == 1) & (predictions == 0)))
    both = len(set(labels.tolist())) == 2
    return {
        "support": int(labels.size),
        "positive": int(labels.sum()),
        "negative": int(labels.size - labels.sum()),
        "positive_prevalence": float(labels.mean()) if labels.size else None,
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "F1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        "sensitivity": tp / (tp + fn) if tp + fn else "UNDEFINED_SINGLE_CLASS",
        "specificity": tn / (tn + fp) if tn + fp else "UNDEFINED_SINGLE_CLASS",
        "AUPRC": float(average_precision_score(labels, probabilities))
        if both
        else "UNDEFINED_SINGLE_CLASS",
        "AUROC": float(roc_auc_score(labels, probabilities)) if both else "UNDEFINED_SINGLE_CLASS",
    }


@dataclass(frozen=True)
class HRSliceRow:
    window_id: str
    participant_group_id: str
    rate_bpm: float | None
