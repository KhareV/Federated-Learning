from __future__ import annotations

import numpy as np
import pytest

from federated.validation_group_metrics import validation_patient_metrics


def test_patient_macro_is_unweighted_and_worst_is_minimum() -> None:
    result = validation_patient_metrics(
        np.array([0, 1, 0, 0, 1]),
        np.array([0.1, 0.9, 0.8, 0.2, 0.3]),
        np.array(["A", "A", "B", "B", "B"]),
        record_ids=["100", "100", "201", "201", "202"],
    )
    values = [row["AUPRC"] for row in result["per_group"]]
    assert result["macro_AUPRC"] == pytest.approx(sum(values) / 2)
    assert result["worst_AUPRC"] == min(values)
    assert result["per_group"][1]["record_ids"] == ["201", "202"]
    assert result["validation_patients_are_clients"] is False


def test_group_without_positive_fails() -> None:
    with pytest.raises(RuntimeError, match="FEDPROX_SELECTION_METRIC_UNDEFINED"):
        validation_patient_metrics(
            np.array([0, 0, 1]), np.array([0.1, 0.2, 0.9]), np.array(["A", "A", "B"])
        )
