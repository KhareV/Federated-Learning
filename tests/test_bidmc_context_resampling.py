from __future__ import annotations

import numpy as np
import pytest

from preprocessing.context_resample import load_context_resampler_spec, make_context_resampler


@pytest.mark.parametrize(
    ("identifier", "up", "down", "taps", "delay", "delay_samples"),
    [
        ("BIDMC_PPG_125_TO_100_V1", 4, 5, 101, 0.1, 10),
        ("BIDMC_ECG_HR_125_TO_250_V1", 2, 1, 41, 0.08, 20),
    ],
)
def test_context_specs(identifier, up, down, taps, delay, delay_samples) -> None:
    spec = load_context_resampler_spec(identifier)
    assert (spec.up, spec.down, spec.num_taps) == (up, down, taps)
    assert spec.group_delay_seconds == delay
    assert spec.group_delay_output_samples == delay_samples
    assert spec.preproc_id == "BIDMC_CONTEXT_V1"


@pytest.mark.parametrize("identifier", ["BIDMC_PPG_125_TO_100_V1", "BIDMC_ECG_HR_125_TO_250_V1"])
def test_context_resampler_chunk_and_future_append_invariance(identifier: str) -> None:
    values = np.sin(np.arange(1000) * 0.031) + np.arange(1000) * 1e-5

    whole = make_context_resampler(identifier).process(values, 0)
    chunked_resampler = make_context_resampler(identifier)
    parts = []
    start = 0
    for size in [1] * 11 + [37, 113, 5, 509, 325]:
        stop = start + size
        parts.append(chunked_resampler.process(values[start:stop], start).values)
        start = stop
    assert start == len(values)
    np.testing.assert_array_equal(np.concatenate(parts), whole.values)

    prefix = make_context_resampler(identifier).process(values[:613], 0)
    np.testing.assert_array_equal(prefix.values, whole.values[: len(prefix.values)])
    assert whole.timestamps_us is None


def test_context_resampler_exact_timestamp_grid_and_reset() -> None:
    first = make_context_resampler("BIDMC_PPG_125_TO_100_V1")
    first.reset(segment_start_timestamp_us=0)
    a = first.process(np.arange(125, dtype=float), 0)
    assert np.array_equal(a.timestamps_us, np.arange(len(a.values)) * 10_000)
    first.reset(segment_start_timestamp_us=0)
    reset = first.process(np.arange(125, dtype=float), 0)
    fresh = make_context_resampler("BIDMC_PPG_125_TO_100_V1")
    fresh.reset(segment_start_timestamp_us=0)
    expected = fresh.process(np.arange(125, dtype=float), 0)
    np.testing.assert_array_equal(reset.values, expected.values)
