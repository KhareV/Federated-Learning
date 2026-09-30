from __future__ import annotations

import pytest

from evaluation.ecg_hr_v2 import candidate_eligible, passes_quality_floor, select_candidate
from preprocessing.ecg_hr_context import GQRS_ID, HISTORICAL_ID, XQRS_ID


def metric(macro=3.0, median=2.0, p95=10.0, coverage=0.98, patient_coverage=1.0):
    return {
        "patient_macro_mae_bpm": macro,
        "median_absolute_error_bpm": median,
        "p95_absolute_error_bpm": p95,
        "coverage": coverage,
        "patient_coverage_fraction_ge_0_90": patient_coverage,
    }


def test_coverage_gate_and_quality_floor() -> None:
    assert candidate_eligible(metric())
    assert not candidate_eligible(metric(coverage=0.949))
    assert not candidate_eligible(metric(patient_coverage=0.89))
    assert passes_quality_floor(metric())
    assert not passes_quality_floor(metric(macro=10.01))
    assert not passes_quality_floor(metric(median=5.01))
    assert not passes_quality_floor(metric(p95=20.01))


def test_selection_uses_patient_macro_then_frozen_ties() -> None:
    selected, _ = select_candidate({XQRS_ID: metric(macro=4), GQRS_ID: metric(macro=3)})
    assert selected == GQRS_ID
    selected, _ = select_candidate(
        {
            XQRS_ID: metric(macro=3, median=2),
            GQRS_ID: metric(macro=3.05, median=3),
        }
    )
    assert selected == XQRS_ID


def test_historical_comparator_cannot_be_selected() -> None:
    metrics = {XQRS_ID: metric(macro=4), GQRS_ID: metric(macro=3), HISTORICAL_ID: metric(macro=0)}
    selected, _ = select_candidate(metrics)
    assert selected == GQRS_ID


def test_no_passing_candidate_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="VALIDATION_FAILURE"):
        select_candidate({XQRS_ID: metric(coverage=0.1), GQRS_ID: metric(coverage=0.2)})
