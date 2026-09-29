from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

from evaluation.metrics import (
    MetricError,
    confusion_counts,
    patient_macro_f1,
    pooled_binary_metrics,
)


def test_metrics_match_trusted_references() -> None:
    labels = np.asarray([0, 0, 1, 1, 1, 0])
    probabilities = np.asarray([0.1, 0.8, 0.9, 0.7, 0.2, 0.3])
    predictions = (probabilities >= 0.5).astype(np.int64)
    patients = np.asarray(["A", "A", "B", "B", "C", "C"])
    result = pooled_binary_metrics(labels, probabilities, predictions, patients)
    assert result["AUPRC"] == pytest.approx(average_precision_score(labels, probabilities))
    assert result["AUROC"] == pytest.approx(roc_auc_score(labels, probabilities))
    assert result["pooled_F1"] == pytest.approx(f1_score(labels, predictions))
    assert result["confusion_matrix"] == {"tp": 2, "fp": 1, "tn": 2, "fn": 1}
    assert result["specificity"] == pytest.approx(2 / 3)


def test_patient_macro_f1_is_equal_patient_weighted() -> None:
    patients = np.asarray(["A", "A", "A", "B"])
    labels = np.asarray([1, 1, 1, 1])
    predictions = np.asarray([1, 1, 1, 0])
    assert patient_macro_f1(patients, labels, predictions) == pytest.approx(0.5)


def test_zero_division_is_zero() -> None:
    counts = confusion_counts(np.asarray([0, 0]), np.asarray([0, 0]))
    assert counts == {"tp": 0, "fp": 0, "tn": 2, "fn": 0}
    result = pooled_binary_metrics(
        np.asarray([0, 0]),
        np.asarray([0.1, 0.2]),
        np.asarray([0, 0]),
        np.asarray(["A", "B"]),
        allow_undefined=True,
    )
    assert result["AUPRC"] is None
    assert result["AUROC"] is None
    assert result["pooled_F1"] == 0.0
    assert result["precision"] == 0.0
    assert result["sensitivity"] is None


def test_original_evaluation_requires_both_classes() -> None:
    with pytest.raises(MetricError, match="EVALUATION_CLASS_DEGENERACY"):
        pooled_binary_metrics(
            np.asarray([1, 1]),
            np.asarray([0.8, 0.9]),
            np.asarray([1, 1]),
            np.asarray(["A", "B"]),
        )

