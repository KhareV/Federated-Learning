"""GAP_POLICY_V1: exact 100-ms boundary classification, causal ZOH short-gap fill, long-gap
no-fill/segment-reset provenance, determinism, and adversarial post-gap-value independence."""

from __future__ import annotations

import numpy as np
import pytest

from preprocessing.gaps import (
    GAP_KIND_LONG,
    GAP_KIND_SHORT,
    GAP_POLICY_ID,
    QUALITY_FLOOR_DEGRADED,
    QUALITY_REQUIREMENT_UNUSABLE,
    GapController,
    NonMonotonicSourceIndexError,
    is_short_gap,
)

BOUNDARY_CASES = [
    (250, 25, "SHORT"), (250, 26, "LONG"),
    (360, 36, "SHORT"), (360, 37, "LONG"),
    (257, 25, "SHORT"), (257, 26, "LONG"),
    (100, 10, "SHORT"), (100, 11, "LONG"),
    (125, 12, "SHORT"), (125, 13, "LONG"),
]


@pytest.mark.parametrize("source_rate_hz,missing_count,expected_class", BOUNDARY_CASES)
def test_100ms_boundary_is_exact(
    source_rate_hz: int, missing_count: int, expected_class: str
) -> None:
    assert is_short_gap(missing_count, source_rate_hz) == (expected_class == "SHORT")


def test_zero_missing_is_not_a_gap() -> None:
    gc = GapController(250)
    out = gc.process(np.array([1.0, 2.0]), np.array([0, 1]))
    assert out.events == []
    assert len(out.chunks) == 1
    assert np.array_equal(out.chunks[0].gap_mask, [0, 0])


# ---------------------------------------------------------------------------------------
# Short gap: exact causal ZOH fill
# ---------------------------------------------------------------------------------------


def test_short_gap_fills_with_exact_last_pre_gap_value() -> None:
    """Distinctive exactly-representable float; every filled position must equal it exactly,
    no tolerance."""
    gc = GapController(250)
    gc.process(np.array([123.456789]), np.array([0]))
    out = gc.process(np.array([999.0]), np.array([26]))  # missing=25, SHORT at 250Hz
    chunk = out.chunks[0]
    filled = chunk.values[chunk.gap_mask == 1]
    assert filled.size == 25
    assert np.all(filled == 123.456789)


def test_short_gap_mask_marks_fills_1_and_real_samples_0() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([0]))
    out = gc.process(np.array([2.0]), np.array([11]))  # missing=10, SHORT
    chunk = out.chunks[0]
    assert list(chunk.gap_mask) == [1] * 10 + [0]
    assert chunk.values[-1] == 2.0  # post-gap real sample retains its own real value


def test_short_gap_does_not_break_the_segment() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([0]))
    out = gc.process(np.array([2.0]), np.array([11]))
    assert out.events[0].gap_kind == GAP_KIND_SHORT
    assert out.events[0].previous_segment_id == out.events[0].next_segment_id == 0
    assert out.chunks[0].starts_new_segment is False


def test_short_gap_quality_requirement_is_degraded() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([0]))
    out = gc.process(np.array([2.0]), np.array([11]))
    assert out.events[0].quality_requirement == QUALITY_FLOOR_DEGRADED


def test_short_gap_fill_is_independent_of_post_gap_value() -> None:
    """Adversarial: identical prefix/gap, radically different post-gap value -- every filled
    value must be identical between the two cases."""
    pre_gap_value = 42.0

    gc_a = GapController(250)
    gc_a.process(np.array([pre_gap_value]), np.array([0]))
    out_a = gc_a.process(np.array([1.0]), np.array([26]))

    gc_b = GapController(250)
    gc_b.process(np.array([pre_gap_value]), np.array([0]))
    out_b = gc_b.process(np.array([1e9]), np.array([26]))

    fills_a = out_a.chunks[0].values[out_a.chunks[0].gap_mask == 1]
    fills_b = out_b.chunks[0].values[out_b.chunks[0].gap_mask == 1]
    assert np.array_equal(fills_a, fills_b)
    assert np.all(fills_a == pre_gap_value)


def test_short_gap_processing_order_fills_before_real_sample() -> None:
    gc = GapController(250)
    gc.process(np.array([7.0]), np.array([0]))
    out = gc.process(np.array([8.0]), np.array([6]))  # missing=5
    chunk = out.chunks[0]
    assert list(chunk.gap_mask) == [1, 1, 1, 1, 1, 0]
    assert list(chunk.values) == [7.0, 7.0, 7.0, 7.0, 7.0, 8.0]
    assert list(chunk.source_indices) == [1, 2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------------------
# Long gap: no fill, segment break, reset provenance
# ---------------------------------------------------------------------------------------


def test_long_gap_produces_no_fill() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([0]))
    out = gc.process(np.array([2.0]), np.array([27]))  # missing=26, LONG
    event = out.events[0]
    assert event.gap_kind == GAP_KIND_LONG
    assert event.fill_count == 0
    chunk = out.chunks[0]
    assert len(chunk.values) == 1
    assert chunk.values[0] == 2.0
    assert chunk.gap_mask[0] == 0


def test_long_gap_increments_segment_id_and_flags_new_segment() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([0]))
    out = gc.process(np.array([2.0]), np.array([27]))
    assert out.events[0].previous_segment_id == 0
    assert out.events[0].next_segment_id == 1
    assert out.chunks[0].segment_id == 1
    assert out.chunks[0].starts_new_segment is True


def test_long_gap_quality_requirement_is_unusable() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([0]))
    out = gc.process(np.array([2.0]), np.array([27]))
    assert out.events[0].quality_requirement == QUALITY_REQUIREMENT_UNUSABLE


def test_long_gap_event_carries_complete_provenance() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([0]))
    out = gc.process(np.array([2.0]), np.array([27]))
    event = out.events[0]
    assert event.gap_policy_id == GAP_POLICY_ID
    assert event.missing_count == 26
    assert event.first_missing_index == 1
    assert event.last_missing_index == 26
    assert event.last_pre_gap_index == 0
    assert event.first_post_gap_index == 27


# ---------------------------------------------------------------------------------------
# Nonmonotonic input, determinism, cross-chunk/multi-gap, future independence
# ---------------------------------------------------------------------------------------


def test_duplicate_source_index_is_rejected() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([5]))
    with pytest.raises(NonMonotonicSourceIndexError, match="NON_MONOTONIC_SOURCE_INDEX"):
        gc.process(np.array([2.0]), np.array([5]))


def test_backward_source_index_is_rejected() -> None:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([10]))
    with pytest.raises(NonMonotonicSourceIndexError, match="NON_MONOTONIC_SOURCE_INDEX"):
        gc.process(np.array([2.0]), np.array([3]))


def test_gap_detection_is_identical_whether_gap_is_inside_or_across_calls() -> None:
    values = np.array([1.0, 2.0, 3.0])
    indices = np.array([0, 1, 40])  # missing=38 at 250Hz -> LONG, inside a single call

    gc_single = GapController(250)
    out_single = gc_single.process(values, indices)

    gc_split = GapController(250)
    out_split_a = gc_split.process(values[:2], indices[:2])
    out_split_b = gc_split.process(values[2:], indices[2:])

    combined_events = out_split_a.events + out_split_b.events
    assert len(combined_events) == len(out_single.events) == 1
    assert combined_events[0] == out_single.events[0]


def test_multiple_gaps_in_one_stream_are_deterministic_state_machine() -> None:
    """no gap, short gap, short gap, long gap, short gap after reset."""

    def build_stream() -> tuple[np.ndarray, np.ndarray]:
        values = [0.0, 1.0]
        indices = [0, 1]
        values.append(2.0)
        indices.append(12)  # +10 missing -> SHORT
        values.append(3.0)
        indices.append(23)  # +10 missing -> SHORT
        values.append(4.0)
        indices.append(23 + 30)  # +29 missing -> LONG (>25 at 250Hz)
        base = 23 + 30
        values.append(5.0)
        indices.append(base + 6)  # +5 missing -> SHORT, in the new segment
        return np.array(values), np.array(indices)

    def run() -> tuple[list, list]:
        gc = GapController(250)
        vals, idx = build_stream()
        out = gc.process(vals, idx)
        return [event.gap_kind for event in out.events], [c.segment_id for c in out.chunks]

    kinds_a, segments_a = run()
    kinds_b, segments_b = run()
    assert kinds_a == kinds_b == [GAP_KIND_SHORT, GAP_KIND_SHORT, GAP_KIND_LONG, GAP_KIND_SHORT]
    assert segments_a == segments_b


def test_gap_events_are_deterministic_across_runs() -> None:
    rng_indices = np.array([0, 1, 2, 40, 41, 42, 43])  # one long gap at index 3
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])

    gc_a = GapController(360)
    out_a = gc_a.process(values, rng_indices)
    gc_b = GapController(360)
    out_b = gc_b.process(values, rng_indices)

    assert out_a.events == out_b.events
    for chunk_a, chunk_b in zip(out_a.chunks, out_b.chunks, strict=True):
        assert np.array_equal(chunk_a.values, chunk_b.values)
        assert np.array_equal(chunk_a.gap_mask, chunk_b.gap_mask)
        assert np.array_equal(chunk_a.source_indices, chunk_b.source_indices)
        assert chunk_a.segment_id == chunk_b.segment_id


def test_future_samples_do_not_change_already_processed_gap_fills() -> None:
    gc = GapController(250)
    gc.process(np.array([5.0]), np.array([0]))
    out_before = gc.process(np.array([6.0]), np.array([11]))  # short gap, filled with 5.0
    fills_before = out_before.chunks[0].values[out_before.chunks[0].gap_mask == 1].copy()

    # append drastically different future data; earlier fills must not change
    gc.process(np.array([1e9, -1e9]), np.array([12, 13]))
    assert np.all(fills_before == 5.0)


def test_nonfinite_values_are_rejected() -> None:
    gc = GapController(250)
    with pytest.raises(ValueError, match="NONFINITE_SOURCE_SAMPLE"):
        gc.process(np.array([1.0, float("nan")]), np.array([0, 1]))
