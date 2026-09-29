"""BASELINE_FEATURES_V1: deterministic waveform-only 10-second ECG features.

The public API accepts only a filtered ECG waveform and its sample rate. It has no label,
annotation, quality, identifier, partition, or record-context input. The QRS-like detector is
an engineering feature primitive for classical baselines only; it is not a clinical detector,
reference annotation system, wearable HR algorithm, or MODEL_V1 preprocessing stage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy
from scipy.signal import find_peaks, peak_widths
from scipy.stats import kurtosis, skew

FEATURE_SET_ID = "BASELINE_FEATURES_V1"
DETECTOR_ID = "SCIPY_FIND_PEAKS_ABS_MEDIAN_V1"
EXPECTED_SAMPLE_RATE_HZ = 250
EXPECTED_WINDOW_SAMPLES = 2500
DETECTOR_DISTANCE_SAMPLES = 50
DETECTOR_PROMINENCE_FACTOR = 3.0
DETECTOR_PROMINENCE_FLOOR = 1e-12
DETECTOR_WIDTH_REL_HEIGHT = 0.5
LOCAL_HALF_WIDTH_SAMPLES = 13

BASELINE_FEATURE_NAMES_V1: tuple[str, ...] = (
    "ecg_mean",
    "ecg_std",
    "ecg_median",
    "ecg_mad",
    "ecg_rms",
    "ecg_min",
    "ecg_max",
    "ecg_peak_to_peak",
    "ecg_iqr",
    "ecg_mean_absolute",
    "ecg_skewness",
    "ecg_kurtosis",
    "ecg_mean_absolute_difference",
    "detected_beat_count",
    "rr_mean_seconds",
    "rr_median_seconds",
    "rr_std_seconds",
    "rr_min_seconds",
    "rr_max_seconds",
    "rr_rmssd_seconds",
    "detected_hr_mean_bpm",
    "rr_available",
    "qrs_peak_absolute_mean",
    "qrs_peak_absolute_std",
    "qrs_local_energy_mean",
    "qrs_local_energy_std",
    "qrs_local_max_slope_mean",
    "qrs_width_half_prominence_mean_ms",
    "qrs_available",
)


@dataclass(frozen=True)
class FeatureExtractionResult:
    values: np.ndarray
    detected_peak_indices: np.ndarray
    feature_set_id: str = FEATURE_SET_ID
    detector_id: str = DETECTOR_ID


def feature_schema_sha256() -> str:
    from nhm.hashing import hash_canonical_json

    return hash_canonical_json(
        {
            "feature_set_id": FEATURE_SET_ID,
            "feature_names": list(BASELINE_FEATURE_NAMES_V1),
            "sample_rate_hz": EXPECTED_SAMPLE_RATE_HZ,
            "window_samples": EXPECTED_WINDOW_SAMPLES,
            "detector": detector_metadata(),
        }
    )


def detector_metadata() -> dict[str, object]:
    return {
        "detector_id": DETECTOR_ID,
        "package": "scipy",
        "package_version": scipy.__version__,
        "function": "scipy.signal.find_peaks",
        "input_transform": "absolute(signal - median(signal))",
        "distance_samples": DETECTOR_DISTANCE_SAMPLES,
        "prominence_factor_times_window_mad": DETECTOR_PROMINENCE_FACTOR,
        "prominence_numerical_floor": DETECTOR_PROMINENCE_FLOOR,
        "width_rel_height": DETECTOR_WIDTH_REL_HEIGHT,
        "local_half_width_samples": LOCAL_HALF_WIDTH_SAMPLES,
    }


def _safe_shape(signal: np.ndarray, sample_rate_hz: int) -> np.ndarray:
    values = np.asarray(signal, dtype=np.float64)
    if values.ndim != 1 or values.size != EXPECTED_WINDOW_SAMPLES:
        raise ValueError(f"expected one {EXPECTED_WINDOW_SAMPLES}-sample ECG window")
    if sample_rate_hz != EXPECTED_SAMPLE_RATE_HZ:
        raise ValueError(f"expected sample_rate_hz={EXPECTED_SAMPLE_RATE_HZ}")
    if not np.all(np.isfinite(values)):
        raise ValueError("eligible baseline ECG window must be finite")
    return values


def detect_qrs_like_peaks(signal: np.ndarray, sample_rate_hz: int = 250) -> np.ndarray:
    values = _safe_shape(signal, sample_rate_hz)
    centered_absolute = np.abs(values - np.median(values))
    mad = float(np.median(np.abs(values - np.median(values))))
    prominence = max(DETECTOR_PROMINENCE_FACTOR * mad, DETECTOR_PROMINENCE_FLOOR)
    peaks, _ = find_peaks(
        centered_absolute,
        distance=DETECTOR_DISTANCE_SAMPLES,
        prominence=prominence,
    )
    return np.asarray(peaks, dtype=np.int64)


def _mean_std(values: np.ndarray) -> tuple[float, float]:
    if values.size == 0:
        return float("nan"), float("nan")
    return float(np.mean(values)), float(np.std(values, ddof=0))


def extract_baseline_features(
    signal: np.ndarray, sample_rate_hz: int = EXPECTED_SAMPLE_RATE_HZ
) -> FeatureExtractionResult:
    values = _safe_shape(signal, sample_rate_hz)
    median = float(np.median(values))
    std = float(np.std(values, ddof=0))
    differences = np.diff(values)
    peaks = detect_qrs_like_peaks(values, sample_rate_hz)
    rr = np.diff(peaks).astype(np.float64) / sample_rate_hz

    if rr.size:
        rr_mean = float(np.mean(rr))
        rr_median = float(np.median(rr))
        rr_std = float(np.std(rr, ddof=0))
        rr_min = float(np.min(rr))
        rr_max = float(np.max(rr))
        rr_rmssd = float(np.sqrt(np.mean(np.square(np.diff(rr))))) if rr.size >= 2 else np.nan
        heart_rate = float(60.0 / rr_mean) if rr_mean > 0 else np.nan
        rr_available = 1.0
    else:
        rr_mean = rr_median = rr_std = rr_min = rr_max = rr_rmssd = heart_rate = np.nan
        rr_available = 0.0

    peak_absolute = np.abs(values[peaks] - median) if peaks.size else np.empty(0)
    peak_mean, peak_std = _mean_std(peak_absolute)
    local_energies: list[float] = []
    local_slopes: list[float] = []
    for peak in peaks.tolist():
        left = max(0, peak - LOCAL_HALF_WIDTH_SAMPLES)
        right = min(values.size, peak + LOCAL_HALF_WIDTH_SAMPLES + 1)
        local = values[left:right]
        local_energies.append(float(np.mean(np.square(local - median))))
        local_slopes.append(
            float(np.max(np.abs(np.diff(local)))) if local.size >= 2 else float("nan")
        )
    energy_mean, energy_std = _mean_std(np.asarray(local_energies, dtype=np.float64))
    slope_values = np.asarray(local_slopes, dtype=np.float64)
    slope_mean = float(np.nanmean(slope_values)) if slope_values.size else np.nan
    if peaks.size:
        width_samples = peak_widths(
            np.abs(values - median), peaks, rel_height=DETECTOR_WIDTH_REL_HEIGHT
        )[0]
        width_mean_ms = float(np.mean(width_samples) * 1000.0 / sample_rate_hz)
        qrs_available = 1.0
    else:
        width_mean_ms = np.nan
        qrs_available = 0.0

    statistical_skew = 0.0 if std == 0.0 else float(skew(values, bias=False))
    statistical_kurtosis = 0.0 if std == 0.0 else float(kurtosis(values, bias=False))
    vector = np.asarray(
        [
            float(np.mean(values)),
            std,
            median,
            float(np.median(np.abs(values - median))),
            float(np.sqrt(np.mean(np.square(values)))),
            float(np.min(values)),
            float(np.max(values)),
            float(np.ptp(values)),
            float(np.percentile(values, 75) - np.percentile(values, 25)),
            float(np.mean(np.abs(values))),
            statistical_skew,
            statistical_kurtosis,
            float(np.mean(np.abs(differences))),
            float(peaks.size),
            rr_mean,
            rr_median,
            rr_std,
            rr_min,
            rr_max,
            rr_rmssd,
            heart_rate,
            rr_available,
            peak_mean,
            peak_std,
            energy_mean,
            energy_std,
            slope_mean,
            width_mean_ms,
            qrs_available,
        ],
        dtype=np.float64,
    )
    if vector.shape != (len(BASELINE_FEATURE_NAMES_V1),):
        raise AssertionError("feature vector/schema length mismatch")
    return FeatureExtractionResult(vector, peaks)
