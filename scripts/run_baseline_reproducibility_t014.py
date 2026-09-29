#!/usr/bin/env python3
"""Repeat BASELINE_V1 fitting in fresh objects and compare semantic outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from models.baselines import (  # noqa: E402
    FeatureTransformer,
    MajorityBaseline,
    descriptive_metrics,
    fit_logistic,
    fit_random_forest,
)
from nhm.hashing import hash_canonical_json  # noqa: E402
from training.train_baselines import (  # noqa: E402
    FEATURE_CACHE_ROOT,
    build_feature_population,
)


def fit_once(train, validation) -> dict:
    majority = MajorityBaseline.fit(train.labels)
    transformer = FeatureTransformer.fit(
        train.features,
        training_patient_count=len(set(train.participant_group_ids.tolist())),
    )
    train_i = transformer.transform_imputed(train.features)
    val_i = transformer.transform_imputed(validation.features)
    train_s = transformer.transform_scaled(train.features)
    val_s = transformer.transform_scaled(validation.features)
    logistic = fit_logistic(train_s, train.labels)
    forest = fit_random_forest(train_i, train.labels)
    lr_prob = logistic.predict_proba(val_s)[:, 1]
    rf_prob = forest.predict_proba(val_i)[:, 1]
    metrics = {
        "logistic": descriptive_metrics(
            validation.labels, lr_prob, validation.participant_group_ids
        ),
        "random_forest": descriptive_metrics(
            validation.labels, rf_prob, validation.participant_group_ids
        ),
    }
    return {
        "majority": majority,
        "transformer": transformer,
        "logistic": logistic,
        "forest": forest,
        "lr_prob": lr_prob,
        "rf_prob": rf_prob,
        "metrics": metrics,
    }


def main() -> None:
    train_a = build_feature_population("TRAIN")
    validation_a = build_feature_population("VALIDATION")
    train_b = build_feature_population("TRAIN")
    validation_b = build_feature_population("VALIDATION")
    feature_equal = np.array_equal(
        train_a.features, train_b.features, equal_nan=True
    ) and np.array_equal(validation_a.features, validation_b.features, equal_nan=True)
    first = fit_once(train_a, validation_a)
    second = fit_once(train_b, validation_b)
    checks = {
        "feature_extraction_deterministic": bool(feature_equal),
        "majority_deterministic": first["majority"].as_dict() == second["majority"].as_dict(),
        "imputer_statistics_repeat_identical": bool(
            np.array_equal(
                first["transformer"].imputer.statistics_,
                second["transformer"].imputer.statistics_,
                equal_nan=True,
            )
        ),
        "scaler_statistics_repeat_identical": bool(
            np.array_equal(first["transformer"].scaler.mean_, second["transformer"].scaler.mean_)
            and np.array_equal(
                first["transformer"].scaler.var_, second["transformer"].scaler.var_
            )
        ),
        "LR_coefficients_repeat_identical": bool(
            np.array_equal(first["logistic"].coef_, second["logistic"].coef_)
            and np.array_equal(first["logistic"].intercept_, second["logistic"].intercept_)
        ),
        "LR_predictions_repeat_identical": bool(
            np.array_equal(first["lr_prob"], second["lr_prob"])
        ),
        "RF_predictions_repeat_identical": bool(
            np.array_equal(first["rf_prob"], second["rf_prob"])
        ),
        "metric_report_repeat_identical": first["metrics"] == second["metrics"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"BASELINE_V1 reproducibility failure: {checks}")
    report = {
        "task_id": "T014",
        "baseline_id": "BASELINE_V1",
        "feature_set_id": "BASELINE_FEATURES_V1",
        "checks": checks,
        "semantic_metrics_sha256": hash_canonical_json(first["metrics"]),
        "serialization_note": (
            "Model artifact bytes are frozen once; reproducibility is established by exact "
            "parameters, probabilities, and metrics because joblib metadata need not be portable."
        ),
        "feature_cache_root": str(FEATURE_CACHE_ROOT.relative_to(ROOT)),
        "overall_status": "PASS",
    }
    path = ROOT / "reports/t014/reproducibility.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("T014 reproducibility: PASS")


if __name__ == "__main__":
    main()
