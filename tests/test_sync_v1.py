from __future__ import annotations

import numpy as np
import pytest

from preprocessing.sync import (
    HARDWARE_TOLERANCE_STATUS,
    causal_context_window,
    latest_at_or_before,
    measured_event_offset_us,
    offset_within_tolerance,
)


def test_latest_at_or_before_rejects_future_nearest_and_handles_duplicates() -> None:
    times = np.array([9_900_000, 10_000_000, 10_000_000, 10_020_000])
    aligned = latest_at_or_before(times, [1, 2, 3, 4], 10_001_000)
    assert aligned.available
    assert aligned.timestamp_us == 10_000_000
    assert aligned.value == 3  # deterministic rightmost duplicate policy
    assert aligned.age_us == 1000
    assert latest_at_or_before(times, [1, 2, 3, 4], 9_000_000).status == "CONTEXT_UNAVAILABLE"


def test_fixture_tolerance_and_known_offset_are_engineering_only() -> None:
    offset = measured_event_offset_us(10_000_000, 10_020_000)
    assert offset == 20_000
    assert offset_within_tolerance(offset, 25_000)
    assert not offset_within_tolerance(offset, 10_000)
    assert HARDWARE_TOLERANCE_STATUS == "VERIFICATION_REQUIRED_T004"


def test_context_window_is_half_open_and_causal() -> None:
    times = np.arange(0, 12_000_000, 10_000, dtype=np.int64)
    selected_times, selected = causal_context_window(times, times.copy(), 10_000_000)
    assert selected_times[0] == 0
    assert selected_times[-1] == 9_990_000
    assert np.all(selected_times < 10_000_000)
    np.testing.assert_array_equal(selected_times, selected)


def test_out_of_order_rejected_and_stale_tolerance_enforced() -> None:
    with pytest.raises(ValueError, match="OUT_OF_ORDER_TIMESTAMPS"):
        latest_at_or_before(np.array([2, 1]), ["b", "a"], 3)
    aligned = latest_at_or_before(np.array([1]), ["old"], 10, tolerance_us=5)
    assert not aligned.available
    assert aligned.status == "CONTEXT_OUTSIDE_TOLERANCE"
