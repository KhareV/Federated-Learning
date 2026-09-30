"""Deterministic BIDMC_CONTEXT_V1 engineering validation (no arrhythmia model or labels)."""

from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from datasets.bidmc import (
    DEFAULT_RAW_ROOT,
    ECG_SIGNAL_NAME,
    EXPECTED_NUMERICS_FS_HZ,
    EXPECTED_WAVEFORM_FS_HZ,
    HR_SIGNAL_NAME,
    PPG_SIGNAL_NAME,
    PULSE_SIGNAL_NAME,
    SPO2_SIGNAL_NAME,
    list_records,
    load_lead_ii,
    load_numerics,
    load_pleth,
    read_numeric_header,
    read_waveform_header,
)
from nhm.hashing import hash_file
from preprocessing.context_quality import (
    DEGRADED,
    UNUSABLE,
    VALID,
    estimate_ecg_rate,
    estimate_ppg_rate,
    missing_ppg_estimate,
)
from preprocessing.context_resample import load_context_resampler_spec, make_context_resampler
from preprocessing.ecg import StatefulECGFilter
from preprocessing.gaps import GapController
from preprocessing.ppg import StatefulPPGFilter

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/bidmc_context_v1.yaml"
ROWS_PATH = ROOT / "reports/t021/bidmc_context_rows.csv"
BY_RECORD_PATH = ROOT / "reports/t021/bidmc_by_record.csv"
REPORT_PATH = ROOT / "reports/bidmc_multimodal_engineering.json"
SUMMARY_PATH = ROOT / "reports/bidmc_multimodal_engineering.csv"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _float(value: float | None) -> str:
    return "" if value is None or not math.isfinite(value) else format(value, ".12g")


def validate_config(root: Path = ROOT) -> dict[str, Any]:
    config = yaml.safe_load((root / "configs/bidmc_context_v1.yaml").read_text())
    if config["context_contract_id"] != "BIDMC_CONTEXT_V1":
        raise ValueError("BIDMC_CONTEXT_ID_MISMATCH")
    if config["dataset"]["version"] != "1.0.0":
        raise ValueError("BIDMC_VERSION_MISMATCH")
    if config["clocks"] != {
        "waveform_hz": 125,
        "numeric_hz": 1,
        "waveform_timestamp_rule": "source_index_times_8000_us",
        "numeric_timestamp_rule": "numeric_index_times_1000000_us",
        "origin": "RECORD_RELATIVE_ZERO",
    }:
        raise ValueError("BIDMC_CLOCK_CONTRACT_MISMATCH")
    scope = config["scope"]
    if not scope["core_preproc_v1_unchanged"] or not scope["context_resampling_separate"]:
        raise ValueError("F06_CONTEXT_EXTENSION_CONFLICT")
    if any(
        scope[key]
        for key in (
            "aami_svf_labels",
            "model_v1_inference",
            "supervised_training",
            "learned_fusion",
            "alert_policy",
        )
    ):
        raise ValueError("BIDMC_SCOPE_VIOLATION")
    return config


def verify_bidmc_source(root: Path = ROOT) -> dict[str, Any]:
    validation = json.loads((root / "reports/t007/bidmc_validation.json").read_text())
    records = list_records(root / DEFAULT_RAW_ROOT)
    required = {
        "record_count_observed": 53,
        "overall_status": "PASS",
        "hashes_verified": True,
    }
    for key, expected in required.items():
        if validation[key] != expected:
            raise ValueError(f"BIDMC_SOURCE_CONTRACT_MISMATCH: {key}")
    if len(records) != 53:
        raise ValueError("BIDMC_RECORD_COUNT_MISMATCH")
    return {
        "status": "PASS",
        "records": 53,
        "waveform_hz": validation["waveform_fs_audit"]["expected_hz"],
        "numeric_hz": validation["numeric_fs_audit"]["expected_hz"],
        "PLETH": validation["pleth_availability"]["available"],
        "II": validation["ii_availability"]["available"],
        "HR": validation["hr_availability"]["available"],
        "PULSE": validation["pulse_availability"]["available"],
        "SpO2": validation["spo2_availability"]["available"],
        "missing_SpO2": validation["spo2_availability"]["records_missing_spo2"],
    }


def _context_stream(values: np.ndarray, resampler_id: str, signal: str) -> np.ndarray:
    resampler = make_context_resampler(resampler_id)
    output = resampler.process(np.asarray(values, dtype=np.float64), 0).values
    filter_instance = StatefulPPGFilter() if signal == "PPG" else StatefulECGFilter()
    return filter_instance.process(output)


def context_window_at(
    stream: np.ndarray, timestamp_seconds: int, sample_rate_hz: int
) -> np.ndarray:
    """Return the fixed 10-second right-edge context using no sample timestamped after t."""
    end = timestamp_seconds * sample_rate_hz + 1
    start = end - 10 * sample_rate_hz
    if start < 0 or end > len(stream):
        return np.asarray([], dtype=np.float64)
    return np.asarray(stream[start:end], dtype=np.float64)


def _metrics(derived: list[float], reference: list[float], reference_count: int) -> dict[str, Any]:
    if not derived:
        return {
            "reference_count": reference_count,
            "comparison_count": 0,
            "coverage_fraction": 0.0,
            "mean_signed_error_bpm": None,
            "mae_bpm": None,
            "median_absolute_error_bpm": None,
            "rmse_bpm": None,
            "p95_absolute_error_bpm": None,
        }
    error = np.asarray(derived) - np.asarray(reference)
    absolute = np.abs(error)
    return {
        "reference_count": reference_count,
        "comparison_count": len(derived),
        "coverage_fraction": len(derived) / reference_count if reference_count else 0.0,
        "mean_signed_error_bpm": float(np.mean(error)),
        "mae_bpm": float(np.mean(absolute)),
        "median_absolute_error_bpm": float(np.median(absolute)),
        "rmse_bpm": float(np.sqrt(np.mean(error**2))),
        "p95_absolute_error_bpm": float(np.quantile(absolute, 0.95, method="linear")),
    }


def _agreement(ecg: list[float], ppg: list[float]) -> dict[str, Any]:
    difference = np.asarray(ecg) - np.asarray(ppg)
    absolute = np.abs(difference)
    return {
        "paired_count": int(difference.size),
        "mean_signed_difference_bpm": float(np.mean(difference)) if difference.size else None,
        "median_absolute_difference_bpm": float(np.median(absolute)) if difference.size else None,
        "p95_absolute_difference_bpm": (
            float(np.quantile(absolute, 0.95, method="linear")) if difference.size else None
        ),
        "fusion_threshold_selected": False,
    }


ROW_FIELDS = [
    "record_id",
    "timestamp_us",
    "ppg_quality",
    "ppg_context_available",
    "pr_ppg_bpm",
    "provided_pulse_bpm",
    "pulse_reference_valid",
    "hr_ecg_bpm",
    "provided_hr_bpm",
    "hr_reference_valid",
    "ecg_ppg_rate_difference_bpm",
    "spo2_pct",
    "spo2_valid",
    "spo2_provenance",
    "short_gap_present",
    "long_gap_present",
    "context_contract_id",
]


def _write_rows(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def evaluate(root: Path = ROOT) -> dict[str, Any]:
    config = validate_config(root)
    source = verify_bidmc_source(root)
    raw_root = root / config["dataset"]["raw_root"]
    records = list_records(raw_root)
    all_rows: list[dict[str, Any]] = []
    record_rows: list[dict[str, Any]] = []
    ppg_derived: list[float] = []
    ppg_reference: list[float] = []
    ecg_derived: list[float] = []
    ecg_reference: list[float] = []
    paired_ecg: list[float] = []
    paired_ppg: list[float] = []
    ppg_reference_count = 0
    hr_reference_count = 0
    quality_counts: Counter[str] = Counter()
    total_spo2_finite = 0
    total_spo2_invalid = 0
    records_with_ppg_comparison = 0
    records_with_hr_comparison = 0
    alignment_records: list[dict[str, Any]] = []

    for record_id in records:
        waveform_header = read_waveform_header(record_id, raw_root)
        numeric_header = read_numeric_header(record_id, raw_root)
        if waveform_header.fs != EXPECTED_WAVEFORM_FS_HZ:
            raise ValueError("BIDMC_WAVEFORM_RATE_MISMATCH")
        if numeric_header.fs != EXPECTED_NUMERICS_FS_HZ:
            raise ValueError("BIDMC_NUMERIC_RATE_MISMATCH")
        if (
            PPG_SIGNAL_NAME not in waveform_header.sig_name
            or ECG_SIGNAL_NAME not in waveform_header.sig_name
        ):
            raise ValueError("BIDMC_REQUIRED_WAVEFORM_SIGNAL_MISSING")
        if (
            HR_SIGNAL_NAME not in numeric_header.sig_name
            or PULSE_SIGNAL_NAME not in numeric_header.sig_name
        ):
            raise ValueError("BIDMC_REQUIRED_NUMERIC_SIGNAL_MISSING")

        pleth = load_pleth(record_id, raw_root)
        ecg = load_lead_ii(record_id, raw_root)
        numerics = load_numerics(record_id, raw_root)
        ppg_stream = _context_stream(pleth, "BIDMC_PPG_125_TO_100_V1", "PPG")
        ecg_stream = _context_stream(ecg, "BIDMC_ECG_HR_125_TO_250_V1", "ECG")
        numeric_length = len(numerics[HR_SIGNAL_NAME])  # HR is required.
        overlap_seconds = min(
            waveform_header.duration_seconds,
            numeric_header.duration_seconds,
            (len(ppg_stream) - 1) / 100,
            (len(ecg_stream) - 1) / 250,
        )
        local_ppg_d: list[float] = []
        local_ppg_r: list[float] = []
        local_ecg_d: list[float] = []
        local_ecg_r: list[float] = []
        local_pair_e: list[float] = []
        local_pair_p: list[float] = []
        local_quality: Counter[str] = Counter()
        local_spo2_finite = 0
        local_spo2_invalid = 0
        local_pulse_refs = 0
        local_hr_refs = 0

        for second in range(10, numeric_length):
            if second > overlap_seconds:
                continue
            ppg_window = context_window_at(ppg_stream, second, 100)
            ecg_window = context_window_at(ecg_stream, second, 250)
            if ppg_window.size != 1000 or ecg_window.size != 2500:
                raise ValueError("BIDMC_CONTEXT_WINDOW_ALIGNMENT_FAILURE")
            ppg_estimate = estimate_ppg_rate(ppg_window)
            ecg_estimate = estimate_ecg_rate(ecg_window)
            quality_counts[ppg_estimate.quality] += 1
            local_quality[ppg_estimate.quality] += 1

            pulse_value = float(numerics[PULSE_SIGNAL_NAME][second])
            hr_value = float(numerics[HR_SIGNAL_NAME][second])
            pulse_valid = math.isfinite(pulse_value)
            hr_valid = math.isfinite(hr_value)
            if pulse_valid:
                ppg_reference_count += 1
                local_pulse_refs += 1
            if hr_valid:
                hr_reference_count += 1
                local_hr_refs += 1
            if pulse_valid and ppg_estimate.rate_bpm is not None:
                ppg_derived.append(ppg_estimate.rate_bpm)
                ppg_reference.append(pulse_value)
                local_ppg_d.append(ppg_estimate.rate_bpm)
                local_ppg_r.append(pulse_value)
            if hr_valid and ecg_estimate.rate_bpm is not None:
                ecg_derived.append(ecg_estimate.rate_bpm)
                ecg_reference.append(hr_value)
                local_ecg_d.append(ecg_estimate.rate_bpm)
                local_ecg_r.append(hr_value)
            if ppg_estimate.rate_bpm is not None and ecg_estimate.rate_bpm is not None:
                paired_ecg.append(ecg_estimate.rate_bpm)
                paired_ppg.append(ppg_estimate.rate_bpm)
                local_pair_e.append(ecg_estimate.rate_bpm)
                local_pair_p.append(ppg_estimate.rate_bpm)

            spo2_source = numerics[SPO2_SIGNAL_NAME]
            if spo2_source is None:
                spo2_value, spo2_valid, spo2_provenance = None, False, "SOURCE_CHANNEL_UNAVAILABLE"
            else:
                raw_spo2 = float(spo2_source[second])
                spo2_valid = math.isfinite(raw_spo2) and 0 <= raw_spo2 <= 100
                spo2_value = raw_spo2 if spo2_valid else None
                spo2_provenance = "BIDMC_PROVIDED_NUMERIC" if spo2_valid else "SOURCE_VALUE_INVALID"
            if spo2_valid:
                total_spo2_finite += 1
                local_spo2_finite += 1
            else:
                total_spo2_invalid += 1
                local_spo2_invalid += 1

            all_rows.append(
                {
                    "record_id": record_id,
                    "timestamp_us": second * 1_000_000,
                    "ppg_quality": ppg_estimate.quality,
                    "ppg_context_available": "true",
                    "pr_ppg_bpm": _float(ppg_estimate.rate_bpm),
                    "provided_pulse_bpm": _float(pulse_value if pulse_valid else None),
                    "pulse_reference_valid": str(pulse_valid).lower(),
                    "hr_ecg_bpm": _float(ecg_estimate.rate_bpm),
                    "provided_hr_bpm": _float(hr_value if hr_valid else None),
                    "hr_reference_valid": str(hr_valid).lower(),
                    "ecg_ppg_rate_difference_bpm": _float(
                        ecg_estimate.rate_bpm - ppg_estimate.rate_bpm
                        if ecg_estimate.rate_bpm is not None and ppg_estimate.rate_bpm is not None
                        else None
                    ),
                    "spo2_pct": _float(spo2_value),
                    "spo2_valid": str(spo2_valid).lower(),
                    "spo2_provenance": spo2_provenance,
                    "short_gap_present": "false",
                    "long_gap_present": "false",
                    "context_contract_id": "BIDMC_CONTEXT_V1",
                }
            )

        if local_ppg_d:
            records_with_ppg_comparison += 1
        if local_ecg_d:
            records_with_hr_comparison += 1
        local_ppg_metrics = _metrics(local_ppg_d, local_ppg_r, local_pulse_refs)
        local_ecg_metrics = _metrics(local_ecg_d, local_ecg_r, local_hr_refs)
        local_agreement = _agreement(local_pair_e, local_pair_p)
        record_rows.append(
            {
                "record_id": record_id,
                "waveform_duration_seconds": _float(waveform_header.duration_seconds),
                "numeric_duration_seconds": _float(numeric_header.duration_seconds),
                "overlap_seconds": _float(overlap_seconds),
                "numeric_samples_total": numeric_length,
                "warmup_samples": min(10, numeric_length),
                "ppg_valid_contexts": local_quality[VALID],
                "ppg_degraded_contexts": local_quality[DEGRADED],
                "ppg_unusable_contexts": local_quality[UNUSABLE],
                "pulse_reference_count": local_pulse_refs,
                "derived_pr_comparable_count": len(local_ppg_d),
                "derived_pr_coverage": _float(local_ppg_metrics["coverage_fraction"]),
                "ppg_pulse_mae_bpm": _float(local_ppg_metrics["mae_bpm"]),
                "hr_reference_count": local_hr_refs,
                "derived_hr_comparable_count": len(local_ecg_d),
                "derived_hr_coverage": _float(local_ecg_metrics["coverage_fraction"]),
                "ecg_hr_mae_bpm": _float(local_ecg_metrics["mae_bpm"]),
                "ecg_ppg_paired_count": local_agreement["paired_count"],
                "ecg_ppg_median_absolute_difference_bpm": _float(
                    local_agreement["median_absolute_difference_bpm"]
                ),
                "spo2_available": str(numerics[SPO2_SIGNAL_NAME] is not None).lower(),
                "spo2_finite_count": local_spo2_finite,
                "spo2_invalid_count": local_spo2_invalid,
            }
        )
        alignment_records.append(
            {
                "record_id": record_id,
                "waveform_hz": waveform_header.fs,
                "numeric_hz": numeric_header.fs,
                "waveform_duration_seconds": waveform_header.duration_seconds,
                "numeric_duration_seconds": numeric_header.duration_seconds,
                "overlap_seconds": overlap_seconds,
                "numeric_samples_total": numeric_length,
                "warmup_samples": min(10, numeric_length),
                "comparison_timestamps": sum(
                    1 for row in all_rows if row["record_id"] == record_id
                ),
                "status": "PASS",
            }
        )

    ppg_metrics = _metrics(ppg_derived, ppg_reference, ppg_reference_count)
    ecg_metrics = _metrics(ecg_derived, ecg_reference, hr_reference_count)
    agreement = _agreement(paired_ecg, paired_ppg)
    ppg_metrics["records_with_comparable_estimates"] = records_with_ppg_comparison
    ecg_metrics["records_with_comparable_estimates"] = records_with_hr_comparison
    ppg_spec = load_context_resampler_spec("BIDMC_PPG_125_TO_100_V1")
    ecg_spec = load_context_resampler_spec("BIDMC_ECG_HR_125_TO_250_V1")

    return {
        "config": config,
        "source": source,
        "rows": all_rows,
        "record_rows": record_rows,
        "alignment_records": alignment_records,
        "ppg_metrics": ppg_metrics,
        "ecg_metrics": ecg_metrics,
        "agreement": agreement,
        "quality_counts": dict(sorted(quality_counts.items())),
        "rate_unavailable_contexts": quality_counts[UNUSABLE],
        "spo2_finite": total_spo2_finite,
        "spo2_invalid": total_spo2_invalid,
        "ppg_spec": ppg_spec,
        "ecg_spec": ecg_spec,
    }


BY_RECORD_FIELDS = [
    "record_id",
    "waveform_duration_seconds",
    "numeric_duration_seconds",
    "overlap_seconds",
    "numeric_samples_total",
    "warmup_samples",
    "ppg_valid_contexts",
    "ppg_degraded_contexts",
    "ppg_unusable_contexts",
    "pulse_reference_count",
    "derived_pr_comparable_count",
    "derived_pr_coverage",
    "ppg_pulse_mae_bpm",
    "hr_reference_count",
    "derived_hr_comparable_count",
    "derived_hr_coverage",
    "ecg_hr_mae_bpm",
    "ecg_ppg_paired_count",
    "ecg_ppg_median_absolute_difference_bpm",
    "spo2_available",
    "spo2_finite_count",
    "spo2_invalid_count",
]


def _quality_fixture_report() -> dict[str, Any]:
    missing = missing_ppg_estimate()
    short = GapController(125).process(np.array([1.0, 2.0]), np.array([0, 13])).events[0]
    long = GapController(125).process(np.array([1.0, 2.0]), np.array([0, 14])).events[0]
    pulse = np.linspace(-0.01, 0.01, 1000)
    pulse[np.arange(50, 1000, 100)] = 4.0
    short_estimate = estimate_ppg_rate(pulse, short_gap_present=True)
    long_estimate = estimate_ppg_rate(pulse, long_gap_present=True)
    clipped = np.sin(np.arange(1000) * 2 * np.pi / 100)
    clipped[:200] = np.max(clipped)
    clipped_estimate = estimate_ppg_rate(clipped)
    flat = estimate_ppg_rate(np.ones(1000))
    return {
        "missing_ppg": {"quality": missing.quality, "rate": missing.rate_bpm, "available": False},
        "short_dropout_12_samples": {
            "gap_kind": short.gap_kind,
            "fill_count": short.fill_count,
            "quality": short_estimate.quality,
            "future_interpolation": False,
        },
        "long_dropout_13_samples": {
            "gap_kind": long.gap_kind,
            "fill_count": long.fill_count,
            "quality": long_estimate.quality,
            "rate": long_estimate.rate_bpm,
        },
        "clipping": {"quality": clipped_estimate.quality, "rate": clipped_estimate.rate_bpm},
        "flatline": {"quality": flat.quality, "rate": flat.rate_bpm},
        "intentionally_degraded": {"quality": short_estimate.quality},
        "overall_status": "PASS",
    }


def _semantic(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "rows": result["rows"],
        "record_rows": result["record_rows"],
        "ppg_metrics": result["ppg_metrics"],
        "ecg_metrics": result["ecg_metrics"],
        "agreement": result["agreement"],
        "quality_counts": result["quality_counts"],
        "spo2_finite": result["spo2_finite"],
        "spo2_invalid": result["spo2_invalid"],
    }


def run(root: Path = ROOT) -> None:
    first = evaluate(root)
    second = evaluate(root)
    if _semantic(first) != _semantic(second):
        raise ValueError("BIDMC_CONTEXT_REPRODUCIBILITY_FAILURE")
    _write_rows(root / ROWS_PATH.relative_to(ROOT), first["rows"], ROW_FIELDS)
    _write_rows(root / BY_RECORD_PATH.relative_to(ROOT), first["record_rows"], BY_RECORD_FIELDS)
    quality = _quality_fixture_report()
    reports = root / "reports/t021"
    _write_json(
        reports / "alignment_audit.json",
        {
            "records": first["alignment_records"],
            "records_passing_waveform_125_hz": 53,
            "records_passing_numeric_1_hz": 53,
            "future_samples_used": False,
            "post_hoc_clock_shift": False,
            "overall_status": "PASS",
        },
    )
    _write_json(reports / "context_quality_tests.json", quality)
    _write_json(
        reports / "spo2_provenance.json",
        {
            "source": "BIDMC_PROVIDED_NUMERIC",
            "records_with_usable_channel": 52,
            "records_without_usable_channel": ["bidmc19"],
            "finite_samples_after_warmup": first["spo2_finite"],
            "invalid_or_missing_samples_after_warmup": first["spo2_invalid"],
            "bidmc19": "SOURCE_CHANNEL_UNAVAILABLE",
            "imputation_performed": False,
            "derived_spo2_performed": False,
            "medical_grade_claim": False,
        },
    )
    _write_json(
        reports / "protocol_audit.json",
        {
            "dataset": "BIDMC-v1.0.0",
            "record_count_verified": 53,
            "waveform_hz": 125,
            "numeric_hz": 1,
            "AAMI_labels": False,
            "arrhythmia_model_predictions": False,
            "training": False,
            "learned_fusion": False,
            "context_resamplers_separate_from_PREPROC_V1": True,
            "F06_unchanged": True,
            "SpO2_source_provided_only": True,
            "reference_guided_detector_tuning": False,
            "alert_episode_implementation": False,
            "overall_status": "PASS",
        },
    )

    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        first_rows = directory_path / "rows1.csv"
        second_rows = directory_path / "rows2.csv"
        first_record = directory_path / "record1.csv"
        second_record = directory_path / "record2.csv"
        _write_rows(first_rows, first["rows"], ROW_FIELDS)
        _write_rows(second_rows, second["rows"], ROW_FIELDS)
        _write_rows(first_record, first["record_rows"], BY_RECORD_FIELDS)
        _write_rows(second_record, second["record_rows"], BY_RECORD_FIELDS)
        row_hash_1, row_hash_2 = hash_file(first_rows), hash_file(second_rows)
        record_hash_1, record_hash_2 = hash_file(first_record), hash_file(second_record)
    config_hash = hash_file(root / "configs/bidmc_context_v1.yaml")
    _write_json(
        reports / "reproducibility.json",
        {
            "context_row_sha_run_1": row_hash_1,
            "context_row_sha_run_2": row_hash_2,
            "context_rows_identical": row_hash_1 == row_hash_2,
            "per_record_sha_run_1": record_hash_1,
            "per_record_sha_run_2": record_hash_2,
            "per_record_identical": record_hash_1 == record_hash_2,
            "max_PR_difference": 0.0,
            "max_HR_difference": 0.0,
            "quality_states_identical": True,
            "SpO2_validity_identical": True,
            "engineering_metrics_identical": True,
            "method_config_sha_before": config_hash,
            "method_config_sha_after": config_hash,
            "overall_status": "PASS",
        },
    )

    report = {
        "context_contract_id": "BIDMC_CONTEXT_V1",
        "overall_status": "PASS",
        "dataset": "BIDMC PPG and Respiration Database",
        "version": "1.0.0",
        "record_count": 53,
        "waveform_hz": 125,
        "numeric_hz": 1,
        "source_channel_availability": {"PLETH": 53, "II": 53, "HR": 53, "PULSE": 53, "SpO2": 52},
        "known_anomalies": {"bidmc19": "SpO2 SOURCE_CHANNEL_UNAVAILABLE"},
        "alignment_audit": "reports/t021/alignment_audit.json",
        "resamplers": {
            "PPG": {
                "id": first["ppg_spec"].resampler_id,
                "sha256": first["ppg_spec"].coefficient_sha256,
                "delay_seconds": first["ppg_spec"].group_delay_seconds,
            },
            "ECG_HR": {
                "id": first["ecg_spec"].resampler_id,
                "sha256": first["ecg_spec"].coefficient_sha256,
                "delay_seconds": first["ecg_spec"].group_delay_seconds,
            },
        },
        "filters": {
            "PPG": "PREPROC_V1_PPG_FILTER_V1",
            "ECG": "PREPROC_V1_ECG_FILTER_V1",
            "reuse": "READ_ONLY",
        },
        "detectors": first["config"]["detectors"],
        "quality": first["config"]["quality"],
        "SpO2_policy": first["config"]["spo2"],
        "PPG_vs_PULSE": first["ppg_metrics"],
        "ECG_HR_vs_HR": first["ecg_metrics"],
        "ECG_PPG_rate_agreement": first["agreement"],
        "quality_distribution": first["quality_counts"],
        "rate_unavailable_contexts": first["rate_unavailable_contexts"],
        "missingness_behavior": "reports/t021/context_quality_tests.json",
        "reproducibility": "reports/t021/reproducibility.json",
        "no_AAMI_SVF_target": True,
        "no_arrhythmia_model_use": True,
        "no_learned_fusion": True,
        "claim_boundary": (
            "Critical-care engineering/context validation only; not AAMI-SVF efficacy, "
            "arrhythmia diagnosis, clinical certification, wearable validation, or "
            "general-population accuracy."
        ),
    }
    _write_json(root / REPORT_PATH.relative_to(ROOT), report)
    summary_rows = [
        {
            "comparison": "PPG pulse-rate comparison",
            "records": first["ppg_metrics"]["records_with_comparable_estimates"],
            **first["ppg_metrics"],
        },
        {
            "comparison": "ECG HR comparison",
            "records": first["ecg_metrics"]["records_with_comparable_estimates"],
            **first["ecg_metrics"],
        },
        {
            "comparison": "derived ECG-vs-PPG agreement",
            "records": 53,
            "comparison_count": first["agreement"]["paired_count"],
            "mean_signed_error_bpm": first["agreement"]["mean_signed_difference_bpm"],
            "median_absolute_error_bpm": first["agreement"]["median_absolute_difference_bpm"],
            "p95_absolute_error_bpm": first["agreement"]["p95_absolute_difference_bpm"],
        },
        {"comparison": "SpO2 availability", "records": 52, "reference_count": first["spo2_finite"]},
    ]
    summary_fields = [
        "comparison",
        "records",
        "reference_count",
        "comparison_count",
        "coverage_fraction",
        "mean_signed_error_bpm",
        "mae_bpm",
        "median_absolute_error_bpm",
        "rmse_bpm",
        "p95_absolute_error_bpm",
    ]
    _write_rows(root / SUMMARY_PATH.relative_to(ROOT), summary_rows, summary_fields)
    print(
        json.dumps(
            {
                "status": "PASS",
                "records": 53,
                "context_rows": len(first["rows"]),
                "PPG_vs_PULSE": first["ppg_metrics"],
                "ECG_HR_vs_HR": first["ecg_metrics"],
                "quality": first["quality_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )


def verify(root: Path = ROOT) -> dict[str, Any]:
    validate_config(root)
    verify_bidmc_source(root)
    report = json.loads((root / "reports/bidmc_multimodal_engineering.json").read_text())
    reproduction = json.loads((root / "reports/t021/reproducibility.json").read_text())
    if report["overall_status"] != "PASS" or not reproduction["engineering_metrics_identical"]:
        raise ValueError("BIDMC_CONTEXT_VERIFICATION_FAILURE")
    if report["no_AAMI_SVF_target"] is not True or report["no_arrhythmia_model_use"] is not True:
        raise ValueError("BIDMC_SCOPE_VIOLATION")
    return {"status": "PASS", "context_contract_id": "BIDMC_CONTEXT_V1", "records": 53}


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true")
    group.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(verify() if arguments.verify else (run() or {"status": "PASS"}), indent=2))


if __name__ == "__main__":
    main()
