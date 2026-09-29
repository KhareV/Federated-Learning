#!/usr/bin/env python3
"""Create and verify the F06 PREPROC_V1 lock after complete G6 evidence passes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402

LOCK_PATH = ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"
AUDIT_PATH = ROOT / "reports/t013/preproc_freeze_audit.json"

BOUND_ARTIFACTS = [
    "configs/preproc_v1.yaml",
    "configs/quality_v1.yaml",
    "preprocessing/resample.py",
    "preprocessing/gaps.py",
    "preprocessing/filters.py",
    "preprocessing/ecg.py",
    "preprocessing/ppg.py",
    "preprocessing/windowing.py",
    "preprocessing/sync.py",
    "preprocessing/quality.py",
    "preprocessing/mitdb_windows.py",
    "preprocessing/freeze.py",
    "preprocessing/coefficients/MITDB_360_TO_250_V1.npy",
    "preprocessing/coefficients/INCART_257_TO_250_V1.npy",
    "preprocessing/coefficients/PREPROC_V1_ECG_FILTER_V1.npy",
    "preprocessing/coefficients/PREPROC_V1_PPG_FILTER_V1.npy",
    "preprocessing/coefficients/manifest.json",
    "manifests/labels/AAMI_SVF_MAP_V1.yaml",
    "manifests/splits/MITDB_SPLIT_V1.csv",
    "manifests/splits/MITDB_SPLIT_V1.lock.json",
    "manifests/windows/MITDB_WINDOWS_V1.csv",
    "manifests/windows/MITDB_WINDOWS_V1.cache.csv",
]


def main() -> None:
    verify_frozen_split(ROOT)
    required_reports = [
        "reports/preprocessing/resampler_causality.json",
        "reports/preprocessing/filter_causality.json",
        "reports/preprocessing/gap_tests.json",
        "reports/preprocessing/window_tests.json",
        "reports/preprocessing/quality_tests.json",
        "reports/preprocessing/sync_tests.json",
        "reports/t013/real_window_audit.json",
    ]
    statuses = {
        path: json.loads((ROOT / path).read_text(encoding="utf-8"))["overall_status"]
        for path in required_reports
    }
    if any(status != "PASS" for status in statuses.values()):
        raise RuntimeError(f"G6 component failure prevents F06 freeze: {statuses}")

    config = yaml.safe_load((ROOT / "configs/preproc_v1.yaml").read_text(encoding="utf-8"))
    quality = yaml.safe_load((ROOT / "configs/quality_v1.yaml").read_text(encoding="utf-8"))
    lock = {
        "freeze_id": "F06",
        "status": "FROZEN",
        "frozen_by_task": "T013",
        "preproc_id": "PREPROC_V1",
        "gap_policy_id": "GAP_POLICY_V1",
        "windowing_id": "WINDOWING_V1",
        "quality_id": "QUALITY_V1",
        "target_id": "AAMI_SVF_WINDOW_V1",
        "map_id": "AAMI_SVF_MAP_V1",
        "split_id": "MITDB_SPLIT_V1",
        "semantic_contract": {
            "preproc_id": config["preproc_id"],
            "gap_policy_id": config["gap_policy"]["policy_id"],
            "windowing_id": config["windowing"]["windowing_id"],
            "quality_id": quality["quality_id"],
            "ecg_rate_hz": config["windowing"]["sample_rate_hz"],
            "window_samples": config["windowing"]["window_samples"],
            "stride_samples": config["windowing"]["stride_samples"],
            "signal_interval": config["windowing"]["signal_interval"],
            "annotation_interval": config["windowing"]["annotation_interval"],
            "timestamp_mapping_id": config["resampler"]["timestamp_mapping_id"],
            "resampler_delay_us": 40000,
            "timestamp_backdating": config["windowing"]["timestamp_backdating"],
            "normalization_id": config["normalization"]["normalization_id"],
            "normalization_epsilon": float(config["normalization"]["epsilon"]),
        },
        "annotation_time_mapping": "EXACT_RATIONAL_SOURCE_GRID_NO_RESAMPLER_DELAY_SHIFT",
        "causal_iir_phase": "INHERENT_NOT_BACKDATED",
        "artifact_sha256": {path: hash_file(ROOT / path) for path in BOUND_ARTIFACTS},
        "upstream_evidence_sha256": {
            path: hash_file(ROOT / path) for path in required_reports[:3]
        },
        "post_freeze_change_rule": (
            "Any change to resampling, filter coefficients, gap behavior, window geometry, "
            "timestamp conventions, quality rules, or PER_WINDOW_ZSCORE_V1 is a Class C "
            "PREPROC version change and invalidates window caches, features, baselines, "
            "models, calibration, evaluations, federated experiments, and deployment artifacts."
        ),
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verification = verify_preproc_freeze(ROOT)
    audit = {
        "task_id": "T013",
        "freeze_id": "F06",
        "lock_path": str(LOCK_PATH.relative_to(ROOT)),
        "lock_sha256": hash_file(LOCK_PATH),
        "component_statuses": statuses,
        "bound_artifact_count": len(BOUND_ARTIFACTS),
        "tamper_test_status": "PASS_TEST_SUITE",
        "verification": verification,
        "overall_status": "PASS",
    }
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("T013 F06 freeze: PASS")


if __name__ == "__main__":
    main()
