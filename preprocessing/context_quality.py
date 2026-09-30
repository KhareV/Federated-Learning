"""BIDMC_CONTEXT_V1 quality and deterministic engineering rate estimators."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks

VALID = "VALID"
DEGRADED = "DEGRADED"
UNUSABLE = "UNUSABLE"
EPSILON = 1e-12
CLIPPING_THRESHOLD = 0.20


@dataclass(frozen=True)
class RateEstimate:
    rate_bpm: float | None
    quality: str
    valid_interval_count: int
    clipping_fraction: float


def robust_normalize(values: np.ndarray) -> tuple[np.ndarray, float]:
    values = np.asarray(values, dtype=np.float64)
    center = float(np.median(values))
    scale = float(1.4826 * np.median(np.abs(values - center)))
    return (values - center) / (scale + EPSILON), scale


def clipping_fraction(values: np.ndarray) -> float:
    values = np.asarray(values)
    if values.size == 0:
        return 1.0
    low, high = np.min(values), np.max(values)
    if low == high:
        return 1.0
    return float((np.count_nonzero(values == low) + np.count_nonzero(values == high)) / values.size)


def _estimate(
    values: np.ndarray,
    *,
    sample_rate_hz: int,
    distance: int,
    prominence: float,
    absolute: bool,
    short_gap_present: bool = False,
    long_gap_present: bool = False,
) -> RateEstimate:
    values = np.asarray(values, dtype=np.float64)
    clip = clipping_fraction(values) if np.all(np.isfinite(values)) else 1.0
    if (
        long_gap_present
        or values.size == 0
        or not np.all(np.isfinite(values))
        or clip >= CLIPPING_THRESHOLD
    ):
        return RateEstimate(None, UNUSABLE, 0, clip)
    normalized, scale = robust_normalize(values)
    if scale <= EPSILON:
        return RateEstimate(None, UNUSABLE, 0, clip)
    detector_values = np.abs(normalized) if absolute else normalized
    peaks, _ = find_peaks(detector_values, distance=distance, prominence=prominence)
    intervals = np.diff(peaks) / sample_rate_hz
    valid = intervals[(intervals >= 0.25) & (intervals <= 2.0)]
    if valid.size < 2:
        return RateEstimate(None, UNUSABLE, int(valid.size), clip)
    rate = float(60.0 / np.median(valid))
    return RateEstimate(rate, DEGRADED if short_gap_present else VALID, int(valid.size), clip)


def estimate_ppg_rate(
    values: np.ndarray, *, short_gap_present: bool = False, long_gap_present: bool = False
) -> RateEstimate:
    return _estimate(
        values,
        sample_rate_hz=100,
        distance=25,
        prominence=0.5,
        absolute=False,
        short_gap_present=short_gap_present,
        long_gap_present=long_gap_present,
    )


def estimate_ecg_rate(values: np.ndarray) -> RateEstimate:
    return _estimate(values, sample_rate_hz=250, distance=62, prominence=1.0, absolute=True)


def missing_ppg_estimate() -> RateEstimate:
    return RateEstimate(None, UNUSABLE, 0, 1.0)
