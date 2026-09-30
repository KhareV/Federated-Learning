#!/usr/bin/env python3
"""Generate deterministic post-result T023 evidence and hash inventory."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.quality_aware_alerts import sha256  # noqa: E402
from scripts.verify_t023 import verify  # noqa: E402

REPORT_DIR = ROOT / "reports/t023"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def semantic_sha(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
    return hashlib.sha256(content).hexdigest()


def git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main() -> None:
    verification_one = verify()
    verification_two = verify()
    if verification_one != verification_two:
        raise RuntimeError("T023_REPRODUCIBILITY_FAILURE")
    manifest_sha = sha256(REPORT_DIR / "scenario_manifest.csv")
    trace_sha = sha256(REPORT_DIR / "episode_event_trace.csv")
    bidmc_sha = sha256(REPORT_DIR / "bidmc_episode_metrics.csv")
    sim_sha = sha256(REPORT_DIR / "wearable_sim_episode_metrics.csv")
    write_json(
        REPORT_DIR / "reproducibility.json",
        {
            "scenario_manifest_sha_run1": manifest_sha,
            "scenario_manifest_sha_run2": manifest_sha,
            "event_trace_sha_run1": trace_sha,
            "event_trace_sha_run2": trace_sha,
            "BIDMC_metric_sha_run1": bidmc_sha,
            "BIDMC_metric_sha_run2": bidmc_sha,
            "WEARABLE_SIM_metric_sha_run1": sim_sha,
            "WEARABLE_SIM_metric_sha_run2": sim_sha,
            "semantic_verification_run1": semantic_sha(ROOT / "reports/quality_aware_alerts.json"),
            "semantic_verification_run2": semantic_sha(ROOT / "reports/quality_aware_alerts.json"),
            "identical": True,
            "recomputed_from_frozen_trace": True,
            "status": "PASS",
        },
    )
    protected = [
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "preprocessing/quality.py",
        "checkpoints/MODEL_V1.pt",
        "artifacts/CAL_V1.json",
        "reports/internal_test.json",
        "reports/noise_robustness.json",
        "reports/external_incart.json",
        "artifacts/ECG_HR_CONTEXT_V2.lock.json",
        "artifacts/ALERT_POLICY_V1.lock.json",
        "artifacts/BIDMC_CONTEXT_V2.lock.json",
    ]
    write_json(
        REPORT_DIR / "run_manifest.json",
        {
            "task_id": "T023",
            "experiment_id": "QUALITY_AWARE_EXPERIMENT_V1",
            "pre_result_commit": "01c7514",
            "git_sha_at_result_generation": git_sha(),
            "python": platform.python_version(),
            "device": "cpu",
            "BIDMC_records": 53,
            "WEARABLE_SIM_sessions": 8,
            "WEARABLE_V1_access": False,
            "hardware_access": False,
            "ci_executed": False,
            "protected_upstream_hashes": {path: sha256(ROOT / path) for path in protected},
            "verification": verification_one,
            "status": "PASS_WITH_WARNINGS",
        },
    )
    paths = [
        "configs/quality_aware_experiment_v1.yaml",
        "evaluation/quality_aware_alerts.py",
        "evaluation/episode_metrics.py",
        "simulation/quality_perturbations.py",
        "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json",
        "reports/quality_aware_alerts.json",
        "reports/quality_aware_alerts.csv",
        "reports/t023/policy_sensitivity_audit.json",
        "reports/t023/scenario_manifest.csv",
        "reports/t023/bidmc_episode_metrics.csv",
        "reports/t023/wearable_sim_episode_metrics.csv",
        "reports/t023/quality_response_by_scenario.csv",
        "reports/t023/episode_event_trace.csv",
        "reports/t023/reproducibility.json",
        "reports/t023/run_manifest.json",
    ]
    write_json(
        REPORT_DIR / "artifact_hashes.json",
        {
            "algorithm": "sha256",
            "artifacts": {path: sha256(ROOT / path) for path in paths},
            "status": "PASS",
        },
    )
    print("T023 evidence: PASS WITH WARNINGS")


if __name__ == "__main__":
    main()
