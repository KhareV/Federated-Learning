from __future__ import annotations

import numpy as np
import pytest

from evaluation.bootstrap import (
    BootstrapError,
    bootstrap_replicates,
    expand_cluster_draw,
    generate_patient_draws,
    percentile_summary,
)
from evaluation.metrics import pooled_binary_metrics


def fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    patients = np.asarray(["P1", "P1", "P1", "P2", "P3", "P3"])
    labels = np.asarray([1, 1, 0, 0, 1, 0])
    probabilities = np.asarray([0.9, 0.8, 0.7, 0.1, 0.4, 0.6])
    predictions = (probabilities >= 0.5).astype(np.int64)
    return patients, labels, probabilities, predictions


def test_cluster_expansion_preserves_multiplicity() -> None:
    patients, _, _, _ = fixture()
    ordered = np.asarray(["P1", "P2", "P3"])
    expanded = expand_cluster_draw(patients, ordered, np.asarray([0, 0, 2]))
    assert expanded.tolist() == [0, 1, 2, 0, 1, 2, 4, 5]


def test_patient_macro_multiplicity_uses_sampled_slots() -> None:
    patients, labels, probabilities, predictions = fixture()
    draws = np.tile(np.asarray([[0, 0, 2]]), (2000, 1))
    _, rows = bootstrap_replicates(
        patients,
        labels,
        probabilities,
        predictions,
        replicates=2000,
        seed=20260927,
        draws=draws,
    )
    # P1 F1=0.8, P3 F1=0.0; sampled-slot macro=(0.8+0.8+0)/3.
    assert rows[0]["patient_macro_F1"] == pytest.approx(1.6 / 3)
    assert rows[0]["sampled_patient_slots"] == 3
    assert rows[0]["unique_patient_count"] == 2


def test_exact_draw_count_and_rng_determinism() -> None:
    patients, _, _, _ = fixture()
    ordered1, draws1 = generate_patient_draws(patients, 2000, 20260927)
    ordered2, draws2 = generate_patient_draws(patients, 2000, 20260927)
    _, draws3 = generate_patient_draws(patients, 2000, 20260928)
    assert ordered1.tolist() == ordered2.tolist() == ["P1", "P2", "P3"]
    assert draws1.shape == (2000, 3)
    assert np.array_equal(draws1, draws2)
    assert not np.array_equal(draws1, draws3)
    assert draws1.min() >= 0 and draws1.max() < 3


def test_rejects_noncanonical_replicate_count() -> None:
    patients, _, _, _ = fixture()
    with pytest.raises(BootstrapError, match="MUST_EQUAL_2000"):
        generate_patient_draws(patients, 1999, 1)


def test_degenerate_draws_are_not_redrawn_and_are_counted() -> None:
    patients, labels, probabilities, predictions = fixture()
    # Every draw selects only P2: discrimination metrics are undefined.
    draws = np.ones((2000, 3), dtype=np.int64)
    actual_draws, rows = bootstrap_replicates(
        patients,
        labels,
        probabilities,
        predictions,
        replicates=2000,
        seed=20260927,
        draws=draws,
    )
    assert np.array_equal(actual_draws, draws)
    assert all(row["AUPRC"] is None and row["AUROC"] is None for row in rows)
    point = pooled_binary_metrics(labels, probabilities, predictions, patients)
    with pytest.raises(BootstrapError, match="BOOTSTRAP_METRIC_DEGENERACY"):
        percentile_summary(point, rows)


def test_percentile_summary_uses_original_point_estimate() -> None:
    patients, labels, probabilities, predictions = fixture()
    point = pooled_binary_metrics(labels, probabilities, predictions, patients)
    _, rows = bootstrap_replicates(
        patients,
        labels,
        probabilities,
        predictions,
        replicates=2000,
        seed=20260927,
    )
    summary = percentile_summary(point, rows)
    assert summary["AUPRC"]["point_estimate"] == point["AUPRC"]
    assert summary["AUPRC"]["valid_replicates"] <= 2000
    assert summary["AUPRC"]["valid_replicates"] + summary["AUPRC"]["invalid_replicates"] == 2000

