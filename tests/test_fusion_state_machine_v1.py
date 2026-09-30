from __future__ import annotations

import math

import pytest

from fusion.episode_manager import AlertEpisodeManager, load_alert_policy
from fusion.state_machine import FusionObservation, MonitoringState, WindowSignal


def observation(
    timestamp_us: int,
    probability: float,
    *,
    ecg_quality: str = "VALID",
    ppg_quality: str | None = "VALID",
    spo2_pct: float | None = 98.0,
    spo2_valid: bool = True,
    hr_ecg_bpm: float | None = 70.0,
    hr_ecg_valid: bool = True,
    pr_ppg_bpm: float | None = 70.0,
    pr_ppg_valid: bool = True,
    session_id: str = "S1",
    system_error: bool = False,
) -> FusionObservation:
    return FusionObservation(
        session_id=session_id,
        timestamp_us=timestamp_us,
        source_domain_calibrated_probability=probability,
        ecg_quality=ecg_quality,
        ppg_quality=ppg_quality,
        spo2_pct=spo2_pct,
        spo2_valid=spo2_valid,
        hr_ecg_bpm=hr_ecg_bpm,
        hr_ecg_valid=hr_ecg_valid,
        pr_ppg_bpm=pr_ppg_bpm,
        pr_ppg_valid=pr_ppg_valid,
        model_id="MODEL_V1",
        calibration_id="CAL_V1",
        system_error=system_error,
    )


def manager() -> AlertEpisodeManager:
    return AlertEpisodeManager(load_alert_policy())


def test_threshold_equality_is_above_and_counts_toward_opening() -> None:
    machine = manager()
    threshold = machine.policy.threshold
    first = machine.process(observation(0, threshold))
    second = machine.process(observation(5_000_000, threshold))
    assert first.window_signal == WindowSignal.VALID_ABOVE_THRESHOLD.value
    assert first.open_counter == 1
    assert second.episode_opened is True


@pytest.mark.parametrize(
    ("quality", "probability_delta", "expected_signal"),
    [
        ("VALID", 0.1, WindowSignal.VALID_ABOVE_THRESHOLD.value),
        ("VALID", -0.1, WindowSignal.VALID_BELOW_THRESHOLD.value),
        ("DEGRADED", 0.1, WindowSignal.DEGRADED_ABOVE_THRESHOLD.value),
        ("DEGRADED", -0.1, WindowSignal.DEGRADED_BELOW_THRESHOLD.value),
        ("UNUSABLE", 0.1, WindowSignal.UNUSABLE.value),
    ],
)
def test_window_signal_mapping(
    quality: str, probability_delta: float, expected_signal: str
) -> None:
    machine = manager()
    decision = machine.process(
        observation(0, machine.policy.threshold + probability_delta, ecg_quality=quality)
    )
    assert decision.window_signal == expected_signal


def test_public_state_precedence() -> None:
    machine = manager()
    high = machine.policy.threshold + 0.1
    assert (
        machine.process(observation(0, high, system_error=True)).monitoring_state == "SYSTEM_ERROR"
    )
    machine.reset("S1")
    assert (
        machine.process(observation(0, high, ecg_quality="UNUSABLE")).monitoring_state
        == "RECHECK_SENSOR"
    )
    machine.reset("S1")
    degraded = machine.process(observation(0, high, ecg_quality="DEGRADED"))
    assert degraded.monitoring_state == "RECHECK_SENSOR"
    assert degraded.possible_pattern is True


def test_context_unavailable_preserves_probability_and_partial_values() -> None:
    machine = manager()
    probability = machine.policy.threshold - 0.1
    decision = machine.process(
        observation(
            0,
            probability,
            ppg_quality="VALID",
            spo2_pct=None,
            spo2_valid=False,
            pr_ppg_bpm=72.0,
        )
    )
    assert decision.monitoring_state == MonitoringState.CONTEXT_UNAVAILABLE.value
    assert decision.context_available is False
    assert decision.source_domain_calibrated_probability == probability
    assert decision.threshold == machine.policy.threshold
    assert decision.pr_ppg_bpm == 72.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timestamp_us": -1},
        {"probability": math.nan},
        {"probability": 1.01},
        {"ecg_quality": "UNKNOWN"},
        {"ppg_quality": "UNKNOWN"},
        {"hr_ecg_bpm": 0.0, "hr_ecg_valid": True},
        {"pr_ppg_bpm": math.inf, "pr_ppg_valid": True},
        {"spo2_pct": 101.0, "spo2_valid": True},
    ],
)
def test_invalid_observations_are_rejected(kwargs: dict[str, object]) -> None:
    machine = manager()
    values: dict[str, object] = {"timestamp_us": 0, "probability": 0.1}
    values.update(kwargs)
    with pytest.raises(ValueError):
        machine.process(observation(**values))  # type: ignore[arg-type]


def test_nonmonotonic_timestamp_and_session_change_are_rejected() -> None:
    machine = manager()
    machine.process(observation(5, 0.1))
    with pytest.raises(ValueError, match="NON_MONOTONIC"):
        machine.process(observation(5, 0.1))
    with pytest.raises(ValueError, match="SESSION_CHANGE"):
        machine.process(observation(10, 0.1, session_id="S2"))
