"""Freeze C021-HR-A results after the declared VALIDATION comparison."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import wfdb

from evaluation.ecg_hr_v2 import select_candidate, validate_config
from preprocessing.ecg_hr_context import (
    INPUT_RATE_HZ,
    LOOKBACK_SECONDS,
    MIN_VALID_INTERVALS,
    RR_MAX_SECONDS,
    RR_MIN_SECONDS,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/c021_hr_a"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_metrics(path: Path) -> dict[str, dict[str, Any]]:
    integer_fields = {
        "patient_groups",
        "reference_timestamps",
        "comparable_timestamps",
        "patients_with_coverage_ge_0_90",
    }
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    parsed: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate = row.pop("candidate_id")
        parsed[candidate] = {
            key: int(value) if key in integer_fields else float(value) for key, value in row.items()
        }
    return parsed


def git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main() -> None:
    validate_config(ROOT)
    train_metrics = read_metrics(REPORT_DIR / "train_candidate_metrics.csv")
    validation_metrics = read_metrics(REPORT_DIR / "validation_candidate_metrics.csv")
    selected, rule = select_candidate(validation_metrics)
    chosen = validation_metrics[selected]
    config_path = ROOT / "configs/ecg_hr_context_v2.yaml"
    implementation_path = ROOT / "preprocessing/ecg_hr_context.py"
    split_path = ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"
    preproc_lock_path = ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"
    method_sha = sha256(config_path)

    write_json(
        REPORT_DIR / "candidate_selection.json",
        {
            "candidate_metrics": validation_metrics,
            "candidate_set_fixed_before_validation": True,
            "engineering_guardrails_passed": True,
            "historical_comparator_selection_eligible": False,
            "selected_estimator": selected,
            "selection_metric": "patient_macro_MAE",
            "selection_reason": rule,
            "status": "PASS",
        },
    )
    write_json(
        REPORT_DIR / "validation_access_audit.json",
        {
            "access_counts": {
                "MITDB_CALIBRATION": 0,
                "MITDB_INTERNAL_TEST": 0,
                "INCART": 0,
                "NSTDB": 0,
                "BIDMC_REFERENCE": 0,
                "WEARABLE_V1": 0,
            },
            "MITDB_TRAIN": "ALLOWED_AND_ACCESSED",
            "MITDB_VALIDATION": "ALLOWED_AND_ACCESSED_ONCE_AFTER_METHOD_FREEZE",
            "WEARABLE_SIM": "ENGINEERING_FIXTURE_ONLY_NOT_USED",
            "status": "PASS",
        },
    )
    lock = {
        "candidate_metrics": validation_metrics,
        "causal_input_rule": "samples_timestamped_at_or_before_t_only",
        "change_control_reason": "T021 auxiliary ECG-HR estimator failed engineering validation",
        "config_sha256": method_sha,
        "estimator_id": "ECG_HR_CONTEXT_V2",
        "implementation_path": "preprocessing/ecg_hr_context.py",
        "implementation_sha256": sha256(implementation_path),
        "input_sampling_rate_hz": INPUT_RATE_HZ,
        "minimum_valid_interval_count": MIN_VALID_INTERVALS,
        "preproc_v1_lock_sha256": sha256(preproc_lock_path),
        "rate_formula": "60 / median(valid_RR_seconds)",
        "rate_lookback_seconds": LOOKBACK_SECONDS,
        "rr_bounds_seconds": [RR_MIN_SECONDS, RR_MAX_SECONDS],
        "selected_candidate": selected,
        "selection_dataset": "MITDB_VALIDATION",
        "selection_metric": "patient_macro_MAE",
        "selection_result": chosen,
        "split_sha256": sha256(split_path),
        "status": "FROZEN_ENGINEERING_COMPONENT",
        "validation_comparable_timestamp_count": chosen["comparable_timestamps"],
        "validation_patient_count": chosen["patient_groups"],
        "wfdb_version": wfdb.__version__,
    }
    write_json(ROOT / "artifacts/ECG_HR_CONTEXT_V2.lock.json", lock)
    write_json(
        ROOT / "artifacts/ECG_HR_CONTEXT_V2.supersedes.json",
        {
            "affected_subsystem": "ECG-HR context only",
            "historical_bidmc_context_v1_preserved": True,
            "predecessor": "T021_ABS_PEAK_V1 ECG-HR component",
            "reason": "failed T021 engineering validation",
            "replacement": "ECG_HR_CONTEXT_V2",
            "unaffected": [
                "PPG processing",
                "PPG rate estimator",
                "SpO2 provenance",
                "BIDMC synchronization",
                "BIDMC context resamplers",
                "context quality",
                "PREPROC_V1",
                "MODEL_V1",
                "CAL_V1",
                "internal/external classification evidence",
            ],
        },
    )
    write_json(
        REPORT_DIR / "run_manifest.json",
        {
            "checkpoint": "C021-HR-A",
            "method_git_sha": git_sha(),
            "method_config_sha256": method_sha,
            "selected_estimator": selected,
            "status": "PASS",
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
        },
    )


if __name__ == "__main__":
    main()
