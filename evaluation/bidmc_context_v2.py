"""Frozen post-remediation BIDMC engineering evaluation for ECG_HR_CONTEXT_V2."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from datasets.bidmc import DEFAULT_RAW_ROOT, list_records, load_lead_ii
from evaluation.bidmc_context import context_window_at, verify_bidmc_source
from preprocessing.context_resample import make_context_resampler
from preprocessing.ecg import StatefulECGFilter
from preprocessing.ecg_hr_context import ESTIMATOR_ID, XQRS_ID, estimate_hr

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/bidmc_context_v2.yaml"
T021_ROWS_PATH = ROOT / "reports/t021/bidmc_context_rows.csv"
ROWS_PATH = ROOT / "reports/c021_hr_b/bidmc_context_rows_v2.csv"
BY_RECORD_PATH = ROOT / "reports/c021_hr_b/bidmc_by_record_v2.csv"
REPORT_PATH = ROOT / "reports/bidmc_multimodal_engineering_v2.json"
SUMMARY_PATH = ROOT / "reports/bidmc_multimodal_engineering_v2.csv"
LOCK_PATH = ROOT / "artifacts/BIDMC_CONTEXT_V2.lock.json"

INHERITED_FIELDS = (
    "record_id",
    "timestamp_us",
    "ppg_quality",
    "ppg_context_available",
    "pr_ppg_bpm",
    "provided_pulse_bpm",
    "pulse_reference_valid",
    "provided_hr_bpm",
    "hr_reference_valid",
    "spo2_pct",
    "spo2_valid",
    "spo2_provenance",
    "short_gap_present",
    "long_gap_present",
)

ROW_FIELDS = [
    *INHERITED_FIELDS,
    "hr_ecg_bpm_v2",
    "hr_ecg_valid_v2",
    "ecg_ppg_difference_bpm",
    "difference_gt_20_bpm",
    "quality_warning_natural",
    "ecg_hr_context_id",
    "bidmc_context_id",
]

METRIC_FIELDS = (
    "reference_samples",
    "comparable_samples",
    "coverage",
    "mean_signed_difference_bpm",
    "mae_bpm",
    "median_absolute_error_bpm",
    "rmse_bpm",
    "p95_absolute_error_bpm",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def _format_float(value: float | None) -> str:
    return "" if value is None or not math.isfinite(value) else format(value, ".12g")


def _optional_float(value: str) -> float | None:
    return float(value) if value != "" else None


def load_config(root: Path = ROOT) -> dict[str, Any]:
    config = yaml.safe_load((root / CONFIG_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
    if config["context_contract_id"] != "BIDMC_CONTEXT_V2":
        raise ValueError("BIDMC_CONTEXT_V2_ID_MISMATCH")
    if config["predecessor"] != "BIDMC_CONTEXT_V1":
        raise ValueError("BIDMC_CONTEXT_V2_PREDECESSOR_MISMATCH")
    if config["changed_component"]["replacement"] != ESTIMATOR_ID:
        raise ValueError("BIDMC_CONTEXT_V2_ESTIMATOR_MISMATCH")
    if config["changed_component"]["selected_detector"] != XQRS_ID:
        raise ValueError("BIDMC_CONTEXT_V2_DETECTOR_MISMATCH")
    if config["guardrails"] != {
        "pooled_coverage_min": 0.90,
        "pooled_median_absolute_error_bpm_max": 10.0,
        "pooled_MAE_bpm_max": 20.0,
    }:
        raise ValueError("BIDMC_CONTEXT_V2_GUARDRAIL_MISMATCH")
    if config["rate_consistency_audit"]["tolerance_bpm"] != 20.0:
        raise ValueError("BIDMC_CONTEXT_V2_RATE_POLICY_MISMATCH")
    if config["alignment"]["time_shift_optimization"] is not False:
        raise ValueError("BIDMC_CONTEXT_V2_ALIGNMENT_SCOPE_VIOLATION")
    return config


def load_t021_rows(root: Path = ROOT) -> list[dict[str, str]]:
    with (root / T021_ROWS_PATH.relative_to(ROOT)).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    identities = [(row["record_id"], int(row["timestamp_us"])) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("BIDMC_CONTEXT_V2_DUPLICATE_T021_IDENTITY")
    return rows


def preprocess_ecg(record_id: str, root: Path = ROOT) -> np.ndarray:
    raw_root = root / DEFAULT_RAW_ROOT
    ecg = load_lead_ii(record_id, raw_root)
    resampler = make_context_resampler("BIDMC_ECG_HR_125_TO_250_V1")
    resampled = resampler.process(np.asarray(ecg, dtype=np.float64), 0).values
    return StatefulECGFilter().process(resampled)


def error_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    reference_count = sum(row["hr_reference_valid"] == "true" for row in rows)
    comparable = [
        row
        for row in rows
        if row["hr_reference_valid"] == "true" and row["hr_ecg_valid_v2"] == "true"
    ]
    error = np.asarray(
        [float(row["hr_ecg_bpm_v2"]) - float(row["provided_hr_bpm"]) for row in comparable],
        dtype=np.float64,
    )
    absolute = np.abs(error)
    return {
        "reference_samples": reference_count,
        "comparable_samples": len(comparable),
        "coverage": len(comparable) / reference_count if reference_count else 0.0,
        "mean_signed_difference_bpm": float(np.mean(error)) if error.size else None,
        "mae_bpm": float(np.mean(absolute)) if absolute.size else None,
        "median_absolute_error_bpm": float(np.median(absolute)) if absolute.size else None,
        "rmse_bpm": float(np.sqrt(np.mean(error**2))) if error.size else None,
        "p95_absolute_error_bpm": (
            float(np.quantile(absolute, 0.95, method="linear")) if absolute.size else None
        ),
    }


def agreement_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    paired = [
        row
        for row in rows
        if row["hr_ecg_valid_v2"] == "true" and row["pr_ppg_bpm"] != ""
    ]
    difference = np.asarray(
        [float(row["hr_ecg_bpm_v2"]) - float(row["pr_ppg_bpm"]) for row in paired],
        dtype=np.float64,
    )
    absolute = np.abs(difference)
    within = int(np.sum(absolute <= 20.0))
    beyond = int(np.sum(absolute > 20.0))
    return {
        "paired_samples": len(paired),
        "mean_signed_difference_bpm": float(np.mean(difference)) if difference.size else None,
        "mae_bpm": float(np.mean(absolute)) if absolute.size else None,
        "median_absolute_difference_bpm": float(np.median(absolute)) if absolute.size else None,
        "p95_absolute_difference_bpm": (
            float(np.quantile(absolute, 0.95, method="linear")) if absolute.size else None
        ),
        "within_or_equal_20_count": within,
        "greater_than_20_count": beyond,
        "within_or_equal_20_fraction": within / len(paired) if paired else 0.0,
        "greater_than_20_fraction": beyond / len(paired) if paired else 0.0,
    }


def apply_natural_warning(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_record[row["record_id"]].append(row)
    run_count = 0
    warning_count = 0
    paired_count = 0
    affected: set[str] = set()
    for record_id, record_rows in by_record.items():
        started_at: int | None = None
        warning_in_run = False
        for row in sorted(record_rows, key=lambda item: int(item["timestamp_us"])):
            paired = row["hr_ecg_valid_v2"] == "true" and row["pr_ppg_bpm"] != ""
            mismatch = paired and abs(
                float(row["hr_ecg_bpm_v2"]) - float(row["pr_ppg_bpm"])
            ) > 20.0
            if paired:
                paired_count += 1
            if not mismatch:
                started_at = None
                warning_in_run = False
                row["quality_warning_natural"] = "false"
                continue
            timestamp = int(row["timestamp_us"])
            if started_at is None:
                started_at = timestamp
            warning = timestamp - started_at >= 10_000_000
            row["quality_warning_natural"] = str(warning).lower()
            if warning:
                warning_count += 1
                affected.add(record_id)
                if not warning_in_run:
                    run_count += 1
                    warning_in_run = True
    return {
        "policy": "HR_DISAGREEMENT_TOLERANCE_V1",
        "tolerance_bpm": 20.0,
        "duration_seconds": 10,
        "sustained_disagreement_runs": run_count,
        "records_affected": len(affected),
        "record_ids_affected": sorted(affected),
        "warning_timestamps": warning_count,
        "paired_timestamps": paired_count,
        "warning_time_fraction": warning_count / paired_count if paired_count else 0.0,
        "policy_changed_from_result": False,
    }


def passes_guardrails(metrics: dict[str, Any], config: dict[str, Any]) -> bool:
    guardrails = config["guardrails"]
    return (
        metrics["coverage"] >= guardrails["pooled_coverage_min"]
        and metrics["median_absolute_error_bpm"]
        <= guardrails["pooled_median_absolute_error_bpm_max"]
        and metrics["mae_bpm"] <= guardrails["pooled_MAE_bpm_max"]
    )


def evaluate(root: Path = ROOT) -> dict[str, Any]:
    config = load_config(root)
    source = verify_bidmc_source(root)
    inherited = load_t021_rows(root)
    expected_records = list_records(root / DEFAULT_RAW_ROOT)
    by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in inherited:
        by_record[row["record_id"]].append(row)
    if sorted(by_record) != expected_records or len(expected_records) != 53:
        raise ValueError("BIDMC_CONTEXT_V2_RECORD_CLOSURE_FAILURE")

    output_rows: list[dict[str, str]] = []
    for record_id in expected_records:
        stream = preprocess_ecg(record_id, root)
        for source_row in sorted(by_record[record_id], key=lambda row: int(row["timestamp_us"])):
            timestamp_us = int(source_row["timestamp_us"])
            second = timestamp_us // 1_000_000
            window = context_window_at(stream, second, 250)
            result = estimate_hr(window, timestamp_us=timestamp_us, candidate_id=XQRS_ID)
            ppg_rate = _optional_float(source_row["pr_ppg_bpm"])
            difference = (
                result.hr_ecg_bpm - ppg_rate
                if result.hr_ecg_bpm is not None and ppg_rate is not None
                else None
            )
            output_rows.append(
                {
                    **{field: source_row[field] for field in INHERITED_FIELDS},
                    "hr_ecg_bpm_v2": _format_float(result.hr_ecg_bpm),
                    "hr_ecg_valid_v2": str(result.valid).lower(),
                    "ecg_ppg_difference_bpm": _format_float(difference),
                    "difference_gt_20_bpm": (
                        str(abs(difference) > 20.0).lower() if difference is not None else ""
                    ),
                    "quality_warning_natural": "false",
                    "ecg_hr_context_id": ESTIMATOR_ID,
                    "bidmc_context_id": "BIDMC_CONTEXT_V2",
                }
            )
    source_ids = [(row["record_id"], row["timestamp_us"]) for row in inherited]
    output_ids = [(row["record_id"], row["timestamp_us"]) for row in output_rows]
    if source_ids != output_ids:
        raise ValueError("BIDMC_CONTEXT_V2_ROW_IDENTITY_MISMATCH")

    warning = apply_natural_warning(output_rows)
    metrics = error_metrics(output_rows)
    agreement = agreement_metrics(output_rows)
    per_record: list[dict[str, Any]] = []
    record_maes: list[float] = []
    for record_id in expected_records:
        record_metrics = error_metrics(
            [row for row in output_rows if row["record_id"] == record_id]
        )
        per_record.append({"record_id": record_id, **record_metrics})
        if record_metrics["mae_bpm"] is not None:
            record_maes.append(record_metrics["mae_bpm"])
    metrics["record_macro_mae_bpm"] = float(np.mean(record_maes))
    metrics["records_with_comparisons"] = len(record_maes)
    return {
        "config": config,
        "source": source,
        "rows": output_rows,
        "metrics": metrics,
        "per_record": per_record,
        "agreement": agreement,
        "warning": warning,
    }


def _v1_metrics(root: Path) -> dict[str, Any]:
    report = json.loads(
        (root / "reports/bidmc_multimodal_engineering.json").read_text(encoding="utf-8")
    )
    source = report["ECG_HR_vs_HR"]
    return {
        "coverage": source["coverage_fraction"],
        "mean_signed_difference_bpm": source["mean_signed_error_bpm"],
        "mae_bpm": source["mae_bpm"],
        "median_absolute_error_bpm": source["median_absolute_error_bpm"],
        "rmse_bpm": source["rmse_bpm"],
        "p95_absolute_error_bpm": source["p95_absolute_error_bpm"],
    }


def run(root: Path = ROOT) -> None:
    result = evaluate(root)
    if not passes_guardrails(result["metrics"], result["config"]):
        raise RuntimeError("ECG_HR_CROSS_MODAL_NOT_VALIDATED")
    _write_csv(root / ROWS_PATH.relative_to(ROOT), result["rows"], ROW_FIELDS)
    per_record_fields = ["record_id", *METRIC_FIELDS]
    _write_csv(root / BY_RECORD_PATH.relative_to(ROOT), result["per_record"], per_record_fields)
    v1 = _v1_metrics(root)
    comparison = {
        key: {
            "V1": v1[key],
            "V2": result["metrics"][key],
            "change": result["metrics"][key] - v1[key],
        }
        for key in v1
    }
    _write_json(root / "reports/c021_hr_b/v1_v2_comparison.json", comparison)
    _write_json(root / "reports/c021_hr_b/rate_consistency_audit.json", result["warning"])
    report = {
        "context_id": "BIDMC_CONTEXT_V2",
        "predecessor": "BIDMC_CONTEXT_V1",
        "changed_component": "ECG_HR_CONTEXT_V2 only",
        "dataset": "BIDMC-v1.0.0",
        "source_audit": result["source"],
        "alignment": "frozen T021 record/timestamp identity; samples <= t only; no time shift",
        "estimator": {
            "id": ESTIMATOR_ID,
            "candidate": XQRS_ID,
            "lock_sha256": sha256(root / "artifacts/ECG_HR_CONTEXT_V2.lock.json"),
        },
        "alert_policy": {
            "id": "ALERT_POLICY_V1",
            "lock_sha256": sha256(root / "artifacts/ALERT_POLICY_V1.lock.json"),
            "changed": False,
        },
        "V2_ECG_HR_vs_HR": result["metrics"],
        "V1_historical_ECG_HR_vs_HR": v1,
        "V1_to_V2": comparison,
        "ECG_PPG_V2_agreement": result["agreement"],
        "natural_rate_warning_audit": result["warning"],
        "unchanged_PPG_metrics": json.loads(
            (root / "reports/bidmc_multimodal_engineering.json").read_text()
        )["PPG_vs_PULSE"],
        "SpO2_provenance": "BIDMC_PROVIDED_NUMERIC; bidmc19 unavailable",
        "critical_care_domain_limitation": True,
        "no_AAMI_target": True,
        "no_clinical_certification": True,
        "no_tuning": True,
        "overall_status": "PASS",
    }
    _write_json(root / REPORT_PATH.relative_to(ROOT), report)
    summary = [
        {"comparison": "V2 ECG HR vs provided HR", **result["metrics"]},
        {"comparison": "V2 ECG HR vs T021 PPG PR", **result["agreement"]},
    ]
    summary_fields = [
        "comparison",
        *METRIC_FIELDS,
        "record_macro_mae_bpm",
        "records_with_comparisons",
        "paired_samples",
        "median_absolute_difference_bpm",
        "p95_absolute_difference_bpm",
        "within_or_equal_20_fraction",
        "greater_than_20_fraction",
    ]
    _write_csv(root / SUMMARY_PATH.relative_to(ROOT), summary, summary_fields)
    _write_json(
        root / "artifacts/BIDMC_CONTEXT_V2.supersedes.json",
        {
            "predecessor": "BIDMC_CONTEXT_V1",
            "replacement": "BIDMC_CONTEXT_V2",
            "change": "ECG HR estimator only",
            "reason": "T021 ECG-HR engineering failure",
            "replacement_component": ESTIMATOR_ID,
            "preserved": [
                "PPG estimator",
                "SpO2 provenance",
                "synchronization",
                "resampling",
                "quality/missingness behavior",
            ],
        },
    )
    print(json.dumps({"status": "PASS", "metrics": result["metrics"]}, indent=2))


def load_rows(path: Path = ROWS_PATH) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify_rows(root: Path = ROOT) -> dict[str, Any]:
    rows = load_rows(root / ROWS_PATH.relative_to(ROOT))
    inherited = load_t021_rows(root)
    if len(rows) != len(inherited):
        raise ValueError("BIDMC_CONTEXT_V2_ROW_COUNT_MISMATCH")
    for old, new in zip(inherited, rows, strict=True):
        for field in INHERITED_FIELDS:
            if old[field] != new[field]:
                raise ValueError(f"BIDMC_CONTEXT_V2_INHERITED_FIELD_MISMATCH: {field}")
    metrics = error_metrics(rows)
    record_maes = []
    for record_id in sorted({row["record_id"] for row in rows}):
        item = error_metrics([row for row in rows if row["record_id"] == record_id])
        if item["mae_bpm"] is not None:
            record_maes.append(item["mae_bpm"])
    metrics["record_macro_mae_bpm"] = float(np.mean(record_maes))
    metrics["records_with_comparisons"] = len(record_maes)
    agreement = agreement_metrics(rows)
    warning = apply_natural_warning(rows)
    return {"metrics": metrics, "agreement": agreement, "warning": warning, "rows": len(rows)}


def context_lock_payload(root: Path = ROOT) -> dict[str, Any]:
    """Build the deterministic engineering-context lock from frozen result artifacts."""
    bound_paths = {
        "config": "configs/bidmc_context_v2.yaml",
        "ecg_hr_context_lock": "artifacts/ECG_HR_CONTEXT_V2.lock.json",
        "alert_policy_lock": "artifacts/ALERT_POLICY_V1.lock.json",
        "t021_context_config": "configs/bidmc_context_v1.yaml",
        "t021_context_rows": "reports/t021/bidmc_context_rows.csv",
        "t021_report": "reports/bidmc_multimodal_engineering.json",
        "v2_rows": "reports/c021_hr_b/bidmc_context_rows_v2.csv",
        "v2_by_record": "reports/c021_hr_b/bidmc_by_record_v2.csv",
        "v2_report": "reports/bidmc_multimodal_engineering_v2.json",
        "v2_summary": "reports/bidmc_multimodal_engineering_v2.csv",
        "supersession": "artifacts/BIDMC_CONTEXT_V2.supersedes.json",
    }
    return {
        "context_id": "BIDMC_CONTEXT_V2",
        "predecessor": "BIDMC_CONTEXT_V1",
        "changed_component": "ECG_HR_CONTEXT_V2 only",
        "dataset": "BIDMC-v1.0.0",
        "alignment": "T021 record_id/timestamp_us; causal samples <= t; no time shift",
        "hashes": {name: sha256(root / path) for name, path in bound_paths.items()},
        "paths": bound_paths,
        "status": "FROZEN_ENGINEERING_CONTEXT",
    }


def verify_context_lock(root: Path = ROOT) -> dict[str, Any]:
    lock_path = root / LOCK_PATH.relative_to(ROOT)
    actual = json.loads(lock_path.read_text(encoding="utf-8"))
    expected = context_lock_payload(root)
    if actual != expected:
        raise ValueError("BIDMC_CONTEXT_V2_LOCK_MISMATCH")
    verification = verify_rows(root)
    if not passes_guardrails(verification["metrics"], load_config(root)):
        raise ValueError("ECG_HR_CROSS_MODAL_NOT_VALIDATED")
    return {"context_id": "BIDMC_CONTEXT_V2", "status": "PASS", **verification}


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.run:
        run(ROOT)
    else:
        print(json.dumps(verify_rows(ROOT), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
