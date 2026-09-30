from __future__ import annotations

from evaluation.quality_aware_alerts import replay_arms
from simulation.quality_perturbations import experiment_interval


def _inputs(context_missing: bool = False):
    timestamps = [10_000_000, 15_000_000, 20_000_000]
    inference = {
        timestamp: {"probability": probability, "raw_logit": 1.0, "ecg_quality": "VALID"}
        for timestamp, probability in zip(timestamps, (0.1, 0.9, 0.9), strict=True)
    }
    contexts = {
        timestamp: {
            "ppg_quality": None if context_missing else "VALID",
            "spo2_pct": None if context_missing else 98.0,
            "spo2_valid": not context_missing,
            "hr_ecg_bpm": 70.0,
            "pr_ppg_bpm": None if context_missing else 70.0,
            "context_injection": "TEST",
        }
        for timestamp in timestamps
    }
    return timestamps, inference, contexts


def test_healthy_context_preserves_episode_and_state() -> None:
    timestamps, inference, contexts = _inputs()
    trace = replay_arms(
        "TEST",
        "SESSION",
        "CLEAN_REFERENCE",
        timestamps,
        inference,
        contexts,
        experiment_interval(300_000_000),
    )
    left, right = trace[:3], trace[3:]
    assert [row["episode_opened"] for row in left] == [row["episode_opened"] for row in right]
    assert [row["monitoring_state"] for row in left] == [row["monitoring_state"] for row in right]


def test_missing_context_cannot_change_episode_transitions() -> None:
    timestamps, inference, contexts = _inputs(context_missing=True)
    trace = replay_arms(
        "TEST",
        "SESSION",
        "MISSING_PPG",
        timestamps,
        inference,
        contexts,
        experiment_interval(300_000_000),
    )
    left, right = trace[:3], trace[3:]
    assert [row["episode_opened"] for row in left] == [row["episode_opened"] for row in right]
    assert right[0]["monitoring_state"] == "CONTEXT_UNAVAILABLE"
    assert right[-1]["monitoring_state"] == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"


def test_both_arms_consume_identical_probability_rows() -> None:
    timestamps, inference, contexts = _inputs(context_missing=True)
    trace = replay_arms(
        "TEST",
        "SESSION",
        "MISSING_PPG",
        timestamps,
        inference,
        contexts,
        experiment_interval(300_000_000),
    )
    assert [row["source_domain_calibrated_probability"] for row in trace[:3]] == [
        row["source_domain_calibrated_probability"] for row in trace[3:]
    ]
