"""FIXTURE_STATE_POLICY_V0 — a deliberately minimal, explicitly temporary state mapping
for the T005 vertical slice.

This is NOT `ALERT_POLICY_V1`. It has no 2-consecutive-open/close debounce, no 30-second
cooldown, and no episode metrics — those belong to later fusion/episode work. It exists only
to prove that an observed record + a mock inference result can be mapped to the locked v2.2
monitoring-state vocabulary.

Consumes only `ObservedRecord`/`MockInferenceResult`-shaped input. Must never import
`simulation.wearable` or otherwise gain access to `SimulationTruth`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

FIXTURE_STATE_POLICY_ID = "FIXTURE_STATE_POLICY_V0"

MONITORING_STATES = frozenset(
    {
        "NORMAL_MONITORED_PATTERN",
        "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
        "RECHECK_SENSOR",
        "CONTEXT_UNAVAILABLE",
        "SYSTEM_ERROR",
    }
)

# Arbitrary fixture-only threshold for the mock score, not a clinical or calibrated value.
POTENTIAL_PATTERN_SCORE_THRESHOLD = 0.75


class ObservedContextInput(Protocol):
    ecg_quality: str
    ppg_quality: str | None
    ppg_red_raw: int | None
    ppg_ir_raw: int | None
    spo2_pct: float | None


class InferenceInput(Protocol):
    raw_score: float | None


class RuntimeContextInput(Protocol):
    session_id: str
    timestamp_us: int
    ecg_quality: str
    ppg_quality: str | None
    spo2_pct: float | None
    spo2_valid: bool
    hr_ecg_bpm: float | None
    pr_ppg_bpm: float | None


def _context_available(record: ObservedContextInput) -> bool:
    return not (
        record.ppg_quality is None
        and record.ppg_red_raw is None
        and record.ppg_ir_raw is None
        and record.spo2_pct is None
    )


def classify(record: ObservedContextInput, inference: InferenceInput) -> str:
    """Map one observed record + mock inference result to a locked monitoring state.

    Precedence (deliberately simple; ALERT_POLICY_V1 will replace this):
    1. UNUSABLE ECG -> RECHECK_SENSOR
    2. PPG/context entirely absent -> CONTEXT_UNAVAILABLE
    3. mock score at/above the fixture threshold -> POTENTIAL_ECTOPY_ASSOCIATED_PATTERN
    4. otherwise -> NORMAL_MONITORED_PATTERN

    DEGRADED ecg_quality is treated the same as VALID here; ALERT_POLICY_V1's quality-aware
    nuance (R14.1) is explicitly deferred, not implemented in this fixture policy.
    """
    if record.ecg_quality == "UNUSABLE":
        return "RECHECK_SENSOR"
    if not _context_available(record):
        return "CONTEXT_UNAVAILABLE"
    score = inference.raw_score
    if score is not None and score >= POTENTIAL_PATTERN_SCORE_THRESHOLD:
        return "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"
    return "NORMAL_MONITORED_PATTERN"


def classify_safe(record: ObservedContextInput, inference: InferenceInput) -> str:
    """Like `classify`, but any internal failure maps to SYSTEM_ERROR instead of raising.

    This is the only path that may produce SYSTEM_ERROR; it is exercised by feeding a
    malformed/incomplete input directly (a truly broken record cannot appear in a valid
    golden fixture, since the fixture must remain schema-compliant).
    """
    try:
        return classify(record, inference)
    except (AttributeError, TypeError, ValueError):
        return "SYSTEM_ERROR"


class QualityState(StrEnum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    UNUSABLE = "UNUSABLE"


class WindowSignal(StrEnum):
    VALID_ABOVE_THRESHOLD = "VALID_ABOVE_THRESHOLD"
    VALID_BELOW_THRESHOLD = "VALID_BELOW_THRESHOLD"
    DEGRADED_ABOVE_THRESHOLD = "DEGRADED_ABOVE_THRESHOLD"
    DEGRADED_BELOW_THRESHOLD = "DEGRADED_BELOW_THRESHOLD"
    UNUSABLE = "UNUSABLE"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class MonitoringState(StrEnum):
    NORMAL_MONITORED_PATTERN = "NORMAL_MONITORED_PATTERN"
    POTENTIAL_ECTOPY_ASSOCIATED_PATTERN = "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"
    RECHECK_SENSOR = "RECHECK_SENSOR"
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass(frozen=True)
class FusionObservation:
    session_id: str
    timestamp_us: int
    source_domain_calibrated_probability: float
    ecg_quality: str
    ppg_quality: str | None
    spo2_pct: float | None
    spo2_valid: bool
    hr_ecg_bpm: float | None
    hr_ecg_valid: bool
    pr_ppg_bpm: float | None
    pr_ppg_valid: bool
    model_id: str
    calibration_id: str
    system_error: bool = False


@dataclass(frozen=True)
class FusionDecision:
    timestamp_us: int
    monitoring_state: str
    window_signal: str
    episode_active: bool
    episode_opened: bool
    episode_closed: bool
    episode_count: int
    open_counter: int
    close_counter: int
    cooldown_active: bool
    cooldown_until_us: int | None
    possible_pattern: bool
    context_available: bool
    quality_warning: bool
    quality_warning_reasons: tuple[str, ...]
    ecg_quality: str
    ppg_quality: str | None
    hr_ecg_bpm: float | None
    pr_ppg_bpm: float | None
    spo2_pct: float | None
    spo2_valid: bool
    source_domain_calibrated_probability: float
    threshold: float
    alert_policy_id: str


def observation_from_runtime(
    record: RuntimeContextInput,
    *,
    source_domain_calibrated_probability: float,
    model_id: str,
    calibration_id: str,
) -> FusionObservation:
    """Adapt the canonical observed runtime shape without importing simulator internals."""
    return FusionObservation(
        session_id=record.session_id,
        timestamp_us=record.timestamp_us,
        source_domain_calibrated_probability=source_domain_calibrated_probability,
        ecg_quality=record.ecg_quality,
        ppg_quality=record.ppg_quality,
        spo2_pct=record.spo2_pct,
        spo2_valid=record.spo2_valid,
        hr_ecg_bpm=record.hr_ecg_bpm,
        hr_ecg_valid=record.hr_ecg_bpm is not None,
        pr_ppg_bpm=record.pr_ppg_bpm,
        pr_ppg_valid=record.pr_ppg_bpm is not None,
        model_id=model_id,
        calibration_id=calibration_id,
    )


def validate_observation(observation: FusionObservation) -> None:
    if not observation.session_id:
        raise ValueError("EMPTY_SESSION_ID")
    if observation.timestamp_us < 0:
        raise ValueError("NEGATIVE_TIMESTAMP")
    probability = observation.source_domain_calibrated_probability
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("INVALID_CALIBRATED_PROBABILITY")
    if observation.ecg_quality not in {state.value for state in QualityState}:
        raise ValueError("INVALID_ECG_QUALITY")
    if observation.ppg_quality is not None and observation.ppg_quality not in {
        state.value for state in QualityState
    }:
        raise ValueError("INVALID_PPG_QUALITY")
    for value, valid, name in (
        (observation.hr_ecg_bpm, observation.hr_ecg_valid, "ECG_HR"),
        (observation.pr_ppg_bpm, observation.pr_ppg_valid, "PPG_PR"),
    ):
        if value is not None and not math.isfinite(value):
            raise ValueError(f"NONFINITE_{name}")
        if valid and (value is None or value <= 0):
            raise ValueError(f"INVALID_VALID_{name}")
    if observation.spo2_valid and (
        observation.spo2_pct is None
        or not math.isfinite(observation.spo2_pct)
        or not 0.0 <= observation.spo2_pct <= 100.0
    ):
        raise ValueError("INVALID_VALID_SPO2")


def window_signal(observation: FusionObservation, threshold: float) -> WindowSignal:
    if observation.system_error:
        return WindowSignal.SYSTEM_ERROR
    above = observation.source_domain_calibrated_probability >= threshold
    if observation.ecg_quality == QualityState.UNUSABLE.value:
        return WindowSignal.UNUSABLE
    if observation.ecg_quality == QualityState.DEGRADED.value:
        return (
            WindowSignal.DEGRADED_ABOVE_THRESHOLD
            if above
            else WindowSignal.DEGRADED_BELOW_THRESHOLD
        )
    return WindowSignal.VALID_ABOVE_THRESHOLD if above else WindowSignal.VALID_BELOW_THRESHOLD


def context_available(observation: FusionObservation) -> bool:
    ppg_available = observation.ppg_quality not in (None, QualityState.UNUSABLE.value)
    return ppg_available and observation.spo2_valid


def public_monitoring_state(
    signal: WindowSignal,
    *,
    episode_active: bool,
    has_context: bool,
) -> tuple[MonitoringState, bool]:
    """Apply the frozen public-state precedence; warning metadata is deliberately separate."""
    if signal is WindowSignal.SYSTEM_ERROR:
        return MonitoringState.SYSTEM_ERROR, False
    if signal is WindowSignal.UNUSABLE:
        return MonitoringState.RECHECK_SENSOR, False
    if signal is WindowSignal.DEGRADED_ABOVE_THRESHOLD:
        return MonitoringState.RECHECK_SENSOR, True
    if episode_active:
        return MonitoringState.POTENTIAL_ECTOPY_ASSOCIATED_PATTERN, False
    if not has_context:
        return MonitoringState.CONTEXT_UNAVAILABLE, False
    return MonitoringState.NORMAL_MONITORED_PATTERN, False
