"""C-V2-D0.6 frozen diagnostic computation primitives. Pure functions only -- no I/O, no model
fitting. Implements exactly the definitions bound in configs/model_v2/
d0_6_diagnostic_reconstruction_v1.yaml: diagnostic threshold selection, score-distribution
summaries, threshold-region error mass, leave-one-patient-out AUPRC contribution, and
patient-level Brier.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, f1_score

PERCENTILES = (5, 25, 50, 75, 95)
NEAR_THRESHOLD_WINDOW = 0.05


def diagnostic_threshold(labels: np.ndarray, probabilities: np.ndarray) -> float:
    """Maximize pooled F1 over candidate thresholds = unique observed probabilities plus 0.0
    and 1.0 boundary sentinels; comparator is >=; tie rule is HIGHEST_THRESHOLD_AMONG_MAX_F1."""
    labels = np.asarray(labels, dtype=np.int64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    candidates = np.unique(np.concatenate([probabilities, [0.0, 1.0]]))
    best_f1 = -1.0
    best_threshold = 0.0
    for threshold in candidates:
        predictions = (probabilities >= threshold).astype(np.int64)
        score = f1_score(labels, predictions, zero_division=0)
        if score > best_f1 or (score == best_f1 and threshold > best_threshold):
            best_f1 = score
            best_threshold = float(threshold)
    return best_threshold


def score_distribution_summary(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return {
            "n": 0, "mean": None, "std": None, "min": None, "max": None,
            **{f"p{p:02d}": None for p in PERCENTILES},
        }
    percentile_values = np.percentile(values, PERCENTILES)
    summary = {
        "n": int(values.size),
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=0)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }
    for p, value in zip(PERCENTILES, percentile_values, strict=True):
        key = "median" if p == 50 else f"p{p:02d}"
        summary[key] = float(value)
    return summary


def threshold_region_counts(
    labels: np.ndarray, probabilities: np.ndarray, threshold: float
) -> dict:
    labels = np.asarray(labels, dtype=np.int64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    predictions = (probabilities >= threshold).astype(np.int64)
    near = np.abs(probabilities - threshold) <= NEAR_THRESHOLD_WINDOW

    fp_mask = (predictions == 1) & (labels == 0)
    fn_mask = (predictions == 0) & (labels == 1)
    error_mask = fp_mask | fn_mask

    fp_total = int(fp_mask.sum())
    fn_total = int(fn_mask.sum())
    error_total = int(error_mask.sum())
    fp_near = int((fp_mask & near).sum())
    fn_near = int((fn_mask & near).sum())
    error_near = int((error_mask & near).sum())

    return {
        "threshold": float(threshold),
        "FP_near": fp_near,
        "FP_total": fp_total,
        "FP_near_fraction": (fp_near / fp_total) if fp_total else None,
        "FN_near": fn_near,
        "FN_total": fn_total,
        "FN_near_fraction": (fn_near / fn_total) if fn_total else None,
        "ALL_errors_near": error_near,
        "ALL_errors_total": error_total,
        "ALL_errors_near_fraction": (error_near / error_total) if error_total else None,
    }


def pooled_auprc(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    labels = np.asarray(labels, dtype=np.int64)
    if len(np.unique(labels)) < 2:
        return None
    return float(average_precision_score(labels, probabilities))


def leave_one_patient_out_auprc(
    labels: np.ndarray, probabilities: np.ndarray, groups: np.ndarray
) -> dict[str, float | None]:
    """contribution_delta[p] = full_AUPRC - without_p_AUPRC for every participant p. Never
    patient-averaged AUPRC -- always the pooled metric with/without that participant's rows."""
    labels = np.asarray(labels, dtype=np.int64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    groups = np.asarray(groups, dtype=str)
    full = pooled_auprc(labels, probabilities)
    deltas: dict[str, float | None] = {}
    for patient in sorted(set(groups.tolist())):
        mask = groups != patient
        without_p = pooled_auprc(labels[mask], probabilities[mask])
        if full is None or without_p is None:
            deltas[patient] = None
        else:
            deltas[patient] = full - without_p
    return deltas


def patient_brier(
    labels: np.ndarray, probabilities: np.ndarray, groups: np.ndarray
) -> dict[str, float]:
    labels = np.asarray(labels, dtype=np.int64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    groups = np.asarray(groups, dtype=str)
    result: dict[str, float] = {}
    for patient in sorted(set(groups.tolist())):
        mask = groups == patient
        result[patient] = float(np.mean(np.square(probabilities[mask] - labels[mask])))
    return result


__all__ = [
    "NEAR_THRESHOLD_WINDOW",
    "PERCENTILES",
    "diagnostic_threshold",
    "leave_one_patient_out_auprc",
    "patient_brier",
    "pooled_auprc",
    "score_distribution_summary",
    "threshold_region_counts",
]
