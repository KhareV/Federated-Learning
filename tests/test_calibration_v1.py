from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from evaluation.calibration import (
    apply_operating_threshold,
    apply_temperature,
    binary_nll,
    brier_score,
    fit_temperature,
    raw_probability_from_logit,
    reliability_bins,
    select_f1_threshold,
    source_domain_calibrated_probability,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs/calibration_v1.yaml").read_text())


def test_temperature_scaling_formula_identity_and_positive_fit() -> None:
    logits = np.asarray([-2.0, -0.5, 0.25, 2.0], dtype=np.float64)
    labels = np.asarray([0, 0, 1, 1], dtype=np.int64)
    assert np.array_equal(apply_temperature(logits, {"temperature": 1.0}), logits)
    result = fit_temperature(logits, labels, CONFIG)
    assert result["temperature"] > 0
    assert result["calibrated_nll"] <= result["raw_nll"] + 1e-12
    assert binary_nll(logits / result["temperature"], labels) == result["calibrated_nll"]


def test_probability_brier_and_threshold_helpers() -> None:
    logits = np.asarray([-2.0, 0.0, 2.0])
    cal = {"temperature": 2.0, "threshold": 0.5}
    raw = raw_probability_from_logit(logits)
    calibrated = source_domain_calibrated_probability(logits, cal)
    assert np.allclose(calibrated, raw_probability_from_logit(logits / 2.0))
    assert brier_score(raw, np.asarray([0, 0, 1])) >= 0
    assert np.array_equal(apply_operating_threshold(calibrated, cal), [0, 1, 1])


def test_reliability_exact_bin_boundaries_and_empty_bins() -> None:
    rows = reliability_bins(
        np.asarray([0.0, 0.1, 0.9, 1.0]), np.asarray([0, 1, 1, 1])
    )
    assert rows[0]["count"] == 1
    assert rows[1]["count"] == 1
    assert rows[9]["count"] == 2
    assert rows[2]["count"] == 0
    assert rows[2]["mean_probability"] is None


def test_threshold_unique_optimum_inclusive_comparator() -> None:
    result = select_f1_threshold(
        np.asarray([0.9, 0.8, 0.1]), np.asarray([1, 0, 0])
    )
    assert result["selected_threshold"] == 0.9
    assert result["selected_f1"] == 1.0
    assert result["comparator"] == ">="


def test_threshold_tie_selects_highest_threshold() -> None:
    result = select_f1_threshold(np.asarray([0.9, 0.8]), np.asarray([1, 1]))
    assert result["selected_threshold"] == 0.8
    assert result["selected_f1"] == 1.0
    assert result["maximum_f1_tie_count"] == 2
