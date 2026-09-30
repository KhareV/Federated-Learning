"""Deterministic T023 perturbations; this module never consumes outcome labels or truth."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

BASE_SEED = 20260930
SCENARIOS = (
    "CLEAN_REFERENCE",
    "ECG_CLIPPING",
    "ECG_DROPOUT",
    "ECG_NOISE_0DB",
    "PPG_CLIPPING",
    "PPG_DROPOUT",
    "MISSING_PPG",
    "CROSS_MODAL_RATE_DISAGREEMENT",
    "SPO2_UNAVAILABLE",
)
SIM_EXTRA_SCENARIOS = ("MOTION_TAGGED",)


@dataclass(frozen=True)
class Interval:
    perturb_start_us: int
    perturb_end_us: int
    analysis_start_us: int
    analysis_end_us: int


def derived_seed(dataset_id: str, session_id: str, scenario_id: str) -> int:
    payload = f"{BASE_SEED}|{dataset_id}|{session_id}|{scenario_id}".encode()
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


def experiment_interval(session_end_us: int) -> Interval:
    preferred = 120_000_000
    latest = (session_end_us - 120_000_000) // 5_000_000 * 5_000_000
    start = min(preferred, latest)
    if start < 30_000_000:
        raise ValueError("T023_SESSION_TOO_SHORT")
    return Interval(start, start + 60_000_000, start - 30_000_000, start + 120_000_000)


def apply_ecg_perturbation(
    source: np.ndarray,
    *,
    sample_rate_hz: int,
    interval: Interval,
    scenario_id: str,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return signal, explicit clipping mask, and long-gap mask on the source clock."""
    values = np.asarray(source, dtype=np.float64).copy()
    clipping = np.zeros(values.size, dtype=bool)
    long_gap = np.zeros(values.size, dtype=bool)
    start = interval.perturb_start_us * sample_rate_hz // 1_000_000
    end = interval.perturb_end_us * sample_rate_hz // 1_000_000
    if scenario_id == "ECG_CLIPPING":
        low, high = float(np.min(values[start:end])), float(np.max(values[start:end]))
        values[start:end:2] = low
        values[start + 1 : end : 2] = high
        clipping[start:end] = True
    elif scenario_id == "ECG_DROPOUT":
        gap_start = start + 20 * sample_rate_hz
        gap_end = gap_start + 10 * sample_rate_hz
        values[gap_start:gap_end] = np.nan
        long_gap[gap_start:gap_end] = True
    elif scenario_id in {"ECG_NOISE_0DB", "MOTION_TAGGED"}:
        clean = values[start:end]
        rms = float(np.sqrt(np.mean(clean**2)))
        rng = np.random.Generator(np.random.PCG64(seed))
        noise = rng.normal(0.0, 1.0, clean.size)
        noise -= float(np.mean(noise))
        noise_rms = float(np.sqrt(np.mean(noise**2)))
        values[start:end] = clean + noise * (rms / noise_rms)
    return values, clipping, long_gap


def perturb_context(
    scenario_id: str,
    timestamp_us: int,
    interval: Interval,
    *,
    ppg_quality: str | None,
    spo2_pct: float | None,
    spo2_valid: bool,
    hr_ecg_bpm: float | None,
    pr_ppg_bpm: float | None,
) -> dict[str, object]:
    active = interval.perturb_start_us <= timestamp_us < interval.perturb_end_us
    result: dict[str, object] = {
        "ppg_quality": ppg_quality,
        "spo2_pct": spo2_pct,
        "spo2_valid": spo2_valid,
        "hr_ecg_bpm": hr_ecg_bpm,
        "pr_ppg_bpm": pr_ppg_bpm,
        "context_injection": "NONE",
    }
    if not active:
        return result
    if scenario_id == "PPG_CLIPPING":
        result.update(ppg_quality="UNUSABLE", pr_ppg_bpm=None, context_injection="PPG_CLIPPING")
    elif scenario_id == "PPG_DROPOUT":
        gap_start = interval.perturb_start_us + 20_000_000
        if gap_start <= timestamp_us < gap_start + 10_000_000:
            result.update(ppg_quality="UNUSABLE", pr_ppg_bpm=None, context_injection="PPG_LONG_GAP")
    elif scenario_id == "MISSING_PPG":
        result.update(ppg_quality=None, pr_ppg_bpm=None, context_injection="MISSING_PPG")
    elif scenario_id == "SPO2_UNAVAILABLE":
        result.update(spo2_pct=None, spo2_valid=False, context_injection="SPO2_UNAVAILABLE")
    elif scenario_id == "CROSS_MODAL_RATE_DISAGREEMENT" and hr_ecg_bpm is not None:
        perturbed = hr_ecg_bpm + 30.0 if hr_ecg_bpm <= 180 else hr_ecg_bpm - 30.0
        result.update(
            pr_ppg_bpm=perturbed,
            context_injection="CONTEXT_RATE_DISAGREEMENT_INJECTION",
        )
    return result
