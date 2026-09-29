from __future__ import annotations

import numpy as np

from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.gaps import GAP_KIND_LONG, GAP_KIND_SHORT
from preprocessing.quality import QualityReason, QualityState, evaluate_ecg_quality
from preprocessing.windowing import (
    WINDOW_SAMPLES,
    candidate_window_starts,
    gap_event_intersects_signal_window,
)


def _pipeline() -> ECGPreprocessingPipeline:
    return ECGPreprocessingPipeline(360, "MITDB_360_TO_250_V1")


def test_short_gap_provenance_forces_degraded_without_suppressing_window() -> None:
    pipeline = _pipeline()
    # 36 missing 360-Hz positions is exactly 100 ms and remains in one segment.
    indices = np.concatenate([np.arange(0, 1000), np.arange(1036, 5000)])
    values = np.sin(indices / 20.0)
    output = pipeline.process(values, indices)
    event = output.events[0]
    assert event.gap_kind == GAP_KIND_SHORT
    filtered = np.concatenate([chunk.filtered_values for chunk in output.chunks])
    assert filtered.size >= WINDOW_SAMPLES
    prediction_us = 10_000_000
    intersects = gap_event_intersects_signal_window(
        event,
        source_rate_hz=360,
        signal_start_timestamp_us=0,
        signal_end_exclusive_timestamp_us=prediction_us,
    )
    result = evaluate_ecg_quality(filtered[:2500], short_gap_intersects=intersects)
    assert result.state == QualityState.DEGRADED
    assert QualityReason.SHORT_GAP_FILL in result.reasons


def test_long_gap_resets_segment_local_history_and_no_window_joins_segments() -> None:
    pipeline = _pipeline()
    pre_indices = np.arange(0, 4000)
    pre = pipeline.process(np.sin(pre_indices / 30.0), pre_indices)
    # 37 missing positions is >100 ms. The new global index is kept as provenance while the
    # resampler is correctly restarted on segment-local zero by ECGPreprocessingPipeline.
    post_start = 4037
    post_indices = np.arange(post_start, post_start + 4000)
    post = pipeline.process(np.cos(post_indices / 25.0), post_indices)
    assert post.events[0].gap_kind == GAP_KIND_LONG
    assert post.chunks[0].global_source_index_start == post_start
    assert post.chunks[0].output_indices[0] == 0
    by_segment = {
        0: np.concatenate([chunk.filtered_values for chunk in pre.chunks]),
        1: np.concatenate([chunk.filtered_values for chunk in post.chunks]),
    }
    assert all(
        next(iter(candidate_window_starts(values.size))) == 0
        for values in by_segment.values()
    )
    assert all(values[:WINDOW_SAMPLES].size == WINDOW_SAMPLES for values in by_segment.values())
    # A conceptual interval spanning the discontinuity is explicitly unusable, but the
    # segment-local builder never materializes it from samples on both sides.
    spanning = evaluate_ecg_quality(
        np.zeros(WINDOW_SAMPLES), long_gap_spans=True
    )
    assert spanning.state == QualityState.UNUSABLE
    assert QualityReason.LONG_GAP_SPAN in spanning.reasons


def test_post_gap_requires_full_new_segment_history() -> None:
    assert len(candidate_window_starts(2499)) == 0
    assert list(candidate_window_starts(2500)) == [0]
