"""WEARABLE_SIM_V1 generator kernel.

Implements only what the T005 vertical slice needs: deterministic virtual participants,
one smoke scenario, and iterators over `ObservedRecord`/`SimulationTruth`. Full physiological
morphology synthesis, large-cohort materialization, and additional simulator modes are
explicitly out of scope for T005 (contracts/WEARABLE_SIM_V1.md Section 15) but this module's
interfaces (`generate_participant`, `generate_session`, `iter_observed_records`, `get_truth`)
are designed so later tasks can extend the engine without changing consumers.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

from simulation import SIMULATION_VERSION
from simulation.types import (
    SAMPLE_CONTRACT_VERSION,
    ObservedRecord,
    SegmentSpec,
    SimulationScenario,
    SimulationSession,
    SimulationTruth,
    VirtualParticipant,
)

DATASET_ID = "WEARABLE_SIM_V1"
DEFAULT_SOURCE_MODE = "SYNTHETIC_PHYSIOLOGY"

# Nominal simulated sample spacing: the project's LOCKED_BY_SPEC canonical ECG target
# (250 Hz -> 4000 microseconds/sample). This is a *simulation timeline* choice, not a claim
# that any physical device has been measured at this rate — see
# contracts/HARDWARE_DATA_CONTRACT_V1.md Section 7 (VERIFICATION_REQUIRED) and Section 10 of
# the T005 execution instructions. The smoke fixture is sparse (a handful of samples per
# scenario segment) and does not represent a continuous high-rate stream.
NOMINAL_TIMESTAMP_STEP_US = 4000

# The deterministic mock-inference score formula lives entirely in
# deployment/mock_inference.py, which consumes only ObservedRecord fields — it does not
# import from this generator module, keeping the "score depends only on observed data"
# property structurally obvious rather than merely conventional.
_STATE_NORMAL_OFFSET = 100
_STATE_MOCK_EVENT_OFFSET = 2000


def participant_id_for_index(index: int) -> str:
    return f"SIM_P{index:06d}"


def _combined_seed(*parts: object) -> str:
    """Combine heterogeneous seed parts into one deterministic string seed.

    `random.Random` only accepts None/int/float/str/bytes/bytearray, not tuples, so
    composite seeds (e.g. simulation seed + session id) are joined into a single string.
    """
    return "|".join(str(part) for part in parts)


def generate_participant(index: int, seed: int) -> VirtualParticipant:
    """Deterministically derive a virtual participant from an index and seed."""
    rng = random.Random(_combined_seed(seed, index))
    return VirtualParticipant(
        participant_id=participant_id_for_index(index),
        participant_seed=seed,
        baseline_ecg_level=2200 + rng.randint(-20, 20),
        baseline_ppg_red=18000 + rng.randint(-200, 200),
        baseline_ppg_ir=19000 + rng.randint(-200, 200),
        nominal_pulse_rate=72.0 + rng.uniform(-3.0, 3.0),
        nominal_spo2=97.5 + rng.uniform(-0.5, 0.5),
        device_offset=rng.randint(-5, 5),
    )


def generate_session(
    participant: VirtualParticipant,
    scenario: SimulationScenario,
    *,
    session_id: str,
    session_seed: int,
    source_mode: str = DEFAULT_SOURCE_MODE,
    profile: str,
) -> SimulationSession:
    return SimulationSession(
        session_id=session_id,
        participant=participant,
        scenario=scenario,
        simulation_version=SIMULATION_VERSION,
        simulation_seed=session_seed,
        dataset_id=DATASET_ID,
        source_mode=source_mode,
        profile=profile,
    )


def _segment_ecg(
    segment: SegmentSpec, participant: VirtualParticipant, rng: random.Random
) -> tuple[int | None, str]:
    """Return (ecg_raw, ecg_quality) for one sample in the given segment."""
    if segment.kind == "UNUSABLE_ECG":
        return None, "UNUSABLE"
    if segment.kind == "MOCK_EVENT":
        value = participant.baseline_ecg_level + _STATE_MOCK_EVENT_OFFSET + rng.randint(-10, 10)
        return value, "VALID"
    if segment.kind == "DEGRADED_CONTEXT":
        value = participant.baseline_ecg_level + rng.randint(-5, 5)
        return value, "VALID"
    value = participant.baseline_ecg_level + _STATE_NORMAL_OFFSET + rng.randint(-10, 10)
    return value, "VALID"


def _segment_ppg(
    segment: SegmentSpec, participant: VirtualParticipant, rng: random.Random
) -> tuple[int | None, int | None, float | None, bool, float | None, str | None]:
    """Return (ppg_red_raw, ppg_ir_raw, spo2_pct, spo2_valid, pr_ppg_bpm, ppg_quality)."""
    if segment.kind == "CONTEXT_UNAVAILABLE":
        return None, None, None, False, None, None
    if segment.kind == "DEGRADED_CONTEXT":
        red = participant.baseline_ppg_red + rng.randint(-500, 500)
        ir = participant.baseline_ppg_ir + rng.randint(-500, 500)
        return (
            red,
            ir,
            round(participant.nominal_spo2, 1),
            True,
            round(participant.nominal_pulse_rate, 1),
            "DEGRADED",
        )
    red = participant.baseline_ppg_red + rng.randint(-50, 50)
    ir = participant.baseline_ppg_ir + rng.randint(-50, 50)
    return (
        red,
        ir,
        round(participant.nominal_spo2, 1),
        True,
        round(participant.nominal_pulse_rate, 1),
        "VALID",
    )


def _iter_indexed_segment_samples(
    scenario: SimulationScenario,
) -> Iterator[tuple[int, SegmentSpec, int]]:
    """Yield (global_sample_index, segment, index_within_segment) in scenario order."""
    index = 0
    for segment in scenario.segments:
        for within in range(segment.sample_count):
            yield index, segment, within
            index += 1


def iter_observed_records(session: SimulationSession) -> Iterator[ObservedRecord]:
    """Deterministically generate the production-facing observed records for a session."""
    rng = random.Random(_combined_seed(session.simulation_seed, session.session_id))
    for sample_index, segment, _within in _iter_indexed_segment_samples(session.scenario):
        ecg_raw, ecg_quality = _segment_ecg(segment, session.participant, rng)
        red, ir, spo2_pct, spo2_valid, pr_bpm, ppg_quality = _segment_ppg(
            segment, session.participant, rng
        )
        hr_ecg_bpm = (
            round(session.participant.nominal_pulse_rate, 1) if ecg_quality != "UNUSABLE" else None
        )
        yield ObservedRecord(
            contract_version=SAMPLE_CONTRACT_VERSION,
            participant_id=session.participant.participant_id,
            session_id=session.session_id,
            timestamp_us=sample_index * NOMINAL_TIMESTAMP_STEP_US,
            sample_index=sample_index,
            ecg_raw=ecg_raw,
            ppg_red_raw=red,
            ppg_ir_raw=ir,
            spo2_pct=spo2_pct,
            spo2_valid=spo2_valid,
            hr_ecg_bpm=hr_ecg_bpm,
            pr_ppg_bpm=pr_bpm,
            ecg_quality=ecg_quality,
            ppg_quality=ppg_quality,
            source=session.source_mode,
            preprocess_version=None,
        )


_EXPECTED_STATE_BY_KIND = {
    "NORMAL": "NORMAL_MONITORED_PATTERN",
    "CONTEXT_UNAVAILABLE": "CONTEXT_UNAVAILABLE",
    "DEGRADED_CONTEXT": "NORMAL_MONITORED_PATTERN",
    "UNUSABLE_ECG": "RECHECK_SENSOR",
    "MOCK_EVENT": "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
}


def get_truth(session: SimulationSession) -> Iterator[SimulationTruth]:
    """Internal-only ground truth. Never pass this to production-path modules."""
    for sample_index, segment, _within in _iter_indexed_segment_samples(session.scenario):
        yield SimulationTruth(
            participant_id=session.participant.participant_id,
            session_id=session.session_id,
            sample_index=sample_index,
            segment_name=segment.name,
            segment_kind=segment.kind,
            true_activity="rest_seated",
            latent_hr=session.participant.nominal_pulse_rate,
            latent_spo2=session.participant.nominal_spo2,
            scheduled_fault=segment.kind if segment.kind == "UNUSABLE_ECG" else None,
            actual_fault_active=segment.kind == "UNUSABLE_ECG",
            true_signal_quality="UNUSABLE" if segment.kind == "UNUSABLE_ECG" else "VALID",
            source_mode=session.source_mode,
            expected_monitoring_state=_EXPECTED_STATE_BY_KIND[segment.kind],
        )
