"""T023 deterministic paired ECG-only versus quality-aware operational experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from datasets.bidmc import DEFAULT_RAW_ROOT, list_records, load_lead_ii
from evaluation.bidmc_context import verify_bidmc_source
from evaluation.calibration import load_cal_v1, source_domain_calibrated_probability
from evaluation.episode_metrics import metrics_from_trace
from fusion.episode_manager import AlertEpisodeManager, load_alert_policy
from fusion.state_machine import FusionObservation
from models.model_freeze import load_frozen_model_v1
from preprocessing.context_resample import make_context_resampler
from preprocessing.ecg import StatefulECGFilter
from preprocessing.ecg_hr_context import XQRS_ID, estimate_hr
from preprocessing.quality import evaluate_ecg_quality
from preprocessing.windowing import normalize_window_zscore
from simulation.quality_perturbations import (
    BASE_SEED,
    SCENARIOS,
    SIM_EXTRA_SCENARIOS,
    Interval,
    apply_ecg_perturbation,
    derived_seed,
    experiment_interval,
    perturb_context,
)
from simulation.types import SAMPLE_CONTRACT_VERSION, ObservedRecord

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/quality_aware_experiment_v1.yaml"
TRACE_PATH = ROOT / "reports/t023/episode_event_trace.csv"
BIDMC_METRICS_PATH = ROOT / "reports/t023/bidmc_episode_metrics.csv"
SIM_METRICS_PATH = ROOT / "reports/t023/wearable_sim_episode_metrics.csv"
REPORT_PATH = ROOT / "reports/quality_aware_alerts.json"
SUMMARY_PATH = ROOT / "reports/quality_aware_alerts.csv"
MODEL_ID = "MODEL_V1"
CALIBRATION_ID = "CAL_V1"
ARMS = ("ECG_ONLY_MONITOR_V1", "QUALITY_AWARE_MONITOR_V1")
CONTEXT_SCENARIOS = {
    "PPG_CLIPPING",
    "PPG_DROPOUT",
    "MISSING_PPG",
    "CROSS_MODAL_RATE_DISAGREEMENT",
    "SPO2_UNAVAILABLE",
}
ECG_SCENARIOS = {"ECG_CLIPPING", "ECG_DROPOUT", "ECG_NOISE_0DB", "MOTION_TAGGED"}

TRACE_FIELDS = [
    "dataset_id",
    "session_id",
    "scenario_id",
    "arm_id",
    "timestamp_us",
    "source_domain_calibrated_probability",
    "raw_logit",
    "ecg_quality",
    "ppg_quality",
    "spo2_valid",
    "hr_ecg_bpm",
    "pr_ppg_bpm",
    "monitoring_state",
    "window_signal",
    "episode_opened",
    "episode_closed",
    "episode_active",
    "episode_count",
    "recheck_sensor",
    "context_available",
    "quality_warning",
    "context_injection",
    "analysis_horizon",
]

METRIC_FIELDS = [
    "dataset_id",
    "session_id",
    "scenario_id",
    "arm_id",
    "candidate_slots",
    "usable_slots",
    "candidate_monitoring_hours",
    "usable_monitoring_hours",
    "alert_episode_opens",
    "alert_episodes_per_usable_hour",
    "degradation_excess_alert_rate",
    "state_transitions",
    "state_chattering_per_hour",
    "degradation_excess_chattering_per_hour",
    "recheck_sensor_slots",
    "recheck_sensor_fraction",
    "recheck_sensor_entries",
    "recheck_sensor_entries_per_hour",
    "prediction_suppression_rate",
    "context_unavailable_fraction",
    "quality_warning_fraction",
    "quality_warning_runs",
    "quality_warning_duration_seconds",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def load_config(root: Path = ROOT) -> dict[str, Any]:
    config = yaml.safe_load((root / CONFIG_PATH.relative_to(ROOT)).read_text())
    if config["experiment_id"] != "QUALITY_AWARE_EXPERIMENT_V1":
        raise ValueError("T023_EXPERIMENT_ID_MISMATCH")
    if config["seed"]["base"] != BASE_SEED:
        raise ValueError("T023_SEED_MISMATCH")
    if tuple(config["scenarios"]) != SCENARIOS:
        raise ValueError("T023_SCENARIO_MISMATCH")
    shared = config["shared"]
    if (shared["open_K"], shared["close_M"], shared["cooldown_seconds"]) != (2, 2, 30):
        raise ValueError("T023_POLICY_SEMANTICS_MISMATCH")
    return config


def load_bidmc_context_rows(root: Path = ROOT) -> dict[tuple[str, int], dict[str, str]]:
    path = root / "reports/c021_hr_b/bidmc_context_rows_v2.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {(row["record_id"], int(row["timestamp_us"])): row for row in rows}


def _preprocess_bidmc(source: np.ndarray) -> np.ndarray:
    resampler = make_context_resampler("BIDMC_ECG_HR_125_TO_250_V1")
    values = resampler.process(np.asarray(source, dtype=np.float64), 0).values
    return StatefulECGFilter().process(values)


def _window_masks(
    timestamp_us: int,
    interval: Interval,
    scenario_id: str,
    sample_rate_hz: int = 250,
) -> tuple[np.ndarray | None, bool]:
    window_start = timestamp_us - 10_000_000
    sample_times = window_start + np.arange(2500, dtype=np.int64) * 1_000_000 // sample_rate_hz
    clipping = None
    long_gap = False
    if scenario_id == "ECG_CLIPPING":
        clipping = (sample_times >= interval.perturb_start_us) & (
            sample_times < interval.perturb_end_us
        )
    elif scenario_id == "ECG_DROPOUT":
        gap_start = interval.perturb_start_us + 20_000_000
        long_gap = bool(
            np.any((sample_times >= gap_start) & (sample_times < gap_start + 10_000_000))
        )
    return clipping, long_gap


def infer_windows(
    stream: np.ndarray,
    timestamps_us: list[int],
    scenario_id: str,
    interval: Interval,
    model: torch.nn.Module,
    cal: dict[str, Any],
    clean_fallback: dict[int, tuple[float, float]] | None = None,
) -> dict[int, dict[str, Any]]:
    windows: list[np.ndarray] = []
    infer_timestamps: list[int] = []
    result: dict[int, dict[str, Any]] = {}
    for timestamp_us in timestamps_us:
        end = timestamp_us * 250 // 1_000_000
        start = end - 2500
        window = np.asarray(stream[start:end], dtype=np.float64)
        clipping, long_gap = _window_masks(timestamp_us, interval, scenario_id)
        quality = evaluate_ecg_quality(
            window,
            clipping_mask=clipping,
            long_gap_spans=long_gap,
        ).state.value
        if quality == "UNUSABLE" or not np.all(np.isfinite(window)):
            fallback = (clean_fallback or {}).get(timestamp_us, (0.0, 0.5))
            result[timestamp_us] = {
                "raw_logit": fallback[0],
                "probability": fallback[1],
                "ecg_quality": "UNUSABLE",
                "suppressed": True,
            }
        else:
            windows.append(normalize_window_zscore(window).astype(np.float32))
            infer_timestamps.append(timestamp_us)
            result[timestamp_us] = {"ecg_quality": quality, "suppressed": False}
    if windows:
        inputs = torch.from_numpy(np.stack(windows)[:, None, :])
        with torch.inference_mode():
            logits = model(inputs).cpu().numpy().reshape(-1).astype(np.float64)
        probabilities = source_domain_calibrated_probability(logits, cal)
        for timestamp_us, logit, probability in zip(
            infer_timestamps, logits, probabilities, strict=True
        ):
            result[timestamp_us].update(raw_logit=float(logit), probability=float(probability))
    return result


def _bidmc_context(
    row: dict[str, str], scenario_id: str, timestamp_us: int, interval: Interval
) -> dict[str, object]:
    def optional(value: str) -> float | None:
        return float(value) if value else None

    return perturb_context(
        scenario_id,
        timestamp_us,
        interval,
        ppg_quality=row["ppg_quality"] or None,
        spo2_pct=optional(row["spo2_pct"]),
        spo2_valid=row["spo2_valid"] == "true",
        hr_ecg_bpm=optional(row["hr_ecg_bpm_v2"]),
        pr_ppg_bpm=optional(row["pr_ppg_bpm"]),
    )


def _sim_source(session_index: int, duration_seconds: int = 600) -> np.ndarray:
    fs = 250
    rng = np.random.Generator(np.random.PCG64(BASE_SEED + session_index))
    time = np.arange(duration_seconds * fs, dtype=np.float64) / fs
    rate = 60.0 + 3.0 * session_index
    signal = 0.04 * np.sin(2 * np.pi * 1.1 * time) + rng.normal(0, 0.01, time.size)
    beat_samples = np.arange(fs, time.size, max(1, round(60 * fs / rate)))
    kernel = np.asarray([0.2, 0.8, 1.8, 0.8, 0.2])
    for sample in beat_samples:
        if sample + kernel.size <= signal.size:
            signal[sample : sample + kernel.size] += kernel
    return signal


def _sim_runtime_record(
    session_id: str,
    timestamp_us: int,
    *,
    ecg_quality: str,
    context: dict[str, object],
) -> ObservedRecord:
    return ObservedRecord(
        contract_version=SAMPLE_CONTRACT_VERSION,
        participant_id=session_id.replace("SESSION", "P"),
        session_id=session_id,
        timestamp_us=timestamp_us,
        sample_index=timestamp_us * 250 // 1_000_000,
        ecg_raw=0 if ecg_quality != "UNUSABLE" else None,
        ppg_red_raw=18000 if context["ppg_quality"] is not None else None,
        ppg_ir_raw=19000 if context["ppg_quality"] is not None else None,
        spo2_pct=context["spo2_pct"],
        spo2_valid=bool(context["spo2_valid"]),
        hr_ecg_bpm=context["hr_ecg_bpm"],
        pr_ppg_bpm=context["pr_ppg_bpm"],
        ecg_quality=ecg_quality,
        ppg_quality=context["ppg_quality"],
        source="WEARABLE_SIM_V1",
        preprocess_version="PREPROC_V1",
    )


def replay_arms(
    dataset_id: str,
    session_id: str,
    scenario_id: str,
    timestamps_us: list[int],
    inference: dict[int, dict[str, Any]],
    contexts: dict[int, dict[str, object]],
    interval: Interval,
) -> list[dict[str, Any]]:
    policy = load_alert_policy(ROOT)
    trace: list[dict[str, Any]] = []
    for arm_id in ARMS:
        manager = AlertEpisodeManager(policy)
        manager.reset(session_id)
        for timestamp_us in timestamps_us:
            model_row = inference[timestamp_us]
            full = contexts[timestamp_us]
            if arm_id == "ECG_ONLY_MONITOR_V1":
                hr = full["hr_ecg_bpm"]
                context = {
                    "ppg_quality": "VALID",
                    "spo2_pct": 98.0,
                    "spo2_valid": True,
                    "hr_ecg_bpm": hr,
                    "pr_ppg_bpm": hr,
                    "context_injection": "ECG_ONLY_PROJECTION",
                }
            else:
                context = full
            observation = FusionObservation(
                session_id=session_id,
                timestamp_us=timestamp_us,
                source_domain_calibrated_probability=model_row["probability"],
                ecg_quality=model_row["ecg_quality"],
                ppg_quality=context["ppg_quality"],
                spo2_pct=context["spo2_pct"],
                spo2_valid=bool(context["spo2_valid"]),
                hr_ecg_bpm=context["hr_ecg_bpm"],
                hr_ecg_valid=context["hr_ecg_bpm"] is not None,
                pr_ppg_bpm=context["pr_ppg_bpm"],
                pr_ppg_valid=context["pr_ppg_bpm"] is not None,
                model_id=MODEL_ID,
                calibration_id=CALIBRATION_ID,
            )
            decision = manager.process(observation)
            trace.append(
                {
                    "dataset_id": dataset_id,
                    "session_id": session_id,
                    "scenario_id": scenario_id,
                    "arm_id": arm_id,
                    "timestamp_us": timestamp_us,
                    "source_domain_calibrated_probability": model_row["probability"],
                    "raw_logit": model_row["raw_logit"],
                    "ecg_quality": model_row["ecg_quality"],
                    "ppg_quality": context["ppg_quality"] or "UNAVAILABLE",
                    "spo2_valid": bool(context["spo2_valid"]),
                    "hr_ecg_bpm": context["hr_ecg_bpm"],
                    "pr_ppg_bpm": context["pr_ppg_bpm"],
                    "monitoring_state": decision.monitoring_state,
                    "window_signal": decision.window_signal,
                    "episode_opened": decision.episode_opened,
                    "episode_closed": decision.episode_closed,
                    "episode_active": decision.episode_active,
                    "episode_count": decision.episode_count,
                    "recheck_sensor": decision.monitoring_state == "RECHECK_SENSOR",
                    "context_available": decision.context_available,
                    "quality_warning": decision.quality_warning,
                    "context_injection": context["context_injection"],
                    "analysis_horizon": (
                        interval.analysis_start_us <= timestamp_us <= interval.analysis_end_us
                    ),
                }
            )
    return trace


def _add_metric_rows(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in trace:
        if row["analysis_horizon"]:
            grouped[
                (row["dataset_id"], row["session_id"], row["scenario_id"], row["arm_id"])
            ].append(row)
    output = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda row: row["timestamp_us"])
        output.append(
            dict(
                zip(("dataset_id", "session_id", "scenario_id", "arm_id"), key, strict=True),
                **metrics_from_trace(rows),
            )
        )
    clean = {
        (row["dataset_id"], row["session_id"], row["arm_id"]): row
        for row in output
        if row["scenario_id"] == "CLEAN_REFERENCE"
    }
    for row in output:
        baseline = clean[(row["dataset_id"], row["session_id"], row["arm_id"])]
        row["degradation_excess_alert_rate"] = (
            row["alert_episodes_per_usable_hour"] - baseline["alert_episodes_per_usable_hour"]
            if row["alert_episodes_per_usable_hour"] is not None
            and baseline["alert_episodes_per_usable_hour"] is not None
            else None
        )
        row["degradation_excess_chattering_per_hour"] = (
            row["state_chattering_per_hour"] - baseline["state_chattering_per_hour"]
        )
    return output


def _process_bidmc(model: torch.nn.Module, cal: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    verify_bidmc_source(root)
    context_rows = load_bidmc_context_rows(root)
    trace: list[dict[str, Any]] = []
    for record_id in list_records(root / DEFAULT_RAW_ROOT):
        session_rows = {
            timestamp: row
            for (record, timestamp), row in context_rows.items()
            if record == record_id and timestamp % 5_000_000 == 0
        }
        timestamps = sorted(session_rows)
        interval = experiment_interval(max(timestamps))
        clean_source = load_lead_ii(record_id, root / DEFAULT_RAW_ROOT)
        clean_stream = _preprocess_bidmc(clean_source)
        clean_inference = infer_windows(
            clean_stream, timestamps, "CLEAN_REFERENCE", interval, model, cal
        )
        clean_fallback = {
            timestamp: (row["raw_logit"], row["probability"])
            for timestamp, row in clean_inference.items()
        }
        inference_by_scenario = {scenario: clean_inference for scenario in SCENARIOS}
        for scenario in ECG_SCENARIOS & set(SCENARIOS):
            perturbed, _clipping, _gap = apply_ecg_perturbation(
                clean_source,
                sample_rate_hz=125,
                interval=interval,
                scenario_id=scenario,
                seed=derived_seed("BIDMC-v1.0.0", record_id, scenario),
            )
            finite = np.where(np.isfinite(perturbed), perturbed, 0.0)
            stream = _preprocess_bidmc(finite)
            inference_by_scenario[scenario] = infer_windows(
                stream, timestamps, scenario, interval, model, cal, clean_fallback
            )
        for scenario in SCENARIOS:
            contexts = {
                timestamp: _bidmc_context(session_rows[timestamp], scenario, timestamp, interval)
                for timestamp in timestamps
            }
            trace.extend(
                replay_arms(
                    "BIDMC-v1.0.0",
                    record_id,
                    scenario,
                    timestamps,
                    inference_by_scenario[scenario],
                    contexts,
                    interval,
                )
            )
    return trace


def _process_sim(model: torch.nn.Module, cal: dict[str, Any]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    scenarios = (*SCENARIOS, *SIM_EXTRA_SCENARIOS)
    for index in range(1, 9):
        session_id = f"SIM_T023_SESSION_{index:02d}"
        timestamps = list(range(10_000_000, 600_000_001, 5_000_000))
        interval = experiment_interval(600_000_000)
        clean_source = _sim_source(index)
        clean_stream = StatefulECGFilter().process(clean_source)
        clean_inference = infer_windows(
            clean_stream, timestamps, "CLEAN_REFERENCE", interval, model, cal
        )
        clean_fallback = {
            timestamp: (row["raw_logit"], row["probability"])
            for timestamp, row in clean_inference.items()
        }
        inference_by_scenario = {scenario: clean_inference for scenario in scenarios}
        for scenario in ECG_SCENARIOS:
            perturbed, _clipping, _gap = apply_ecg_perturbation(
                clean_source,
                sample_rate_hz=250,
                interval=interval,
                scenario_id=scenario,
                seed=derived_seed("WEARABLE_SIM_V1", session_id, scenario),
            )
            finite = np.where(np.isfinite(perturbed), perturbed, 0.0)
            stream = StatefulECGFilter().process(finite)
            inference_by_scenario[scenario] = infer_windows(
                stream, timestamps, scenario, interval, model, cal, clean_fallback
            )
        for scenario in scenarios:
            contexts: dict[int, dict[str, object]] = {}
            for timestamp in timestamps:
                window_end = timestamp * 250 // 1_000_000
                hr_result = estimate_hr(
                    clean_stream[window_end - 2500 : window_end],
                    timestamp_us=timestamp,
                    candidate_id=XQRS_ID,
                )
                base = perturb_context(
                    scenario,
                    timestamp,
                    interval,
                    ppg_quality="VALID",
                    spo2_pct=98.0,
                    spo2_valid=True,
                    hr_ecg_bpm=hr_result.hr_ecg_bpm,
                    pr_ppg_bpm=hr_result.hr_ecg_bpm,
                )
                if (
                    scenario == "MOTION_TAGGED"
                    and interval.perturb_start_us <= timestamp < interval.perturb_end_us
                ):
                    base["context_injection"] = "MOTION_TAGGED_GENERATOR_ONLY"
                record = _sim_runtime_record(
                    session_id,
                    timestamp,
                    ecg_quality=inference_by_scenario[scenario][timestamp]["ecg_quality"],
                    context=base,
                )
                record.to_canonical_dict()
                contexts[timestamp] = base
            trace.extend(
                replay_arms(
                    "WEARABLE_SIM_V1",
                    session_id,
                    scenario,
                    timestamps,
                    inference_by_scenario[scenario],
                    contexts,
                    interval,
                )
            )
    return trace


def _aggregate(metric_rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    scenarios = sorted({row["scenario_id"] for row in metric_rows})
    for scenario in scenarios:
        result[scenario] = {}
        by_arm = {
            arm: [
                row
                for row in metric_rows
                if row["scenario_id"] == scenario and row["arm_id"] == arm
            ]
            for arm in ARMS
        }
        for arm, rows in by_arm.items():
            opens = sum(int(row["alert_episode_opens"]) for row in rows)
            usable_hours = sum(float(row["usable_monitoring_hours"]) for row in rows)
            result[scenario][arm] = {
                "sessions": len(rows),
                "pooled_alert_episodes_per_usable_hour": opens / usable_hours
                if usable_hours
                else None,
                "record_macro_excess_alert_rate": float(
                    np.mean([row["degradation_excess_alert_rate"] for row in rows])
                ),
                "record_macro_chattering_per_hour": float(
                    np.mean([row["state_chattering_per_hour"] for row in rows])
                ),
                "record_macro_recheck_fraction": float(
                    np.mean([row["recheck_sensor_fraction"] for row in rows])
                ),
                "record_macro_recheck_entries_per_hour": float(
                    np.mean([row["recheck_sensor_entries_per_hour"] for row in rows])
                ),
                "record_macro_suppression_rate": float(
                    np.mean([row["prediction_suppression_rate"] for row in rows])
                ),
                "record_macro_context_unavailable_fraction": float(
                    np.mean([row["context_unavailable_fraction"] for row in rows])
                ),
                "record_macro_quality_warning_fraction": float(
                    np.mean([row["quality_warning_fraction"] for row in rows])
                ),
            }
        left = by_arm[ARMS[0]]
        right = by_arm[ARMS[1]]
        differences = np.asarray(
            [
                b["degradation_excess_alert_rate"] - a["degradation_excess_alert_rate"]
                for a, b in zip(left, right, strict=True)
            ]
        )
        result[scenario]["primary_contrast_B_minus_A"] = float(np.mean(differences))
        result[scenario]["record_distribution"] = {
            "B_lt_A": int(np.sum(differences < 0)),
            "B_eq_A": int(np.sum(differences == 0)),
            "B_gt_A": int(np.sum(differences > 0)),
            "median": float(np.median(differences)),
            "minimum": float(np.min(differences)),
            "maximum": float(np.max(differences)),
        }
    return result


def _quality_response(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        row
        for row in trace
        if row["arm_id"] == "QUALITY_AWARE_MONITOR_V1" and row["analysis_horizon"]
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["dataset_id"], row["scenario_id"])].append(row)
    output = []
    for (dataset, scenario), members in sorted(grouped.items()):
        ecg = Counter(row["ecg_quality"] for row in members)
        ppg = Counter(row["ppg_quality"] for row in members)
        total = len(members)
        output.append(
            {
                "dataset_id": dataset,
                "scenario_id": scenario,
                "slots": total,
                **{
                    f"ecg_{state.lower()}_fraction": ecg[state] / total
                    for state in ("VALID", "DEGRADED", "UNUSABLE")
                },
                **{
                    f"ppg_{state.lower()}_fraction": ppg[state] / total
                    for state in ("VALID", "DEGRADED", "UNUSABLE", "UNAVAILABLE")
                },
                "spo2_valid_fraction": sum(bool(row["spo2_valid"]) for row in members) / total,
                "quality_warning_fraction": sum(bool(row["quality_warning"]) for row in members)
                / total,
            }
        )
    return output


def run(root: Path = ROOT) -> None:
    load_config(root)
    model, _metadata = load_frozen_model_v1(root)
    model.eval()
    cal = load_cal_v1(root)
    bidmc_trace = _process_bidmc(model, cal, root)
    sim_trace = _process_sim(model, cal)
    trace = bidmc_trace + sim_trace
    metric_rows = _add_metric_rows(trace)
    bidmc_metrics = [row for row in metric_rows if row["dataset_id"] == "BIDMC-v1.0.0"]
    sim_metrics = [row for row in metric_rows if row["dataset_id"] == "WEARABLE_SIM_V1"]
    quality = _quality_response(trace)
    write_csv(TRACE_PATH, trace, TRACE_FIELDS)
    write_csv(BIDMC_METRICS_PATH, bidmc_metrics, METRIC_FIELDS)
    write_csv(SIM_METRICS_PATH, sim_metrics, METRIC_FIELDS)
    quality_fields = list(quality[0])
    write_csv(root / "reports/t023/quality_response_by_scenario.csv", quality, quality_fields)
    bidmc_aggregate = _aggregate(bidmc_metrics)
    sim_aggregate = _aggregate(sim_metrics)
    clean_healthy = [
        row
        for row in bidmc_trace
        if row["scenario_id"] == "CLEAN_REFERENCE" and row["analysis_horizon"]
    ]
    paired: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in clean_healthy:
        paired[(row["session_id"], row["timestamp_us"])][row["arm_id"]] = row
    healthy_pairs = [
        arms
        for arms in paired.values()
        if len(arms) == 2
        and arms[ARMS[1]]["ppg_quality"] == "VALID"
        and arms[ARMS[1]]["spo2_valid"]
        and not arms[ARMS[1]]["quality_warning"]
    ]
    matching = sum(
        arms[ARMS[0]]["episode_active"] == arms[ARMS[1]]["episode_active"]
        and arms[ARMS[0]]["episode_opened"] == arms[ARMS[1]]["episode_opened"]
        and arms[ARMS[0]]["episode_closed"] == arms[ARMS[1]]["episode_closed"]
        and arms[ARMS[0]]["monitoring_state"] == arms[ARMS[1]]["monitoring_state"]
        for arms in healthy_pairs
    )
    preservation = {
        "healthy_timestamps": len(healthy_pairs),
        "matching": matching,
        "fraction": matching / len(healthy_pairs) if healthy_pairs else None,
    }
    noise_row = next(
        row
        for row in quality
        if row["dataset_id"] == "BIDMC-v1.0.0" and row["scenario_id"] == "ECG_NOISE_0DB"
    )
    report = {
        "experiment_id": "QUALITY_AWARE_EXPERIMENT_V1",
        "method_lock": "artifacts/QUALITY_AWARE_EXPERIMENT_V1.lock.json",
        "calibration_domain": "MIT-BIH-v1.0.0",
        "BIDMC": bidmc_aggregate,
        "WEARABLE_SIM_V1_engineering_replay_only": sim_aggregate,
        "healthy_context_preservation": preservation,
        "structural_sensitivity": {
            "episode_transition_inputs": ["ECG probability", "ECG quality"],
            "context_only_episode_invariant": True,
            "PRIMARY_EPISODE_CONTEXT_INVARIANCE_EXPECTED": True,
            "RQ5_PRIMARY_EPISODE_RESULT": "NO_REDUCTION_UNDER_ALERT_POLICY_V1",
        },
        "QUALITY_V1_noise_sensitivity_limitation": noise_row["ecg_valid_fraction"] > 0.9,
        "no_AAMI_labels": True,
        "no_diagnostic_metrics": True,
        "no_learned_fusion": True,
        "no_tuning": True,
        "hardware_deferred": True,
        "WEARABLE_V1_pending_T030": True,
        "overall_status": "PASS_WITH_WARNINGS",
    }
    write_json(REPORT_PATH, report)
    summary_rows = []
    for dataset, aggregate in (
        ("BIDMC-v1.0.0", bidmc_aggregate),
        ("WEARABLE_SIM_V1", sim_aggregate),
    ):
        for scenario, values in aggregate.items():
            summary_rows.append(
                {
                    "dataset_id": dataset,
                    "scenario_id": scenario,
                    "primary_B_minus_A": values["primary_contrast_B_minus_A"],
                    "B_lt_A": values["record_distribution"]["B_lt_A"],
                    "B_eq_A": values["record_distribution"]["B_eq_A"],
                    "B_gt_A": values["record_distribution"]["B_gt_A"],
                }
            )
    write_csv(
        SUMMARY_PATH,
        summary_rows,
        ["dataset_id", "scenario_id", "primary_B_minus_A", "B_lt_A", "B_eq_A", "B_gt_A"],
    )
    print(
        json.dumps({"status": "PASS_WITH_WARNINGS", "healthy_preservation": preservation}, indent=2)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("use --run; verification is provided by scripts/verify_t023.py")
    run(ROOT)


if __name__ == "__main__":
    main()
