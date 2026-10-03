"""WEARABLE_SIM_V1 V2-013 integration profile (GENERATOR side).

Extends the T005 smoke kernel with a minimal, deterministic SYNTHETIC_PHYSIOLOGY *waveform*
source at the PREPROC_V1 source rate (360 Hz), a fault schedule, a context schedule and the
canonical-stream emitter that yields `simulation.types.ObservedRecord`s. It is engineering data
only: the synthetic ECG morphology makes NO physiological-accuracy claim, virtual participants
are not humans, and nothing here is evidence of clinical or real-wearable performance.

The runtime side (simulation/stream_runtime_v2013.py) consumes ONLY ObservedRecord and must never
import this module or simulation.truth_v2013.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from simulation import SIMULATION_VERSION
from simulation.types import SAMPLE_CONTRACT_VERSION, ObservedRecord
from simulation.wearable import DATASET_ID, generate_participant, participant_id_for_index

SOURCE_RATE_HZ = 360
SIM_ECG_COUNTS_PER_MV = 1000  # simulation-only unit convention, not a hardware claim
ADC_RAIL_COUNTS = 2500  # simulated ADC rail (+/- counts); declared in the stream interface
SOURCE_MODE = "SYNTHETIC_PHYSIOLOGY"
PROFILE_ID = "WEARABLE_SIM_V2013_INTEGRATION_PROFILE_V1"
PARTICIPANT_INDEX = 13
SEED = 20260927

ECG_FAULTS = ("ECG_SHORT_GAP", "ECG_LONG_GAP", "TRANSPORT_DROPPED_CHUNK", "ECG_FLATLINE",
              "ECG_CLIPPING", "ECG_SENSOR_DROPOUT")
CONTEXT_MODES = ("VALID", "MISSING_PPG", "INVALID_SPO2", "RATE_DISAGREEMENT")


@dataclass(frozen=True)
class FaultSegment:
    start_s: float
    end_s: float
    kind: str


@dataclass(frozen=True)
class ContextSegment:
    start_s: float
    end_s: float
    mode: str


@dataclass(frozen=True)
class IntegrationProfile:
    profile_id: str
    session_id: str
    duration_s: int
    seed: int
    base_hr_bpm: float
    faults: tuple[FaultSegment, ...]
    context: tuple[ContextSegment, ...]
    # TRUTH-ONLY annotations (never read by the generator's observed output nor the runtime):
    truth_notes: dict[str, str] = field(default_factory=dict)


FULL_PROFILE = IntegrationProfile(
    profile_id=PROFILE_ID,
    session_id="SIM_S_V2013_LONGITUDINAL_000001",
    duration_s=480,
    seed=SEED,
    base_hr_bpm=72.0,
    faults=(
        FaultSegment(100.0, 100.08, "ECG_SHORT_GAP"),          # 80 ms (<= 100 ms) -> DEGRADED
        FaultSegment(250.0, 250.4, "ECG_LONG_GAP"),            # 400 ms -> segment reset
        FaultSegment(330.0, 345.0, "ECG_SENSOR_DROPOUT"),      # 15 s of None -> long gap
        FaultSegment(400.0, 410.0, "ECG_CLIPPING"),            # explicit ADC-rail clipping
        FaultSegment(440.0, 441.0, "TRANSPORT_DROPPED_CHUNK"),  # 1 s of records never arrive
        FaultSegment(455.0, 460.0, "ECG_SENSOR_DROPOUT"),      # ecg_raw None for 5 s
    ),
    context=(
        ContextSegment(0.0, 120.0, "VALID"),
        ContextSegment(120.0, 170.0, "MISSING_PPG"),
        ContextSegment(170.0, 220.0, "INVALID_SPO2"),
        ContextSegment(220.0, 300.0, "VALID"),
        ContextSegment(300.0, 360.0, "RATE_DISAGREEMENT"),
        ContextSegment(360.0, 480.0, "VALID"),
    ),
)

LIVE_EXCERPT_PROFILE = IntegrationProfile(
    profile_id=PROFILE_ID + "_LIVE_EXCERPT",
    session_id="SIM_S_V2013_LIVE_EXCERPT_000001",
    duration_s=45,
    seed=SEED,
    base_hr_bpm=72.0,
    faults=(FaultSegment(20.0, 20.08, "ECG_SHORT_GAP"),),
    context=(ContextSegment(0.0, 30.0, "VALID"), ContextSegment(30.0, 45.0, "MISSING_PPG")),
)


def synth_ecg_mv(n_samples: int, fs: int, hr_bpm: float, seed: int) -> np.ndarray:
    """Deterministic Gaussian-sum ECG-like waveform (mV): beat template + baseline wander +
    seeded noise. Engineering waveform only."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_samples) / fs
    duration = n_samples / fs
    beats, now = [], 0.4
    while now < duration + 1.0:
        beats.append(now)
        now += (60.0 / hr_bpm) * (1.0 + 0.03 * rng.standard_normal())
    wave = np.zeros(n_samples)
    for centre in beats:
        for amp, offset, width in ((0.12, -0.20, 0.025), (-0.10, -0.04, 0.010),
                                   (1.10, 0.0, 0.012), (-0.25, 0.04, 0.012),
                                   (0.30, 0.25, 0.040)):
            wave += amp * np.exp(-0.5 * ((t - (centre + offset)) / width) ** 2)
    wave += 0.10 * np.sin(2 * np.pi * 0.25 * t) + 0.02 * rng.standard_normal(n_samples)
    return wave


def _context_mode_at(profile: IntegrationProfile, second: float) -> str:
    for segment in profile.context:
        if segment.start_s <= second < segment.end_s:
            return segment.mode
    return "VALID"


def iter_observed_records(profile: IntegrationProfile = FULL_PROFILE) -> Iterator[ObservedRecord]:
    """Canonical stream: ObservedRecord per delivered source sample (360 Hz). Samples dropped by
    TRANSPORT_DROPPED_CHUNK / ECG_LONG_GAP / ECG_SHORT_GAP are simply never emitted (source
    indices skip); ECG_SENSOR_DROPOUT emits ecg_raw=None."""
    n = profile.duration_s * SOURCE_RATE_HZ
    participant = generate_participant(PARTICIPANT_INDEX, profile.seed)
    mv = synth_ecg_mv(n, SOURCE_RATE_HZ, profile.base_hr_bpm, profile.seed)
    counts = np.rint(mv * SIM_ECG_COUNTS_PER_MV).astype(np.int64)
    for fault in profile.faults:
        a, b = round(fault.start_s * SOURCE_RATE_HZ), round(fault.end_s * SOURCE_RATE_HZ)
        if fault.kind == "ECG_FLATLINE":
            counts[a:b] = 120
        elif fault.kind == "ECG_CLIPPING":
            counts[a:b] = np.clip(counts[a:b] * 4, -ADC_RAIL_COUNTS, ADC_RAIL_COUNTS)
    dropped = np.zeros(n, dtype=bool)
    sensor_none = np.zeros(n, dtype=bool)
    for fault in profile.faults:
        a, b = round(fault.start_s * SOURCE_RATE_HZ), round(fault.end_s * SOURCE_RATE_HZ)
        if fault.kind in ("ECG_SHORT_GAP", "ECG_LONG_GAP", "TRANSPORT_DROPPED_CHUNK"):
            dropped[a:b] = True
        if fault.kind == "ECG_SENSOR_DROPOUT":
            sensor_none[a:b] = True
    nominal_pr = participant.nominal_pulse_rate
    for index in range(n):
        if dropped[index]:
            continue
        second = index / SOURCE_RATE_HZ
        mode = _context_mode_at(profile, second)
        ppg_quality = None if mode == "MISSING_PPG" else "VALID"
        pr = None if mode == "MISSING_PPG" else (
            round(profile.base_hr_bpm + 38.0, 1) if mode == "RATE_DISAGREEMENT"
            else round(nominal_pr, 1))
        spo2_valid = mode not in ("MISSING_PPG", "INVALID_SPO2")
        spo2 = round(participant.nominal_spo2, 1) if spo2_valid else None
        ecg = None if sensor_none[index] else int(counts[index])
        yield ObservedRecord(
            contract_version=SAMPLE_CONTRACT_VERSION,
            participant_id=participant_id_for_index(PARTICIPANT_INDEX),
            session_id=profile.session_id,
            timestamp_us=round(index * 1_000_000 / SOURCE_RATE_HZ),
            sample_index=index,
            ecg_raw=ecg,
            ppg_red_raw=None, ppg_ir_raw=None,
            spo2_pct=spo2, spo2_valid=spo2_valid,
            hr_ecg_bpm=None, pr_ppg_bpm=pr,
            ecg_quality="UNUSABLE" if ecg is None else "VALID",
            ppg_quality=ppg_quality,
            source=SOURCE_MODE,
            preprocess_version=None,
        )


def provenance(profile: IntegrationProfile = FULL_PROFILE) -> dict[str, object]:
    participant = generate_participant(PARTICIPANT_INDEX, profile.seed)
    return {
        "dataset_id": DATASET_ID,
        "source": SOURCE_MODE,
        "simulation_version": SIMULATION_VERSION,
        "simulation_seed": profile.seed,
        "participant_id": participant.participant_id,
        "session_id": profile.session_id,
        "profile_id": profile.profile_id,
        "virtual_participant_is_human": False,
        "clinical_or_real_wearable_claim": False,
    }
