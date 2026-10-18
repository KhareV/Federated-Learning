# ruff: noqa: E501
"""WEARABLE_SIM_REALISTIC_ECG_V2 -- a more realistic synthetic single-lead ECG with annotated ectopic beats (GENERATOR side; engineering data only).

Additive: nothing frozen is edited. The original cohort generator (``simulation/fl_cohort_v1.py``) stays byte-identical because recorded FL10 evidence depends on it.

What this models that the original did not (each item is a documented modelling choice, not a measured population statistic):

* Rhythm: beat-to-beat variability (respiratory sinus arrhythmia, a 0.1 Hz Mayer-wave component, white jitter) and slow heart-rate drift, instead of a nearly metronomic 3 % jitter.
* Per-participant physiology: heart rate, P/Q/R/S/T amplitudes and widths, QT shortening with heart rate, device gain, and respiration-linked R-wave amplitude modulation. Every beat varies a little.
* Ectopy as rhythm, not a pasted bump: an ectopic beat REPLACES a sinus beat and comes early (coupling interval 50-85 % of the preceding RR).
    - V (ventricular, PVC-like): no P wave, wide slurred QRS of either polarity and variable size relative to the normal beat (some are smaller than the normal R wave), discordant T wave,
      and a full compensatory pause (the sinus node is not reset; sinus beats inside the ventricular refractory period are blocked).
    - S (supraventricular, PAC-like): premature, narrow, normal-looking QRS with a changed (absent / inverted / early) P wave, and a non-compensatory pause (the sinus node resets).
    - F (fusion-like): near-normal timing, a blend of the normal and the ventricular morphology, partial P wave.
    - Episodes: isolated beats (most), couplets, bigeminy / trigeminy runs and short runs. Burden (ectopic beats per minute) differs a lot between people, and may be zero.
* Hard negatives: baseline wander (several sines plus a random walk), non-stationary muscle noise bursts, mains pickup, motion artifacts that look like wide QRS complexes, electrode pops.
* Annotation noise: an annotator misses a small share of true ectopic beats and mislabels a small share of large motion artifacts as ectopy; annotation times carry a few milliseconds of jitter.
  The label provider reads ANNOTATIONS, never the hidden truth, exactly as a clinical label would be an annotation and not the physiology.

Nothing here is a clinical claim. The morphology is a Gaussian-sum approximation, not a model of cardiac electrophysiology, and the rates are plausible round numbers chosen for a demo.
The label contract is ``WEARABLE_SIM_REALISTIC_EVENT_WINDOW_V2``: a window is positive when at least one ANNOTATED ectopic beat lies in [t-10 s, t] (same window convention as the original)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from simulation.profile_v2013 import ADC_RAIL_COUNTS, SIM_ECG_COUNTS_PER_MV, SOURCE_RATE_HZ

GENERATOR_ID = "WEARABLE_SIM_REALISTIC_ECG_V2"
LABEL_CONTRACT_ID = "WEARABLE_SIM_REALISTIC_EVENT_WINDOW_V2"
MISS_RATE = 0.02                      # share of true ectopic beats an annotator does not mark
FALSE_ARTIFACT_RATE = 0.04            # share of large motion artifacts marked as ectopy
ANNOTATION_JITTER_S = 0.012
REFRACTORY_S = 0.40                   # sinus beats this soon after a ventricular beat are blocked
EPISODE_KINDS = ("isolated", "couplet", "bigeminy", "trigeminy", "run")
EPISODE_PROBS = (0.72, 0.12, 0.07, 0.04, 0.05)
MEAN_BEATS_PER_EPISODE = 1.0 * 0.72 + 2.0 * 0.12 + 6.0 * 0.07 + 4.0 * 0.04 + 3.5 * 0.05


@dataclass(frozen=True)
class Physiology:
    hr_bpm: float
    rsa_amp: float
    rsa_hz: float
    lf_amp: float
    rr_noise: float
    drift_bpm: float
    drift_period_s: float
    r_amp: float
    q_amp: float
    s_amp: float
    p_amp: float
    t_amp: float
    r_width: float
    p_width: float
    t_width: float
    resp_mod: float
    wander_amp: float
    emg_sigma: float
    mains_amp: float
    motion_per_min: float
    pop_per_min: float
    pvc_polarity: float
    pvc_ratio: float
    pvc_width: float
    coupling: float
    kind_weights: tuple[float, float, float]      # V, S, F
    noise_scale: float


@dataclass(frozen=True)
class Beat:
    time_s: float
    kind: str                       # N (sinus), V, S, F (ectopic)


@dataclass(frozen=True)
class Artifact:
    time_s: float
    kind: str                       # MOTION or POP
    amplitude_mv: float


@dataclass
class Rendered:
    mv: np.ndarray
    beats: tuple[Beat, ...]
    artifacts: tuple[Artifact, ...]
    annotations: tuple[float, ...] = field(default=())     # seconds; what the label provider reads
    true_ectopic: tuple[float, ...] = field(default=())    # hidden truth, for audit only


def draw_physiology(seed: int, hr_bpm: float, noise_log_mean: float = 0.0, noise_log_sigma: float = 0.30) -> Physiology:
    rng = np.random.default_rng(seed ^ 0x51A7)
    noise_scale = float(np.exp(rng.normal(noise_log_mean, noise_log_sigma)))
    weights = rng.dirichlet(np.array([4.0, 2.0, 0.7]))
    return Physiology(
        hr_bpm=float(hr_bpm), rsa_amp=float(rng.uniform(0.02, 0.06)), rsa_hz=float(rng.uniform(0.18, 0.30)), lf_amp=float(rng.uniform(0.008, 0.025)), rr_noise=float(rng.uniform(0.010, 0.022)),
        drift_bpm=float(rng.uniform(2.0, 7.0)), drift_period_s=float(rng.uniform(150.0, 420.0)),
        r_amp=float(rng.uniform(0.85, 1.45)), q_amp=float(rng.uniform(0.05, 0.14)), s_amp=float(rng.uniform(0.12, 0.30)), p_amp=float(rng.uniform(0.07, 0.18)), t_amp=float(rng.uniform(0.18, 0.42)),
        r_width=float(rng.uniform(0.010, 0.014)), p_width=float(rng.uniform(0.020, 0.030)), t_width=float(rng.uniform(0.035, 0.050)), resp_mod=float(rng.uniform(0.02, 0.07)),
        wander_amp=float(rng.uniform(0.04, 0.16)) * noise_scale, emg_sigma=float(rng.uniform(0.012, 0.030)) * noise_scale, mains_amp=float(rng.uniform(0.004, 0.020)) * noise_scale,
        motion_per_min=float(rng.uniform(0.6, 3.2)) * noise_scale, pop_per_min=float(rng.uniform(0.0, 0.8)) * noise_scale,
        pvc_polarity=float(rng.choice([-1.0, 1.0])), pvc_ratio=float(rng.uniform(0.65, 2.1)), pvc_width=float(rng.uniform(0.030, 0.048)),
        coupling=float(rng.uniform(0.52, 0.80)), kind_weights=(float(weights[0]), float(weights[1]), float(weights[2])), noise_scale=noise_scale)


def _sinus_times(rng: np.random.Generator, phys: Physiology, duration: float) -> np.ndarray:
    ph = rng.uniform(0, 2 * np.pi, 3)
    times, t = [], 0.4
    while t < duration + 2.0:
        hr = phys.hr_bpm + phys.drift_bpm * np.sin(2 * np.pi * t / phys.drift_period_s + ph[2])
        rr = 60.0 / hr * (1.0 + phys.rsa_amp * np.sin(2 * np.pi * phys.rsa_hz * t + ph[0]) + phys.lf_amp * np.sin(2 * np.pi * 0.1 * t + ph[1]) + phys.rr_noise * rng.standard_normal())
        times.append(t)
        t += float(np.clip(rr, 0.38, 1.8))
    return np.asarray(times)


def _episodes(rng: np.random.Generator, burden_per_min: float, duration: float, n_sinus: int, minimum: int) -> list[tuple[int, str]]:
    """(sinus beat index, pattern) pairs, Poisson in time with a minimum spacing; ``minimum`` ectopic beats are forced (a participant with a declared burden always has some)."""
    if burden_per_min <= 0.0:
        return []
    rate = burden_per_min / MEAN_BEATS_PER_EPISODE / 60.0
    out: list[tuple[int, str]] = []
    t, last = 0.0, -99
    while True:
        t += float(rng.exponential(1.0 / rate))
        if t >= duration - 8.0:
            break
        k = int(np.searchsorted(np.linspace(0.4, duration, n_sinus), t))
        k = int(np.clip(k, 3, n_sinus - 12))
        if k - last < 14:
            continue
        out.append((k, str(rng.choice(EPISODE_KINDS, p=EPISODE_PROBS))))
        last = k
    beats = sum({"isolated": 1, "couplet": 2, "bigeminy": 6, "trigeminy": 4, "run": 3}[p] for _, p in out)
    while beats < minimum:
        k = int(rng.integers(3, n_sinus - 12))
        if all(abs(k - o) >= 14 for o, _ in out):
            out.append((k, "isolated"))
            beats += 1
    return sorted(out)


def _timeline(rng: np.random.Generator, phys: Physiology, duration: float, burden_per_min: float, minimum: int) -> tuple[list[Beat], list[float]]:
    sinus = _sinus_times(rng, phys, duration)
    rr_local = np.diff(sinus, prepend=sinus[0] - 60.0 / phys.hr_bpm)
    episodes = {k: p for k, p in _episodes(rng, burden_per_min, duration, len(sinus), minimum)}
    kinds = np.array(["V", "S", "F"])
    weights = np.asarray(phys.kind_weights) / sum(phys.kind_weights)
    beats: list[Beat] = []
    shift, blocked_until = 0.0, -1.0
    i = 0
    while i < len(sinus):
        t = float(sinus[i] + shift)
        if t < blocked_until:
            i += 1
            continue
        if i not in episodes:
            beats.append(Beat(t, "N"))
            i += 1
            continue
        pattern = episodes.pop(i)
        kind = str(rng.choice(kinds, p=weights))
        count = {"isolated": 1, "couplet": 2, "bigeminy": int(rng.integers(3, 9)), "trigeminy": int(rng.integers(2, 5)), "run": int(rng.integers(3, 6))}[pattern]
        last = beats[-1].time_s if beats else t - float(rr_local[i])
        rr = float(rr_local[i])
        last_gap = rr
        for n in range(count):
            gap = (phys.coupling + float(rng.normal(0.0, 0.03))) * rr if n == 0 or pattern in ("bigeminy", "trigeminy") else float(rng.uniform(0.34, 0.50)) * rr
            if pattern in ("bigeminy", "trigeminy") and n > 0:                           # one (bigeminy) or two (trigeminy) conducted sinus beats precede each further ectopic beat
                for step in range(1 if pattern == "bigeminy" else 2):
                    # the first beat after a ventricular beat keeps the full compensatory pause (the sinus node was not reset): ectopic gap + this gap = two sinus cycles
                    gap_normal = (max(0.55 * rr, 2.0 * rr - last_gap) if step == 0 and kind != "S" else rr) * float(rng.uniform(0.97, 1.03))
                    beats.append(Beat(last + gap_normal, "N"))
                    last += gap_normal
            if kind == "F":
                te = max(last + 0.25, t - float(rng.uniform(0.04, 0.10)))
            else:
                te = last + max(0.28, min(gap, 0.9 * rr))
            beats.append(Beat(te, kind))
            last_gap = te - last
            last = te
            if kind == "S":
                shift = te + float(rng.uniform(1.0, 1.08)) * rr - float(sinus[min(i + 1, len(sinus) - 1)])    # the sinus node resets: later beats follow the premature one
                blocked_until = te + 0.05
            elif kind == "V":
                blocked_until = te + REFRACTORY_S
        i += 1
    return beats, [b.time_s for b in beats if b.kind != "N"]


def _gauss(t: np.ndarray, centre: float, amp: float, width: float) -> np.ndarray:
    return amp * np.exp(-0.5 * ((t - centre) / width) ** 2)


def _render_beat(mv: np.ndarray, t: np.ndarray, beat: Beat, phys: Physiology, rr_prev: float, rng: np.random.Generator) -> None:
    lo, hi = max(0, int((beat.time_s - 0.55) * SOURCE_RATE_HZ)), min(len(mv), int((beat.time_s + 0.80) * SOURCE_RATE_HZ))
    if hi <= lo:
        return
    tt, c = t[lo:hi], beat.time_s
    gain = (1.0 + 0.045 * rng.standard_normal()) * (1.0 + phys.resp_mod * np.sin(2 * np.pi * phys.rsa_hz * c))
    t_gain = 1.0 + 0.09 * rng.standard_normal()
    qt = 0.26 * np.sqrt(max(rr_prev, 0.35))
    wave = np.zeros_like(tt)

    def normal(scale: float, with_p: float = 1.0, p_sign: float = 1.0, wscale: float = 1.0, t_scale: float = 1.0) -> np.ndarray:
        w = _gauss(tt, c - 0.20, p_sign * phys.p_amp * with_p, phys.p_width)
        w += _gauss(tt, c - 0.04, -phys.q_amp * scale, 0.010) + _gauss(tt, c, phys.r_amp * gain * scale, phys.r_width * wscale)
        w += _gauss(tt, c + 0.04, -phys.s_amp * scale, 0.012 * wscale) + _gauss(tt, c + qt * 0.65, phys.t_amp * t_gain * t_scale, phys.t_width * (0.9 + 0.3 * rr_prev))
        return w

    def ventricular(strength: float) -> np.ndarray:
        main = phys.pvc_polarity * phys.r_amp * phys.pvc_ratio * gain * strength
        w = _gauss(tt, c, main, phys.pvc_width) + _gauss(tt, c + 0.075, -0.30 * main, 0.050)       # slurred, notched
        return w + _gauss(tt, c + 0.25, -0.40 * main, 0.075)                                          # discordant T wave

    if beat.kind == "N":
        wave = normal(1.0)
    elif beat.kind == "V":
        wave = ventricular(1.0) * float(rng.uniform(0.92, 1.08))
    elif beat.kind == "S":
        roll = rng.random()
        p_kind = 0.0 if roll < 0.35 else (-1.0 if roll < 0.60 else 1.0)
        wave = normal(float(rng.uniform(0.9, 1.1)), with_p=abs(p_kind), p_sign=p_kind if p_kind else 1.0, wscale=float(rng.uniform(0.95, 1.12)), t_scale=float(rng.uniform(0.8, 1.1)))
    else:
        w = float(rng.uniform(0.35, 0.65))
        wave = (1 - w) * normal(1.0, with_p=0.5, t_scale=0.7) + w * ventricular(1.0)
    mv[lo:hi] += wave


def _smooth(x: np.ndarray, width: int) -> np.ndarray:
    kernel = np.ones(width) / width
    return np.convolve(x, kernel, mode="same")


def render(seed: int, hr_bpm: float, duration_s: float, burden_per_min: float, noise_log_mean: float = 0.0, noise_log_sigma: float = 0.30, minimum_ectopic: int = 0) -> tuple[Rendered, Physiology]:
    """Deterministic in every argument. ``mv`` is the clean-plus-noisy waveform in millivolts at SOURCE_RATE_HZ (before the ADC)."""
    phys = draw_physiology(seed, hr_bpm, noise_log_mean, noise_log_sigma)
    rng = np.random.default_rng(seed ^ 0xBEA7)
    n = int(duration_s * SOURCE_RATE_HZ)
    t = np.arange(n) / SOURCE_RATE_HZ
    beats, truth = _timeline(rng, phys, duration_s, burden_per_min, minimum_ectopic)
    mv = np.zeros(n)
    previous = beats[0].time_s - 60.0 / phys.hr_bpm if beats else 0.0
    for beat in beats:
        _render_beat(mv, t, beat, phys, max(beat.time_s - previous, 0.35), rng)
        previous = beat.time_s
    # baseline wander: slow sines plus a smoothed random walk
    wander = sum(phys.wander_amp * rng.uniform(0.4, 1.0) * np.sin(2 * np.pi * rng.uniform(0.05, 0.35) * t + rng.uniform(0, 2 * np.pi)) for _ in range(3)) / 1.6
    walk = _smooth(np.cumsum(rng.standard_normal(n)), SOURCE_RATE_HZ)
    wander = wander + 0.5 * phys.wander_amp * walk / max(float(np.std(walk)), 1e-9)
    # muscle noise with non-stationary bursts
    envelope = np.ones(n)
    for _ in range(int(rng.poisson(duration_s / 60.0 * 0.9))):
        centre, width = rng.uniform(0, duration_s), rng.uniform(1.0, 3.0)
        envelope += rng.uniform(1.0, 3.0) * np.exp(-0.5 * ((t - centre) / width) ** 2)
    emg = phys.emg_sigma * envelope * _smooth(rng.standard_normal(n), 2) * 1.6
    mains = phys.mains_amp * np.sin(2 * np.pi * 50.0 * t + rng.uniform(0, 2 * np.pi))
    artifacts: list[Artifact] = []
    art = np.zeros(n)
    for _ in range(int(rng.poisson(duration_s / 60.0 * phys.motion_per_min))):
        centre, dur, amp = float(rng.uniform(1.0, duration_s - 1.5)), float(rng.uniform(0.25, 1.2)), float(rng.uniform(0.35, 1.8)) * float(rng.choice([-1.0, 1.0]))
        lo, hi = int((centre - 0.1) * SOURCE_RATE_HZ), min(n, int((centre + dur) * SOURCE_RATE_HZ))
        u = np.linspace(0.0, 1.0, hi - lo)
        art[lo:hi] += amp * np.sin(np.pi * u) ** 2 * np.cos(2 * np.pi * rng.uniform(0.5, 2.0) * u)
        artifacts.append(Artifact(centre, "MOTION", abs(amp)))
    for _ in range(int(rng.poisson(duration_s / 60.0 * phys.pop_per_min))):
        centre, amp, tau = float(rng.uniform(1.0, duration_s - 1.5)), float(rng.uniform(0.4, 1.2)) * float(rng.choice([-1.0, 1.0])), float(rng.uniform(0.3, 0.8))
        lo = int(centre * SOURCE_RATE_HZ)
        decay = amp * np.exp(-(np.arange(n - lo) / SOURCE_RATE_HZ) / tau)
        art[lo:] += decay * (decay != 0)
        artifacts.append(Artifact(centre, "POP", abs(amp)))
    mv = mv + wander + emg + mains + art
    # annotations: what a labeller marked, not the hidden truth
    arng = np.random.default_rng(seed ^ 0xA770)
    marked = [float(x + arng.normal(0.0, ANNOTATION_JITTER_S)) for x in truth if arng.random() >= MISS_RATE]
    marked += [a.time_s for a in artifacts if a.kind == "MOTION" and a.amplitude_mv >= 0.8 and arng.random() < FALSE_ARTIFACT_RATE]
    return Rendered(mv=mv, beats=tuple(beats), artifacts=tuple(artifacts), annotations=tuple(sorted(marked)), true_ectopic=tuple(truth)), phys


def to_counts(mv: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(mv * SIM_ECG_COUNTS_PER_MV), -ADC_RAIL_COUNTS, ADC_RAIL_COUNTS).astype(np.int64)
