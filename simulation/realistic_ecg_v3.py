# ruff: noqa: E501
"""WEARABLE_SIM_REALISTIC_ECG_V3: the realistic ECG generator V2 with RECORDED noise.

The clean ECG, the rhythm, the ectopy (V, S and F beats, couplets, bigeminy, trigeminy, runs) and the annotation process are exactly those of ``simulation/realistic_ecg_v2.py`` (same functions, same random
streams: for a given seed the clean waveform and the true ectopic beats are identical to V2's). What changes is the noise. V2's baseline wander, muscle noise, motion artifacts and electrode pops were invented;
here they are the recorded noise of the MIT-BIH Noise Stress Test Database v1.0.0 (PhysioNet; the pure-noise records ``bw`` baseline wander, ``em`` electrode motion, ``ma`` muscle artifact, 360 Hz, ~30 min, mV),
scaled to NSTDB's own documented signal-to-noise levels (24, 18, 12, 6, 0 dB; the level is relative to the RMS of the participant's clean waveform, as NSTDB defines it).

* Each participant draws one SNR level (training: mostly clean; evaluation: mildly noisier, a new person on a new device) and one random segment of each noise record, from disjoint regions of the recordings
  for training and evaluation participants (training: the first 60 % of the recording, evaluation: the last 40 %), so no recorded noise segment is shared between the two cohorts.
* The three recorded noises are combined by power (baseline wander 40 %, electrode motion 40 %, muscle artifact 20 %) and scaled so that the composite hits the participant's SNR.
* A small 50 Hz mains component is kept (a trivial sine, the one remaining invented noise term).
* Annotation noise as in V2: 2 % of true ectopic beats are missed, 4 % of large noise deflections (peaks of at least 0.6 mV in the noise) are marked as ectopy, annotation times jitter by 12 ms. Noise peaks of at least
  0.35 mV are recorded as ``MOTION`` artifacts for audit only (the label provider reads annotations, never these).

Everything about the clean physiology remains a plausible-round-number generator, not a population statistic; only the noise is real. No clinical claim."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

from simulation import realistic_ecg_v2 as v2
from simulation.profile_v2013 import SOURCE_RATE_HZ

ROOT = Path(__file__).resolve().parents[1]
NSTDB_DIR = ROOT / "data/raw/nstdb/1.0.0"
NSTDB_FILES = ROOT / "manifests/datasets/nstdb_v1_files.csv"
GENERATOR_ID = "WEARABLE_SIM_REALISTIC_ECG_V3"
LABEL_CONTRACT_ID = "WEARABLE_SIM_REALISTIC_EVENT_WINDOW_V3"
NOISE_RECORDS = ("bw", "em", "ma")
NOISE_POWER_SHARES = {"bw": 0.4, "em": 0.4, "ma": 0.2}
SNR_LEVELS_DB = (24, 18, 12, 6, 0)
TRAIN_SNR_PROBS = (0.30, 0.35, 0.22, 0.10, 0.03)
EVAL_SNR_PROBS = (0.18, 0.28, 0.26, 0.20, 0.08)
TRAIN_REGION, EVAL_REGION = (0, 390_000), (390_000, 650_000)          # sample ranges of each 650,000-sample noise record
ARTIFACT_RECORD_MV, FALSE_MARK_MV = 0.35, 0.60
MAINS_AMP_MV = (0.003, 0.010)


@dataclass(frozen=True)
class NoiseInfo:
    snr_db: int
    noise_rms_mv: float
    signal_rms_mv: float
    segment_starts: tuple[int, int, int]            # bw, em, ma
    channels: tuple[int, int, int]


class NoiseDataError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def noise_records() -> dict[str, np.ndarray]:
    """The three recorded noise signals [650000, 2] in mV, after a check of every file against the official SHA-256 values in the repository's NSTDB manifest."""
    import csv

    import wfdb

    official = {row["relative_path"]: row["official_sha256"] for row in csv.DictReader(NSTDB_FILES.open())}
    for name in NOISE_RECORDS:
        for ext in ("dat", "hea"):
            rel = f"data/raw/nstdb/1.0.0/{name}.{ext}"
            if rel not in official or hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() != official[rel]:
                raise NoiseDataError(f"NSTDB_FILE_DIGEST_MISMATCH:{rel}")
    out = {}
    for name in NOISE_RECORDS:
        record = wfdb.rdrecord(str(NSTDB_DIR / name))
        if record.fs != SOURCE_RATE_HZ or record.p_signal.shape != (650_000, 2) or not np.isfinite(record.p_signal).all():
            raise NoiseDataError(f"NSTDB_RECORD_UNEXPECTED:{name}")
        out[name] = np.asarray(record.p_signal, dtype=np.float64)
    return out


def noise_manifest() -> dict[str, str]:
    """The official digests of the three noise records' signal files (pinned into the cohort manifest)."""
    import csv

    official = {row["relative_path"]: row["official_sha256"] for row in csv.DictReader(NSTDB_FILES.open())}
    return {name: official[f"data/raw/nstdb/1.0.0/{name}.dat"] for name in NOISE_RECORDS}


def _unit_segment(rec: np.ndarray, rng: np.random.Generator, n: int, region: tuple[int, int]) -> tuple[np.ndarray, int, int]:
    channel = int(rng.integers(0, 2))
    sign = float(rng.choice([-1.0, 1.0]))
    start = int(rng.integers(region[0], region[1] - n + 1))
    segment = sign * rec[start:start + n, channel]
    segment = segment - float(np.mean(segment))
    return segment / max(float(np.sqrt(np.mean(segment**2))), 1e-12), start, channel


def render(seed: int, hr_bpm: float, duration_s: float, burden_per_min: float, *, evaluation: bool, minimum_ectopic: int = 0) -> tuple[v2.Rendered, v2.Physiology, NoiseInfo]:
    """Deterministic in every argument. The clean waveform and the true ectopic beats equal V2's for the same seed; only the noise differs."""
    phys = v2.draw_physiology(seed, hr_bpm, 0.0, 0.0)                    # noise_scale 1.0: V2's noise parameters are not used
    rng = np.random.default_rng(seed ^ 0xBEA7)
    n = int(duration_s * SOURCE_RATE_HZ)
    t = np.arange(n) / SOURCE_RATE_HZ
    beats, truth = v2._timeline(rng, phys, duration_s, burden_per_min, minimum_ectopic)
    clean = np.zeros(n)
    previous = beats[0].time_s - 60.0 / phys.hr_bpm if beats else 0.0
    for beat in beats:
        v2._render_beat(clean, t, beat, phys, max(beat.time_s - previous, 0.35), rng)
        previous = beat.time_s
    nrng = np.random.default_rng(seed ^ 0x7015)
    region = EVAL_REGION if evaluation else TRAIN_REGION
    probs = EVAL_SNR_PROBS if evaluation else TRAIN_SNR_PROBS
    snr_db = int(nrng.choice(SNR_LEVELS_DB, p=probs))
    records = noise_records()
    composite = np.zeros(n)
    starts, channels = [], []
    for name in NOISE_RECORDS:
        unit, start, channel = _unit_segment(records[name], nrng, n, region)
        composite += np.sqrt(NOISE_POWER_SHARES[name]) * unit
        starts.append(start)
        channels.append(channel)
    signal_rms = float(np.sqrt(np.mean(clean**2)))
    noise_rms = signal_rms / 10 ** (snr_db / 20)
    noise = composite * noise_rms
    mains = float(nrng.uniform(*MAINS_AMP_MV)) * np.sin(2 * np.pi * 50.0 * t + float(nrng.uniform(0, 2 * np.pi)))
    mv = clean + noise + mains
    peaks, _ = find_peaks(np.abs(noise), height=ARTIFACT_RECORD_MV, distance=int(0.4 * SOURCE_RATE_HZ))
    artifacts = tuple(v2.Artifact(float(p / SOURCE_RATE_HZ), "MOTION", float(abs(noise[p]))) for p in peaks)
    arng = np.random.default_rng(seed ^ 0xA770)
    marked = [float(x + arng.normal(0.0, v2.ANNOTATION_JITTER_S)) for x in truth if arng.random() >= v2.MISS_RATE]
    marked += [a.time_s for a in artifacts if a.amplitude_mv >= FALSE_MARK_MV and arng.random() < v2.FALSE_ARTIFACT_RATE]
    return (v2.Rendered(mv=mv, beats=tuple(beats), artifacts=artifacts, annotations=tuple(sorted(marked)), true_ectopic=tuple(truth)), phys,
            NoiseInfo(snr_db, noise_rms, signal_rms, (starts[0], starts[1], starts[2]), (channels[0], channels[1], channels[2])))


to_counts = v2.to_counts
