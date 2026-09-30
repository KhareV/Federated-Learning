from __future__ import annotations

import math

import pytest

from evaluation.bidmc_context_v2 import (
    agreement_metrics,
    apply_natural_warning,
    error_metrics,
    load_config,
    passes_guardrails,
)


def _row(timestamp: int, derived: float | None, reference: float | None, pulse: float | None):
    return {
        "record_id": "bidmc01",
        "timestamp_us": str(timestamp),
        "hr_ecg_bpm_v2": "" if derived is None else str(derived),
        "hr_ecg_valid_v2": str(derived is not None).lower(),
        "provided_hr_bpm": "" if reference is None else str(reference),
        "hr_reference_valid": str(reference is not None).lower(),
        "pr_ppg_bpm": "" if pulse is None else str(pulse),
        "quality_warning_natural": "false",
    }


def test_frozen_protocol_identity_and_guardrails() -> None:
    config = load_config()
    assert config["context_contract_id"] == "BIDMC_CONTEXT_V2"
    assert config["changed_component"]["selected_detector"] == "WFDB_XQRS_V1"
    assert config["alignment"]["time_shift_optimization"] is False


def test_hr_metrics_and_record_scale_counts() -> None:
    rows = [_row(10_000_000, 70, 60, 65), _row(11_000_000, None, 80, 80)]
    metrics = error_metrics(rows)
    assert metrics["reference_samples"] == 2
    assert metrics["comparable_samples"] == 1
    assert metrics["coverage"] == 0.5
    assert metrics["mean_signed_difference_bpm"] == 10
    assert metrics["mae_bpm"] == 10
    assert metrics["median_absolute_error_bpm"] == 10
    assert metrics["rmse_bpm"] == 10
    assert metrics["p95_absolute_error_bpm"] == 10


def test_guardrails_are_fixed_and_conjunctive() -> None:
    config = load_config()
    passing = {"coverage": 0.9, "median_absolute_error_bpm": 10.0, "mae_bpm": 20.0}
    assert passes_guardrails(passing, config)
    for field, value in (
        ("coverage", math.nextafter(0.9, 0.0)),
        ("median_absolute_error_bpm", math.nextafter(10.0, math.inf)),
        ("mae_bpm", math.nextafter(20.0, math.inf)),
    ):
        failing = dict(passing)
        failing[field] = value
        assert not passes_guardrails(failing, config)


def test_rate_agreement_uses_frozen_20_bpm_boundary() -> None:
    rows = [_row(0, 70, 70, 50), _row(1_000_000, 70, 70, 49)]
    metrics = agreement_metrics(rows)
    assert metrics["within_or_equal_20_count"] == 1
    assert metrics["greater_than_20_count"] == 1


def test_natural_warning_requires_continuous_ten_seconds() -> None:
    rows = [_row(timestamp, 70, 70, 95) for timestamp in (0, 5_000_000, 9_999_999)]
    rows.append(_row(10_000_000, 70, 70, 95))
    audit = apply_natural_warning(rows)
    assert [row["quality_warning_natural"] for row in rows] == [
        "false",
        "false",
        "false",
        "true",
    ]
    assert audit["sustained_disagreement_runs"] == 1


def test_warning_resets_when_pair_is_unavailable() -> None:
    rows = [
        _row(0, 70, 70, 95),
        _row(5_000_000, 70, 70, None),
        _row(15_000_000, 70, 70, 95),
    ]
    apply_natural_warning(rows)
    assert all(row["quality_warning_natural"] == "false" for row in rows)


def test_empty_reference_is_well_defined() -> None:
    metrics = error_metrics([_row(0, None, None, None)])
    assert metrics["coverage"] == 0.0
    assert metrics["mae_bpm"] is None


@pytest.mark.parametrize("field", ["coverage", "mae_bpm", "median_absolute_error_bpm"])
def test_guardrail_metrics_are_required(field: str) -> None:
    metrics = {"coverage": 1.0, "mae_bpm": 0.0, "median_absolute_error_bpm": 0.0}
    del metrics[field]
    with pytest.raises(KeyError):
        passes_guardrails(metrics, load_config())
