from __future__ import annotations

import numpy as np
import pytest

from evaluation.ecg_hr_v2 import reference_hr_at


def test_reference_counts_all_genuine_beats_and_ignores_nonbeats() -> None:
    # Includes paced '/', unmappable 'B', and Q while ignoring rhythm/noise annotations.
    samples = np.asarray([0, 360, 720, 1080, 1440, 1800, 2160, 2520, 2880, 3240, 3600])
    symbols = ["N", "/", "B", "Q", "V", "+", "A", "~", "F", "n", "N"]
    result = reference_hr_at(samples, symbols, timestamp_seconds=10)
    assert result == pytest.approx(60.0)


def test_reference_ignores_future_annotations() -> None:
    base_samples = np.arange(0, 11 * 360, 360)
    base_symbols = ["N"] * len(base_samples)
    first = reference_hr_at(base_samples, base_symbols, timestamp_seconds=10)
    appended = np.append(base_samples, [3601, 3610, 3620])
    second = reference_hr_at(appended, [*base_symbols, "N", "N", "N"], timestamp_seconds=10)
    assert first == second


def test_reference_rr_bounds_and_minimum_count() -> None:
    assert reference_hr_at(np.asarray([0, 50, 100]), ["N"] * 3, timestamp_seconds=1) is None
    assert reference_hr_at(np.asarray([0, 360]), ["N"] * 2, timestamp_seconds=1) is None
