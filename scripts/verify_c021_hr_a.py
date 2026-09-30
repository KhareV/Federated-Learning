#!/usr/bin/env python3
"""Verification-only checks for the frozen C021-HR-A engineering component."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.ecg_hr_v2 import passes_quality_floor, select_candidate  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify() -> dict[str, object]:
    lock_path = ROOT / "artifacts/ECG_HR_CONTEXT_V2.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock["status"] != "FROZEN_ENGINEERING_COMPONENT":
        raise RuntimeError("ECG_HR_V2_LOCK_STATUS_MISMATCH")
    config_path = ROOT / "configs/ecg_hr_context_v2.yaml"
    implementation_path = ROOT / "preprocessing/ecg_hr_context.py"
    if sha256(config_path) != lock["config_sha256"]:
        raise RuntimeError("ECG_HR_V2_CONFIG_HASH_MISMATCH")
    if sha256(implementation_path) != lock["implementation_sha256"]:
        raise RuntimeError("ECG_HR_V2_IMPLEMENTATION_HASH_MISMATCH")
    selected, _ = select_candidate(lock["candidate_metrics"])
    if selected != lock["selected_candidate"]:
        raise RuntimeError("ECG_HR_V2_SELECTION_MISMATCH")
    if not passes_quality_floor(lock["selection_result"]):
        raise RuntimeError("ECG_HR_V2_QUALITY_FLOOR_FAILURE")

    baseline = json.loads(
        (ROOT / "reports/c021_hr_a/immutability_baseline.json").read_text(encoding="utf-8")
    )
    paths = {
        "CAL_V1": "artifacts/CAL_V1.json",
        "MODEL_V1": "checkpoints/MODEL_V1.pt",
        "PREPROC_V1_lock": "manifests/preprocessing/PREPROC_V1.lock.json",
        "internal_test": "reports/internal_test.json",
        "nstdb": "reports/noise_robustness.json",
        "incart": "reports/external_incart.json",
    }
    for key, relative in paths.items():
        if sha256(ROOT / relative) != baseline[key]:
            raise RuntimeError(f"C021_UPSTREAM_IMMUTABILITY_FAILURE: {relative}")
    for relative, expected in baseline.items():
        if "/" in relative and sha256(ROOT / relative) != expected:
            raise RuntimeError(f"C021_UPSTREAM_IMMUTABILITY_FAILURE: {relative}")

    audit = json.loads(
        (ROOT / "reports/c021_hr_a/validation_access_audit.json").read_text(encoding="utf-8")
    )
    if any(audit["access_counts"].values()):
        raise RuntimeError("ECG_HR_V2_SCOPE_VIOLATION")
    return {
        "status": "PASS",
        "selected_estimator": selected,
        "config_sha256": lock["config_sha256"],
        "lock_sha256": sha256(lock_path),
        "upstream_immutability": "PASS",
        "forbidden_access": 0,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
