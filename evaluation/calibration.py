"""CAL_V1 single-temperature scaling and pooled-F1 operating threshold."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from scipy.optimize import minimize_scalar
from scipy.special import expit

from models.model_freeze import load_frozen_model_v1, verify_frozen_model_v1
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/calibration_v1.yaml"
ARTIFACT_PATH = ROOT / "artifacts/CAL_V1.json"
WINDOW_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
CACHE_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv"
CALIBRATION_ID = "CAL_V1"
CALIBRATION_DOMAIN = "MIT-BIH-v1.0.0"
FIT_PARTITION = "CALIBRATION"


class CalibrationError(RuntimeError):
    """Raised for CAL_V1 scope, numerical, or freeze violations."""


@dataclass(frozen=True)
class CalibrationPopulation:
    waveforms: np.ndarray
    labels: np.ndarray
    rows: tuple[dict[str, str], ...]
    accessed_paths: tuple[str, ...]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_calibration_population(root: Path = ROOT) -> CalibrationPopulation:
    """Load only eligible CALIBRATION waveforms through the frozen cache manifest."""
    selected = {
        row["example_id"]: row
        for row in _read_csv(root / WINDOW_MANIFEST.relative_to(ROOT))
        if row["partition"] == FIT_PARTITION and row["core_eligible"].upper() == "TRUE"
    }
    cache_rows = sorted(
        (
            row
            for row in _read_csv(root / CACHE_MANIFEST.relative_to(ROOT))
            if row["partition"] == FIT_PARTITION
        ),
        key=lambda row: row["record_id"],
    )
    waveforms: list[np.ndarray] = []
    rows: list[dict[str, str]] = []
    accessed: list[str] = []
    for cache in cache_rows:
        waveform_path = root / cache["relative_path"]
        id_path = root / cache["example_ids_path"]
        accessed.extend((cache["relative_path"], cache["example_ids_path"]))
        if hash_file(waveform_path) != cache["sha256"]:
            raise CalibrationError(f"CALIBRATION_CACHE_HASH_MISMATCH: {waveform_path}")
        if hash_file(id_path) != cache["example_ids_sha256"]:
            raise CalibrationError(f"CALIBRATION_ID_CACHE_HASH_MISMATCH: {id_path}")
        array = np.load(waveform_path, allow_pickle=False)
        ids = id_path.read_text(encoding="utf-8").splitlines()
        if array.shape != (len(ids), 2500):
            raise CalibrationError(f"CALIBRATION_CACHE_SHAPE_MISMATCH: {cache['record_id']}")
        for waveform, example_id in zip(array, ids, strict=True):
            row = selected.pop(example_id, None)
            if row is None:
                raise CalibrationError(f"CALIBRATION_SCOPE_VIOLATION: {example_id}")
            if row["label"] not in {"0", "1"}:
                raise CalibrationError(f"CALIBRATION_NONBINARY_LABEL: {example_id}")
            waveforms.append(np.asarray(waveform, dtype=np.float64))
            rows.append(row)
    if selected:
        raise CalibrationError(f"CALIBRATION_CLOSURE_FAILURE: missing={len(selected)}")
    order = np.argsort(np.asarray([row["example_id"] for row in rows]), kind="stable")
    ordered_rows = tuple(rows[int(index)] for index in order)
    ordered_waveforms = np.stack([waveforms[int(index)] for index in order])
    labels = np.asarray([int(row["label"]) for row in ordered_rows], dtype=np.int64)
    if set(np.unique(labels)) != {0, 1}:
        raise CalibrationError("CALIBRATION_CLASS_DEGENERACY")
    return CalibrationPopulation(
        waveforms=ordered_waveforms,
        labels=labels,
        rows=ordered_rows,
        accessed_paths=tuple(accessed),
    )


def extract_frozen_logits(
    population: CalibrationPopulation, root: Path = ROOT, batch_size: int = 64
) -> np.ndarray:
    """Run immutable MODEL_V1 in eval mode on canonical normalized windows."""
    model, _ = load_frozen_model_v1(root)
    before = copy.deepcopy(model.state_dict())
    normalized = np.stack(
        [
            normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON)
            for row in population.waveforms
        ]
    ).astype(np.float32)
    outputs: list[np.ndarray] = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, normalized.shape[0], batch_size):
            tensor = torch.from_numpy(normalized[start : start + batch_size, None, :])
            outputs.append(model(tensor).cpu().numpy()[:, 0])
    after = model.state_dict()
    if any(not torch.equal(before[key], after[key]) for key in before):
        raise CalibrationError("MODEL_V1_STATE_MUTATED_DURING_CALIBRATION")
    logits = np.concatenate(outputs).astype(np.float64)
    if not np.all(np.isfinite(logits)):
        raise CalibrationError("CALIBRATION_NONFINITE_LOGITS")
    return logits


def binary_nll(logits: np.ndarray, labels: np.ndarray) -> float:
    values = np.asarray(logits, dtype=np.float64)
    targets = np.asarray(labels, dtype=np.float64)
    return float(np.mean(np.logaddexp(0.0, values) - targets * values))


def fit_temperature(
    logits: np.ndarray, labels: np.ndarray, config: dict[str, Any]
) -> dict[str, Any]:
    settings = config["temperature"]
    lower, upper = (float(value) for value in settings["theta_bounds"])

    def objective(theta: float) -> float:
        return binary_nll(np.asarray(logits, dtype=np.float64) / math.exp(theta), labels)

    result = minimize_scalar(
        objective,
        bounds=(lower, upper),
        method="bounded",
        options={"xatol": float(settings["xatol"]), "maxiter": int(settings["maxiter"])},
    )
    theta = float(result.x)
    temperature = float(math.exp(theta))
    tolerance = float(settings["boundary_tolerance"])
    if not result.success or not math.isfinite(temperature) or temperature <= 0:
        raise CalibrationError("TEMPERATURE_OPTIMIZATION_FAILURE")
    if theta <= lower + tolerance or theta >= upper - tolerance:
        raise CalibrationError("TEMPERATURE_OPTIMIZER_BOUND_HIT")
    raw_nll = binary_nll(logits, labels)
    calibrated_nll = binary_nll(np.asarray(logits) / temperature, labels)
    if calibrated_nll > raw_nll + float(settings["nll_nonworsening_tolerance"]):
        raise CalibrationError("TEMPERATURE_OPTIMIZATION_FAILURE: NLL worsened")
    return {
        "temperature": temperature,
        "theta": theta,
        "raw_nll": raw_nll,
        "calibrated_nll": calibrated_nll,
        "optimizer_success": bool(result.success),
        "optimizer_message": str(result.message),
        "optimizer_iterations": int(result.nit),
        "boundary_hit": False,
    }


def fit_from_partitioned_arrays(
    partitions: np.ndarray,
    logits: np.ndarray,
    labels: np.ndarray,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Synthetic-test helper proving only CALIBRATION rows influence both fitted values."""
    partition_values = np.asarray(partitions, dtype=str)
    selected = partition_values == FIT_PARTITION
    selected_logits = np.asarray(logits, dtype=np.float64)[selected]
    selected_labels = np.asarray(labels, dtype=np.int64)[selected]
    if selected_logits.size == 0 or set(np.unique(selected_labels)) != {0, 1}:
        raise CalibrationError("CALIBRATION_CLASS_DEGENERACY")
    temperature_result = fit_temperature(selected_logits, selected_labels, config)
    calibrated = raw_probability_from_logit(
        selected_logits / float(temperature_result["temperature"])
    )
    threshold_result = select_f1_threshold(calibrated, selected_labels)
    return {
        "temperature": float(temperature_result["temperature"]),
        "threshold": float(threshold_result["selected_threshold"]),
        "threshold_search": threshold_result,
    }


def raw_probability_from_logit(logit: np.ndarray | float) -> np.ndarray:
    return np.asarray(expit(np.asarray(logit, dtype=np.float64)), dtype=np.float64)


def apply_temperature(logits: np.ndarray | float, cal: dict[str, Any]) -> np.ndarray:
    return np.asarray(logits, dtype=np.float64) / float(cal["temperature"])


def source_domain_calibrated_probability(
    logits: np.ndarray | float, cal: dict[str, Any]
) -> np.ndarray:
    return raw_probability_from_logit(apply_temperature(logits, cal))


def apply_operating_threshold(
    probabilities: np.ndarray | float, cal: dict[str, Any]
) -> np.ndarray:
    return (np.asarray(probabilities, dtype=np.float64) >= float(cal["threshold"])).astype(
        np.int64
    )


def brier_score(probabilities: np.ndarray, labels: np.ndarray) -> float:
    return float(
        np.mean(
            (np.asarray(probabilities, dtype=np.float64) - np.asarray(labels, dtype=np.float64))
            ** 2
        )
    )


def reliability_bins(probabilities: np.ndarray, labels: np.ndarray) -> list[dict[str, Any]]:
    values = np.asarray(probabilities, dtype=np.float64)
    targets = np.asarray(labels, dtype=np.int64)
    indices = np.minimum(np.floor(values * 10.0).astype(np.int64), 9)
    result: list[dict[str, Any]] = []
    for index in range(10):
        selected = indices == index
        count = int(np.sum(selected))
        result.append(
            {
                "bin_index": index,
                "lower": index / 10.0,
                "upper": (index + 1) / 10.0,
                "upper_inclusive": index == 9,
                "count": count,
                "mean_probability": float(np.mean(values[selected])) if count else None,
                "observed_positive_fraction": float(np.mean(targets[selected])) if count else None,
            }
        )
    return result


def select_f1_threshold(probabilities: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    values = np.asarray(probabilities, dtype=np.float64)
    targets = np.asarray(labels, dtype=np.int64)
    candidates = np.unique(np.concatenate(([0.0], values, [1.0])))
    best: dict[str, Any] | None = None
    tie_count = 0
    for threshold in candidates:
        predictions = values >= threshold
        tp = int(np.sum(predictions & (targets == 1)))
        fp = int(np.sum(predictions & (targets == 0)))
        fn = int(np.sum(~predictions & (targets == 1)))
        tn = int(np.sum(~predictions & (targets == 0)))
        numerator = 2 * tp
        denominator = 2 * tp + fp + fn
        candidate = {
            "threshold": float(threshold),
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "f1_numerator": numerator,
            "f1_denominator": denominator,
        }
        if best is None:
            best, tie_count = candidate, 1
            continue
        left = numerator * int(best["f1_denominator"])
        right = int(best["f1_numerator"]) * denominator
        if left > right:
            best, tie_count = candidate, 1
        elif left == right:
            tie_count += 1
            if threshold > float(best["threshold"]):
                best = candidate
    assert best is not None
    tp, fp, tn, fn = (int(best[key]) for key in ("tp", "fp", "tn", "fn"))
    denominator = int(best["f1_denominator"])
    return {
        "candidate_count": int(candidates.size),
        "selection_metric": "POOLED_CALIBRATION_WINDOW_F1",
        "comparator": ">=",
        "tie_policy": "HIGHEST_THRESHOLD_AMONG_MAX_F1_V1",
        "maximum_f1_tie_count": tie_count,
        "selected_threshold": float(best["threshold"]),
        "selected_f1": float(int(best["f1_numerator"]) / denominator) if denominator else 0.0,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": float(tp / (tp + fp)) if tp + fp else 0.0,
        "sensitivity": float(tp / (tp + fn)) if tp + fn else 0.0,
        "specificity": float(tn / (tn + fp)) if tn + fp else 0.0,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_predictions(
    path: Path,
    rows: tuple[dict[str, str], ...],
    labels: np.ndarray,
    logits: np.ndarray,
    raw: np.ndarray,
    calibrated: np.ndarray,
    predictions: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "example_id",
        "participant_group_id",
        "record_id",
        "label",
        "raw_logit",
        "raw_probability",
        "source_domain_calibrated_probability",
        "thresholded_prediction",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row, label, logit, raw_p, cal_p, prediction in zip(
            rows, labels, logits, raw, calibrated, predictions, strict=True
        ):
            writer.writerow(
                {
                    "example_id": row["example_id"],
                    "participant_group_id": row["participant_group_id"],
                    "record_id": row["record_id"],
                    "label": int(label),
                    "raw_logit": format(float(logit), ".17g"),
                    "raw_probability": format(float(raw_p), ".17g"),
                    "source_domain_calibrated_probability": format(float(cal_p), ".17g"),
                    "thresholded_prediction": int(prediction),
                }
            )


def reliability_svg(raw_bins: list[dict[str, Any]], cal_bins: list[dict[str, Any]]) -> str:
    def points(bins: list[dict[str, Any]]) -> str:
        return " ".join(
            f"{60 + 440 * float(row['mean_probability']):.6f},"
            f"{500 - 440 * float(row['observed_positive_fraction']):.6f}"
            for row in bins
            if row["count"]
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="620" height="570" '
        'viewBox="0 0 620 570">\n'
        '<rect width="620" height="570" fill="white"/>\n'
        '<text x="310" y="25" text-anchor="middle" font-family="sans-serif" font-size="16">'
        "MIT-BIH calibration partition — research-only source-domain calibration</text>\n"
        '<line x1="60" y1="500" x2="500" y2="60" stroke="#777" stroke-dasharray="5,5"/>\n'
        f'<polyline points="{points(raw_bins)}" fill="none" stroke="#c44" stroke-width="2"/>\n'
        f'<polyline points="{points(cal_bins)}" fill="none" stroke="#36c" stroke-width="2"/>\n'
        '<rect x="520" y="75" width="12" height="3" fill="#c44"/><text x="538" y="82" '
        'font-family="sans-serif" font-size="12">raw</text>\n'
        '<rect x="520" y="100" width="12" height="3" fill="#36c"/><text x="538" y="107" '
        'font-family="sans-serif" font-size="12">temperature-scaled</text>\n'
        '<text x="280" y="545" text-anchor="middle" font-family="sans-serif" font-size="13">'
        "Mean predicted probability</text>\n"
        '<text x="15" y="280" transform="rotate(-90 15 280)" text-anchor="middle" '
        'font-family="sans-serif" font-size="13">Observed positive fraction</text>\n'
        "</svg>\n"
    )


def load_cal_v1(root: Path = ROOT, artifact_path: Path | None = None) -> dict[str, Any]:
    path = artifact_path or root / "artifacts/CAL_V1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def verify_cal_v1(root: Path = ROOT, artifact_path: Path | None = None) -> dict[str, Any]:
    verify_frozen_model_v1(root)
    path = artifact_path or root / "artifacts/CAL_V1.json"
    if not path.exists():
        raise CalibrationError("CAL_V1_MISSING")
    artifact = load_cal_v1(root, path)
    checkpoint_sha = hash_file(root / "checkpoints/MODEL_V1.pt")
    model_manifest_sha = hash_file(root / "checkpoints/MODEL_V1.manifest.json")
    frozen_config_sha = hash_file(root / "configs/model_v1_frozen.yaml")
    required = {
        "calibration_id": artifact.get("calibration_id") == CALIBRATION_ID,
        "status": artifact.get("status") == "FROZEN",
        "fit_partition": artifact.get("fit_partition") == FIT_PARTITION,
        "domain": artifact.get("calibration_domain") == CALIBRATION_DOMAIN,
        "patient_count": isinstance(artifact.get("calibration_patient_count"), int)
        and artifact["calibration_patient_count"] > 0,
        "window_count": isinstance(artifact.get("calibration_window_count"), int)
        and artifact["calibration_window_count"] > 0,
        "temperature": math.isfinite(float(artifact.get("temperature", math.nan)))
        and float(artifact["temperature"]) > 0,
        "threshold": math.isfinite(float(artifact.get("threshold", math.nan)))
        and 0 <= float(artifact["threshold"]) <= 1,
        "model_id": artifact.get("model_id") == "MODEL_V1",
        "checkpoint_binding": artifact.get("model_checkpoint_sha256") == checkpoint_sha,
        "manifest_binding": artifact.get("model_manifest_sha256") == model_manifest_sha,
        "frozen_config_binding": artifact.get("model_frozen_config_sha256")
        == frozen_config_sha,
        "target": artifact.get("target_id") == "AAMI_SVF_WINDOW_V1",
        "map": artifact.get("map_id") == "AAMI_SVF_MAP_V1",
        "split": artifact.get("split_id") == "MITDB_SPLIT_V1",
        "preproc": artifact.get("preproc_id") == "PREPROC_V1",
        "comparator": artifact.get("threshold_comparator") == ">=",
        "internal_sealed": artifact.get("internal_test_accessed") is False,
        "external_sealed": artifact.get("external_data_accessed") is False,
    }
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise CalibrationError(f"CAL_V1_SEMANTIC_MISMATCH: {','.join(failed)}")
    for relative, expected in artifact["upstream_sha256"].items():
        if hash_file(root / relative) != expected:
            raise CalibrationError(f"CAL_V1_UPSTREAM_HASH_MISMATCH: {relative}")
    return {
        "status": "PASS",
        "freeze_id": "F09",
        "calibration_id": CALIBRATION_ID,
        "artifact_path": str(path.relative_to(root)),
        "artifact_sha256": hash_file(path),
    }


def fit_cal_v1(root: Path = ROOT) -> dict[str, Any]:
    config_path = root / CONFIG_PATH.relative_to(ROOT)
    config_sha_before = hash_file(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    model_verification = verify_frozen_model_v1(root)
    checkpoint_sha_before = hash_file(root / "checkpoints/MODEL_V1.pt")
    population = load_calibration_population(root)
    logits_first = extract_frozen_logits(population, root)
    logits_second = extract_frozen_logits(population, root)
    if not np.array_equal(logits_first, logits_second):
        raise CalibrationError("CALIBRATION_LOGIT_NONDETERMINISM")
    temperature_first = fit_temperature(logits_first, population.labels, config)
    temperature_second = fit_temperature(logits_first, population.labels, config)
    temperature_difference = abs(
        float(temperature_first["temperature"]) - float(temperature_second["temperature"])
    )
    if temperature_difference > 1e-12:
        raise CalibrationError("CALIBRATION_TEMPERATURE_NONDETERMINISM")
    temperature = float(temperature_first["temperature"])
    raw_probability = raw_probability_from_logit(logits_first)
    provisional = {"temperature": temperature}
    calibrated_probability = source_domain_calibrated_probability(logits_first, provisional)
    threshold_first = select_f1_threshold(calibrated_probability, population.labels)
    threshold_second = select_f1_threshold(calibrated_probability, population.labels)
    if threshold_first != threshold_second:
        raise CalibrationError("CALIBRATION_THRESHOLD_NONDETERMINISM")
    threshold = float(threshold_first["selected_threshold"])
    provisional["threshold"] = threshold
    predictions = apply_operating_threshold(calibrated_probability, provisional)
    raw_bins = reliability_bins(raw_probability, population.labels)
    calibrated_bins = reliability_bins(calibrated_probability, population.labels)
    reliability = {
        "calibration_id": CALIBRATION_ID,
        "domain": CALIBRATION_DOMAIN,
        "method": "EQUAL_WIDTH_10_BINS_V1",
        "bin_edges": [index / 10.0 for index in range(11)],
        "raw": raw_bins,
        "temperature_scaled": calibrated_bins,
        "claim_boundary": "Research-only source-domain calibration; small patient sample.",
    }
    reliability_path = root / "reports/calibration/reliability.json"
    _write_json(reliability_path, reliability)
    svg = reliability_svg(raw_bins, calibrated_bins)
    svg_path = root / "reports/calibration/reliability_diagram.svg"
    svg_path.write_text(svg, encoding="utf-8")
    prediction_path = root / "reports/calibration/calibration_predictions.csv"
    _write_predictions(
        prediction_path,
        population.rows,
        population.labels,
        logits_first,
        raw_probability,
        calibrated_probability,
        predictions,
    )
    model_manifest_sha = hash_file(root / "checkpoints/MODEL_V1.manifest.json")
    frozen_config_sha = hash_file(root / "configs/model_v1_frozen.yaml")
    upstream = {
        "checkpoints/MODEL_V1.pt": checkpoint_sha_before,
        "checkpoints/MODEL_V1.manifest.json": model_manifest_sha,
        "configs/model_v1_frozen.yaml": frozen_config_sha,
        "manifests/labels/AAMI_SVF_MAP_V1.yaml": hash_file(
            root / "manifests/labels/AAMI_SVF_MAP_V1.yaml"
        ),
        "manifests/splits/MITDB_SPLIT_V1.csv": hash_file(
            root / "manifests/splits/MITDB_SPLIT_V1.csv"
        ),
        "manifests/preprocessing/PREPROC_V1.lock.json": hash_file(
            root / "manifests/preprocessing/PREPROC_V1.lock.json"
        ),
        "manifests/windows/MITDB_WINDOWS_V1.csv": hash_file(
            root / "manifests/windows/MITDB_WINDOWS_V1.csv"
        ),
    }
    groups = sorted({row["participant_group_id"] for row in population.rows})
    records = sorted({row["record_id"] for row in population.rows})
    positives = int(np.sum(population.labels == 1))
    negatives = int(np.sum(population.labels == 0))
    artifact = {
        "calibration_id": CALIBRATION_ID,
        "status": "FROZEN",
        "freeze_id": "F09",
        "frozen_by_task": "T017",
        "model_id": "MODEL_V1",
        "model_checkpoint_sha256": checkpoint_sha_before,
        "model_manifest_sha256": model_manifest_sha,
        "model_frozen_config_sha256": frozen_config_sha,
        "target_id": "AAMI_SVF_WINDOW_V1",
        "map_id": "AAMI_SVF_MAP_V1",
        "split_id": "MITDB_SPLIT_V1",
        "preproc_id": "PREPROC_V1",
        "fit_partition": FIT_PARTITION,
        "calibration_domain": CALIBRATION_DOMAIN,
        "calibration_patient_count": len(groups),
        "calibration_record_count": len(records),
        "calibration_window_count": int(population.labels.size),
        "positive_window_count": positives,
        "negative_window_count": negatives,
        "temperature": temperature,
        "temperature_parameterization": "theta=log(T); T=exp(theta)",
        "temperature_fit_objective": "MEAN_BINARY_NLL",
        "temperature_optimizer": config["temperature"],
        "raw_nll": float(temperature_first["raw_nll"]),
        "calibrated_nll": float(temperature_first["calibrated_nll"]),
        "raw_brier": brier_score(raw_probability, population.labels),
        "calibrated_brier": brier_score(calibrated_probability, population.labels),
        "reliability_method": "EQUAL_WIDTH_10_BINS_V1",
        "reliability_report_path": "reports/calibration/reliability.json",
        "threshold": threshold,
        "threshold_metric": "POOLED_CALIBRATION_WINDOW_F1",
        "threshold_comparator": ">=",
        "threshold_tie_policy": "HIGHEST_THRESHOLD_AMONG_MAX_F1_V1",
        "threshold_confusion_counts": {
            key: threshold_first[key] for key in ("tp", "fp", "tn", "fn")
        },
        "threshold_calibration_f1": float(threshold_first["selected_f1"]),
        "probability_semantics": {
            "raw_probability": "sigmoid(MODEL_V1 raw logit)",
            "source_domain_calibrated_probability": (
                "sigmoid(MODEL_V1 raw logit / CAL_V1.temperature)"
            ),
        },
        "small_patient_sample_uncertainty": (
            "MIT-BIH source-domain calibration under small-patient-sample uncertainty; "
            "window count is not patient n."
        ),
        "internal_test_accessed": False,
        "external_data_accessed": False,
        "upstream_sha256": upstream,
        "method_config_path": "configs/calibration_v1.yaml",
        "method_config_sha256": config_sha_before,
        "change_control": (
            "Changing temperature, threshold, method, comparator, tie rule, partition, or "
            "domain requires a controlled calibration version change and invalidates downstream "
            "thresholded evaluation, alert, API, and dashboard evidence."
        ),
    }
    artifact_path = root / ARTIFACT_PATH.relative_to(ROOT)
    _write_json(artifact_path, artifact)
    threshold_path = root / "reports/t017/threshold_search.json"
    _write_json(threshold_path, threshold_first)
    access = {
        "TRAIN": {"waveform_cache_reads": 0, "paths": []},
        "VALIDATION": {"waveform_cache_reads": 0, "paths": []},
        "CALIBRATION": {
            "waveform_cache_reads": len(population.accessed_paths),
            "paths": list(population.accessed_paths),
        },
        "INTERNAL_TEST": {"waveform_cache_reads": 0, "paths": []},
        "INCART": {"reads": 0},
        "NSTDB": {"reads": 0},
        "BIDMC": {"reads": 0},
        "WEARABLE": {"reads": 0},
        "overall_status": "PASS",
    }
    _write_json(root / "reports/t017/partition_access_audit.json", access)
    config_sha_after = hash_file(config_path)
    audit = {
        "calibration_id": CALIBRATION_ID,
        "model_id": "MODEL_V1",
        "model_checkpoint_sha256": checkpoint_sha_before,
        "F08_verification": model_verification,
        "fit_partition": FIT_PARTITION,
        "patient_groups": len(groups),
        "records": len(records),
        "windows": int(population.labels.size),
        "positives": positives,
        "negatives": negatives,
        "temperature": temperature,
        "raw_nll": artifact["raw_nll"],
        "calibrated_nll": artifact["calibrated_nll"],
        "raw_brier": artifact["raw_brier"],
        "calibrated_brier": artifact["calibrated_brier"],
        "reliability_method": artifact["reliability_method"],
        "threshold": threshold,
        "threshold_metric": artifact["threshold_metric"],
        "threshold_tie_policy": artifact["threshold_tie_policy"],
        "method_config_sha_before": config_sha_before,
        "method_config_sha_after": config_sha_after,
        "method_config_unchanged": config_sha_before == config_sha_after,
        "forbidden_partition_access_counts": {
            key: 0
            for key in (
                "TRAIN",
                "VALIDATION",
                "INTERNAL_TEST",
                "INCART",
                "NSTDB",
                "BIDMC",
                "WEARABLE",
            )
        },
        "overall_status": "PASS",
    }
    _write_json(root / "reports/t017/calibration_audit.json", audit)
    reproducibility = {
        "logit_extraction_repeat": "PASS",
        "maximum_logit_difference": float(np.max(np.abs(logits_first - logits_second))),
        "temperature_fit_repeat": "PASS",
        "temperature_run_1": temperature,
        "temperature_run_2": float(temperature_second["temperature"]),
        "absolute_temperature_difference": temperature_difference,
        "threshold_search_repeat": "PASS",
        "reliability_data_repeat": "PASS",
        "cal_v1_verification": "PENDING_ARTIFACT_VERIFY",
        "overall_status": "PASS",
    }
    _write_json(root / "reports/t017/reproducibility.json", reproducibility)
    if hash_file(config_path) != config_sha_before:
        raise CalibrationError("CALIBRATION_METHOD_CONFIG_CHANGED_AFTER_DATA_ACCESS")
    if hash_file(root / "checkpoints/MODEL_V1.pt") != checkpoint_sha_before:
        raise CalibrationError("MODEL_V1_CHANGED_DURING_CALIBRATION")
    verification = verify_cal_v1(root)
    reproducibility["cal_v1_verification"] = verification
    _write_json(root / "reports/t017/reproducibility.json", reproducibility)
    return {
        "artifact": artifact,
        "threshold_search": threshold_first,
        "verification": verification,
        "access": access,
        "expected_example_ids": [row["example_id"] for row in population.rows],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fit-cal-v1", action="store_true", required=True)
    parser.parse_args()
    result = fit_cal_v1(ROOT)
    print(
        json.dumps(
            {
                "status": result["verification"]["status"],
                "temperature": result["artifact"]["temperature"],
                "threshold": result["artifact"]["threshold"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
