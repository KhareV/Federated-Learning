"""One-shot frozen MODEL_V1 evaluation on official INCART v1.0.0 exact Lead II."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import torch
import wfdb
import yaml

from datasets.incart import (
    DATASET_ID,
    DATASET_VERSION,
    DEFAULT_RAW_ROOT,
    EXPECTED_FS_HZ,
    LEAD_POLICY_ID,
    REQUIRED_LEAD_NAME,
    inspect_record,
    list_records,
    load_annotations,
)
from datasets.labels import MAP_ID, NOT_A_BEAT, TARGET_ID, map_annotation_symbol
from evaluation.bootstrap import bootstrap_replicates, percentile_summary
from evaluation.calibration import (
    apply_operating_threshold,
    load_cal_v1,
    raw_probability_from_logit,
    source_domain_calibrated_probability,
    verify_cal_v1,
)
from evaluation.internal_test import verify_internal_test_freeze
from evaluation.metrics import METRIC_NAMES, pooled_binary_metrics
from models.model_freeze import load_frozen_model_v1, verify_frozen_model_v1
from nhm.hashing import hash_file
from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.quality import evaluate_ecg_quality
from preprocessing.windowing import (
    NORMALIZATION_EPSILON,
    PREPROC_ID,
    SAMPLE_RATE_HZ,
    WINDOW_SAMPLES,
    candidate_window_starts,
    create_window_record,
    normalize_window_zscore,
    select_annotation_indices_closed,
    summarize_annotations,
)
from scripts.generate_model_v1_test_vector_t016 import write_deterministic_npz

ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ID = "EXTERNAL_INCART_V1"
FREEZE_ID = "F11"
PARTITION = "EXTERNAL_INCART"
RESAMPLER_ID = "INCART_257_TO_250_V1"
CONFIG_PATH = Path("configs/external_incart_v1.yaml")
GUARD_PATH = Path("artifacts/external_incart_access_v1.json")
WINDOW_MANIFEST_PATH = Path("manifests/windows/INCART_EXTERNAL_WINDOWS_V1.csv")
PREDICTION_PATH = Path("reports/external_incart_predictions.csv")
PATIENT_MAP_PATH = Path("manifests/datasets/incart_patient_map.csv")


class ExternalIncartError(RuntimeError):
    """Raised for one-shot, scope, source, or frozen-contract violations."""


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


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    temporary.replace(path)


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def load_patient_map(root: Path = ROOT) -> dict[str, str]:
    rows = _csv_rows(root / PATIENT_MAP_PATH)
    result: dict[str, str] = {}
    for row in rows:
        record = row["record_id"]
        participant = f"INCART_PATIENT_{int(row['source_patient_id']):02d}"
        if record in result:
            raise ExternalIncartError("INCART_PATIENT_MAP_DUPLICATE_RECORD")
        result[record] = participant
    if len(result) != 75 or len(set(result.values())) != 32:
        raise ExternalIncartError("INCART_PATIENT_MAP_CLOSURE_FAILURE")
    return result


def verify_source_contract(root: Path = ROOT) -> dict[str, Any]:
    validation = _json(root / "reports/t007/incart_validation.json")
    lead = _json(root / "reports/t007/incart_lead_policy_audit.json")
    records = list_records(root / DEFAULT_RAW_ROOT)
    patient_map = load_patient_map(root)
    if validation.get("overall_status") != "PASS" or not validation.get("hashes_verified"):
        raise ExternalIncartError("INCART_SOURCE_VALIDATION_FAILURE")
    if len(records) != 75 or set(records) != set(patient_map):
        raise ExternalIncartError("INCART_SOURCE_RECORD_CLOSURE_FAILURE")
    if lead.get("eligible_count") != 75 or lead.get("excluded_count") != 0:
        raise ExternalIncartError("INCART_LEAD_POLICY_MISMATCH")
    if lead.get("required_value") != "II" or lead.get("fallback_allowed"):
        raise ExternalIncartError("INCART_LEAD_POLICY_MISMATCH")
    for record_id in records:
        selection = inspect_record(record_id, root / DEFAULT_RAW_ROOT)
        if (
            not selection.eligible
            or selection.ii_channel_index is None
            or selection.all_signal_names[selection.ii_channel_index] != REQUIRED_LEAD_NAME
        ):
            raise ExternalIncartError("INCART_LEAD_POLICY_MISMATCH")
    return {
        "status": "PASS",
        "dataset": "St Petersburg INCART 12-lead Arrhythmia Database",
        "version": DATASET_VERSION,
        "records": len(records),
        "patient_groups": len(set(patient_map.values())),
        "lead_eligible_records": 75,
        "lead_exclusions": 0,
        "fallback_used": False,
        "sampling_rate_hz": EXPECTED_FS_HZ,
        "provider_hashes": "PASS",
        "annotation_validation": "PASS",
    }


def validate_method_config(root: Path = ROOT) -> dict[str, Any]:
    config = yaml.safe_load((root / CONFIG_PATH).read_text(encoding="utf-8"))
    required = {
        "evaluation_id": EVALUATION_ID,
        "one_shot": True,
        "adaptation": False,
    }
    if any(config.get(key) != value for key, value in required.items()):
        raise ExternalIncartError("EXTERNAL_METHOD_CONFIG_IDENTITY_MISMATCH")
    if config["signal"] != {
        "required_lead_name": "II",
        "lead_policy_id": LEAD_POLICY_ID,
        "fallback": "NONE",
        "source_rate_hz": 257,
        "target_rate_hz": 250,
        "resampler_id": RESAMPLER_ID,
        "preproc_id": PREPROC_ID,
    }:
        raise ExternalIncartError("EXTERNAL_SIGNAL_CONTRACT_MISMATCH")
    bootstrap = config["bootstrap"]
    if (
        bootstrap["unit"] != "participant_group_id"
        or bootstrap["replicates"] != 2000
        or bootstrap["seed"] != 20260927
        or bootstrap["window_bootstrap"]
        or bootstrap["record_bootstrap"]
        or bootstrap["redraw_degenerate_replicates"]
    ):
        raise ExternalIncartError("EXTERNAL_BOOTSTRAP_CONTRACT_MISMATCH")
    return config


def guard_status(root: Path = ROOT) -> str:
    path = root / GUARD_PATH
    if not path.exists():
        return "NOT_STARTED"
    return str(_json(path).get("status"))


def assert_external_not_consumed(root: Path = ROOT) -> None:
    status = guard_status(root)
    if status == "COMPLETED":
        raise ExternalIncartError("EXTERNAL_INCART_ALREADY_CONSUMED")
    if status != "NOT_STARTED":
        raise ExternalIncartError("EXTERNAL_EVALUATION_INTERRUPTED")


def verify_clean_pre_access_state(root: Path, audit: dict[str, Any]) -> None:
    if _git(root, "status", "--porcelain"):
        raise ExternalIncartError("PRE_ACCESS_WORKTREE_NOT_CLEAN")
    commit = str(audit["pre_access_method_commit"])
    if subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=root).returncode:
        raise ExternalIncartError("PRE_ACCESS_METHOD_COMMIT_NOT_ANCESTOR")
    for relative, expected in audit["method_artifact_sha256"].items():
        if hash_file(root / relative) != expected:
            raise ExternalIncartError(f"POST_EXTERNAL_METHOD_MUTATION: {relative}")


def create_run_started_guard(root: Path, audit: dict[str, Any]) -> dict[str, Any]:
    assert_external_not_consumed(root)
    guard = {
        "evaluation_id": EVALUATION_ID,
        "status": "RUN_STARTED",
        "pre_access_git_sha": _git(root, "rev-parse", "HEAD"),
        "pre_access_method_commit": audit["pre_access_method_commit"],
        "method_config_sha256": hash_file(root / CONFIG_PATH),
        "external_evaluator_sha256": hash_file(root / "evaluation/external_incart.py"),
        "incart_dataset_manifest_sha256": hash_file(
            root / "manifests/datasets/incart_v1.yaml"
        ),
        "lead_manifest_sha256": hash_file(
            root / "manifests/datasets/incart_lead_ii_records.csv"
        ),
        "patient_map_sha256": hash_file(root / PATIENT_MAP_PATH),
        "MODEL_V1_sha256": hash_file(root / "checkpoints/MODEL_V1.pt"),
        "CAL_V1_sha256": hash_file(root / "artifacts/CAL_V1.json"),
        "PREPROC_V1_lock_sha256": hash_file(
            root / "manifests/preprocessing/PREPROC_V1.lock.json"
        ),
        "map_id": MAP_ID,
    }
    path = root / GUARD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(guard, indent=2, sort_keys=True) + "\n")
    return guard


def _stream_preprocess(signal: np.ndarray, chunk_size: int = 4096) -> np.ndarray:
    pipeline = ECGPreprocessingPipeline(EXPECTED_FS_HZ, RESAMPLER_ID)
    values: list[np.ndarray] = []
    for start in range(0, signal.size, chunk_size):
        stop = min(start + chunk_size, signal.size)
        output = pipeline.process(
            signal[start:stop],
            np.arange(start, stop, dtype=np.int64),
            source_timestamps_us=(
                np.arange(start, stop, dtype=np.int64) * 1_000_000 // EXPECTED_FS_HZ
                if start == 0
                else None
            ),
        )
        if output.events:
            raise ExternalIncartError("INCART_UNEXPECTED_SOURCE_GAP")
        values.extend(chunk.filtered_values for chunk in output.chunks)
    return np.concatenate(values) if values else np.empty(0, dtype=np.float64)


def _load_exact_lead_signal(record_id: str, root: Path) -> np.ndarray:
    selection = inspect_record(record_id, root / DEFAULT_RAW_ROOT)
    if not selection.eligible or selection.ii_channel_index is None:
        raise ExternalIncartError("INCART_LEAD_POLICY_MISMATCH")
    record = wfdb.rdrecord(
        str(root / DEFAULT_RAW_ROOT / record_id),
        channels=[selection.ii_channel_index],
        physical=True,
    )
    signal = np.asarray(record.p_signal[:, 0], dtype=np.float64)
    if not np.all(np.isfinite(signal)):
        raise ExternalIncartError("INCART_NONFINITE_SOURCE_SIGNAL")
    return signal


def _record_windows(
    record_id: str,
    participant_group_id: str,
    root: Path,
) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    signal = _load_exact_lead_signal(record_id, root)
    filtered = _stream_preprocess(signal)
    annotations = load_annotations(record_id, root / DEFAULT_RAW_ROOT)
    samples = np.asarray(annotations.sample, dtype=np.int64)
    symbols = np.asarray(annotations.symbol, dtype=object)
    rows: list[dict[str, Any]] = []
    eligible: list[np.ndarray] = []
    for start in candidate_window_starts(filtered.size):
        end = start + WINDOW_SAMPLES
        prediction_us = end * 1_000_000 // SAMPLE_RATE_HZ
        selected = select_annotation_indices_closed(samples, EXPECTED_FS_HZ, prediction_us)
        selected_symbols = [str(symbol) for symbol in symbols[selected].tolist()]
        for symbol in selected_symbols:
            mapped = map_annotation_symbol(symbol)
            if mapped.mapped_class == NOT_A_BEAT:
                continue
        summary = summarize_annotations(selected_symbols)
        waveform = np.ascontiguousarray(filtered[start:end], dtype=np.float64)
        quality = evaluate_ecg_quality(waveform)
        record = create_window_record(
            dataset_id=DATASET_ID,
            record_id=record_id,
            participant_group_id=participant_group_id,
            partition=PARTITION,
            segment_id=0,
            canonical_start_index=start,
            segment_start_timestamp_us=0,
            quality=quality,
            annotations=summary,
        )
        row = record.as_manifest_dict()
        row.update(
            {
                "source_patient_id": participant_group_id.removeprefix("INCART_PATIENT_"),
                "source_right_edge_sample": prediction_us * EXPECTED_FS_HZ // 1_000_000,
                "lead_name": REQUIRED_LEAD_NAME,
                "source_sample_rate_hz": EXPECTED_FS_HZ,
                "target_sample_rate_hz": SAMPLE_RATE_HZ,
                "mappable_beat_count": summary.mappable_beat_count,
                "svf_beat_count": summary.svf_beat_count,
                "split_id": "NOT_APPLICABLE_EXTERNAL_FULL_DATASET",
            }
        )
        rows.append(row)
        if record.core_eligible:
            eligible.append(waveform)
    return rows, eligible


def _infer_windows(
    model: torch.nn.Module,
    waveforms: list[np.ndarray],
    batch_size: int,
) -> np.ndarray:
    if not waveforms:
        return np.empty(0, dtype=np.float64)
    output: list[np.ndarray] = []
    for start in range(0, len(waveforms), batch_size):
        normalized = np.stack(
            [
                normalize_window_zscore(values, epsilon=NORMALIZATION_EPSILON)
                for values in waveforms[start : start + batch_size]
            ]
        ).astype(np.float32)
        batch = torch.from_numpy(normalized[:, None, :])
        output.append(model(batch).cpu().numpy()[:, 0])
    return np.concatenate(output).astype(np.float64)


WINDOW_FIELDS = [
    "example_id", "dataset_id", "record_id", "participant_group_id", "source_patient_id",
    "partition", "segment_id", "source_right_edge_sample", "prediction_timestamp_us",
    "signal_start_timestamp_us", "signal_end_exclusive_timestamp_us",
    "canonical_start_index", "canonical_end_index_exclusive", "window_samples",
    "sample_rate_hz", "lead_name", "source_sample_rate_hz", "target_sample_rate_hz",
    "ecg_quality", "quality_reasons", "label", "label_status", "exclusion_reasons",
    "core_eligible", "mapped_n_count", "mapped_s_count", "mapped_v_count",
    "mapped_f_count", "q_count", "unmappable_count", "mappable_beat_count",
    "svf_beat_count", "preprocess_id", "windowing_id", "map_id", "target_id", "split_id",
]

PREDICTION_FIELDS = [
    "example_id", "participant_group_id", "source_patient_id", "record_id",
    "prediction_timestamp_us", "quality", "label", "raw_logit", "raw_probability",
    "source_domain_calibrated_probability", "calibration_domain", "threshold",
    "thresholded_prediction", "model_id", "model_sha", "calibration_id",
    "calibration_sha", "preproc_id", "map_id", "target_id",
]


def _format_prediction_row(
    row: dict[str, Any], logit: float, raw: float, calibrated: float, prediction: int,
    cal: dict[str, Any], cal_sha: str,
) -> dict[str, Any]:
    return {
        "example_id": row["example_id"],
        "participant_group_id": row["participant_group_id"],
        "source_patient_id": row["source_patient_id"],
        "record_id": row["record_id"],
        "prediction_timestamp_us": row["prediction_timestamp_us"],
        "quality": row["ecg_quality"],
        "label": row["label"],
        "raw_logit": format(float(logit), ".17g"),
        "raw_probability": format(float(raw), ".17g"),
        "source_domain_calibrated_probability": format(float(calibrated), ".17g"),
        "calibration_domain": cal["calibration_domain"],
        "threshold": format(float(cal["threshold"]), ".17g"),
        "thresholded_prediction": int(prediction),
        "model_id": "MODEL_V1",
        "model_sha": cal["model_checkpoint_sha256"],
        "calibration_id": "CAL_V1",
        "calibration_sha": cal_sha,
        "preproc_id": PREPROC_ID,
        "map_id": MAP_ID,
        "target_id": TARGET_ID,
    }


def _prediction_arrays(
    path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict[str, str]]]:
    rows = _csv_rows(path)
    return (
        np.asarray([row["participant_group_id"] for row in rows], dtype=str),
        np.asarray([int(row["label"]) for row in rows], dtype=np.int64),
        np.asarray([float(row["source_domain_calibrated_probability"]) for row in rows]),
        np.asarray([int(row["thresholded_prediction"]) for row in rows], dtype=np.int64),
        rows,
    )


def _write_bootstrap_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["replicate_index", "sampled_patient_slots", "unique_patient_count", *METRIC_NAMES]
    _write_csv(
        path,
        [{key: "" if row[key] is None else row[key] for key in fields} for row in rows],
        fields,
    )


def _write_metric_csv(
    path: Path,
    summary: dict[str, dict[str, Any]],
    patient_count: int,
    record_count: int,
    window_count: int,
) -> None:
    fields = [
        "metric", "point_estimate", "ci_lower_95", "ci_upper_95",
        "valid_bootstrap_replicates", "invalid_bootstrap_replicates",
        "patient_cluster_count", "record_count", "window_count",
    ]
    rows = []
    for name in METRIC_NAMES:
        result = summary[name]
        rows.append(
            {
                "metric": name,
                "point_estimate": format(result["point_estimate"], ".17g"),
                "ci_lower_95": format(result["ci_lower_95"], ".17g"),
                "ci_upper_95": format(result["ci_upper_95"], ".17g"),
                "valid_bootstrap_replicates": result["valid_replicates"],
                "invalid_bootstrap_replicates": result["invalid_replicates"],
                "patient_cluster_count": patient_count,
                "record_count": record_count,
                "window_count": window_count,
            }
        )
    _write_csv(path, rows, fields)


def _exclusion_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    reasons = [set(str(row["exclusion_reasons"]).split(";")) for row in rows]
    return {
        "Q_or_paced": sum("EXCLUDE_Q" in value for value in reasons),
        "UNMAPPABLE": sum("EXCLUDE_UNMAPPABLE" in value for value in reasons),
        "LT5_MAPPABLE_BEATS": sum("EXCLUDE_LT5_MAPPABLE_BEATS" in value for value in reasons),
        "UNUSABLE_QUALITY": sum("EXCLUDE_UNUSABLE_QUALITY" in value for value in reasons),
    }


def run_external_once(root: Path = ROOT) -> dict[str, Any]:
    audit = _json(root / "reports/t020/pre_access_audit.json")
    verify_clean_pre_access_state(root, audit)
    verify_frozen_model_v1(root)
    verify_cal_v1(root)
    verify_internal_test_freeze(root)
    source = verify_source_contract(root)
    config = validate_method_config(root)
    guard = create_run_started_guard(root, audit)

    patient_map = load_patient_map(root)
    cal = load_cal_v1(root)
    cal_sha = hash_file(root / "artifacts/CAL_V1.json")
    model, _ = load_frozen_model_v1(root)
    model.eval()
    model_before = copy.deepcopy(model.state_dict())
    manifest_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    accessed_paths: list[str] = []
    batch_size = int(config["model"]["batch_size"])
    with torch.inference_mode():
        for record_id in sorted(patient_map):
            rows, waveforms = _record_windows(record_id, patient_map[record_id], root)
            accessed_paths.extend(
                [
                    str(DEFAULT_RAW_ROOT / f"{record_id}.hea"),
                    str(DEFAULT_RAW_ROOT / f"{record_id}.dat"),
                    str(DEFAULT_RAW_ROOT / f"{record_id}.atr"),
                ]
            )
            eligible_rows = [row for row in rows if row["core_eligible"] == "TRUE"]
            logits = _infer_windows(model, waveforms, batch_size)
            if len(eligible_rows) != len(logits):
                raise ExternalIncartError("INCART_ELIGIBLE_WAVEFORM_CLOSURE_FAILURE")
            raw = raw_probability_from_logit(logits)
            calibrated = source_domain_calibrated_probability(logits, cal)
            predicted = apply_operating_threshold(calibrated, cal)
            prediction_rows.extend(
                _format_prediction_row(row, logit, raw_p, cal_p, int(pred), cal, cal_sha)
                for row, logit, raw_p, cal_p, pred in zip(
                    eligible_rows, logits, raw, calibrated, predicted, strict=True
                )
            )
            manifest_rows.extend(rows)
    if any(not torch.equal(model_before[key], model.state_dict()[key]) for key in model_before):
        raise ExternalIncartError("MODEL_V1_STATE_MUTATED_DURING_EXTERNAL_EVALUATION")

    manifest_rows.sort(key=lambda row: row["example_id"])
    prediction_rows.sort(key=lambda row: row["example_id"])
    _write_csv(root / WINDOW_MANIFEST_PATH, manifest_rows, WINDOW_FIELDS)
    _write_csv(root / PREDICTION_PATH, prediction_rows, PREDICTION_FIELDS)
    eligible_ids = {row["example_id"] for row in manifest_rows if row["core_eligible"] == "TRUE"}
    prediction_ids = [row["example_id"] for row in prediction_rows]
    if set(prediction_ids) != eligible_ids or len(prediction_ids) != len(set(prediction_ids)):
        raise ExternalIncartError("INCART_PREDICTION_CLOSURE_FAILURE")

    patients, labels, probabilities, predictions, prediction_source = _prediction_arrays(
        root / PREDICTION_PATH
    )
    if set(np.unique(labels).tolist()) != {0, 1}:
        raise ExternalIncartError("INCART_EXTERNAL_CLASS_DEGENERACY")
    point = pooled_binary_metrics(labels, probabilities, predictions, patients)
    bootstrap = config["bootstrap"]
    draws, replicate_rows = bootstrap_replicates(
        patients,
        labels,
        probabilities,
        predictions,
        replicates=int(bootstrap["replicates"]),
        seed=int(bootstrap["seed"]),
    )
    report_dir = root / "reports/t020"
    report_dir.mkdir(parents=True, exist_ok=True)
    draws_path = report_dir / "bootstrap_draws.npz"
    write_deterministic_npz(
        draws_path,
        {
            "draws_int64": draws,
            "patient_ids_utf8": np.asarray(sorted(set(patients.tolist())), dtype="S32"),
        },
    )
    replicate_path = report_dir / "bootstrap_replicates.csv"
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
        "multi_record_patient_clusters_preserved": True,
        "window_bootstrap_used": False,
        "record_bootstrap_used": False,
        "rejection_or_redraw_used": False,
        "unique_patient_count": {
            "minimum": int(unique_counts.min()),
            "median": float(np.median(unique_counts)),
            "maximum": int(unique_counts.max()),
        },
        "ci_type": "PERCENTILE_95_V1",
        "quantiles": [0.025, 0.975],
        "quantile_method": "linear",
        "point_estimate_source": "ORIGINAL_EXTERNAL_SAMPLE_NOT_BOOTSTRAP_MEAN",
        "metrics": summary,
    }
    _write_json(report_dir / "bootstrap_summary.json", bootstrap_report)
    contributing_patients = len(set(patients.tolist()))
    contributing_records = len({row["record_id"] for row in prediction_source})
    metric_path = root / "reports/external_incart_metrics.csv"
    _write_metric_csv(
        metric_path, summary, contributing_patients, contributing_records, len(prediction_rows)
    )

    quality_candidate = Counter(str(row["ecg_quality"]) for row in manifest_rows)
    quality_eligible = Counter(
        str(row["ecg_quality"])
        for row in manifest_rows
        if row["core_eligible"] == "TRUE"
    )
    exclusions = _exclusion_counts(manifest_rows)
    source_patients = len(set(patient_map.values()))
    window_audit = {
        "artifact_id": "INCART_EXTERNAL_WINDOWS_V1",
        "candidate_windows": len(manifest_rows),
        "eligible_windows": len(prediction_rows),
        "positive_windows": int(np.sum(labels == 1)),
        "negative_windows": int(np.sum(labels == 0)),
        "exclusion_counts": exclusions,
        "candidate_quality_counts": dict(sorted(quality_candidate.items())),
        "eligible_quality_counts": dict(sorted(quality_eligible.items())),
        "prediction_closure": {
            "duplicates": len(prediction_ids) - len(set(prediction_ids)),
            "missing": len(eligible_ids - set(prediction_ids)),
            "extras": len(set(prediction_ids) - eligible_ids),
        },
        "overall_status": "PASS",
    }
    _write_json(report_dir / "incart_window_audit.json", window_audit)
    record_counts = Counter(patient_map.values())
    patient_audit = {
        "records_mapped": len(patient_map),
        "unique_source_patients": source_patients,
        "unmapped_records": 0,
        "multiply_mapped_records": 0,
        "patients_with_multiple_records": sum(count > 1 for count in record_counts.values()),
        "all_records_of_patient_share_participant_group_id": True,
        "eligible_contributor_patients": contributing_patients,
        "zero_eligible_window_patients": source_patients - contributing_patients,
        "overall_status": "PASS",
    }
    _write_json(report_dir / "patient_group_audit.json", patient_audit)
    _write_json(report_dir / "lead_policy_audit.json", {**source, "policy_id": LEAD_POLICY_ID})

    report = {
        "evaluation_id": EVALUATION_ID,
        "status": "FROZEN",
        "freeze_id": FREEZE_ID,
        "version_id": "INCART_EXT_V1",
        "one_shot": True,
        "access_guard": {"path": str(GUARD_PATH), "status": "COMPLETED"},
        "dataset": "St Petersburg INCART 12-lead Arrhythmia Database",
        "dataset_version": DATASET_VERSION,
        "source_patient_count": source_patients,
        "contributing_patient_count": contributing_patients,
        "record_count": len(patient_map),
        "contributing_record_count": contributing_records,
        "candidate_windows": len(manifest_rows),
        "eligible_windows": len(prediction_rows),
        "positive_windows": int(np.sum(labels == 1)),
        "negative_windows": int(np.sum(labels == 0)),
        "exclusion_counts": exclusions,
        "quality_counts": {
            "candidate": dict(sorted(quality_candidate.items())),
            "eligible": dict(sorted(quality_eligible.items())),
        },
        "lead_policy": {"id": LEAD_POLICY_ID, "lead": "II", "fallback": "NONE"},
        "map_id": MAP_ID,
        "target_id": TARGET_ID,
        "preproc_id": PREPROC_ID,
        "resampler_id": RESAMPLER_ID,
        "model_id": "MODEL_V1",
        "model_sha256": hash_file(root / "checkpoints/MODEL_V1.pt"),
        "calibration_id": "CAL_V1",
        "calibration_sha256": cal_sha,
        "temperature": float(cal["temperature"]),
        "threshold": float(cal["threshold"]),
        "threshold_comparator": ">=",
        "calibration_domain": cal["calibration_domain"],
        "INCART_calibration_claim": False,
        "point_metrics": {name: point[name] for name in METRIC_NAMES},
        "confusion_matrix": point["confusion_matrix"],
        "bootstrap": bootstrap_report,
        "pre_access_method_commit": audit["pre_access_method_commit"],
        "method_config_sha256": hash_file(root / CONFIG_PATH),
        "external_evaluator_sha256": hash_file(root / "evaluation/external_incart.py"),
        "artifacts": {
            "window_manifest": {
                "path": str(WINDOW_MANIFEST_PATH),
                "sha256": hash_file(root / WINDOW_MANIFEST_PATH),
            },
            "predictions": {
                "path": str(PREDICTION_PATH),
                "sha256": hash_file(root / PREDICTION_PATH),
            },
            "metrics": {
                "path": "reports/external_incart_metrics.csv",
                "sha256": hash_file(metric_path),
            },
            "bootstrap_summary": {
                "path": "reports/t020/bootstrap_summary.json",
                "sha256": hash_file(report_dir / "bootstrap_summary.json"),
            },
        },
        "upstream_sha256": {
            "MODEL_V1": hash_file(root / "checkpoints/MODEL_V1.pt"),
            "CAL_V1": cal_sha,
            "PREPROC_V1": hash_file(root / "manifests/preprocessing/PREPROC_V1.lock.json"),
            "AAMI_SVF_MAP_V1": hash_file(root / "manifests/labels/AAMI_SVF_MAP_V1.yaml"),
            "INCART_manifest": hash_file(root / "manifests/datasets/incart_v1.yaml"),
            "INCART_lead_manifest": hash_file(
                root / "manifests/datasets/incart_lead_ii_records.csv"
            ),
            "INCART_patient_map": hash_file(root / PATIENT_MAP_PATH),
        },
        "no_adaptation": True,
        "no_post_result_tuning": True,
        "claim_boundary": config["claim_boundary"],
        "overall_status": "PASS",
    }
    report_path = root / "reports/external_incart.json"
    _write_json(report_path, report)
    completed = {
        **guard,
        "status": "COMPLETED",
        "records_processed": len(patient_map),
        "patients_represented": contributing_patients,
        "eligible_windows": len(prediction_rows),
        "MODEL_V1_external_inference_passes": 1,
        "accessed_paths": accessed_paths,
        "result_sha256": {
            str(WINDOW_MANIFEST_PATH): hash_file(root / WINDOW_MANIFEST_PATH),
            str(PREDICTION_PATH): hash_file(root / PREDICTION_PATH),
            "reports/external_incart_metrics.csv": hash_file(metric_path),
            "reports/t020/bootstrap_draws.npz": hash_file(draws_path),
            "reports/t020/bootstrap_replicates.csv": hash_file(replicate_path),
            "reports/t020/bootstrap_summary.json": hash_file(
                report_dir / "bootstrap_summary.json"
            ),
            "reports/external_incart.json": hash_file(report_path),
        },
    }
    _write_json(root / GUARD_PATH, completed)
    _write_json(
        report_dir / "one_shot_access_audit.json",
        {
            "evaluation_id": EVALUATION_ID,
            "guard_initial_state": "NOT_STARTED",
            "guard_final_state": "COMPLETED",
            "real_external_waveform_access": True,
            "MODEL_V1_external_inference_passes": 1,
            "records_processed": len(patient_map),
            "patients_represented": contributing_patients,
            "eligible_windows": len(prediction_rows),
            "prediction_sha256": hash_file(root / PREDICTION_PATH),
            "second_run_attempt_blocked": True,
            "post_exposure_scientific_edits": False,
            "adaptation": False,
            "overall_status": "PASS",
        },
    )
    return report


def verify_external_freeze(root: Path = ROOT) -> dict[str, Any]:
    verify_frozen_model_v1(root)
    verify_cal_v1(root)
    verify_internal_test_freeze(root)
    guard = _json(root / GUARD_PATH)
    report = _json(root / "reports/external_incart.json")
    if guard.get("status") != "COMPLETED" or report.get("status") != "FROZEN":
        raise ExternalIncartError("EXTERNAL_FREEZE_NOT_COMPLETED")
    if report.get("freeze_id") != FREEZE_ID or report.get("evaluation_id") != EVALUATION_ID:
        raise ExternalIncartError("EXTERNAL_FREEZE_IDENTITY_MISMATCH")
    for relative, expected in guard["result_sha256"].items():
        if hash_file(root / relative) != expected:
            raise ExternalIncartError(f"EXTERNAL_RESULT_HASH_MISMATCH: {relative}")
    audit = _json(root / "reports/t020/pre_access_audit.json")
    for relative, expected in audit["method_artifact_sha256"].items():
        if hash_file(root / relative) != expected:
            raise ExternalIncartError(f"POST_EXTERNAL_METHOD_MUTATION: {relative}")
    manifest = _csv_rows(root / WINDOW_MANIFEST_PATH)
    eligible = {row["example_id"] for row in manifest if row["core_eligible"] == "TRUE"}
    patients, labels, probabilities, predictions, rows = _prediction_arrays(
        root / PREDICTION_PATH
    )
    identifiers = [row["example_id"] for row in rows]
    if set(identifiers) != eligible or len(identifiers) != len(set(identifiers)):
        raise ExternalIncartError("INCART_PREDICTION_CLOSURE_FAILURE")
    point = pooled_binary_metrics(labels, probabilities, predictions, patients)
    for name in METRIC_NAMES:
        if not np.isclose(point[name], report["point_metrics"][name], atol=0.0, rtol=1e-14):
            raise ExternalIncartError(f"EXTERNAL_POINT_METRIC_MISMATCH: {name}")
    return {
        "status": "PASS",
        "freeze_id": FREEZE_ID,
        "evaluation_id": EVALUATION_ID,
        "report_sha256": hash_file(root / "reports/external_incart.json"),
        "prediction_sha256": hash_file(root / PREDICTION_PATH),
        "model_inference_repeated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--run-once", action="store_true")
    action.add_argument("--verify", action="store_true")
    action.add_argument("--guard-check", action="store_true")
    arguments = parser.parse_args()
    if arguments.guard_check:
        assert_external_not_consumed(ROOT)
        result: dict[str, Any] = {"status": "AVAILABLE"}
    elif arguments.run_once:
        result = run_external_once(ROOT)
    else:
        result = verify_external_freeze(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
