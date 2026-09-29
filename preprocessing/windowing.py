"""WINDOWING_V1 construction and exact AAMI_SVF_WINDOW_V1 boundary handling.

Signal samples occupy ``[t-10s, t)`` and annotations use the separately locked closed interval
``[t-10s, t]``.  Source annotations remain on their rational source clock and are never rounded
onto the 250-Hz grid or shifted by the causal resampler delay.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

import numpy as np

from datasets.labels import (
    MAP_ID,
    NOT_A_BEAT,
    TARGET_ID,
    UNMAPPABLE,
    classify_window_target,
    map_annotation_symbol,
)
from nhm.hashing import hash_canonical_json
from preprocessing.gaps import GapEvent
from preprocessing.quality import QualityResult, QualityState

WINDOWING_ID = "WINDOWING_V1"
PREPROC_ID = "PREPROC_V1"
SPLIT_ID = "MITDB_SPLIT_V1"
SAMPLE_RATE_HZ = 250
WINDOW_DURATION_US = 10_000_000
WINDOW_SAMPLES = 2500
STRIDE_SAMPLES = 1250
SAMPLE_PERIOD_US = 4000
NORMALIZATION_ID = "PER_WINDOW_ZSCORE_V1"
NORMALIZATION_EPSILON = 1e-8


@dataclass(frozen=True)
class AnnotationWindowSummary:
    label: int | None
    label_status: str
    exclusion_reasons: tuple[str, ...]
    mapped_n_count: int
    mapped_s_count: int
    mapped_v_count: int
    mapped_f_count: int
    q_count: int
    unmappable_count: int

    @property
    def mappable_beat_count(self) -> int:
        return (
            self.mapped_n_count
            + self.mapped_s_count
            + self.mapped_v_count
            + self.mapped_f_count
        )

    @property
    def svf_beat_count(self) -> int:
        return self.mapped_s_count + self.mapped_v_count + self.mapped_f_count


@dataclass(frozen=True)
class WindowRecord:
    example_id: str
    dataset_id: str
    record_id: str
    participant_group_id: str
    partition: str
    segment_id: int
    prediction_timestamp_us: int
    signal_start_timestamp_us: int
    signal_end_exclusive_timestamp_us: int
    canonical_start_index: int
    canonical_end_index_exclusive: int
    window_samples: int
    sample_rate_hz: int
    ecg_quality: str
    quality_reasons: tuple[str, ...]
    label: int | None
    label_status: str
    exclusion_reasons: tuple[str, ...]
    core_eligible: bool
    mapped_n_count: int
    mapped_s_count: int
    mapped_v_count: int
    mapped_f_count: int
    q_count: int
    unmappable_count: int
    preprocess_id: str = PREPROC_ID
    windowing_id: str = WINDOWING_ID
    map_id: str = MAP_ID
    target_id: str = TARGET_ID
    split_id: str = SPLIT_ID

    def as_manifest_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["quality_reasons"] = ";".join(self.quality_reasons)
        result["exclusion_reasons"] = ";".join(self.exclusion_reasons)
        result["label"] = "" if self.label is None else str(self.label)
        result["core_eligible"] = str(self.core_eligible).upper()
        return result


def candidate_window_starts(sample_count: int) -> range:
    if sample_count < WINDOW_SAMPLES:
        return range(0)
    return range(0, sample_count - WINDOW_SAMPLES + 1, STRIDE_SAMPLES)


def annotation_in_closed_window(
    annotation_source_index: int,
    source_rate_hz: int,
    prediction_timestamp_us: int,
) -> bool:
    """Exact integer/rational test for ``annotation_time in [t-10s, t]``."""
    scaled_annotation = int(annotation_source_index) * 1_000_000
    return (
        (prediction_timestamp_us - WINDOW_DURATION_US) * source_rate_hz
        <= scaled_annotation
        <= prediction_timestamp_us * source_rate_hz
    )


def gap_event_intersects_signal_window(
    event: GapEvent,
    *,
    source_rate_hz: int,
    signal_start_timestamp_us: int,
    signal_end_exclusive_timestamp_us: int,
) -> bool:
    """Exact source-time intersection without analog-resampling a binary gap mask.

    Missing source positions occupy the half-open interval from the first missing sample time
    through one source tick after the last missing position.
    """
    event_start_scaled = event.first_missing_index * 1_000_000
    event_end_scaled = (event.last_missing_index + 1) * 1_000_000
    return (
        event_start_scaled < signal_end_exclusive_timestamp_us * source_rate_hz
        and event_end_scaled > signal_start_timestamp_us * source_rate_hz
    )


def select_annotation_indices_closed(
    annotation_source_indices: Sequence[int] | np.ndarray,
    source_rate_hz: int,
    prediction_timestamp_us: int,
) -> np.ndarray:
    annotations = np.asarray(annotation_source_indices, dtype=np.int64)
    lower = (prediction_timestamp_us - WINDOW_DURATION_US) * source_rate_hz
    upper = prediction_timestamp_us * source_rate_hz
    scaled = annotations * 1_000_000
    return np.flatnonzero((scaled >= lower) & (scaled <= upper))


def summarize_annotations(symbols: Iterable[str]) -> AnnotationWindowSummary:
    mapped = [map_annotation_symbol(symbol).mapped_class for symbol in symbols]
    beats = [mapped_class for mapped_class in mapped if mapped_class != NOT_A_BEAT]
    counts = {key: beats.count(key) for key in ("N", "S", "V", "F", "Q", UNMAPPABLE)}
    target = classify_window_target(beats)
    exclusions: list[str] = []
    if counts["Q"]:
        exclusions.append("EXCLUDE_Q")
    if counts[UNMAPPABLE]:
        exclusions.append("EXCLUDE_UNMAPPABLE")
    if not exclusions and target.target is None:
        exclusions.append("EXCLUDE_LT5_MAPPABLE_BEATS")
    if target.target == 1:
        status = "ELIGIBLE_POSITIVE"
    elif target.target == 0:
        status = "ELIGIBLE_NEGATIVE"
    else:
        status = exclusions[0]
    return AnnotationWindowSummary(
        label=target.target,
        label_status=status,
        exclusion_reasons=tuple(exclusions),
        mapped_n_count=counts["N"],
        mapped_s_count=counts["S"],
        mapped_v_count=counts["V"],
        mapped_f_count=counts["F"],
        q_count=counts["Q"],
        unmappable_count=counts[UNMAPPABLE],
    )


def normalize_window_zscore(
    values: np.ndarray, *, epsilon: float = NORMALIZATION_EPSILON
) -> np.ndarray:
    """Pure per-window population z-score; never fits patient/dataset statistics."""
    signal = np.asarray(values, dtype=np.float64)
    if signal.ndim != 1 or signal.size != WINDOW_SAMPLES:
        raise ValueError(f"normalization requires exactly {WINDOW_SAMPLES} samples")
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    return (signal - float(np.mean(signal))) / (float(np.std(signal, ddof=0)) + epsilon)


def deterministic_example_id(
    *,
    dataset_id: str,
    record_id: str,
    participant_group_id: str,
    partition: str,
    segment_id: int,
    prediction_timestamp_us: int,
) -> str:
    payload = {
        "dataset_id": dataset_id,
        "record_id": record_id,
        "participant_group_id": participant_group_id,
        "partition": partition,
        "segment_id": segment_id,
        "prediction_timestamp_us": prediction_timestamp_us,
        "preprocess_id": PREPROC_ID,
        "windowing_id": WINDOWING_ID,
        "target_id": TARGET_ID,
        "split_id": SPLIT_ID,
    }
    return hash_canonical_json(payload)


def source_window_hash(record_id: str, segment_id: int, start: int, end: int) -> str:
    return sha256(f"{record_id}|{segment_id}|{start}|{end}".encode()).hexdigest()


def create_window_record(
    *,
    dataset_id: str,
    record_id: str,
    participant_group_id: str,
    partition: str,
    segment_id: int,
    canonical_start_index: int,
    segment_start_timestamp_us: int,
    quality: QualityResult,
    annotations: AnnotationWindowSummary,
) -> WindowRecord:
    end = canonical_start_index + WINDOW_SAMPLES
    prediction = segment_start_timestamp_us + end * SAMPLE_PERIOD_US
    reasons = list(annotations.exclusion_reasons)
    if quality.state == QualityState.UNUSABLE:
        reasons.append("EXCLUDE_UNUSABLE_QUALITY")
    core_eligible = annotations.label in (0, 1) and quality.state != QualityState.UNUSABLE
    label_status = annotations.label_status
    if quality.state == QualityState.UNUSABLE and annotations.label in (0, 1):
        label_status = "EXCLUDE_UNUSABLE_QUALITY"
    return WindowRecord(
        example_id=deterministic_example_id(
            dataset_id=dataset_id,
            record_id=record_id,
            participant_group_id=participant_group_id,
            partition=partition,
            segment_id=segment_id,
            prediction_timestamp_us=prediction,
        ),
        dataset_id=dataset_id,
        record_id=record_id,
        participant_group_id=participant_group_id,
        partition=partition,
        segment_id=segment_id,
        prediction_timestamp_us=prediction,
        signal_start_timestamp_us=segment_start_timestamp_us
        + canonical_start_index * SAMPLE_PERIOD_US,
        signal_end_exclusive_timestamp_us=prediction,
        canonical_start_index=canonical_start_index,
        canonical_end_index_exclusive=end,
        window_samples=WINDOW_SAMPLES,
        sample_rate_hz=SAMPLE_RATE_HZ,
        ecg_quality=quality.state.value,
        quality_reasons=tuple(reason.value for reason in quality.reasons),
        label=annotations.label,
        label_status=label_status,
        exclusion_reasons=tuple(dict.fromkeys(reasons)),
        core_eligible=core_eligible,
        mapped_n_count=annotations.mapped_n_count,
        mapped_s_count=annotations.mapped_s_count,
        mapped_v_count=annotations.mapped_v_count,
        mapped_f_count=annotations.mapped_f_count,
        q_count=annotations.q_count,
        unmappable_count=annotations.unmappable_count,
    )
