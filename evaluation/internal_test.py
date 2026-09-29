"""One-shot frozen MODEL_V1 evaluation on the sealed MITDB INTERNAL_TEST partition."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from evaluation.bootstrap import bootstrap_replicates, percentile_summary
from evaluation.calibration import (
    apply_operating_threshold,
    load_cal_v1,
    raw_probability_from_logit,
    source_domain_calibrated_probability,
    verify_cal_v1,
)
from evaluation.metrics import METRIC_NAMES, pooled_binary_metrics
from models.model_freeze import load_frozen_model_v1, verify_frozen_model_v1
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore
from scripts.generate_model_v1_test_vector_t016 import write_deterministic_npz

ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ID = "INTERNAL_EVAL_V1"
PARTITION = "INTERNAL_TEST"
GUARD_PATH = Path("artifacts/internal_test_access_v1.json")
CONFIG_PATH = Path("configs/internal_eval_v1.yaml")
WINDOW_MANIFEST = Path("manifests/windows/MITDB_WINDOWS_V1.csv")
CACHE_MANIFEST = Path("manifests/windows/MITDB_WINDOWS_V1.cache.csv")


class InternalTestError(RuntimeError):
    """Raised for one-shot, scope, freeze, or report-integrity failures."""


@dataclass(frozen=True)
class InternalPopulation:
    waveforms: np.ndarray
    labels: np.ndarray
    rows: tuple[dict[str, str], ...]
    accessed_paths: tuple[str, ...]


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def verify_clean_pre_access_state(root: Path, pre_access_audit: dict[str, Any]) -> None:
    if _git(root, "status", "--porcelain"):
        raise InternalTestError("PRE_ACCESS_WORKTREE_NOT_CLEAN")
    method_commit = str(pre_access_audit["pre_access_method_commit"])
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", method_commit, "HEAD"], cwd=root
    ).returncode:
        raise InternalTestError("PRE_ACCESS_METHOD_COMMIT_NOT_ANCESTOR")
    for relative, expected in pre_access_audit["method_artifact_sha256"].items():
        if hash_file(root / relative) != expected:
            raise InternalTestError(f"POST_TEST_METHOD_MUTATION: {relative}")


def create_run_started_guard(root: Path, pre_access_audit: dict[str, Any]) -> dict[str, Any]:
    path = root / GUARD_PATH
    if path.exists():
        status = _json(path).get("status")
        if status == "COMPLETED":
            raise InternalTestError("INTERNAL_TEST_ALREADY_CONSUMED")
        raise InternalTestError("INTERNAL_TEST_RUN_INTERRUPTED")
    guard = {
        "evaluation_id": EVALUATION_ID,
        "status": "RUN_STARTED",
        "pre_access_git_sha": _git(root, "rev-parse", "HEAD"),
        "pre_access_method_commit": pre_access_audit["pre_access_method_commit"],
        "method_config_sha256": hash_file(root / CONFIG_PATH),
        "MODEL_V1_sha256": hash_file(root / "checkpoints/MODEL_V1.pt"),
        "CAL_V1_sha256": hash_file(root / "artifacts/CAL_V1.json"),
        "split_sha256": hash_file(root / "manifests/splits/MITDB_SPLIT_V1.csv"),
        "preproc_lock_sha256": hash_file(root / "manifests/preprocessing/PREPROC_V1.lock.json"),
        "window_manifest_sha256": hash_file(root / WINDOW_MANIFEST),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(guard, indent=2, sort_keys=True) + "\n")
    return guard


def load_internal_population(root: Path) -> InternalPopulation:
    """The only production function that opens INTERNAL_TEST waveform caches."""
    selected = {
        row["example_id"]: row
        for row in _csv_rows(root / WINDOW_MANIFEST)
        if row["partition"] == PARTITION and row["core_eligible"].upper() == "TRUE"
    }
    cache_rows = sorted(
        [row for row in _csv_rows(root / CACHE_MANIFEST) if row["partition"] == PARTITION],
        key=lambda row: row["record_id"],
    )
    waveforms: list[np.ndarray] = []
    rows: list[dict[str, str]] = []
    accessed: list[str] = []
    for cache in cache_rows:
        waveform_path = root / cache["relative_path"]
        id_path = root / cache["example_ids_path"]
        accessed.extend((cache["relative_path"], cache["example_ids_path"]))
        waveform_matches = hash_file(waveform_path) == cache["sha256"]
        identifiers_match = hash_file(id_path) == cache["example_ids_sha256"]
        if not waveform_matches or not identifiers_match:
            raise InternalTestError("INTERNAL_TEST_CACHE_HASH_MISMATCH")
        array = np.load(waveform_path, allow_pickle=False)
        ids = id_path.read_text(encoding="utf-8").splitlines()
        if array.shape != (len(ids), 2500):
            raise InternalTestError("INTERNAL_TEST_CACHE_SHAPE_MISMATCH")
        for waveform, example_id in zip(array, ids, strict=True):
            row = selected.pop(example_id, None)
            if row is None or row["label"] not in {"0", "1"}:
                raise InternalTestError("INTERNAL_TEST_SCOPE_VIOLATION")
            waveforms.append(np.asarray(waveform, dtype=np.float64))
            rows.append(row)
    if selected:
        raise InternalTestError(f"INTERNAL_TEST_CLOSURE_FAILURE: missing={len(selected)}")
    order = np.argsort(np.asarray([row["example_id"] for row in rows]), kind="stable")
    ordered_rows = tuple(rows[int(index)] for index in order)
    population = InternalPopulation(
        waveforms=np.stack([waveforms[int(index)] for index in order]),
        labels=np.asarray([int(row["label"]) for row in ordered_rows], dtype=np.int64),
        rows=ordered_rows,
        accessed_paths=tuple(accessed),
    )
    if set(np.unique(population.labels).tolist()) != {0, 1}:
        raise InternalTestError("INTERNAL_TEST_CLASS_DEGENERACY")
    return population


def extract_logits_once(population: InternalPopulation, root: Path, batch_size: int) -> np.ndarray:
    model, _ = load_frozen_model_v1(root)
    before = copy.deepcopy(model.state_dict())
    normalized = np.stack(
        [
            normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON)
            for row in population.waveforms
        ]
    ).astype(np.float32)
    output: list[np.ndarray] = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(normalized), batch_size):
            batch = torch.from_numpy(normalized[start : start + batch_size, None, :])
            output.append(model(batch).cpu().numpy()[:, 0])
    if any(not torch.equal(before[key], model.state_dict()[key]) for key in before):
        raise InternalTestError("MODEL_V1_STATE_MUTATED_DURING_INTERNAL_TEST")
    return np.concatenate(output).astype(np.float64)


def _write_predictions(
    path: Path,
    population: InternalPopulation,
    logits: np.ndarray,
    raw: np.ndarray,
    calibrated: np.ndarray,
    predictions: np.ndarray,
    cal: dict[str, Any],
) -> None:
    fields = [
        "example_id", "participant_group_id", "record_id", "prediction_timestamp_us",
        "ecg_quality", "label", "raw_logit", "raw_probability",
        "source_domain_calibrated_probability", "threshold", "thresholded_prediction",
        "model_id", "model_sha", "calibration_id",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row, label, logit, raw_p, calibrated_p, prediction in zip(
            population.rows, population.labels, logits, raw, calibrated, predictions, strict=True
        ):
            writer.writerow({
                "example_id": row["example_id"],
                "participant_group_id": row["participant_group_id"],
                "record_id": row["record_id"],
                "prediction_timestamp_us": row["prediction_timestamp_us"],
                "ecg_quality": row["ecg_quality"],
                "label": int(label),
                "raw_logit": format(float(logit), ".17g"),
                "raw_probability": format(float(raw_p), ".17g"),
                "source_domain_calibrated_probability": format(float(calibrated_p), ".17g"),
                "threshold": format(float(cal["threshold"]), ".17g"),
                "thresholded_prediction": int(prediction),
                "model_id": "MODEL_V1",
                "model_sha": cal["model_checkpoint_sha256"],
                "calibration_id": "CAL_V1",
            })


def _write_bootstrap_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["replicate_index", "sampled_patient_slots", "unique_patient_count", *METRIC_NAMES]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row[key] is None else row[key] for key in fields})


def _write_metric_csv(path: Path, summary: dict[str, dict[str, Any]], patient_count: int) -> None:
    fields = [
        "metric", "point_estimate", "ci_lower_95", "ci_upper_95",
        "valid_bootstrap_replicates", "invalid_bootstrap_replicates", "patient_cluster_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for name in METRIC_NAMES:
            row = summary[name]
            writer.writerow({
                "metric": name,
                "point_estimate": format(row["point_estimate"], ".17g"),
                "ci_lower_95": format(row["ci_lower_95"], ".17g"),
                "ci_upper_95": format(row["ci_upper_95"], ".17g"),
                "valid_bootstrap_replicates": row["valid_replicates"],
                "invalid_bootstrap_replicates": row["invalid_replicates"],
                "patient_cluster_count": patient_count,
            })


def run_internal_test_once(root: Path = ROOT) -> dict[str, Any]:
    pre_access_audit = _json(root / "reports/t018/pre_access_audit.json")
    verify_clean_pre_access_state(root, pre_access_audit)
    f08 = verify_frozen_model_v1(root)
    f09 = verify_cal_v1(root)
    cal = load_cal_v1(root)
    config = yaml.safe_load((root / CONFIG_PATH).read_text(encoding="utf-8"))
    if config["evaluation_id"] != EVALUATION_ID or config["partition"] != PARTITION:
        raise InternalTestError("INTERNAL_EVAL_CONFIG_IDENTITY_MISMATCH")
    guard = create_run_started_guard(root, pre_access_audit)
    population = load_internal_population(root)
    logits = extract_logits_once(population, root, int(config["inference"]["batch_size"]))
    raw = raw_probability_from_logit(logits)
    calibrated = source_domain_calibrated_probability(logits, cal)
    predictions = apply_operating_threshold(calibrated, cal)
    prediction_path = root / "reports/internal_test_predictions.csv"
    _write_predictions(prediction_path, population, logits, raw, calibrated, predictions, cal)
    patients = np.asarray([row["participant_group_id"] for row in population.rows], dtype=str)
    point = pooled_binary_metrics(population.labels, calibrated, predictions, patients)
    bootstrap = config["bootstrap"]
    draws, replicate_rows = bootstrap_replicates(
        patients, population.labels, calibrated, predictions,
        replicates=int(bootstrap["replicates"]), seed=int(bootstrap["seed"]),
    )
    draws_path = root / "reports/t018/bootstrap_draws.npz"
    write_deterministic_npz(draws_path, {
        "draws_int64": draws,
        "patient_ids_utf8": np.asarray(sorted(set(patients.tolist())), dtype="S32"),
    })
    replicate_path = root / "reports/t018/bootstrap_replicates.csv"
    _write_bootstrap_csv(replicate_path, replicate_rows)
    summary = percentile_summary(point, replicate_rows)
    unique_counts = np.asarray([row["unique_patient_count"] for row in replicate_rows])
    bootstrap_report = {
        "method_id": "PATIENT_CLUSTER_PERCENTILE_95_V1",
        "replicates_requested": 2000,
        "replicates_generated": len(replicate_rows),
        "cluster_unit": "participant_group_id",
        "source_patient_clusters": len(set(patients.tolist())),
        "patient_slots_per_replicate": int(draws.shape[1]),
        "sampling": "WITH_REPLACEMENT",
        "multiplicity_preserved": True,
        "rejection_or_redraw_used": False,
        "unique_patient_count": {
            "minimum": int(unique_counts.min()),
            "median": float(np.median(unique_counts)),
            "maximum": int(unique_counts.max()),
        },
        "ci_type": "PERCENTILE_95_V1",
        "quantiles": [0.025, 0.975],
        "quantile_method": "linear",
        "point_estimate_source": "ORIGINAL_INTERNAL_TEST_SAMPLE_NOT_BOOTSTRAP_MEAN",
        "metrics": summary,
    }
    _write_json(root / "reports/t018/bootstrap_summary.json", bootstrap_report)
    metric_path = root / "reports/internal_test_metrics.csv"
    _write_metric_csv(metric_path, summary, len(set(patients.tolist())))
    records = sorted({row["record_id"] for row in population.rows})
    report = {
        "evaluation_id": EVALUATION_ID,
        "status": "FROZEN",
        "freeze_id": "F10",
        "one_shot": True,
        "access_guard": {"path": str(GUARD_PATH), "status": "COMPLETED"},
        "dataset": "MIT-BIH-v1.0.0",
        "partition": PARTITION,
        "patient_groups": len(set(patients.tolist())),
        "records": len(records),
        "eligible_windows": len(population.rows),
        "positive_windows": int(np.sum(population.labels == 1)),
        "negative_windows": int(np.sum(population.labels == 0)),
        "model_id": "MODEL_V1",
        "model_sha256": f08["checkpoint_sha256"],
        "calibration_id": "CAL_V1",
        "calibration_sha256": f09["artifact_sha256"],
        "temperature": float(cal["temperature"]),
        "threshold": float(cal["threshold"]),
        "threshold_comparator": ">=",
        "calibration_domain": cal["calibration_domain"],
        "calibration_patient_count": cal["calibration_patient_count"],
        "point_metrics": {name: point[name] for name in METRIC_NAMES},
        "confusion_matrix": point["confusion_matrix"],
        "bootstrap": bootstrap_report,
        "pre_access_method_commit": pre_access_audit["pre_access_method_commit"],
        "method_config_sha256": hash_file(root / CONFIG_PATH),
        "upstream_sha256": {
            "checkpoints/MODEL_V1.manifest.json": hash_file(
                root / "checkpoints/MODEL_V1.manifest.json"
            ),
            "artifacts/CAL_V1.json": f09["artifact_sha256"],
            "manifests/splits/MITDB_SPLIT_V1.csv": hash_file(
                root / "manifests/splits/MITDB_SPLIT_V1.csv"
            ),
            "manifests/preprocessing/PREPROC_V1.lock.json": hash_file(
                root / "manifests/preprocessing/PREPROC_V1.lock.json"
            ),
            str(WINDOW_MANIFEST): hash_file(root / WINDOW_MANIFEST),
        },
        "prediction_artifact": {
            "path": str(prediction_path.relative_to(root)),
            "sha256": hash_file(prediction_path),
        },
        "no_post_test_tuning": True,
        "claim_boundary": (
            "Patient-disjoint MIT-BIH internal-test performance for the frozen "
            "AAMI_SVF_WINDOW_V1 research target; not clinical, wearable, or external evidence."
        ),
        "change_control": (
            "Post-G10 changes to MODEL_V1, CAL_V1, predictions, metrics, or bootstrap method "
            "require a controlled scientific change; later error analysis may not retune them."
        ),
    }
    report_path = root / "reports/internal_test.json"
    _write_json(report_path, report)
    completed = {
        **guard,
        "status": "COMPLETED",
        "eligible_windows_read": len(population.rows),
        "patients_read": len(set(patients.tolist())),
        "model_inference_passes": 1,
        "accessed_paths": list(population.accessed_paths),
        "result_sha256": {
            str(prediction_path.relative_to(root)): hash_file(prediction_path),
            str(metric_path.relative_to(root)): hash_file(metric_path),
            str(replicate_path.relative_to(root)): hash_file(replicate_path),
            "reports/t018/bootstrap_summary.json": hash_file(
                root / "reports/t018/bootstrap_summary.json"
            ),
            str(report_path.relative_to(root)): hash_file(report_path),
        },
    }
    _write_json(root / GUARD_PATH, completed)
    _write_json(root / "reports/t018/one_shot_access_audit.json", {
        "evaluation_id": EVALUATION_ID,
        "guard_status": "COMPLETED",
        "first_access_event": "guard RUN_STARTED written before any waveform cache open",
        "run_completed": True,
        "eligible_windows_read": len(population.rows),
        "patients_read": len(set(patients.tolist())),
        "MODEL_V1_inference_passes": 1,
        "prediction_artifact_sha256": hash_file(prediction_path),
        "second_run_attempt_blocked": True,
        "post_test_tuning": False,
    })
    return report


def _read_predictions(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rows = _csv_rows(path)
    return (
        np.asarray([row["participant_group_id"] for row in rows], dtype=str),
        np.asarray([int(row["label"]) for row in rows], dtype=np.int64),
        np.asarray([float(row["source_domain_calibrated_probability"]) for row in rows]),
        np.asarray([int(row["thresholded_prediction"]) for row in rows], dtype=np.int64),
    )


def verify_internal_test_freeze(root: Path = ROOT) -> dict[str, Any]:
    verify_frozen_model_v1(root)
    verify_cal_v1(root)
    guard = _json(root / GUARD_PATH)
    report = _json(root / "reports/internal_test.json")
    if guard.get("status") != "COMPLETED" or report.get("status") != "FROZEN":
        raise InternalTestError("INTERNAL_TEST_FREEZE_NOT_COMPLETED")
    if report.get("freeze_id") != "F10" or report.get("evaluation_id") != EVALUATION_ID:
        raise InternalTestError("INTERNAL_TEST_FREEZE_IDENTITY_MISMATCH")
    for relative, expected in guard["result_sha256"].items():
        if hash_file(root / relative) != expected:
            raise InternalTestError(f"INTERNAL_TEST_RESULT_HASH_MISMATCH: {relative}")
    audit = _json(root / "reports/t018/pre_access_audit.json")
    for relative, expected in audit["method_artifact_sha256"].items():
        if hash_file(root / relative) != expected:
            raise InternalTestError(f"POST_TEST_METHOD_MUTATION: {relative}")
    patients, labels, probabilities, predictions = _read_predictions(
        root / "reports/internal_test_predictions.csv"
    )
    point = pooled_binary_metrics(labels, probabilities, predictions, patients)
    for name in METRIC_NAMES:
        if not np.isclose(point[name], report["point_metrics"][name], atol=0.0, rtol=1e-14):
            raise InternalTestError(f"INTERNAL_TEST_POINT_METRIC_MISMATCH: {name}")
    return {
        "status": "PASS",
        "freeze_id": "F10",
        "evaluation_id": EVALUATION_ID,
        "report_sha256": hash_file(root / "reports/internal_test.json"),
        "prediction_sha256": hash_file(root / "reports/internal_test_predictions.csv"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run-once", action="store_true")
    action.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    result = (
        run_internal_test_once(ROOT)
        if arguments.run_once
        else verify_internal_test_freeze(ROOT)
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
