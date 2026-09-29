from __future__ import annotations

import numpy as np
import pytest

from preprocessing.quality import QualityResult, QualityState
from preprocessing.windowing import (
    NORMALIZATION_EPSILON,
    SAMPLE_PERIOD_US,
    STRIDE_SAMPLES,
    WINDOW_SAMPLES,
    AnnotationWindowSummary,
    annotation_in_closed_window,
    candidate_window_starts,
    create_window_record,
    deterministic_example_id,
    normalize_window_zscore,
)


@pytest.mark.parametrize(
    ("count", "expected"),
    [(2499, 0), (2500, 1), (3749, 1), (3750, 2), (5000, 3)],
)
def test_candidate_count_boundaries(count: int, expected: int) -> None:
    assert len(candidate_window_starts(count)) == expected


def test_exact_geometry_right_edge_and_no_future_sample() -> None:
    starts = list(candidate_window_starts(3750))
    assert starts == [0, 1250]
    timestamps = np.arange(3750, dtype=np.int64) * SAMPLE_PERIOD_US
    for start, prediction in zip(starts, [10_000_000, 15_000_000], strict=True):
        selected = timestamps[start : start + WINDOW_SAMPLES]
        assert selected.size == 2500
        assert int(selected.max()) == prediction - SAMPLE_PERIOD_US
        assert bool(np.all(selected < prediction))
    assert WINDOW_SAMPLES - STRIDE_SAMPLES == 1250


@pytest.mark.parametrize("source_rate_hz", [360, 257])
def test_annotation_closed_boundaries_use_exact_source_arithmetic(source_rate_hz: int) -> None:
    # Choose t=10s, for which both edges land exactly on either source grid.
    t = 10_000_000
    assert not annotation_in_closed_window(-1, source_rate_hz, t)
    assert annotation_in_closed_window(0, source_rate_hz, t)
    assert annotation_in_closed_window(5 * source_rate_hz, source_rate_hz, t)
    assert annotation_in_closed_window(10 * source_rate_hz, source_rate_hz, t)
    assert not annotation_in_closed_window(10 * source_rate_hz + 1, source_rate_hz, t)


def test_deterministic_example_id_is_stable_and_provenance_sensitive() -> None:
    args = dict(
        dataset_id="MITDB",
        record_id="100",
        participant_group_id="MITDB_P100",
        partition="VALIDATION",
        segment_id=0,
        prediction_timestamp_us=10_000_000,
    )
    assert deterministic_example_id(**args) == deterministic_example_id(**args)
    assert deterministic_example_id(**args) != deterministic_example_id(
        **{**args, "prediction_timestamp_us": 15_000_000}
    )


def test_window_record_keeps_quality_and_label_eligibility_separate() -> None:
    annotations = AnnotationWindowSummary(1, "ELIGIBLE_POSITIVE", (), 4, 1, 0, 0, 0, 0)
    degraded = QualityResult(QualityState.DEGRADED, ())
    row = create_window_record(
        dataset_id="MITDB",
        record_id="100",
        participant_group_id="MITDB_P100",
        partition="VALIDATION",
        segment_id=0,
        canonical_start_index=0,
        segment_start_timestamp_us=0,
        quality=degraded,
        annotations=annotations,
    )
    assert row.core_eligible is True
    assert row.prediction_timestamp_us == 10_000_000
    assert row.signal_end_exclusive_timestamp_us == row.prediction_timestamp_us


def test_per_window_zscore_is_local_population_formula() -> None:
    window = np.linspace(-2.0, 3.0, WINDOW_SAMPLES)
    normalized = normalize_window_zscore(window)
    expected = (window - window.mean()) / (window.std(ddof=0) + NORMALIZATION_EPSILON)
    np.testing.assert_array_equal(normalized, expected)
    changed_future = np.concatenate([window, np.full(100, 1e9)])
    np.testing.assert_array_equal(normalized, normalize_window_zscore(changed_future[:2500]))

