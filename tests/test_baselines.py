from __future__ import annotations

import numpy as np

from models.baselines import (
    FeatureTransformer,
    MajorityBaseline,
    descriptive_metrics,
    fit_logistic,
    fit_random_forest,
)


def matrix(seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(40, 29))
    labels = np.asarray([0] * 25 + [1] * 15, dtype=np.int64)
    return features, labels


def test_majority_uses_training_prevalence_and_fixed_tie_policy() -> None:
    train = MajorityBaseline.fit(np.asarray([0, 0, 1]))
    assert train.chosen_class == 0
    assert np.all(train.predict(5) == 0)
    assert MajorityBaseline.fit(np.asarray([0, 1])).chosen_class == 0
    # Reversing held-out prevalence cannot alter the already fitted object.
    assert np.all(train.predict(100) == 0)


def test_fixed_models_are_deterministic() -> None:
    features, labels = matrix()
    transformer = FeatureTransformer.fit(features, training_patient_count=4)
    scaled = transformer.transform_scaled(features)
    imputed = transformer.transform_imputed(features)
    lr_a = fit_logistic(scaled, labels)
    lr_b = fit_logistic(scaled, labels)
    rf_a = fit_random_forest(imputed, labels)
    rf_b = fit_random_forest(imputed, labels)
    assert np.array_equal(lr_a.predict_proba(scaled), lr_b.predict_proba(scaled))
    assert np.array_equal(rf_a.predict_proba(imputed), rf_b.predict_proba(imputed))


def test_patient_macro_f1_is_unweighted_across_groups() -> None:
    labels = np.asarray([1, 1, 0, 0])
    scores = np.asarray([0.9, 0.9, 0.9, 0.1])
    groups = np.asarray(["A", "A", "B", "B"])
    result = descriptive_metrics(labels, scores, groups)
    assert result["patient_groups"] == 2
    assert result["patient_macro_F1"] == 0.5
