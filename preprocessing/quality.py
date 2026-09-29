"""QUALITY_V1 deterministic ECG engineering-quality classification.

Quality is deliberately independent of AAMI labels, diagnoses, model outputs, and partition
prevalence.  The evaluator consumes only the current 10-second signal and explicit causal
provenance flags.  Its rules are engineering safeguards, not clinical thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

QUALITY_ID = "QUALITY_V1"
EXPECTED_WINDOW_SAMPLES = 2500
FLATLINE_RELATIVE_EPSILON = 1e-12


class QualityState(StrEnum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    UNUSABLE = "UNUSABLE"


class QualityReason(StrEnum):
    SHORT_GAP_FILL = "SHORT_GAP_FILL"
    LONG_GAP_SPAN = "LONG_GAP_SPAN"
    NONFINITE_SIGNAL = "NONFINITE_SIGNAL"
    INCOMPLETE_WINDOW = "INCOMPLETE_WINDOW"
    FLATLINE = "FLATLINE"
    CLIPPING = "CLIPPING"
    DETECTOR_CONSISTENCY_FAILURE = "DETECTOR_CONSISTENCY_FAILURE"


@dataclass(frozen=True)
class QualityResult:
    state: QualityState
    reasons: tuple[QualityReason, ...]
    quality_id: str = QUALITY_ID


def is_flatline(
    values: np.ndarray, *, relative_epsilon: float = FLATLINE_RELATIVE_EPSILON
) -> bool:
    """Return whether variability is numerically absent relative to signal scale.

    ``std / rms`` is invariant to multiplication by a nonzero scale factor.  Exact all-zero
    input is handled explicitly.  The epsilon is a floating-point engineering tolerance and
    was not selected from validation, calibration, internal-test, or external data.
    """
    signal = np.asarray(values, dtype=np.float64)
    if signal.size == 0 or not np.all(np.isfinite(signal)):
        return False
    rms = float(np.sqrt(np.mean(np.square(signal))))
    if rms == 0.0:
        return True
    return float(np.std(signal, ddof=0)) / rms <= relative_epsilon


def evaluate_ecg_quality(
    values: np.ndarray,
    *,
    short_gap_intersects: bool = False,
    long_gap_spans: bool = False,
    clipping_mask: np.ndarray | None = None,
    detector_consistency_failure: bool = False,
    expected_samples: int = EXPECTED_WINDOW_SAMPLES,
    flatline_relative_epsilon: float = FLATLINE_RELATIVE_EPSILON,
) -> QualityResult:
    """Classify one window with precedence ``UNUSABLE > DEGRADED > VALID``.

    ``clipping_mask`` must come from an explicit upstream source.  This module never invents
    public-data or wearable ADC rails.  Hardware rail semantics remain a T004/T030 concern.
    """
    signal = np.asarray(values, dtype=np.float64)
    hard: list[QualityReason] = []
    degraded: list[QualityReason] = []

    if signal.ndim != 1 or signal.size != expected_samples:
        hard.append(QualityReason.INCOMPLETE_WINDOW)
    if not np.all(np.isfinite(signal)):
        hard.append(QualityReason.NONFINITE_SIGNAL)
    if long_gap_spans:
        hard.append(QualityReason.LONG_GAP_SPAN)
    if signal.size == expected_samples and np.all(np.isfinite(signal)) and is_flatline(
        signal, relative_epsilon=flatline_relative_epsilon
    ):
        hard.append(QualityReason.FLATLINE)

    if clipping_mask is not None:
        mask = np.asarray(clipping_mask, dtype=bool)
        if mask.shape != signal.shape:
            raise ValueError("clipping_mask must have the same shape as values")
        if bool(mask.any()):
            hard.append(QualityReason.CLIPPING)
    if detector_consistency_failure:
        hard.append(QualityReason.DETECTOR_CONSISTENCY_FAILURE)
    if short_gap_intersects:
        degraded.append(QualityReason.SHORT_GAP_FILL)

    reasons = tuple(dict.fromkeys([*hard, *degraded]))
    if hard:
        return QualityResult(QualityState.UNUSABLE, reasons)
    if degraded:
        return QualityResult(QualityState.DEGRADED, reasons)
    return QualityResult(QualityState.VALID, ())
