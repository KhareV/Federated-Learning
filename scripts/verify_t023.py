#!/usr/bin/env python3
"""Verification-only T023 checks from frozen trace and metric artifacts."""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.episode_metrics import metrics_from_trace  # noqa: E402
from evaluation.quality_aware_alerts import ARMS, sha256  # noqa: E402
from simulation.quality_perturbations import SCENARIOS, SIM_EXTRA_SCENARIOS  # noqa: E402


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def truth(value: str) -> bool:
    return value == "True"


def parsed_trace(root: Path = ROOT) -> list[dict[str, Any]]:
    rows = load_csv(root / "reports/t023/episode_event_trace.csv")
    booleans = {
        "spo2_valid",
        "episode_opened",
        "episode_closed",
        "episode_active",
        "recheck_sensor",
        "context_available",
        "quality_warning",
        "analysis_horizon",
    }
    for row in rows:
        row["timestamp_us"] = int(row["timestamp_us"])
        row["episode_count"] = int(row["episode_count"])
        for field in booleans:
            row[field] = truth(row[field])
    return rows


def verify_method_lock(root: Path = ROOT) -> dict[str, Any]:
    lock = json.loads((root / "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json").read_text())
    for name, path in lock["paths"].items():
        if sha256(root / path) != lock["hashes"][name]:
            raise RuntimeError(f"T023_METHOD_LOCK_MISMATCH: {name}")
    return lock


def _close(actual: str, expected: float | int | None) -> bool:
    if expected is None:
        return actual == ""
    return math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12)


def verify() -> dict[str, Any]:
    lock = verify_method_lock(ROOT)
    trace = parsed_trace(ROOT)
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in trace:
        grouped[
            (row["dataset_id"], row["session_id"], row["scenario_id"], row["timestamp_us"])
        ].append(row)
    for key, pair in grouped.items():
        if len(pair) != 2 or {row["arm_id"] for row in pair} != set(ARMS):
            raise RuntimeError(f"T023_ARM_PAIR_CLOSURE_FAILURE: {key}")
        if len({row["source_domain_calibrated_probability"] for row in pair}) != 1:
            raise RuntimeError(f"T023_ARM_MODEL_OUTPUT_MISMATCH: {key}")
        if len({row["ecg_quality"] for row in pair}) != 1:
            raise RuntimeError(f"T023_ARM_ECG_QUALITY_MISMATCH: {key}")

    metric_files = (
        ROOT / "reports/t023/bidmc_episode_metrics.csv",
        ROOT / "reports/t023/wearable_sim_episode_metrics.csv",
    )
    metric_rows = [row for path in metric_files for row in load_csv(path)]
    trace_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in trace:
        if row["analysis_horizon"]:
            trace_groups[
                (row["dataset_id"], row["session_id"], row["scenario_id"], row["arm_id"])
            ].append(row)
    metric_names = (
        "candidate_slots",
        "usable_slots",
        "alert_episode_opens",
        "state_transitions",
        "recheck_sensor_slots",
        "recheck_sensor_entries",
        "prediction_suppression_rate",
        "context_unavailable_fraction",
        "quality_warning_fraction",
        "quality_warning_runs",
    )
    for row in metric_rows:
        key = (row["dataset_id"], row["session_id"], row["scenario_id"], row["arm_id"])
        recomputed = metrics_from_trace(
            sorted(trace_groups[key], key=lambda item: item["timestamp_us"])
        )
        for name in metric_names:
            if not _close(row[name], recomputed[name]):
                raise RuntimeError(f"T023_METRIC_TRACEABILITY_FAILURE: {key}:{name}")

    datasets = defaultdict(set)
    for row in metric_rows:
        datasets[row["dataset_id"]].add(row["scenario_id"])
    if datasets["BIDMC-v1.0.0"] != set(SCENARIOS):
        raise RuntimeError("T023_BIDMC_SCENARIO_CLOSURE_FAILURE")
    if datasets["WEARABLE_SIM_V1"] != set((*SCENARIOS, *SIM_EXTRA_SCENARIOS)):
        raise RuntimeError("T023_SIM_SCENARIO_CLOSURE_FAILURE")
    if len({row["session_id"] for row in metric_rows if row["dataset_id"] == "BIDMC-v1.0.0"}) != 53:
        raise RuntimeError("T023_BIDMC_RECORD_CLOSURE_FAILURE")
    if (
        len({row["session_id"] for row in metric_rows if row["dataset_id"] == "WEARABLE_SIM_V1"})
        != 8
    ):
        raise RuntimeError("T023_SIM_SESSION_CLOSURE_FAILURE")

    report = json.loads((ROOT / "reports/quality_aware_alerts.json").read_text())
    if report["healthy_context_preservation"]["fraction"] != 1.0:
        raise RuntimeError("T023_HEALTHY_CONTEXT_PRESERVATION_FAILURE")
    for scenario in SCENARIOS:
        if report["BIDMC"][scenario]["primary_contrast_B_minus_A"] != 0.0:
            raise RuntimeError("T023_STRUCTURAL_EPISODE_INVARIANCE_FAILURE")
    quality = load_csv(ROOT / "reports/t023/quality_response_by_scenario.csv")
    noise = next(
        row
        for row in quality
        if row["dataset_id"] == "BIDMC-v1.0.0" and row["scenario_id"] == "ECG_NOISE_0DB"
    )
    if float(noise["ecg_valid_fraction"]) != 1.0:
        raise RuntimeError("T023_QUALITY_NOISE_FINDING_MISMATCH")
    mismatch = next(
        row
        for row in quality
        if row["dataset_id"] == "BIDMC-v1.0.0"
        and row["scenario_id"] == "CROSS_MODAL_RATE_DISAGREEMENT"
    )
    if float(mismatch["quality_warning_fraction"]) <= 0:
        raise RuntimeError("T023_RATE_WARNING_PERTURBATION_FAILURE")
    with (ROOT / "manifests/task_registry_v1.csv").open(newline="", encoding="utf-8") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    if tasks["T023"]["status"] != "PASS" or tasks["T024"]["status"] != "NOT_STARTED":
        raise RuntimeError("T023_TASK_REGISTRY_MISMATCH")
    with (ROOT / "manifests/gate_registry_v1.csv").open(newline="", encoding="utf-8") as handle:
        gates = {row["gate_id"]: row for row in csv.DictReader(handle)}
    if gates["G9"]["status"] == "PASS" or gates["G10"]["status"] != "PASS":
        raise RuntimeError("T023_GATE_REGISTRY_MISMATCH")
    return {
        "status": "PASS_WITH_WARNINGS",
        "method_lock": "PASS",
        "trace_rows": len(trace),
        "metric_rows": len(metric_rows),
        "BIDMC_records": 53,
        "WEARABLE_SIM_sessions": 8,
        "arm_pairing": "PASS",
        "metric_traceability": "PASS",
        "healthy_context_preservation": 1.0,
        "structural_episode_invariance": "PASS",
        "method_lock_sha256": sha256(ROOT / "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json"),
        "lock_status": lock["status"],
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
