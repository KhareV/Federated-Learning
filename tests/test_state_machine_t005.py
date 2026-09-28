from dataclasses import dataclass

import pytest

from fusion.state_machine import (
    FIXTURE_STATE_POLICY_ID,
    MONITORING_STATES,
    POTENTIAL_PATTERN_SCORE_THRESHOLD,
    classify,
    classify_safe,
)

LOCKED_STATES = {
    "NORMAL_MONITORED_PATTERN",
    "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
    "RECHECK_SENSOR",
    "CONTEXT_UNAVAILABLE",
    "SYSTEM_ERROR",
}

PROHIBITED_WORDS = ("ARRHYTHMIA", "DISEASE", "PATIENT_HAS_AF", "CARDIAC_EMERGENCY", "DIAGNOSIS")


@dataclass(frozen=True)
class _Record:
    ecg_quality: str
    ppg_quality: str | None
    ppg_red_raw: int | None
    ppg_ir_raw: int | None
    spo2_pct: float | None


@dataclass(frozen=True)
class _Inference:
    raw_score: float | None


def test_locked_vocabulary_is_exact() -> None:
    assert MONITORING_STATES == LOCKED_STATES


def test_fixture_policy_id_is_versioned_and_not_alert_policy_v1() -> None:
    assert FIXTURE_STATE_POLICY_ID == "FIXTURE_STATE_POLICY_V0"
    assert FIXTURE_STATE_POLICY_ID != "ALERT_POLICY_V1"


def test_unusable_ecg_yields_recheck_sensor() -> None:
    record = _Record("UNUSABLE", "VALID", 100, 100, 98.0)
    inference = _Inference(raw_score=0.9)
    assert classify(record, inference) == "RECHECK_SENSOR"


def test_missing_context_yields_context_unavailable() -> None:
    record = _Record("VALID", None, None, None, None)
    inference = _Inference(raw_score=0.1)
    assert classify(record, inference) == "CONTEXT_UNAVAILABLE"


def test_degraded_but_present_context_is_not_context_unavailable() -> None:
    record = _Record("VALID", "DEGRADED", 100, 100, 98.0)
    inference = _Inference(raw_score=0.1)
    assert classify(record, inference) == "NORMAL_MONITORED_PATTERN"


def test_ordinary_score_yields_normal() -> None:
    record = _Record("VALID", "VALID", 100, 100, 98.0)
    inference = _Inference(raw_score=POTENTIAL_PATTERN_SCORE_THRESHOLD - 0.01)
    assert classify(record, inference) == "NORMAL_MONITORED_PATTERN"


def test_high_score_yields_potential_pattern() -> None:
    record = _Record("VALID", "VALID", 100, 100, 98.0)
    inference = _Inference(raw_score=POTENTIAL_PATTERN_SCORE_THRESHOLD)
    assert classify(record, inference) == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"


def test_unusable_ecg_takes_precedence_over_high_score() -> None:
    record = _Record("UNUSABLE", "VALID", 100, 100, 98.0)
    inference = _Inference(raw_score=0.99)
    assert classify(record, inference) == "RECHECK_SENSOR"


def test_malformed_input_yields_system_error_via_classify_safe() -> None:
    class _Broken:
        ecg_quality = "VALID"
        # Deliberately missing ppg_quality/ppg_red_raw/etc. to trigger AttributeError.

    inference = _Inference(raw_score=0.1)
    assert classify_safe(_Broken(), inference) == "SYSTEM_ERROR"


def test_classify_raises_on_malformed_input_without_safe_wrapper() -> None:
    class _Broken:
        ecg_quality = "VALID"

    inference = _Inference(raw_score=0.1)
    with pytest.raises(AttributeError):
        classify(_Broken(), inference)


def test_no_prohibited_wording_in_state_module_source() -> None:
    import inspect

    import fusion.state_machine as module

    source = inspect.getsource(module)
    for word in PROHIBITED_WORDS:
        assert word not in source


def test_no_debounce_or_cooldown_behavior_implemented() -> None:
    import fusion.state_machine as module

    assert not hasattr(module, "open_episode")
    assert not hasattr(module, "close_episode")
    assert not hasattr(module, "cooldown_seconds")
    assert not hasattr(module, "episodes_per_hour")
    assert not hasattr(module, "ALERT_POLICY_V1")
