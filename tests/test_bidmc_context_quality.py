from __future__ import annotations

import numpy as np

from preprocessing.context_quality import (
    DEGRADED,
    UNUSABLE,
    estimate_ppg_rate,
    missing_ppg_estimate,
)
from preprocessing.gaps import GAP_KIND_LONG, GAP_KIND_SHORT, GapController


def _pulse() -> np.ndarray:
    values = np.linspace(-0.01, 0.01, 1000)
    values[np.arange(50, 1000, 100)] = 4.0
    return values


def test_missing_ppg_is_unavailable() -> None:
    result = missing_ppg_estimate()
    assert result.quality == UNUSABLE and result.rate_bpm is None


def test_12_sample_short_gap_is_causal_zoh_and_degraded() -> None:
    output = GapController(125).process(np.array([3.0, 9.0]), np.array([0, 13]))
    event = output.events[0]
    assert event.gap_kind == GAP_KIND_SHORT and event.fill_count == 12
    assert np.all(output.chunks[0].values[1:13] == 3.0)
    assert estimate_ppg_rate(_pulse(), short_gap_present=True).quality == DEGRADED


def test_13_sample_long_gap_is_unfilled_and_unusable() -> None:
    output = GapController(125).process(np.array([3.0, 9.0]), np.array([0, 14]))
    event = output.events[0]
    assert event.gap_kind == GAP_KIND_LONG and event.fill_count == 0
    result = estimate_ppg_rate(_pulse(), long_gap_present=True)
    assert result.quality == UNUSABLE and result.rate_bpm is None


def test_clipping_and_flatline_are_unusable() -> None:
    clipped = np.sin(np.arange(1000) * 2 * np.pi / 100)
    clipped[:200] = clipped.max()
    assert estimate_ppg_rate(clipped).quality == UNUSABLE
    flat = estimate_ppg_rate(np.ones(1000))
    assert flat.quality == UNUSABLE and flat.rate_bpm is None
