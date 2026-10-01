from __future__ import annotations

import pytest

from evaluation.error_analysis import (
    assign_hr_bin,
    binary_metrics,
    class_composition,
    derive_hr_quartiles,
    patient_pseudonyms,
    select_explainability_cases,
    threshold_region,
)


def _row(identifier: str, label: int, prediction: int, probability: float) -> dict[str, object]:
    return {
        "example_id": identifier,
        "label": label,
        "thresholded_prediction": prediction,
        "source_domain_calibrated_probability": probability,
    }


def test_case_selection_rule_and_lexical_tie() -> None:
    rows = [
        _row("tp-z", 1, 1, 0.8),
        _row("tp-a", 1, 1, 0.8),
        _row("tn-z", 0, 0, 0.1),
        _row("tn-a", 0, 0, 0.1),
        _row("fp-z", 0, 1, 0.9),
        _row("fp-a", 0, 1, 0.9),
        _row("fn-z", 1, 0, 0.2),
        _row("fn-a", 1, 0, 0.2),
    ]
    selected = select_explainability_cases(rows)
    assert {key: value["example_id"] for key, value in selected.items()} == {
        "TP": "tp-a",
        "TN": "tn-a",
        "FP": "fp-a",
        "FN": "fn-a",
    }


def test_composition_hr_bins_threshold_and_pseudonyms() -> None:
    assert class_composition(2, 1, 0) == "S_DOMINANT"
    assert class_composition(1, 2, 0) == "V_DOMINANT"
    assert class_composition(1, 1, 1) == "F_CONTAINING"
    assert class_composition(1, 1, 0) == "S_V_TIE"
    edges = derive_hr_quartiles([1, 2, 3, 4, 5])
    assert edges == pytest.approx((2, 3, 4))
    assert [assign_hr_bin(value, edges) for value in (2, 3, 4, 5, None)] == [
        "HR_BIN_1",
        "HR_BIN_2",
        "HR_BIN_3",
        "HR_BIN_4",
        "HR_UNDEFINED",
    ]
    assert threshold_region(0.65, 0.60)
    assert not threshold_region(0.651, 0.60)
    assert patient_pseudonyms(["secret-b", "secret-a"]) == {
        "secret-a": "INT_PATIENT_001",
        "secret-b": "INT_PATIENT_002",
    }


def test_single_class_metrics_are_explicitly_undefined() -> None:
    result = binary_metrics([_row("a", 1, 1, 0.9), _row("b", 1, 0, 0.4)])
    assert result["AUPRC"] == "UNDEFINED_SINGLE_CLASS"
    assert result["AUROC"] == "UNDEFINED_SINGLE_CLASS"
