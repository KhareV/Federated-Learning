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
