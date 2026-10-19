# ruff: noqa: E501
"""WEARABLE_SIM_FL_COHORT_REALISTIC_V3: the realistic cohort with RECORDED noise (``simulation/realistic_ecg_v3.py``): NSTDB baseline wander, electrode motion and muscle artifact at NSTDB's documented SNR levels
instead of V2's invented noise. Same structure as V2 (8 training clients on the logical sites SIM_FL_SITE_00..07, 16 fresh evaluation participants, the original site fault and context schedules, the same
``ObservedRecord`` contract and the same unmodified ``build_local_dataset``); different participants, seeds and noise. V1 and V2 cohorts, and every recorded artefact of either, are untouched.

Synthetic ECG with annotation noise and recorded noise: an engineering cohort, no clinical claim."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

from federated.virtual_client_source_v1 import LocalDataset, build_local_dataset
from simulation import SIMULATION_VERSION
from simulation import fl_cohort_v1 as base
from simulation import realistic_ecg_v3 as gen
from simulation.profile_v2013 import SOURCE_MODE, SOURCE_RATE_HZ, ContextSegment, FaultSegment
from simulation.types import SAMPLE_CONTRACT_VERSION, ObservedRecord
from simulation.wearable import generate_participant, participant_id_for_index

COHORT_ID = "WEARABLE_SIM_FL_COHORT_REALISTIC_V3"
EVAL_COHORT_ID = "WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3"
TRAIN_BASE_SEED = 20272001
TRAIN_FIRST_PARTICIPANT_INDEX = 701
EVAL_BASE_SEED = 20272101
EVAL_FIRST_PARTICIPANT_INDEX = 801
TRAIN_COUNT = 8
EVAL_COUNT = 16
SITES = 8
DURATION_S = base.DURATION_S
CLAIM_BOUNDARY = "SYNTHETIC_REALISTIC_ECTOPY_RECORDED_NOISE_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL"


@dataclass(frozen=True)
class RealisticProfile:
    client_id: str
    participant_index: int
    participant_id: str
    session_id: str
    seed: int
    base_hr_bpm: float
    faults: tuple[FaultSegment, ...]
    context: tuple[ContextSegment, ...]
    coverage: tuple[str, ...]
    burden_per_min: float
    minimum_ectopic: int
    evaluation: bool
    site_condition: str


def _burden(seed: int, *, evaluation: bool) -> float:
    rng = np.random.default_rng(seed ^ 0xB0DE)
    if evaluation and rng.random() < 0.12:
        return 0.0                                                      # some people simply have no ectopy in an 8 minute recording
    sigma = 0.9 if evaluation else 0.8
    return float(np.clip(np.exp(rng.normal(0.0, sigma)), 0.2 if evaluation else 0.35, 5.0 if evaluation else 4.0))


def _profile(client_id: str, session_id: str, participant_index: int, site: int, seed: int, *, evaluation: bool) -> RealisticProfile:
    return RealisticProfile(
        client_id=client_id, participant_index=participant_index, participant_id=participant_id_for_index(participant_index), session_id=session_id, seed=seed, base_hr_bpm=float(64 + 3 * site),
        faults=base._FAULTS[site], context=base._CONTEXT[site], coverage=base._COVERAGE[site], burden_per_min=_burden(seed, evaluation=evaluation), minimum_ectopic=0 if evaluation else 2,
        evaluation=evaluation, site_condition=base.client_id(site))


def train_profile(index: int) -> RealisticProfile:
    """The logical site ``SIM_FL_SITE_<index>`` of this cohort (the Studio and the UI key on the site ids), with participants, sessions and signals of its own."""
    if not 0 <= index < TRAIN_COUNT:
        raise ValueError("REALISTIC_V3_TRAIN_INDEX_OUT_OF_RANGE")
    return _profile(base.client_id(index), f"SIM_S_RFL3_{index:02d}_000001", TRAIN_FIRST_PARTICIPANT_INDEX + index, index, TRAIN_BASE_SEED + index, evaluation=False)


def eval_profile(k: int) -> RealisticProfile:
    if not 0 <= k < EVAL_COUNT:
        raise ValueError("REALISTIC_V3_EVAL_INDEX_OUT_OF_RANGE")
    site, replicate = k % SITES, k // SITES
    return _profile(f"SIM_REAL3_EVAL_{k:02d}", f"SIM_S_REAL3_EVAL_{k:02d}_000001", EVAL_FIRST_PARTICIPANT_INDEX + k, site, EVAL_BASE_SEED + 100 * replicate + site, evaluation=True)


def train_profiles() -> tuple[RealisticProfile, ...]:
    return tuple(train_profile(i) for i in range(TRAIN_COUNT))


def eval_profiles() -> tuple[RealisticProfile, ...]:
    return tuple(eval_profile(k) for k in range(EVAL_COUNT))


@lru_cache(maxsize=64)
def rendered(profile: RealisticProfile):
    return gen.render(profile.seed, profile.base_hr_bpm, DURATION_S, profile.burden_per_min, evaluation=profile.evaluation, minimum_ectopic=profile.minimum_ectopic)


def iter_observed_records(profile: RealisticProfile) -> Iterator[ObservedRecord]:
    """The same stream contract as the original cohort; fault and context schedules shape only the observed values."""
    n = DURATION_S * SOURCE_RATE_HZ
    participant = generate_participant(profile.participant_index, profile.seed)
    result, _, _ = rendered(profile)
    counts = gen.to_counts(result.mv)
    dropped = np.zeros(n, dtype=bool)
    sensor_none = np.zeros(n, dtype=bool)
    for fault in profile.faults:
        a, b = round(fault.start_s * SOURCE_RATE_HZ), round(fault.end_s * SOURCE_RATE_HZ)
        if fault.kind == "ECG_CLIPPING":
            counts[a:b] = np.clip(counts[a:b] * 4, -gen.v2.ADC_RAIL_COUNTS, gen.v2.ADC_RAIL_COUNTS)
        elif fault.kind in ("ECG_SHORT_GAP", "ECG_LONG_GAP", "TRANSPORT_DROPPED_CHUNK"):
            dropped[a:b] = True
        elif fault.kind == "ECG_SENSOR_DROPOUT":
            sensor_none[a:b] = True
    for index in range(n):
        if dropped[index]:
            continue
        mode = base._context_mode_at(profile, index / SOURCE_RATE_HZ)          # type: ignore[arg-type]  (duck-typed: only ``context`` is read)
        ppg_quality = None if mode == "MISSING_PPG" else "VALID"
        pr = None if mode == "MISSING_PPG" else (round(profile.base_hr_bpm + 38.0, 1) if mode == "RATE_DISAGREEMENT" else round(participant.nominal_pulse_rate, 1))
        spo2_valid = mode not in ("MISSING_PPG", "INVALID_SPO2")
        ecg = None if sensor_none[index] else int(counts[index])
        yield ObservedRecord(
            contract_version=SAMPLE_CONTRACT_VERSION, participant_id=profile.participant_id, session_id=profile.session_id, timestamp_us=round(index * 1_000_000 / SOURCE_RATE_HZ), sample_index=index,
            ecg_raw=ecg, ppg_red_raw=None, ppg_ir_raw=None, spo2_pct=round(participant.nominal_spo2, 1) if spo2_valid else None, spo2_valid=spo2_valid, hr_ecg_bpm=None, pr_ppg_bpm=pr,
            ecg_quality="UNUSABLE" if ecg is None else "VALID", ppg_quality=ppg_quality, source=SOURCE_MODE, preprocess_version=None)


class RealisticObservedSource:
    def __init__(self, profile: RealisticProfile) -> None:
        self.profile = profile
        self.client_id, self.participant_id, self.session_id = profile.client_id, profile.participant_id, profile.session_id

    def records(self) -> Iterator[ObservedRecord]:
        return iter_observed_records(self.profile)


WINDOW_US = 10_000_000


class RealisticEventLabelProvider:
    """Positive when at least one ANNOTATED ectopic beat lies in [t-10 s, t] (the original window convention). Reads annotations, never the hidden truth."""

    def __init__(self, profile: RealisticProfile) -> None:
        self._events = np.asarray(sorted(round(t * 1_000_000) for t in rendered(profile)[0].annotations), dtype=np.int64)

    def labels_for_windows(self, right_edges_us: list[int]) -> np.ndarray:
        out = np.zeros(len(right_edges_us), dtype=np.float32)
        for i, end in enumerate(right_edges_us):
            out[i] = float(np.any((self._events >= end - WINDOW_US) & (self._events <= end)))
        return out


def build_dataset(profile: RealisticProfile) -> LocalDataset:
    return build_local_dataset(RealisticObservedSource(profile), RealisticEventLabelProvider(profile))


def manifest_entry(profile: RealisticProfile, dataset: LocalDataset) -> dict[str, Any]:
    result, phys, noise = rendered(profile)
    return {"client_id": profile.client_id, "participant_id": profile.participant_id, "session_id": profile.session_id, "seed": profile.seed, "site_condition": profile.site_condition,
            "burden_per_min": round(profile.burden_per_min, 4), "true_ectopic_beats": len(result.true_ectopic), "annotated_events": len(result.annotations), "noise_snr_db": noise.snr_db,
            "noise_rms_mv": round(noise.noise_rms_mv, 5), "noise_segment_starts": list(noise.segment_starts), "noise_channels": list(noise.channels), "noise_peaks_ge_0p35_mv": len(result.artifacts),
            "pvc_ratio": round(phys.pvc_ratio, 3), "counts": dataset.counts, "dataset_sha256": dataset.dataset_sha256}


def build_manifest(cohort_id: str, profiles: tuple[RealisticProfile, ...], datasets: list[LocalDataset]) -> dict[str, Any]:
    return {"cohort_id": cohort_id, "generator_id": gen.GENERATOR_ID, "label_contract": gen.LABEL_CONTRACT_ID, "simulation_version": SIMULATION_VERSION, "claim_boundary": CLAIM_BOUNDARY,
            "annotation_noise": {"miss_rate": gen.v2.MISS_RATE, "false_artifact_rate": gen.v2.FALSE_ARTIFACT_RATE, "jitter_s": gen.v2.ANNOTATION_JITTER_S, "false_mark_peak_mv": gen.FALSE_MARK_MV},
            "noise_source": {"dataset": "MIT-BIH Noise Stress Test Database v1.0.0 (pure-noise records)", "record_sha256": gen.noise_manifest(), "power_shares": gen.NOISE_POWER_SHARES, "snr_levels_db": list(gen.SNR_LEVELS_DB),
                             "train_probs": list(gen.TRAIN_SNR_PROBS), "eval_probs": list(gen.EVAL_SNR_PROBS), "train_region": list(gen.TRAIN_REGION), "eval_region": list(gen.EVAL_REGION)},
            "participants": [manifest_entry(p, d) for p, d in zip(profiles, datasets, strict=True)]}
