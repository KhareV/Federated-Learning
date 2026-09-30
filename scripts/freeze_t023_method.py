#!/usr/bin/env python3
"""Generate the pre-result T023 scenario manifest, sensitivity audit, and method lock."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.quality_aware_alerts import (  # noqa: E402
    load_bidmc_context_rows,
    load_config,
    sha256,
)
from simulation.quality_perturbations import (  # noqa: E402
    BASE_SEED,
    SCENARIOS,
    SIM_EXTRA_SCENARIOS,
    derived_seed,
    experiment_interval,
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_manifest() -> Path:
    rows: list[dict[str, Any]] = []
    context = load_bidmc_context_rows(ROOT)
    by_record: dict[str, list[int]] = {}
    for record, timestamp in context:
        by_record.setdefault(record, []).append(timestamp)
    policy_sha = sha256(ROOT / "artifacts/ALERT_POLICY_V1.lock.json")
    model_sha = sha256(ROOT / "checkpoints/MODEL_V1.pt")
    for record_id in sorted(by_record):
        interval = experiment_interval(max(by_record[record_id]))
        for scenario in SCENARIOS:
            rows.append(
                {
                    "dataset_id": "BIDMC-v1.0.0",
                    "session_id": record_id,
                    "scenario_id": scenario,
                    "base_seed": BASE_SEED,
                    "derived_seed": derived_seed("BIDMC-v1.0.0", record_id, scenario),
                    "perturb_start_us": interval.perturb_start_us,
                    "perturb_end_us": interval.perturb_end_us,
                    "analysis_start_us": interval.analysis_start_us,
                    "analysis_end_us": interval.analysis_end_us,
                    "perturbed_modality": modality(scenario),
                    "perturbation_parameters": scenario,
                    "clean_source_hash": "T007_BIDMC_PROVIDER_HASH_MANIFEST",
                    "policy_id_hash": f"ALERT_POLICY_V1:{policy_sha}",
                    "model_id_hash": f"MODEL_V1:{model_sha}",
                }
            )
    interval = experiment_interval(600_000_000)
    for index in range(1, 9):
        session_id = f"SIM_T023_SESSION_{index:02d}"
        for scenario in (*SCENARIOS, *SIM_EXTRA_SCENARIOS):
            rows.append(
                {
                    "dataset_id": "WEARABLE_SIM_V1",
                    "session_id": session_id,
                    "scenario_id": scenario,
                    "base_seed": BASE_SEED,
                    "derived_seed": derived_seed("WEARABLE_SIM_V1", session_id, scenario),
                    "perturb_start_us": interval.perturb_start_us,
                    "perturb_end_us": interval.perturb_end_us,
                    "analysis_start_us": interval.analysis_start_us,
                    "analysis_end_us": interval.analysis_end_us,
                    "perturbed_modality": modality(scenario),
                    "perturbation_parameters": scenario,
                    "clean_source_hash": f"WEARABLE_SIM_V1:{session_id}",
                    "policy_id_hash": f"ALERT_POLICY_V1:{policy_sha}",
                    "model_id_hash": f"MODEL_V1:{model_sha}",
                }
            )
    path = ROOT / "reports/t023/scenario_manifest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def modality(scenario: str) -> str:
    if scenario.startswith("ECG_") or scenario == "MOTION_TAGGED":
        return "ECG"
    if scenario.startswith("PPG_") or scenario == "MISSING_PPG":
        return "PPG"
    if scenario == "CROSS_MODAL_RATE_DISAGREEMENT":
        return "PPG_RATE_CONTEXT"
    if scenario == "SPO2_UNAVAILABLE":
        return "SpO2"
    return "NONE"


def main() -> None:
    load_config(ROOT)
    write_manifest()
    audit = {
        "ECG_probability": {
            "episode_count": True,
            "suppression": False,
            "RECHECK_SENSOR": False,
            "top_level_state": True,
            "quality_warning_metadata": False,
        },
        "ECG_quality": {
            "episode_count": True,
            "suppression": True,
            "RECHECK_SENSOR": True,
            "top_level_state": True,
            "quality_warning_metadata": False,
        },
        "PPG_quality": {
            "episode_count": False,
            "suppression": False,
            "RECHECK_SENSOR": False,
            "top_level_state": True,
            "quality_warning_metadata": True,
        },
        "SpO2_validity": {
            "episode_count": False,
            "suppression": False,
            "RECHECK_SENSOR": False,
            "top_level_state": True,
            "quality_warning_metadata": False,
        },
        "ECG_PPG_disagreement": {
            "episode_count": False,
            "suppression": False,
            "RECHECK_SENSOR": False,
            "top_level_state": False,
            "quality_warning_metadata": True,
        },
        "confirmed_episode_count_structurally_context_invariant": True,
        "PRIMARY_EPISODE_CONTEXT_INVARIANCE_EXPECTED": True,
        "status": "PASS",
    }
    audit_path = ROOT / "reports/t023/policy_sensitivity_audit.json"
    write_json(audit_path, audit)
    bound = {
        "config": "configs/quality_aware_experiment_v1.yaml",
        "evaluator": "evaluation/quality_aware_alerts.py",
        "metrics": "evaluation/episode_metrics.py",
        "perturbations": "simulation/quality_perturbations.py",
        "scenario_manifest": "reports/t023/scenario_manifest.csv",
        "policy_sensitivity_audit": "reports/t023/policy_sensitivity_audit.json",
        "MODEL_V1": "checkpoints/MODEL_V1.pt",
        "CAL_V1": "artifacts/CAL_V1.json",
        "QUALITY_V1": "preprocessing/quality.py",
        "ECG_HR_CONTEXT_V2": "artifacts/ECG_HR_CONTEXT_V2.lock.json",
        "BIDMC_CONTEXT_V2": "artifacts/BIDMC_CONTEXT_V2.lock.json",
        "ALERT_POLICY_V1": "artifacts/ALERT_POLICY_V1.lock.json",
    }
    lock = {
        "experiment_id": "QUALITY_AWARE_EXPERIMENT_V1",
        "status": "FROZEN_EXPERIMENT_METHOD",
        "base_seed": BASE_SEED,
        "seed_rule": "SHA256(base|dataset|session|scenario), first 16 hex",
        "metric_direction": "quality_aware_excess_minus_ecg_only_excess",
        "paths": bound,
        "hashes": {name: sha256(ROOT / path) for name, path in bound.items()},
    }
    write_json(ROOT / "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json", lock)
    print("T023 method freeze: PASS")


if __name__ == "__main__":
    main()
