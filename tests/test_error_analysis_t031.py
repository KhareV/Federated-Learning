from __future__ import annotations

import csv
import json
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]


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


def test_canonical_error_slices_and_hardware_deferral() -> None:
    required = (
        "patient_slice.csv",
        "class_composition_slice.csv",
        "quality_slice.csv",
        "noise_snr_slice.csv",
        "heart_rate_slice.csv",
        "dataset_slice.csv",
        "threshold_region_slice.csv",
    )
    assert all((ROOT / "reports/t031" / name).exists() for name in required)
    with (ROOT / "reports/t031/heart_rate_slice.csv").open(newline="") as handle:
        heart = list(csv.DictReader(handle))
    assert {row["HR_bin"] for row in heart if row["dataset"] == "MITDB_INTERNAL_TEST"} == {
        "HR_BIN_1",
        "HR_BIN_2",
        "HR_BIN_3",
        "HR_BIN_4",
    }
    wearable = json.loads((ROOT / "reports/t031/wearable_slice_status.json").read_text())
    assert wearable["status"] == "DEFERRED_T030_HARDWARE"
    assert not wearable["WEARABLE_SIM_substituted"]


def test_method_lock_detects_bound_artifact_tamper(tmp_path: Path) -> None:
    from nhm.hashing import hash_file

    source = tmp_path / "method.py"
    source.write_text("steps = 64\n")
    expected = hash_file(source)
    assert hash_file(source) == expected
    source.write_text("steps = 32\n")
    assert hash_file(source) != expected
