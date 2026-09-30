"""C021-HR-A TRAIN/VALIDATION-only candidate evaluation and deterministic selection."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from datasets.labels import BEAT_SYMBOLS
from datasets.mitdb import DEFAULT_RAW_ROOT, load_annotations, load_mlii
from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.ecg_hr_context import (
    COMPARISON_CANDIDATES,
    ELIGIBLE_CANDIDATES,
    HISTORICAL_ID,
    INPUT_RATE_HZ,
    LOOKBACK_SECONDS,
    MIN_VALID_INTERVALS,
    RR_MAX_SECONDS,
    RR_MIN_SECONDS,
    estimate_hr_at,
)

ROOT = Path(__file__).resolve().parents[1]
SPLIT_PATH = ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"
CONFIG_PATH = ROOT / "configs/ecg_hr_context_v2.yaml"
ALLOWED_PARTITIONS = ("TRAIN", "VALIDATION")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def records_for_partition(partition: str, root: Path = ROOT) -> list[dict[str, str]]:
    if partition not in ALLOWED_PARTITIONS:
        raise ValueError(f"ECG_HR_V2_SCOPE_VIOLATION: forbidden partition {partition}")
    return [
        row
        for row in _read_csv(root / SPLIT_PATH.relative_to(ROOT))
        if row["partition"] == partition
    ]


def reference_hr_at(
    annotation_samples: np.ndarray,
    annotation_symbols: list[str] | tuple[str, ...],
    *,
    timestamp_seconds: int,
    source_fs: int = 360,
) -> float | None:
    """Causal all-genuine-beat reference over [t-10s,t], excluding non-beat annotations."""
    beat_times = np.asarray(
        [
            sample / source_fs
            for sample, symbol in zip(annotation_samples, annotation_symbols, strict=True)
            if symbol in BEAT_SYMBOLS
        ],
        dtype=np.float64,
    )
    selected = beat_times[
        (beat_times >= timestamp_seconds - LOOKBACK_SECONDS) & (beat_times <= timestamp_seconds)
    ]
    intervals = np.diff(selected)
    valid = intervals[(intervals >= RR_MIN_SECONDS) & (intervals <= RR_MAX_SECONDS)]
    if valid.size < MIN_VALID_INTERVALS:
        return None
    return float(60.0 / np.median(valid))


def preprocess_record(record_id: str, root: Path = ROOT) -> np.ndarray:
    signal = load_mlii(record_id, root / DEFAULT_RAW_ROOT)
    indices = np.arange(signal.size, dtype=np.int64)
    timestamps = indices * 1_000_000 // 360
    pipeline = ECGPreprocessingPipeline(360, "MITDB_360_TO_250_V1")
    output = pipeline.process(signal, indices, source_timestamps_us=timestamps)
    return np.concatenate([chunk.filtered_values for chunk in output.chunks])


def _error_metrics(
    rows: list[dict[str, Any]], reference_count: int, patient_reference: dict[str, int]
) -> dict[str, Any]:
    errors = np.asarray([row["derived_hr_bpm"] - row["reference_hr_bpm"] for row in rows])
    absolute = np.abs(errors)
    by_patient: dict[str, list[float]] = defaultdict(list)
    for row, error in zip(rows, absolute.tolist(), strict=True):
        by_patient[row["participant_group_id"]].append(error)
    patient_maes = {patient: float(np.mean(values)) for patient, values in by_patient.items()}
    patient_medians = {patient: float(np.median(values)) for patient, values in by_patient.items()}
    patient_coverages = {
        patient: len(by_patient.get(patient, [])) / count
        for patient, count in patient_reference.items()
    }
    return {
        "patient_groups": len(patient_reference),
        "reference_timestamps": reference_count,
        "comparable_timestamps": len(rows),
        "coverage": len(rows) / reference_count if reference_count else 0.0,
        "mean_signed_error_bpm": float(np.mean(errors)) if errors.size else None,
        "pooled_mae_bpm": float(np.mean(absolute)) if absolute.size else None,
        "median_absolute_error_bpm": float(np.median(absolute)) if absolute.size else None,
        "rmse_bpm": float(np.sqrt(np.mean(errors**2))) if errors.size else None,
        "p95_absolute_error_bpm": (
            float(np.quantile(absolute, 0.95, method="linear")) if absolute.size else None
        ),
        "patient_macro_mae_bpm": (
            float(np.mean(list(patient_maes.values()))) if patient_maes else None
        ),
        "patient_macro_median_ae_bpm": (
            float(np.mean(list(patient_medians.values()))) if patient_medians else None
        ),
        "patients_with_coverage_ge_0_90": sum(
            value >= 0.90 for value in patient_coverages.values()
        ),
        "patient_coverage_fraction_ge_0_90": (
            sum(value >= 0.90 for value in patient_coverages.values()) / len(patient_reference)
            if patient_reference
            else 0.0
        ),
    }


def evaluate_partition(partition: str, root: Path = ROOT) -> dict[str, Any]:
    split_rows = records_for_partition(partition, root)
    candidates: dict[str, list[dict[str, Any]]] = {
        candidate: [] for candidate in COMPARISON_CANDIDATES
    }
    reference_count = 0
    patient_reference: dict[str, int] = defaultdict(int)
    accessed_paths: list[str] = []
    for split in sorted(split_rows, key=lambda row: row["record_id"]):
        record_id = split["record_id"]
        patient = split["participant_group_id"]
        filtered = preprocess_record(record_id, root)
        annotation = load_annotations(record_id, root / DEFAULT_RAW_ROOT)
        accessed_paths.extend(
            [
                f"data/raw/mitdb/1.0.0/{record_id}.hea",
                f"data/raw/mitdb/1.0.0/{record_id}.dat",
                f"data/raw/mitdb/1.0.0/{record_id}.atr",
            ]
        )
        last_second = int((len(filtered) - 1) // INPUT_RATE_HZ)
        for second in range(LOOKBACK_SECONDS, last_second + 1):
            reference = reference_hr_at(
                annotation.sample, annotation.symbol, timestamp_seconds=second
            )
            if reference is None:
                continue
            reference_count += 1
            patient_reference[patient] += 1
            for candidate in COMPARISON_CANDIDATES:
                result = estimate_hr_at(filtered, timestamp_seconds=second, candidate_id=candidate)
                if result.valid:
                    candidates[candidate].append(
                        {
                            "partition": partition,
                            "record_id": record_id,
                            "participant_group_id": patient,
                            "timestamp_us": result.timestamp_us,
                            "candidate_id": candidate,
                            "reference_hr_bpm": reference,
                            "derived_hr_bpm": result.hr_ecg_bpm,
                            "detected_peak_count": result.detected_peak_count,
                            "valid_rr_interval_count": result.valid_rr_interval_count,
                        }
                    )
    return {
        "partition": partition,
        "metrics": {
            candidate: _error_metrics(rows, reference_count, patient_reference)
            for candidate, rows in candidates.items()
        },
        "rows": candidates,
        "accessed_paths": accessed_paths,
        "patient_groups": len(patient_reference),
        "reference_timestamps": reference_count,
    }


def validate_config(root: Path = ROOT) -> dict[str, Any]:
    config = yaml.safe_load((root / CONFIG_PATH.relative_to(ROOT)).read_text())
    if config["estimator_id"] != "ECG_HR_CONTEXT_V2":
        raise ValueError("ECG_HR_V2_CONFIG_ID_MISMATCH")
    if tuple(config["candidates"]["eligible"]) != ELIGIBLE_CANDIDATES:
        raise ValueError("ECG_HR_V2_CANDIDATE_SET_MISMATCH")
    if config["candidates"]["historical_comparator"] != HISTORICAL_ID:
        raise ValueError("ECG_HR_V2_HISTORICAL_COMPARATOR_MISMATCH")
    return config


def candidate_eligible(metrics: dict[str, Any]) -> bool:
    return metrics["coverage"] >= 0.95 and metrics["patient_coverage_fraction_ge_0_90"] >= 0.90


def passes_quality_floor(metrics: dict[str, Any]) -> bool:
    return (
        metrics["coverage"] >= 0.95
        and metrics["patient_macro_mae_bpm"] <= 10.0
        and metrics["median_absolute_error_bpm"] <= 5.0
        and metrics["p95_absolute_error_bpm"] <= 20.0
    )


def select_candidate(metrics: dict[str, dict[str, Any]]) -> tuple[str, str]:
    eligible = [
        candidate for candidate in ELIGIBLE_CANDIDATES if candidate_eligible(metrics[candidate])
    ]
    if not eligible:
        raise RuntimeError("ECG_HR_V2_VALIDATION_FAILURE: no coverage-eligible candidate")
    # Exact predeclared staged tie rule.
    eligible.sort(key=lambda candidate: candidate)
    best = eligible[0]
    for candidate in eligible[1:]:
        current, challenger = metrics[best], metrics[candidate]
        if challenger["patient_macro_mae_bpm"] < current["patient_macro_mae_bpm"] - 0.1:
            best = candidate
            continue
        if abs(challenger["patient_macro_mae_bpm"] - current["patient_macro_mae_bpm"]) > 0.1:
            continue
        for field, lower_is_better in (
            ("median_absolute_error_bpm", True),
            ("p95_absolute_error_bpm", True),
            ("coverage", False),
        ):
            delta = challenger[field] - current[field]
            if abs(delta) <= 0.1:
                continue
            if (lower_is_better and delta < 0) or (not lower_is_better and delta > 0):
                best = candidate
            break
    if not passes_quality_floor(metrics[best]):
        raise RuntimeError("ECG_HR_V2_VALIDATION_FAILURE: selected candidate fails quality floor")
    return best, "PREDECLARED_PATIENT_MACRO_MAE_AND_TIE_RULE_V1"


def write_partition_results(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / f"{result['partition'].lower()}_candidate_metrics.csv"
    fields = ["candidate_id", *next(iter(result["metrics"].values())).keys()]
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for candidate in COMPARISON_CANDIDATES:
            writer.writerow({"candidate_id": candidate, **result["metrics"][candidate]})
    rows_path = output_dir / f"{result['partition'].lower()}_derived_rows.csv"
    row_fields = [
        "partition",
        "record_id",
        "participant_group_id",
        "timestamp_us",
        "candidate_id",
        "reference_hr_bpm",
        "derived_hr_bpm",
        "detected_peak_count",
        "valid_rr_interval_count",
    ]
    with rows_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=row_fields, lineterminator="\n")
        writer.writeheader()
        for candidate in COMPARISON_CANDIDATES:
            writer.writerows(result["rows"][candidate])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partition", choices=ALLOWED_PARTITIONS, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/c021_hr_a")
    args = parser.parse_args()
    if args.partition == "VALIDATION":
        validate_config(ROOT)
    result = evaluate_partition(args.partition, ROOT)
    write_partition_results(result, args.output)
    summary = {"partition": args.partition, "metrics": result["metrics"], "status": "PASS"}
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
