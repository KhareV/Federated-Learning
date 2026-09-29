"""BASELINE_V1 fixed classical models, train-only transforms, and descriptive metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from evaluation.leakage_audit import audit_fit_scope
from features.ecg import BASELINE_FEATURE_NAMES_V1, feature_schema_sha256

BASELINE_ID = "BASELINE_V1"
MAJORITY_MODEL_ID = "MAJORITY_BASELINE_V1"
LOGISTIC_MODEL_ID = "LOGISTIC_BASELINE_V1"
RF_MODEL_ID = "RF_BASELINE_V1"
SEED = 20260927
DECISION_THRESHOLD = 0.5


@dataclass(frozen=True)
class MajorityBaseline:
    chosen_class: int
    training_positive_count: int
    training_negative_count: int
    tie_class: int = 0
    model_id: str = MAJORITY_MODEL_ID

    @classmethod
    def fit(
        cls,
        labels: np.ndarray,
        *,
        fit_partitions: tuple[str, ...] = ("TRAIN",),
        tie_class: int = 0,
    ) -> MajorityBaseline:
        audit_fit_scope("DERIVE_MAJORITY_BASELINE", fit_partitions)
        y = np.asarray(labels, dtype=np.int64)
        if y.ndim != 1 or y.size == 0 or not set(np.unique(y)).issubset({0, 1}):
            raise ValueError("majority labels must be a nonempty binary vector")
        positives = int(np.sum(y == 1))
        negatives = int(np.sum(y == 0))
        chosen = 1 if positives > negatives else tie_class
        return cls(chosen, positives, negatives, tie_class)

    def predict(self, sample_count: int) -> np.ndarray:
        return np.full(sample_count, self.chosen_class, dtype=np.int64)

    def predict_proba_positive(self, sample_count: int) -> np.ndarray:
        return np.full(sample_count, float(self.chosen_class), dtype=np.float64)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "chosen_class": self.chosen_class,
            "training_positive_count": self.training_positive_count,
            "training_negative_count": self.training_negative_count,
            "tie_class": self.tie_class,
            "choice_source": "TRAIN_ONLY",
        }


@dataclass
class FeatureTransformer:
    imputer: SimpleImputer
    scaler: StandardScaler
    feature_names: tuple[str, ...]
    feature_schema_sha256: str
    training_row_count: int
    training_patient_count: int
    fit_partitions: tuple[str, ...]

    @classmethod
    def fit(
        cls,
        features: np.ndarray,
        *,
        training_patient_count: int,
        fit_partitions: tuple[str, ...] = ("TRAIN",),
    ) -> FeatureTransformer:
        audit_fit_scope("FIT_FEATURE_TRANSFORM", fit_partitions)
        audit_fit_scope("FIT_SCALER", fit_partitions)
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != len(BASELINE_FEATURE_NAMES_V1):
            raise ValueError("feature matrix does not match BASELINE_FEATURES_V1")
        imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        imputed = imputer.fit_transform(matrix)
        scaler = StandardScaler(with_mean=True, with_std=True)
        scaler.fit(imputed)
        return cls(
            imputer=imputer,
            scaler=scaler,
            feature_names=BASELINE_FEATURE_NAMES_V1,
            feature_schema_sha256=feature_schema_sha256(),
            training_row_count=matrix.shape[0],
            training_patient_count=training_patient_count,
            fit_partitions=fit_partitions,
        )

    def _verify(self, features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError("feature schema mismatch")
        if self.feature_schema_sha256 != feature_schema_sha256():
            raise ValueError("FEATURE_SCHEMA_HASH_MISMATCH")
        return matrix

    def transform_imputed(self, features: np.ndarray) -> np.ndarray:
        return np.asarray(self.imputer.transform(self._verify(features)), dtype=np.float64)

    def transform_scaled(self, features: np.ndarray) -> np.ndarray:
        return np.asarray(
            self.scaler.transform(self.transform_imputed(features)), dtype=np.float64
        )


def create_logistic_regression() -> LogisticRegression:
    return LogisticRegression(
        l1_ratio=0.0,
        C=1.0,
        solver="liblinear",
        max_iter=1000,
        tol=1e-4,
        fit_intercept=True,
        class_weight=None,
        random_state=SEED,
    )


def create_random_forest() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=200,
        criterion="gini",
        max_depth=12,
        min_samples_split=2,
        min_samples_leaf=1,
        max_features="sqrt",
        bootstrap=True,
        class_weight=None,
        random_state=SEED,
        n_jobs=1,
    )


def fit_logistic(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    fit_partitions: tuple[str, ...] = ("TRAIN",),
) -> LogisticRegression:
    audit_fit_scope("FIT_MODEL_WEIGHTS", fit_partitions)
    model = create_logistic_regression()
    model.fit(np.asarray(features, dtype=np.float64), np.asarray(labels, dtype=np.int64))
    return model


def fit_random_forest(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    fit_partitions: tuple[str, ...] = ("TRAIN",),
) -> RandomForestClassifier:
    audit_fit_scope("FIT_MODEL_WEIGHTS", fit_partitions)
    model = create_random_forest()
    model.fit(np.asarray(features, dtype=np.float64), np.asarray(labels, dtype=np.int64))
    return model


def descriptive_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    participant_group_ids: np.ndarray,
    *,
    threshold: float = DECISION_THRESHOLD,
) -> dict[str, float | int | None]:
    y = np.asarray(labels, dtype=np.int64)
    scores = np.asarray(probabilities, dtype=np.float64)
    groups = np.asarray(participant_group_ids, dtype=str)
    if y.shape != scores.shape or y.shape != groups.shape:
        raise ValueError("labels, probabilities, and participant groups must align")
    predictions = (scores >= threshold).astype(np.int64)
    tn, fp, _fn, _tp = confusion_matrix(y, predictions, labels=[0, 1]).ravel()
    patient_scores = [
        f1_score(y[groups == group], predictions[groups == group], zero_division=0)
        for group in sorted(set(groups.tolist()))
    ]
    auroc = float(roc_auc_score(y, scores)) if len(np.unique(y)) == 2 else None
    return {
        "patient_groups": len(patient_scores),
        "windows": int(y.size),
        "positives": int(np.sum(y == 1)),
        "negatives": int(np.sum(y == 0)),
        "AUPRC": float(average_precision_score(y, scores)),
        "AUROC": auroc,
        "patient_macro_F1": float(np.mean(patient_scores)),
        "pooled_F1": float(f1_score(y, predictions, zero_division=0)),
        "precision": float(precision_score(y, predictions, zero_division=0)),
        "sensitivity": float(recall_score(y, predictions, zero_division=0)),
        "specificity": float(tn / (tn + fp)) if tn + fp else None,
        "accuracy": float(accuracy_score(y, predictions)),
    }


def library_versions() -> dict[str, str]:
    import joblib
    import scipy

    return {
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "joblib": joblib.__version__,
    }
