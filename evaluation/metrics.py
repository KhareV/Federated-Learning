"""Canonical window and patient-level binary metrics for frozen evaluations."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

METRIC_NAMES = (
    "AUPRC",
    "AUROC",
    "pooled_F1",
    "precision",
    "sensitivity",
    "specificity",
    "patient_macro_F1",
)


class MetricError(ValueError):
    """Raised when metric inputs violate the frozen evaluation contract."""


def _binary(values: np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.int64).reshape(-1)
    if not np.all(np.isin(array, (0, 1))):
        raise MetricError(f"{name}_MUST_BE_BINARY")
    return array


def confusion_counts(labels: np.ndarray, predictions: np.ndarray) -> dict[str, int]:
    targets = _binary(labels, "LABELS")
    predicted = _binary(predictions, "PREDICTIONS")
    if targets.shape != predicted.shape or targets.size == 0:
        raise MetricError("METRIC_INPUT_SHAPE_MISMATCH")
    return {
        "tp": int(np.sum((targets == 1) & (predicted == 1))),
        "fp": int(np.sum((targets == 0) & (predicted == 1))),
        "tn": int(np.sum((targets == 0) & (predicted == 0))),
        "fn": int(np.sum((targets == 1) & (predicted == 0))),
    }


def f1_from_counts(counts: dict[str, int]) -> float:
    denominator = 2 * counts["tp"] + counts["fp"] + counts["fn"]
    return float(2 * counts["tp"] / denominator) if denominator else 0.0


def patient_f1_values(
    patient_ids: np.ndarray, labels: np.ndarray, predictions: np.ndarray
) -> dict[str, float]:
    patients = np.asarray(patient_ids, dtype=str).reshape(-1)
    targets = _binary(labels, "LABELS")
    predicted = _binary(predictions, "PREDICTIONS")
    if not (patients.shape == targets.shape == predicted.shape) or patients.size == 0:
        raise MetricError("PATIENT_METRIC_INPUT_SHAPE_MISMATCH")
    result: dict[str, float] = {}
    for patient in sorted(set(patients.tolist())):
        selected = patients == patient
        result[patient] = f1_from_counts(confusion_counts(targets[selected], predicted[selected]))
    return result


def patient_macro_f1(
    patient_ids: np.ndarray, labels: np.ndarray, predictions: np.ndarray
) -> float:
    values = patient_f1_values(patient_ids, labels, predictions)
    return float(np.mean(list(values.values())))


def pooled_binary_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    predictions: np.ndarray,
    patient_ids: np.ndarray,
    *,
    allow_undefined: bool = False,
) -> dict[str, Any]:
    """Recompute all locked metrics from window rows; never average patient AUPRC."""
    targets = _binary(labels, "LABELS")
    scores = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    predicted = _binary(predictions, "PREDICTIONS")
    patients = np.asarray(patient_ids, dtype=str).reshape(-1)
    if not (targets.shape == scores.shape == predicted.shape == patients.shape):
        raise MetricError("METRIC_INPUT_SHAPE_MISMATCH")
    if targets.size == 0 or not np.all(np.isfinite(scores)):
        raise MetricError("METRIC_INPUT_EMPTY_OR_NONFINITE")
    both_classes = set(np.unique(targets).tolist()) == {0, 1}
    if not both_classes and not allow_undefined:
        raise MetricError("EVALUATION_CLASS_DEGENERACY")
    counts = confusion_counts(targets, predicted)
    positive_denominator = counts["tp"] + counts["fn"]
    negative_denominator = counts["tn"] + counts["fp"]
    precision_denominator = counts["tp"] + counts["fp"]
    return {
        "AUPRC": float(average_precision_score(targets, scores)) if both_classes else None,
        "AUROC": float(roc_auc_score(targets, scores)) if both_classes else None,
        "pooled_F1": f1_from_counts(counts),
        "precision": (
            float(counts["tp"] / precision_denominator) if precision_denominator else 0.0
        ),
        "sensitivity": (
            float(counts["tp"] / positive_denominator) if positive_denominator else None
        ),
        "specificity": (
            float(counts["tn"] / negative_denominator) if negative_denominator else None
        ),
        "patient_macro_F1": patient_macro_f1(patients, targets, predicted),
        "confusion_matrix": counts,
    }

