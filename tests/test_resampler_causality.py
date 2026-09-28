"""Causality: direct causal reference equivalence, future-append invariance, timestamp
causality, group delay, and the exact 250-Hz output clock. Declared numerical tolerance:
atol=1e-9, rtol=0 for streaming-vs-reference and future-append comparisons (float64
polyphase dot products over <=5141 taps; observed error is at machine-epsilon scale, see
tests/resampler_reference.py cross-check below). Index/timestamp equality is always exact
(integer), never approximate.
"""

from __future__ import annotations

import numpy as np
import pytest
from resampler_reference import direct_causal_reference

from preprocessing.resample import (
    StatefulRationalResampler,
    expected_output_count,
    load_resampler_spec,
)

RESAMPLER_IDS = ["MITDB_360_TO_250_V1", "INCART_257_TO_250_V1"]
TOLERANCE_ATOL = 1e-9


def _synthetic_signals(n: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return {
        "constant": np.full(n, 2.5),
        "impulse_plus_zeros": np.where(t == 0, 1.0, 0.0),
        "ramp": t.astype(np.float64),
        "low_freq_sine": np.sin(2 * np.pi * 1.5 * t / 250.0),
        "mixed_sinusoid": (
            np.sin(2 * np.pi * 5 * t / 250.0) + 0.3 * np.sin(2 * np.pi * 40 * t / 250.0)
        ),
        "seeded_white_noise": rng.standard_normal(n),
    }


SIGNAL_NAMES = [
    "constant", "impulse_plus_zeros", "ramp", "low_freq_sine", "mixed_sinusoid",
    "seeded_white_noise",
]


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
@pytest.mark.parametrize("signal_name", SIGNAL_NAMES)
def test_streaming_matches_direct_causal_reference(resampler_id: str, signal_name: str) -> None:
    spec = load_resampler_spec(resampler_id)
    n = 300
    x = _synthetic_signals(n, seed=11)[signal_name]
    n_out = expected_output_count(n, spec.up, spec.down)

    reference = direct_causal_reference(x, spec.up, spec.down, spec.coefficients, n_out)
    resampler = StatefulRationalResampler(spec)
    chunk = resampler.process(x, 0)

    assert len(chunk.values) == n_out
    max_error = np.max(np.abs(chunk.values - reference))
    assert max_error <= TOLERANCE_ATOL, f"max streaming-vs-reference error {max_error}"


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_future_append_does_not_change_earlier_outputs(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    rng = np.random.default_rng(2026)
    prefix_n = 400
    prefix = rng.standard_normal(prefix_n)

    adversarial_suffixes = [
        np.full(500, 1e6),
        rng.standard_normal(500) * 1e6,
        np.where(np.arange(500) % 2 == 0, 1e9, -1e9),
    ]

    resampler_prefix_only = StatefulRationalResampler(spec)
    prefix_chunk = resampler_prefix_only.process(prefix, 0)

    for suffix in adversarial_suffixes:
        full_signal = np.concatenate([prefix, suffix])
        resampler_full = StatefulRationalResampler(spec)
        full_chunk = resampler_full.process(full_signal, 0)

        n_common = len(prefix_chunk.values)
        assert np.array_equal(
            full_chunk.output_indices[:n_common], prefix_chunk.output_indices
        )
        max_error = np.max(np.abs(full_chunk.values[:n_common] - prefix_chunk.values))
        assert max_error <= TOLERANCE_ATOL, f"future-append changed earlier output by {max_error}"


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_future_append_timestamp_causality(resampler_id: str) -> None:
    """An output timestamped <= t never changes after appending samples acquired after t."""
    spec = load_resampler_spec(resampler_id)
    rng = np.random.default_rng(99)
    prefix = rng.standard_normal(350)
    segment_start_us = 1_000_000

    resampler_prefix = StatefulRationalResampler(spec, segment_start_timestamp_us=segment_start_us)
    prefix_chunk = resampler_prefix.process(prefix, 0)

    suffix = np.where(np.arange(500) % 3 == 0, 5e8, -5e8)
    full = np.concatenate([prefix, suffix])
    resampler_full = StatefulRationalResampler(spec, segment_start_timestamp_us=segment_start_us)
    full_chunk = resampler_full.process(full, 0)

    latest_prefix_timestamp = prefix_chunk.timestamps_us[-1]
    already_emittable = full_chunk.timestamps_us <= latest_prefix_timestamp
    assert already_emittable.sum() == len(prefix_chunk.timestamps_us)
    assert np.array_equal(
        full_chunk.timestamps_us[already_emittable], prefix_chunk.timestamps_us
    )
    causal_error = np.max(np.abs(full_chunk.values[already_emittable] - prefix_chunk.values))
    assert causal_error <= TOLERANCE_ATOL


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_impulse_response_peak_at_expected_group_delay(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    n = 2 * spec.num_taps
    x = np.zeros(n)
    x[0] = 1.0
    resampler = StatefulRationalResampler(spec)
    chunk = resampler.process(x, 0)

    peak_index = int(np.argmax(np.abs(chunk.values)))
    assert peak_index == spec.group_delay_output_samples == 10

    resampler_ts = StatefulRationalResampler(spec, segment_start_timestamp_us=0)
    chunk_ts = resampler_ts.process(x, 0)
    peak_timestamp_ms = chunk_ts.timestamps_us[peak_index] / 1000.0
    assert peak_timestamp_ms == pytest.approx(40.0, abs=1e-9)
    assert spec.group_delay_seconds == pytest.approx(0.040, abs=1e-12)


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_output_clock_is_exact_4000us_grid_no_drift(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    rng = np.random.default_rng(5)
    x = rng.standard_normal(3000)
    resampler = StatefulRationalResampler(spec, segment_start_timestamp_us=42)
    chunk = resampler.process(x, 0)

    diffs = np.diff(chunk.timestamps_us)
    assert np.all(diffs == 4000), "output clock must increment by exactly 4000us, no drift"


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_output_timestamps_are_not_backdated_by_group_delay(resampler_id: str) -> None:
    """No backward group-delay compensation: output m's timestamp is segment_start + 4000*m,
    never segment_start + 4000*m - group_delay_us."""
    spec = load_resampler_spec(resampler_id)
    x = np.ones(50)
    segment_start_us = 10_000
    resampler = StatefulRationalResampler(spec, segment_start_timestamp_us=segment_start_us)
    chunk = resampler.process(x, 0)
    for m, timestamp in zip(chunk.output_indices, chunk.timestamps_us, strict=True):
        assert timestamp == segment_start_us + 4000 * int(m)
