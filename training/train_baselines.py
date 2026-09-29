"""Deterministic T014 TRAIN-fit / VALIDATION-report baseline runner.

The normal entry point deliberately has no option for calibration, internal-test, or
external data. Waveform files are opened only after their partition is checked against
the fixed allow-list.
"""

from __future__ import annotations

import argparse
import csv
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import yaml
from sklearn.exceptions import ConvergenceWarning

from evaluation.leakage_audit import verify_frozen_split
from features.ecg import (
    BASELINE_FEATURE_NAMES_V1,
    FEATURE_SET_ID,
    detector_metadata,
    extract_baseline_features,
    feature_schema_sha256,
)
from models.baselines import (
    BASELINE_ID,
    DECISION_THRESHOLD,
    FeatureTransformer,
    MajorityBaseline,
    descriptive_metrics,
    fit_logistic,
    fit_random_forest,
    library_versions,
)
from nhm.hashing import hash_file
from preprocessing.freeze import verify_preproc_freeze

ROOT = Path(__file__).resolve().parents[1]
WINDOW_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
CACHE_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv"
FEATURE_MANIFEST = ROOT / "manifests/features/MITDB_BASELINE_FEATURES_V1.csv"
FEATURE_SCHEMA = ROOT / "manifests/features/BASELINE_FEATURES_V1.schema.json"
FEATURE_CACHE_ROOT = (
    ROOT
    / "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/"
    "AAMI_SVF_WINDOW_V1/BASELINE_FEATURES_V1"
)
ARTIFACT_ROOT = ROOT / "artifacts/baselines/BASELINE_V1"
REPORT_ROOT = ROOT / "reports"
ALLOWED_PARTITIONS = ("TRAIN", "VALIDATION")
FORBIDDEN_PARTITIONS = ("CALIBRATION", "INTERNAL_TEST")
EXTERNAL_DATASETS = ("INCART", "NSTDB", "BIDMC", "WEARABLE_SIM_V1")


@dataclass(frozen=True)
class FeaturePopulation:
    partition: str
    features: np.ndarray
    labels: np.ndarray
    example_ids: tuple[str, ...]
    participant_group_ids: np.ndarray
    record_ids: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _eligible_metadata(partition: str) -> dict[str, dict[str, str]]:
    if partition not in ALLOWED_PARTITIONS:
        raise ValueError(f"T014 partition access forbidden: {partition}")
    rows = _read_csv(WINDOW_MANIFEST)
    selected = {
        row["example_id"]: row
        for row in rows
        if row["partition"] == partition and row["core_eligible"].upper() == "TRUE"
    }
    if len(selected) != sum(
        row["partition"] == partition and row["core_eligible"].upper() == "TRUE"
        for row in rows
    ):
        raise RuntimeError("duplicate eligible example IDs in frozen window manifest")
    return selected


def build_feature_population(partition: str) -> FeaturePopulation:
    """Load only an allowed partition and extract waveform-only features."""
    if partition not in ALLOWED_PARTITIONS:
        raise ValueError(f"T014 partition access forbidden: {partition}")
    metadata = _eligible_metadata(partition)
    cache_rows = sorted(
        (row for row in _read_csv(CACHE_MANIFEST) if row["partition"] == partition),
        key=lambda row: row["record_id"],
    )
    vectors: list[np.ndarray] = []
    ids: list[str] = []
    groups: list[str] = []
    records: list[str] = []
    rows: list[dict[str, str]] = []
    for cache in cache_rows:
        waveform_path = ROOT / cache["relative_path"]
        id_path = ROOT / cache["example_ids_path"]
        if hash_file(waveform_path) != cache["sha256"]:
            raise RuntimeError(f"window cache hash mismatch: {waveform_path}")
        waveforms = np.load(waveform_path, allow_pickle=False)
        example_ids = tuple(id_path.read_text(encoding="utf-8").splitlines())
        if waveforms.shape != (len(example_ids), 2500):
            raise RuntimeError(f"window/ID shape mismatch: {cache['record_id']}")
        for waveform, example_id in zip(waveforms, example_ids, strict=True):
            if example_id not in metadata:
                raise RuntimeError(f"cache contains excluded or wrong-partition ID: {example_id}")
            source = metadata.pop(example_id)
            vectors.append(extract_baseline_features(waveform).values)
            ids.append(example_id)
            groups.append(source["participant_group_id"])
            records.append(source["record_id"])
            rows.append(source)
    if metadata:
        raise RuntimeError(f"eligible manifest examples missing from cache: {len(metadata)}")
    return FeaturePopulation(
        partition=partition,
        features=np.vstack(vectors).astype(np.float64, copy=False),
        labels=np.asarray([int(row["label"]) for row in rows], dtype=np.int64),
        example_ids=tuple(ids),
        participant_group_ids=np.asarray(groups, dtype=str),
        record_ids=tuple(records),
        rows=tuple(rows),
    )


def _write_feature_cache(populations: tuple[FeaturePopulation, ...]) -> None:
    FEATURE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    FEATURE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    schema = {
        "feature_set_id": FEATURE_SET_ID,
        "feature_schema_sha256": feature_schema_sha256(),
        "feature_names": list(BASELINE_FEATURE_NAMES_V1),
        "feature_count": len(BASELINE_FEATURE_NAMES_V1),
        "dtype": "float64",
        "source": "PREPROC_V1 filtered unnormalized ECG waveform only",
        "detector": detector_metadata(),
        "feature_selection": "NONE",
    }
    FEATURE_SCHEMA.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = [
        "example_id",
        "participant_group_id",
        "record_id",
        "partition",
        "label",
        "feature_row_index",
        "feature_cache_path",
        "feature_cache_sha256",
        "feature_schema_sha256",
    ]
    manifest_rows: list[dict[str, Any]] = []
    for population in populations:
        path = FEATURE_CACHE_ROOT / f"{population.partition}_features.npy"
        np.save(path, population.features, allow_pickle=False)
        digest = hash_file(path)
        relative = str(path.relative_to(ROOT))
        for index, row in enumerate(population.rows):
            manifest_rows.append(
                {
                    "example_id": row["example_id"],
                    "participant_group_id": row["participant_group_id"],
                    "record_id": row["record_id"],
                    "partition": population.partition,
                    "label": row["label"],
                    "feature_row_index": index,
                    "feature_cache_path": relative,
                    "feature_cache_sha256": digest,
                    "feature_schema_sha256": feature_schema_sha256(),
                }
            )
    manifest_rows.sort(key=lambda row: (row["partition"], row["record_id"], row["example_id"]))
    with FEATURE_MANIFEST.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)


def _probabilities(model: Any, features: np.ndarray) -> np.ndarray:
    return np.asarray(model.predict_proba(features)[:, 1], dtype=np.float64)


def fit_candidate(train: FeaturePopulation) -> dict[str, Any]:
    """Fit all learned state from TRAIN only and persist it before validation access."""
    majority = MajorityBaseline.fit(train.labels, fit_partitions=("TRAIN",))
    transformer = FeatureTransformer.fit(
        train.features,
        training_patient_count=len(set(train.participant_group_ids.tolist())),
        fit_partitions=("TRAIN",),
    )
    imputed = transformer.transform_imputed(train.features)
    scaled = transformer.transform_scaled(train.features)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        logistic = fit_logistic(scaled, train.labels, fit_partitions=("TRAIN",))
    convergence = [
        warning for warning in caught if issubclass(warning.category, ConvergenceWarning)
    ]
    if convergence:
        raise RuntimeError(f"logistic convergence warning: {convergence[0].message}")
    forest = fit_random_forest(imputed, train.labels, fit_partitions=("TRAIN",))
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    joblib.dump(transformer, ARTIFACT_ROOT / "feature_transform.joblib", compress=0)
    joblib.dump(logistic, ARTIFACT_ROOT / "logistic.joblib", compress=0)
    joblib.dump(forest, ARTIFACT_ROOT / "random_forest.joblib", compress=0)
    (ARTIFACT_ROOT / "majority.json").write_text(
        json.dumps(majority.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "majority": majority,
        "transformer": transformer,
        "logistic": logistic,
        "forest": forest,
        "convergence_warning_count": len(convergence),
    }


def _evaluate(population: FeaturePopulation, fitted: dict[str, Any]) -> dict[str, Any]:
    transformer = fitted["transformer"]
    imputed = transformer.transform_imputed(population.features)
    scaled = transformer.transform_scaled(population.features)
    return {
        "majority": descriptive_metrics(
            population.labels,
            fitted["majority"].predict_proba_positive(population.labels.size),
            population.participant_group_ids,
        ),
        "logistic": descriptive_metrics(
            population.labels,
            _probabilities(fitted["logistic"], scaled),
            population.participant_group_ids,
        ),
        "random_forest": descriptive_metrics(
            population.labels,
            _probabilities(fitted["forest"], imputed),
            population.participant_group_ids,
        ),
    }


def _write_metrics_csv(metrics: dict[str, dict[str, dict[str, Any]]]) -> None:
    path = REPORT_ROOT / "baselines/baseline_metrics.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    metric_fields = list(next(iter(next(iter(metrics.values())).values())).keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["model_id", "partition", *metric_fields], lineterminator="\n"
        )
        writer.writeheader()
        model_ids = {
            "majority": "MAJORITY_BASELINE_V1",
            "logistic": "LOGISTIC_BASELINE_V1",
            "random_forest": "RF_BASELINE_V1",
        }
        for partition in ("TRAIN", "VALIDATION"):
            for model in ("majority", "logistic", "random_forest"):
                writer.writerow(
                    {
                        "model_id": model_ids[model],
                        "partition": partition,
                        **metrics[partition][model],
                    }
                )


def run(config_path: Path) -> dict[str, Any]:
    verify_frozen_split(ROOT)
    verify_preproc_freeze(ROOT)
    config_sha_before = hash_file(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config["baseline_id"] != BASELINE_ID or config["input"]["fit_partition"] != "TRAIN":
        raise RuntimeError("BASELINE_V1 config identity or fit scope mismatch")

    # Required order: TRAIN load -> fit/freeze candidate -> then VALIDATION load.
    train = build_feature_population("TRAIN")
    fitted = fit_candidate(train)
    candidate_hashes_before_validation = {
        path.name: hash_file(path)
        for path in sorted(ARTIFACT_ROOT.iterdir())
        if path.is_file()
    }
    validation = build_feature_population("VALIDATION")
    _write_feature_cache((train, validation))
    metrics = {
        "TRAIN": _evaluate(train, fitted),
        "VALIDATION": _evaluate(validation, fitted),
    }
    config_sha_after = hash_file(config_path)
    if config_sha_before != config_sha_after:
        raise RuntimeError("baseline config changed after validation access")
    if candidate_hashes_before_validation != {
        path.name: hash_file(path)
        for path in sorted(ARTIFACT_ROOT.iterdir())
        if path.is_file()
    }:
        raise RuntimeError("fitted candidate changed during validation evaluation")

    _write_metrics_csv(metrics)
    t014 = REPORT_ROOT / "t014"
    t014.mkdir(parents=True, exist_ok=True)
    all_features = np.vstack([train.features, validation.features])
    rr_index = BASELINE_FEATURE_NAMES_V1.index("rr_available")
    qrs_index = BASELINE_FEATURE_NAMES_V1.index("qrs_available")
    missing = np.isnan(all_features)
    transformed_train = fitted["transformer"].transform_scaled(train.features)
    transformed_validation = fitted["transformer"].transform_scaled(validation.features)
    constant_features = [
        name
        for index, name in enumerate(BASELINE_FEATURE_NAMES_V1)
        if float(np.nanstd(train.features[:, index])) == 0.0
    ]
    feature_audit = {
        "feature_set_id": FEATURE_SET_ID,
        "feature_schema_sha256": feature_schema_sha256(),
        "feature_count": len(BASELINE_FEATURE_NAMES_V1),
        "feature_names": list(BASELINE_FEATURE_NAMES_V1),
        "waveform_only": True,
        "annotation_derived_features": False,
        "quality_as_feature": False,
        "detector": detector_metadata(),
        "TRAIN_rows": int(train.labels.size),
        "TRAIN_patients": len(set(train.participant_group_ids.tolist())),
        "VALIDATION_rows": int(validation.labels.size),
        "VALIDATION_patients": len(set(validation.participant_group_ids.tolist())),
        "RR_available_windows": int(np.sum(all_features[:, rr_index] == 1.0)),
        "QRS_available_windows": int(np.sum(all_features[:, qrs_index] == 1.0)),
        "missing_counts_per_feature": {
            name: int(missing[:, index].sum())
            for index, name in enumerate(BASELINE_FEATURE_NAMES_V1)
        },
        "missing_feature_cells_before_imputation": int(missing.sum()),
        "nonfinite_cells_after_transform": int(
            (~np.isfinite(np.vstack([transformed_train, transformed_validation]))).sum()
        ),
        "constant_TRAIN_features": constant_features,
        "imputer_fit_scope": "TRAIN_ONLY",
        "scaler_fit_scope": "TRAIN_ONLY",
        "validation_feature_schema_match": True,
        "overall_status": "PASS",
    }
    (t014 / "feature_audit.json").write_text(
        json.dumps(feature_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    fit_scope = {
        "majority_label_source": "TRAIN_ONLY",
        "imputer_fit_partitions": ["TRAIN"],
        "scaler_fit_partitions": ["TRAIN"],
        "LR_fit_partitions": ["TRAIN"],
        "RF_fit_partitions": ["TRAIN"],
        "VALIDATION": "EVALUATE_ONLY",
        "access_counts": {
            "TRAIN": 1,
            "VALIDATION": 1,
            "CALIBRATION": 0,
            "INTERNAL_TEST": 0,
            "INCART": 0,
            "NSTDB": 0,
            "BIDMC": 0,
            "WEARABLE_SIM_V1": 0,
        },
        "candidate_artifact_hashes_before_validation": candidate_hashes_before_validation,
        "baseline_config_sha_before_validation": config_sha_before,
        "baseline_config_sha_after_validation": config_sha_after,
        "overall_status": "PASS",
    }
    (t014 / "fit_scope_audit.json").write_text(
        json.dumps(fit_scope, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = {
        "baseline_id": BASELINE_ID,
        "feature_set_id": FEATURE_SET_ID,
        "feature_schema_sha256": feature_schema_sha256(),
        "upstream": {
            "split_id": "MITDB_SPLIT_V1",
            "split_sha256": hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"),
            "F05_lock_sha256": hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json"),
            "preproc_id": "PREPROC_V1",
            "F06_lock_sha256": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
            "window_manifest_sha256": hash_file(WINDOW_MANIFEST),
        },
        "majority": {
            **fitted["majority"].as_dict(),
            "model_sha256": hash_file(ARTIFACT_ROOT / "majority.json"),
        },
        "logistic": {
            "model_id": "LOGISTIC_BASELINE_V1",
            "config": config["logistic_regression"],
            "model_sha256": hash_file(ARTIFACT_ROOT / "logistic.joblib"),
            "iterations_used": fitted["logistic"].n_iter_.tolist(),
            "convergence_warning_count": fitted["convergence_warning_count"],
            "TRAIN_metrics": metrics["TRAIN"]["logistic"],
            "VALIDATION_metrics": metrics["VALIDATION"]["logistic"],
        },
        "random_forest": {
            "model_id": "RF_BASELINE_V1",
            "config": config["random_forest"],
            "model_sha256": hash_file(ARTIFACT_ROOT / "random_forest.joblib"),
            "TRAIN_metrics": metrics["TRAIN"]["random_forest"],
            "VALIDATION_metrics": metrics["VALIDATION"]["random_forest"],
        },
        "majority_metrics": {
            "TRAIN": metrics["TRAIN"]["majority"],
            "VALIDATION": metrics["VALIDATION"]["majority"],
        },
        "partition_access": {
            "TRAIN": "FIT",
            "VALIDATION": "EVALUATE_ONLY",
            "CALIBRATION": "NOT_ACCESSED",
            "INTERNAL_TEST": "NOT_ACCESSED",
            "INCART": "NOT_ACCESSED",
            "NSTDB": "NOT_ACCESSED",
            "BIDMC": "NOT_ACCESSED",
        },
        "decision_threshold": DECISION_THRESHOLD,
        "confidence_intervals": "NOT_RUN_T018_OWNED",
        "library_versions": library_versions(),
        "overall_status": "PASS",
    }
    baseline_report = REPORT_ROOT / "baselines/baseline_report.json"
    baseline_report.parent.mkdir(parents=True, exist_ok=True)
    baseline_report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"report": report, "feature_audit": feature_audit, "fit_scope": fit_scope}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/baseline_v1.yaml")
    args = parser.parse_args()
    result = run(args.config.resolve())
    print(
        "T014 baselines: PASS "
        f"(TRAIN={result['feature_audit']['TRAIN_rows']}, "
        f"VALIDATION={result['feature_audit']['VALIDATION_rows']})"
    )


if __name__ == "__main__":
    main()
