"""WEARABLE_SIM_FL_COHORT_V1 generator (GENERATOR side; engineering data only).

Eight deterministic virtual federated clients, one persistent synthetic participant each
(SIM_P000101..SIM_P000108), one 480 s session at the 360 Hz SIMULATION source-rate convention
(software input convention matching the stream path, NOT a physical-device sampling claim).
Scheduled "events" are SYNTHETIC / ENGINEERING EVENT S-like/V-like/F-like perturbations with NO
physiological-morphology claim. Additive to (and never editing) the frozen V2-013 profile; the
production-like runtime consumes ONLY the emitted `ObservedRecord`s and never imports this module.
Event timestamps are exposed to training only through simulation/fl_cohort_truth_v1.py (truth side).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from simulation import SIMULATION_VERSION
from simulation.profile_v2013 import (
    ADC_RAIL_COUNTS,
    SIM_ECG_COUNTS_PER_MV,
    SOURCE_MODE,
    SOURCE_RATE_HZ,
    ContextSegment,
    FaultSegment,
    synth_ecg_mv,
)
from simulation.types import SAMPLE_CONTRACT_VERSION, ObservedRecord
from simulation.wearable import DATASET_ID, generate_participant, participant_id_for_index

COHORT_ID = "WEARABLE_SIM_FL_COHORT_V1"
BASE_SEED = 20260927
DURATION_S = 480
CLIENT_COUNT = 8
FIRST_PARTICIPANT_INDEX = 101
EVENT_LABEL_SUFFIX = "SYNTHETIC / ENGINEERING EVENT"
EVENT_KINDS = ("S-like", "V-like", "F-like")
EVENT_SLOT_START_S = 40.0
EVENT_SLOT_STEP_S = 30.0
EVENT_SLOTS = 15
EVENTS_PER_CLIENT = 10


@dataclass(frozen=True)
class SyntheticEvent:
    time_s: float
    kind: str  # one of EVENT_KINDS; always rendered as "<kind> SYNTHETIC / ENGINEERING EVENT"


@dataclass(frozen=True)
class ClientProfile:
    client_id: str
    participant_index: int
    participant_id: str
    session_id: str
    seed: int
    base_hr_bpm: float
    faults: tuple[FaultSegment, ...]
    context: tuple[ContextSegment, ...]
    events: tuple[SyntheticEvent, ...]
    coverage: tuple[str, ...]


_FAULTS: dict[int, tuple[FaultSegment, ...]] = {
    0: (),
    1: (FaultSegment(100.0, 100.08, "ECG_SHORT_GAP"),),
    2: (FaultSegment(250.0, 250.4, "ECG_LONG_GAP"),),
    3: (FaultSegment(330.0, 345.0, "ECG_SENSOR_DROPOUT"),),
    4: (FaultSegment(400.0, 410.0, "ECG_CLIPPING"),),
    5: (),
    6: (),
    7: (FaultSegment(100.0, 100.08, "ECG_SHORT_GAP"), FaultSegment(250.0, 250.4, "ECG_LONG_GAP"),
        FaultSegment(330.0, 340.0, "ECG_SENSOR_DROPOUT"),
        FaultSegment(420.0, 426.0, "ECG_CLIPPING")),
}
_VALID_ALL = (ContextSegment(0.0, float(DURATION_S), "VALID"),)
_CONTEXT: dict[int, tuple[ContextSegment, ...]] = {
    0: _VALID_ALL, 1: _VALID_ALL, 2: _VALID_ALL, 3: _VALID_ALL, 4: _VALID_ALL,
    5: (ContextSegment(0.0, 120.0, "VALID"), ContextSegment(120.0, 250.0, "MISSING_PPG"),
        ContextSegment(250.0, 480.0, "VALID")),
    6: (ContextSegment(0.0, 100.0, "VALID"), ContextSegment(100.0, 200.0, "INVALID_SPO2"),
        ContextSegment(200.0, 300.0, "VALID"), ContextSegment(300.0, 400.0, "RATE_DISAGREEMENT"),
        ContextSegment(400.0, 480.0, "VALID")),
    7: (ContextSegment(0.0, 120.0, "VALID"), ContextSegment(120.0, 170.0, "MISSING_PPG"),
        ContextSegment(170.0, 220.0, "INVALID_SPO2"), ContextSegment(220.0, 300.0, "VALID"),
        ContextSegment(300.0, 360.0, "RATE_DISAGREEMENT"), ContextSegment(360.0, 480.0, "VALID")),
}
_COVERAGE = {
    0: ("clean signal",), 1: ("short gap",), 2: ("long gap",), 3: ("sensor dropout",),
    4: ("clipping",), 5: ("missing PPG/context",),
    6: ("invalid SpO2/context", "ECG/PPG rate disagreement"),
    7: ("mixed fault/context session", "short gap", "long gap", "sensor dropout", "clipping",
        "missing PPG/context", "invalid SpO2/context", "ECG/PPG rate disagreement"),
}


def client_id(index: int) -> str:
    return f"SIM_FL_SITE_{index:02d}"


def _schedule_events(index: int, seed: int) -> tuple[SyntheticEvent, ...]:
    """Seeded schedule: EVENTS_PER_CLIENT of EVENT_SLOTS fixed 30 s slots, +/-4 s jitter. Depends
    only on (seed, index) -- never on model outputs."""
    rng = np.random.default_rng(seed * 1000 + index)
    slots = sorted(rng.choice(EVENT_SLOTS, size=EVENTS_PER_CLIENT, replace=False).tolist())
    events = []
    for order, slot in enumerate(slots):
        jitter = float(np.round(rng.uniform(-4.0, 4.0), 3))
        events.append(SyntheticEvent(float(np.round(
            EVENT_SLOT_START_S + EVENT_SLOT_STEP_S * slot + jitter, 3)),
            EVENT_KINDS[(index + order) % 3]))
    return tuple(events)


def client_profile(index: int) -> ClientProfile:
    seed = BASE_SEED + index
    participant_index = FIRST_PARTICIPANT_INDEX + index
    return ClientProfile(
        client_id=client_id(index), participant_index=participant_index,
        participant_id=participant_id_for_index(participant_index),
        session_id=f"SIM_S_FL_{index:02d}_000001", seed=seed,
        base_hr_bpm=float(66 + 3 * index), faults=_FAULTS[index], context=_CONTEXT[index],
        events=_schedule_events(index, BASE_SEED), coverage=_COVERAGE[index])


def cohort_profiles() -> tuple[ClientProfile, ...]:
    return tuple(client_profile(i) for i in range(CLIENT_COUNT))


def _event_wave(t: np.ndarray, event: SyntheticEvent) -> np.ndarray:
    """Engineering perturbation added to the baseline waveform (no morphology claim)."""
    c = event.time_s
    if event.kind == "S-like":      # premature narrow beat
        parts = ((1.0, 0.0, 0.010), (-0.2, 0.03, 0.010), (0.25, 0.18, 0.030))
    elif event.kind == "V-like":    # wide high-amplitude opposite-polarity deflection
        parts = ((-1.6, 0.0, 0.045), (0.7, 0.14, 0.060))
    else:                           # F-like: intermediate width/amplitude
        parts = ((1.3, 0.0, 0.028), (-0.5, 0.07, 0.030))
    wave = np.zeros_like(t)
    for amplitude, offset, width in parts:
        wave += amplitude * np.exp(-0.5 * ((t - (c + offset)) / width) ** 2)
    return wave


def _context_mode_at(profile: ClientProfile, second: float) -> str:
    for segment in profile.context:
        if segment.start_s <= second < segment.end_s:
            return segment.mode
    return "VALID"


def iter_observed_records(profile: ClientProfile) -> Iterator[ObservedRecord]:
    """Canonical stream of ObservedRecords (360 Hz). Event/fault/context schedules shape ONLY the
    observed values; no truth or schedule object is attached."""
    n = DURATION_S * SOURCE_RATE_HZ
    participant = generate_participant(profile.participant_index, profile.seed)
    t = np.arange(n) / SOURCE_RATE_HZ
    mv = synth_ecg_mv(n, SOURCE_RATE_HZ, profile.base_hr_bpm, profile.seed)
    for event in profile.events:
        lo = max(0, int((event.time_s - 0.5) * SOURCE_RATE_HZ))
        hi = min(n, int((event.time_s + 0.8) * SOURCE_RATE_HZ))
        mv[lo:hi] += _event_wave(t[lo:hi], event)
    counts = np.rint(mv * SIM_ECG_COUNTS_PER_MV).astype(np.int64)
    dropped = np.zeros(n, dtype=bool)
    sensor_none = np.zeros(n, dtype=bool)
    for fault in profile.faults:
        a, b = round(fault.start_s * SOURCE_RATE_HZ), round(fault.end_s * SOURCE_RATE_HZ)
        if fault.kind == "ECG_CLIPPING":
            counts[a:b] = np.clip(counts[a:b] * 4, -ADC_RAIL_COUNTS, ADC_RAIL_COUNTS)
        elif fault.kind in ("ECG_SHORT_GAP", "ECG_LONG_GAP", "TRANSPORT_DROPPED_CHUNK"):
            dropped[a:b] = True
        elif fault.kind == "ECG_SENSOR_DROPOUT":
            sensor_none[a:b] = True
    for index in range(n):
        if dropped[index]:
            continue
        mode = _context_mode_at(profile, index / SOURCE_RATE_HZ)
        ppg_quality = None if mode == "MISSING_PPG" else "VALID"
        pr = None if mode == "MISSING_PPG" else (
            round(profile.base_hr_bpm + 38.0, 1) if mode == "RATE_DISAGREEMENT"
            else round(participant.nominal_pulse_rate, 1))
        spo2_valid = mode not in ("MISSING_PPG", "INVALID_SPO2")
        ecg = None if sensor_none[index] else int(counts[index])
        yield ObservedRecord(
            contract_version=SAMPLE_CONTRACT_VERSION, participant_id=profile.participant_id,
            session_id=profile.session_id, timestamp_us=round(index * 1_000_000 / SOURCE_RATE_HZ),
            sample_index=index, ecg_raw=ecg, ppg_red_raw=None, ppg_ir_raw=None,
            spo2_pct=round(participant.nominal_spo2, 1) if spo2_valid else None,
            spo2_valid=spo2_valid, hr_ecg_bpm=None, pr_ppg_bpm=pr,
            ecg_quality="UNUSABLE" if ecg is None else "VALID", ppg_quality=ppg_quality,
            source=SOURCE_MODE, preprocess_version=None)


def provenance(profile: ClientProfile) -> dict[str, object]:
    return {
        "dataset_id": DATASET_ID, "source": SOURCE_MODE, "simulation_version": SIMULATION_VERSION,
        "simulation_seed": profile.seed, "participant_id": profile.participant_id,
        "session_id": profile.session_id, "client_id": profile.client_id,
        "cohort_id": COHORT_ID, "engineering_only": True, "clinical_claim": False,
        "real_wearable_claim": False, "virtual_participant_is_human": False}
