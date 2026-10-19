# ruff: noqa: E501
"""The helpers of the realistic-cohort diagnostics: exact metric arithmetic and a threshold search that finds a known optimum."""

from __future__ import annotations

import numpy as np

from scripts.realistic_diagnostics import best_f1_threshold, metrics


def test_metrics_count_the_confusion_matrix_exactly():
    z = np.array([5.0, 5.0, -5.0, -5.0, 5.0, -5.0])      # sigmoid >= 0.5 for the first, second, fifth
    y = np.array([1, 0, 1, 0, 1, 0])
    m = metrics(z, y)
    assert (m["TP"], m["FP"], m["FN"], m["TN"]) == (2, 1, 1, 2) and m["threshold"] == 0.5
    assert abs(m["F1"] - 2 * 2 / (2 * 2 + 1 + 1)) < 1e-12 and abs(m["precision"] - 2 / 3) < 1e-12 and abs(m["recall"] - 2 / 3) < 1e-12 and abs(m["specificity"] - 2 / 3) < 1e-12


def test_the_threshold_search_finds_the_separating_cut_when_one_exists():
    rng = np.random.default_rng(0)
    z = np.concatenate([rng.normal(-3, 0.3, 300), rng.normal(1.0, 0.3, 100)])      # negatives far below, positives above sigmoid 0.5 only for the second group
    y = np.concatenate([np.zeros(300), np.ones(100)])
    t = best_f1_threshold(z, y)
    assert metrics(z, y, t)["F1"] > 0.97
    z_hard = np.concatenate([rng.normal(2.0, 0.3, 300), rng.normal(3.0, 0.3, 100)])  # everything above 0.5: the fixed rule flags all, a higher threshold helps
    assert metrics(z_hard, y, best_f1_threshold(z_hard, y))["F1"] > metrics(z_hard, y)["F1"]
