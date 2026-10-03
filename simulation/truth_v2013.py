"""WEARABLE_SIM V2-013 SimulationTruth side: the scheduled-fault / expected-quality truth used
ONLY by verification code AFTER runtime outputs exist. Never imported by the runtime/API/
gateway/frontend path (tests/test_v2_013_simulation.py enforces this statically and
behaviorally)."""

from __future__ import annotations

from simulation.profile_v2013 import IntegrationProfile

WINDOW_US = 10_000_000


def expected_window_quality(profile: IntegrationProfile, right_edge_us: int) -> str:
    """Truth-side expectation of the window ending at right_edge_us (analytic, not observed)."""
    start, end = right_edge_us - WINDOW_US, right_edge_us
    verdict = "VALID"
    for fault in profile.faults:
        a, b = int(fault.start_s * 1_000_000), int(fault.end_s * 1_000_000)
        if b <= start or a >= end:
            continue
        if fault.kind == "ECG_SHORT_GAP":
            verdict = "DEGRADED" if verdict == "VALID" else verdict
        else:
            return "UNUSABLE"
    return verdict


def expected_context_mode(profile: IntegrationProfile, right_edge_us: int) -> str:
    second = right_edge_us / 1_000_000
    for segment in profile.context:
        if segment.start_s <= second < segment.end_s:
            return segment.mode
    return "VALID"
