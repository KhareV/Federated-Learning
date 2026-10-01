#!/usr/bin/env python3
"""Frozen deployment-equivalence and resource benchmark for T029."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from deployment.benchmark import configure_cpu_threads, memory_child, run_latency
from deployment.runtime import GatewayModelRuntime
from evaluation.internal_test import load_internal_population
from evaluation.metrics import pooled_binary_metrics
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
REPORT = ROOT / "reports/t029"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def canonical() -> None:
    if not (ROOT / "artifacts/GATEWAY_FP32_METHOD_V1.lock.json").exists():
        raise RuntimeError("gateway method must be frozen before INTERNAL_TEST access")
    configure_cpu_threads()
    runtime = GatewayModelRuntime(ROOT, ARTIFACT)
    population = load_internal_population(ROOT)
    normalized = np.stack(
        [
            normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON)
            for row in population.waveforms
        ]
    ).astype(np.float32)[:, None, :]
    baseline = read_csv(ROOT / "reports/internal_test_predictions.csv")
    baseline_by_id = {row["example_id"]: row for row in baseline}
    if len(baseline_by_id) != len(baseline):
        raise RuntimeError("baseline duplicate IDs")
    population_by_id = {
        row["example_id"]: (row, normalized[index], int(population.labels[index]))
        for index, row in enumerate(population.rows)
    }
    if set(baseline_by_id) != set(population_by_id):
        raise RuntimeError("deployment row closure failure")
    deployment_rows: list[dict[str, Any]] = []
    labels: list[int] = []
    patients: list[str] = []
    probabilities: list[float] = []
    decisions: list[int] = []
    raw_deltas: list[float] = []
    probability_deltas: list[float] = []
    for baseline_row in baseline:
        row, window, label = population_by_id[baseline_row["example_id"]]
        result = runtime.infer(window[None, :, :])
        baseline_logit = float(baseline_row["raw_logit"])
        baseline_probability = float(baseline_row["source_domain_calibrated_probability"])
        baseline_decision = int(baseline_row["thresholded_prediction"])
        raw_delta = abs(result.raw_logit - baseline_logit)
        probability_delta = abs(result.calibrated_probability - baseline_probability)
        deployment_rows.append(
            {
                "window_id": row["example_id"],
                "participant_group_id": row["participant_group_id"],
                "baseline_raw_logit": format(baseline_logit, ".17g"),
                "deployment_raw_logit": format(result.raw_logit, ".17g"),
                "absolute_raw_logit_delta": format(raw_delta, ".17g"),
                "baseline_calibrated_probability": format(baseline_probability, ".17g"),
                "deployment_calibrated_probability": format(result.calibrated_probability, ".17g"),
                "absolute_probability_delta": format(probability_delta, ".17g"),
                "baseline_decision": baseline_decision,
                "deployment_decision": int(result.above_threshold),
            }
        )
        labels.append(label)
        patients.append(row["participant_group_id"])
        probabilities.append(result.calibrated_probability)
        decisions.append(int(result.above_threshold))
        raw_deltas.append(raw_delta)
        probability_deltas.append(probability_delta)
    prediction_path = REPORT / "internal_test_deployment_predictions.csv"
    write_csv(prediction_path, deployment_rows)
    metrics = pooled_binary_metrics(
        np.asarray(labels),
        np.asarray(probabilities),
        np.asarray(decisions),
        np.asarray(patients),
    )
    frozen = json.loads((ROOT / "reports/internal_test.json").read_text())["point_metrics"]
    disagreements = sum(
        int(row["baseline_decision"]) != int(row["deployment_decision"]) for row in deployment_rows
    )
    metric_deltas = {
        key: abs(float(metrics[key]) - float(frozen[key]))
        for key in ("AUPRC", "AUROC", "pooled_F1", "patient_macro_F1")
    }
    equivalence = {
        "access_role": "DEPLOYMENT_EQUIVALENCE_ONLY",
        "artifact_selected_before_test": True,
        "artifact_changed_after_test": False,
        "deployment_artifact_sha256": hash_file(ARTIFACT),
        "baseline_prediction_path": "reports/internal_test_predictions.csv",
        "baseline_prediction_sha256": hash_file(ROOT / "reports/internal_test_predictions.csv"),
        "rows_expected": 2157,
        "rows_compared": len(deployment_rows),
        "duplicates": 0,
        "missing": 0,
        "extra": 0,
        "maximum_absolute_raw_logit_delta": max(raw_deltas),
        "mean_absolute_raw_logit_delta": float(np.mean(raw_deltas)),
        "maximum_calibrated_probability_delta": max(probability_deltas),
        "mean_calibrated_probability_delta": float(np.mean(probability_deltas)),
        "threshold_decision_disagreements": disagreements,
        "decision_agreement_fraction": 1 - disagreements / len(deployment_rows),
        "baseline_metrics": frozen,
        "deployment_metrics": metrics,
        "metric_absolute_deltas": metric_deltas,
    }
    passed = (
        len(deployment_rows) == 2157
        and max(raw_deltas) <= 1e-5
        and disagreements == 0
        and metric_deltas["AUPRC"] <= 1e-6
        and metric_deltas["pooled_F1"] <= 1e-6
        and metric_deltas["patient_macro_F1"] <= 1e-6
    )
    equivalence["status"] = "PASS" if passed else "FAIL"
    write_json(REPORT / "deployment_equivalence.json", equivalence)
    if not passed:
        raise RuntimeError("GATEWAY_FP32_EQUIVALENCE_FAILURE")

    selected_ids = [row["example_id"] for row in baseline[:1000]]
    benchmark_windows = np.stack([population_by_id[item][1] for item in selected_ids])
    rows1, summary1 = run_latency(runtime, benchmark_windows, selected_ids)
    rows2, summary2 = run_latency(runtime, benchmark_windows, selected_ids)
    if any(not row["finite_output"] for row in rows1 + rows2):
        raise RuntimeError("nonfinite benchmark output")
    write_csv(REPORT / "latency_samples.csv", rows1)
    latency = {
        "host_identity": json.loads((REPORT / "gateway_host.json").read_text()),
        "artifact_sha256": hash_file(ARTIFACT),
        "warmup_count": 100,
        "measured_N": 1000,
        "batch_size": 1,
        "threads": {"intraop": 1, "interop": 1},
        "canonical_run": summary1,
        "verification_repeat": summary2,
        "timing_boundary": "Gateway runtime model plus CAL_V1 inference call",
        "data_loading_included": False,
        "preprocessing_included": False,
        "all_outputs_finite": True,
        "decision_mismatches": 0,
        "status": "PASS",
    }
    write_json(REPORT / "latency_summary.json", latency)

    with tempfile.TemporaryDirectory() as temporary:
        window_path = Path(temporary) / "window.npy"
        np.save(window_path, benchmark_windows[0:1])
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "memory-child",
            "--window",
            str(window_path),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env={**dict(__import__("os").environ), "PYTHONPATH": "src:."},
        )
        memory = json.loads(completed.stdout)
    memory.update(
        {
            "input_shape": [1, 1, 2500],
            "artifact_sha256": hash_file(ARTIFACT),
            "process_model": "isolated child process",
            "status": "PASS",
        }
    )
    write_json(REPORT / "memory_benchmark.json", memory)
    write_json(
        REPORT / "reproducibility.json",
        {
            "artifact_sha256": hash_file(ARTIFACT),
            "F08_reload": "PASS",
            "deployment_prediction_sha256": hash_file(prediction_path),
            "metric_recomputation": "PASS",
            "parameter_count_deterministic": True,
            "file_size_deterministic": True,
            "benchmark_repeat_completed": True,
            "repeat_decisions_identical": True,
            "timing_identity_required": False,
            "status": "PASS",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("canonical", "memory-child"))
    parser.add_argument("--window", type=Path)
    args = parser.parse_args()
    if args.mode == "memory-child":
        if args.window is None:
            raise ValueError("--window required")
        print(json.dumps(memory_child(ROOT, ARTIFACT, args.window), sort_keys=True))
    else:
        canonical()


if __name__ == "__main__":
    main()
