from __future__ import annotations

from fusion.episode_manager import AlertEpisodeManager, load_alert_policy
from fusion.state_machine import observation_from_runtime
from simulation.profiles import SMOKE_SCENARIO
from simulation.wearable import generate_participant, generate_session, iter_observed_records
from tests.test_fusion_state_machine_v1 import observation


def manager() -> AlertEpisodeManager:
    return AlertEpisodeManager(load_alert_policy())


def test_rate_disagreement_exact_duration_and_value_retention() -> None:
    machine = manager()
    low = machine.policy.threshold - 0.1
    decisions = [
        machine.process(observation(timestamp, low, hr_ecg_bpm=70.0, pr_ppg_bpm=95.0))
        for timestamp in (0, 5_000_000, 9_999_999, 10_000_000)
    ]
    assert [decision.quality_warning for decision in decisions] == [False, False, False, True]
    assert decisions[-1].quality_warning_reasons == ("ECG_PPG_RATE_DISAGREEMENT",)
    assert decisions[-1].hr_ecg_bpm == 70.0
    assert decisions[-1].pr_ppg_bpm == 95.0


def test_exact_tolerance_does_not_warn() -> None:
    machine = manager()
    low = machine.policy.threshold - 0.1
    assert not machine.process(observation(0, low, hr_ecg_bpm=70, pr_ppg_bpm=90)).quality_warning
    assert not machine.process(
        observation(10_000_000, low, hr_ecg_bpm=70, pr_ppg_bpm=90)
    ).quality_warning


def test_agreement_invalid_rate_and_unusable_ppg_reset_timer() -> None:
    low = load_alert_policy().threshold - 0.1
    reset_cases = (
        {"hr_ecg_bpm": 70.0, "pr_ppg_bpm": 80.0},
        {"hr_ecg_bpm": None, "hr_ecg_valid": False, "pr_ppg_bpm": 95.0},
        {"hr_ecg_bpm": 70.0, "pr_ppg_bpm": 95.0, "ppg_quality": "UNUSABLE"},
    )
    for reset_case in reset_cases:
        machine = manager()
        machine.process(observation(0, low, hr_ecg_bpm=70, pr_ppg_bpm=95))
        machine.process(observation(5_000_000, low, hr_ecg_bpm=70, pr_ppg_bpm=95))
        reset = machine.process(observation(8_000_000, low, **reset_case))
        assert reset.quality_warning is False
        after = machine.process(observation(13_000_000, low, hr_ecg_bpm=70, pr_ppg_bpm=95))
        assert after.quality_warning is False
        assert not machine.process(
            observation(18_000_000, low, hr_ecg_bpm=70, pr_ppg_bpm=95)
        ).quality_warning
        assert machine.process(
            observation(23_000_000, low, hr_ecg_bpm=70, pr_ppg_bpm=95)
        ).quality_warning


def test_missing_context_does_not_block_opening_or_hide_active_episode() -> None:
    machine = manager()
    high = machine.policy.threshold + 0.1
    kwargs = {
        "ppg_quality": None,
        "pr_ppg_bpm": None,
        "pr_ppg_valid": False,
        "spo2_pct": None,
        "spo2_valid": False,
    }
    first = machine.process(observation(0, high, **kwargs))
    second = machine.process(observation(5_000_000, high, **kwargs))
    assert first.monitoring_state == "CONTEXT_UNAVAILABLE"
    assert second.episode_opened is True
    assert second.monitoring_state == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"
    assert second.context_available is False


def test_wearable_sim_observed_record_uses_same_production_path() -> None:
    participant = generate_participant(1, 20260927)
    session = generate_session(
        participant,
        SMOKE_SCENARIO,
        session_id="SIM_POLICY_TEST",
        session_seed=20260927,
        profile="SMOKE",
    )
    record = next(iter_observed_records(session))
    policy = load_alert_policy()
    adapted = observation_from_runtime(
        record,
        source_domain_calibrated_probability=policy.threshold - 0.1,
        model_id="MODEL_V1",
        calibration_id="CAL_V1",
    )
    decision = AlertEpisodeManager(policy).process(adapted)
    assert decision.alert_policy_id == "ALERT_POLICY_V1"
    assert decision.monitoring_state == "NORMAL_MONITORED_PATTERN"
