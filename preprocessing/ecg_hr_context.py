"""Deterministic causal ECG heart-rate context estimators for ECG_HR_CONTEXT_V2."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import wfdb.processing as wfdb_processing

from preprocessing.context_quality import estimate_ecg_rate

ESTIMATOR_ID = "ECG_HR_CONTEXT_V2"
XQRS_ID = "WFDB_XQRS_V1"
GQRS_ID = "WFDB_GQRS_V1"
HISTORICAL_ID = "T021_ABS_PEAK_V1"
ELIGIBLE_CANDIDATES = (XQRS_ID, GQRS_ID)
COMPARISON_CANDIDATES = (XQRS_ID, GQRS_ID, HISTORICAL_ID)
INPUT_RATE_HZ = 250
LOOKBACK_SECONDS = 10
RR_MIN_SECONDS = 0.25
RR_MAX_SECONDS = 2.0
MIN_VALID_INTERVALS = 2


@dataclass(frozen=True)
class ECGHRResult:
    timestamp_us: int
    hr_ecg_bpm: float | None
    valid: bool
    detected_peak_count: int
    valid_rr_interval_count: int
    quality_reason: str
    estimator_id: str = ESTIMATOR_ID


def rate_from_peak_samples(
    peaks: np.ndarray, *, fs: int = INPUT_RATE_HZ
) -> tuple[float | None, int]:
    peak_samples = np.asarray(peaks, dtype=np.int64)
    intervals = np.diff(peak_samples) / fs
    valid = intervals[(intervals >= RR_MIN_SECONDS) & (intervals <= RR_MAX_SECONDS)]
    if valid.size < MIN_VALID_INTERVALS:
        return None, int(valid.size)
    return float(60.0 / np.median(valid)), int(valid.size)


def detect_peaks(samples: np.ndarray, candidate_id: str) -> np.ndarray:
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        return np.asarray([], dtype=np.int64)
    if candidate_id == XQRS_ID:
        detector = wfdb_processing.XQRS(sig=values, fs=INPUT_RATE_HZ)
        detector.detect(learn=True, verbose=False)
        return np.asarray(detector.qrs_inds, dtype=np.int64)
    if candidate_id == GQRS_ID:
        return np.asarray(wfdb_processing.gqrs_detect(sig=values, fs=INPUT_RATE_HZ), dtype=np.int64)
    if candidate_id == HISTORICAL_ID:
        # Exact historical T021 implementation retained only as an ineligible comparator.
        estimate = estimate_ecg_rate(values)
        if estimate.rate_bpm is None:
            return np.asarray([], dtype=np.int64)
        interval = max(1, round(INPUT_RATE_HZ * 60.0 / estimate.rate_bpm))
        return np.arange(0, values.size, interval, dtype=np.int64)
    raise ValueError(f"UNKNOWN_ECG_HR_CANDIDATE: {candidate_id}")


def estimate_hr(samples: np.ndarray, *, timestamp_us: int, candidate_id: str) -> ECGHRResult:
    values = np.asarray(samples, dtype=np.float64)
    if values.shape != (INPUT_RATE_HZ * LOOKBACK_SECONDS,):
        return ECGHRResult(timestamp_us, None, False, 0, 0, "INCOMPLETE_10_SECOND_CONTEXT")
    if candidate_id == HISTORICAL_ID:
        historical = estimate_ecg_rate(values)
        return ECGHRResult(
            timestamp_us,
            historical.rate_bpm,
            historical.rate_bpm is not None,
            historical.valid_interval_count + 1 if historical.rate_bpm is not None else 0,
            historical.valid_interval_count,
            "AVAILABLE" if historical.rate_bpm is not None else "INSUFFICIENT_VALID_RR",
        )
    peaks = detect_peaks(values, candidate_id)
    rate, interval_count = rate_from_peak_samples(peaks)
    return ECGHRResult(
        timestamp_us=timestamp_us,
        hr_ecg_bpm=rate,
        valid=rate is not None,
        detected_peak_count=int(peaks.size),
        valid_rr_interval_count=interval_count,
        quality_reason="AVAILABLE" if rate is not None else "INSUFFICIENT_VALID_RR",
    )


def estimate_hr_at(signal: np.ndarray, *, timestamp_seconds: int, candidate_id: str) -> ECGHRResult:
    """Estimate at integer time t using exactly the last 10 seconds ending at t, never future."""
    end = timestamp_seconds * INPUT_RATE_HZ + 1
    start = end - LOOKBACK_SECONDS * INPUT_RATE_HZ
    window = np.asarray(signal[start:end], dtype=np.float64) if start >= 0 else np.asarray([])
    return estimate_hr(
        window,
        timestamp_us=timestamp_seconds * 1_000_000,
        candidate_id=candidate_id,
    )
