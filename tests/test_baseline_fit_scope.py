from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from evaluation.leakage_audit import FitScopeViolation
from models.baselines import FeatureTransformer, MajorityBaseline
from training.train_baselines import build_feature_population

ROOT = Path(__file__).resolve().parents[1]


def test_imputer_and_scaler_fit_training_only() -> None:
    train = np.zeros((3, 29), dtype=np.float64)
    train[:, 0] = [0.0, np.nan, 2.0]
    validation = np.full((2, 29), 1000.0)
    validation[0, 0] = np.nan
    transform = FeatureTransformer.fit(train, training_patient_count=2)
    assert transform.imputer.statistics_[0] == 1.0
    assert transform.scaler.mean_[0] == 1.0
    assert transform.transform_imputed(validation)[0, 0] == 1.0


def test_fit_scope_rejects_validation_or_heldout() -> None:
    with pytest.raises(FitScopeViolation):
        MajorityBaseline.fit(np.asarray([0, 1]), fit_partitions=("TRAIN", "VALIDATION"))
    with pytest.raises(ValueError, match="forbidden"):
        build_feature_population("CALIBRATION")
    with pytest.raises(ValueError, match="forbidden"):
        build_feature_population("INTERNAL_TEST")


def test_standard_runner_has_no_external_or_test_option() -> None:
    source = (ROOT / "training/train_baselines.py").read_text(encoding="utf-8")
    forbidden_tools = (
        "GridSearchCV",
        "RandomizedSearchCV",
        "cross_val_score",
        "Optuna",
        "hyperopt",
        "--include-test",
        "--grid-search",
    )
    assert not any(tool in source for tool in forbidden_tools)
    assert "ALLOWED_PARTITIONS = (\"TRAIN\", \"VALIDATION\")" in source
