"""Chunk equivalence and output-length invariants. Tolerance: atol=1e-9 for value comparisons
across chunkings (see tests/test_resampler_causality.py header for the same declared bound);
output indices/counts must match exactly."""

from __future__ import annotations

import numpy as np
import pytest

from preprocessing.resample import (
    StatefulRationalResampler,
    expected_output_count,
    load_resampler_spec,
)

RESAMPLER_IDS = ["MITDB_360_TO_250_V1", "INCART_257_TO_250_V1"]
TOLERANCE_ATOL = 1e-9

CHUNKING_STRATEGIES = {
    "single_chunk": lambda n: [n],
    "one_sample_chunks": lambda n: [1] * n,
    "small_regular_chunks": lambda n: [4] * (n // 4) + ([n % 4] if n % 4 else []),
    "prime_sized_chunks": lambda n: _fill(n, [7, 11, 13, 17, 19, 23]),
    "pathological_tiny_chunks": lambda n: _fill(n, [1, 2, 3, 7, 11]),
}


def _fill(n: int, cycle: list[int]) -> list[int]:
    sizes = []
    remaining = n
    index = 0
    while remaining > 0:
        size = min(cycle[index % len(cycle)], remaining)
        sizes.append(size)
        remaining -= size
        index += 1
    return sizes


def _boundary_chunk_sizes(resampler_id: str, n: int) -> list[int]:
    boundaries = {
        "MITDB_360_TO_250_V1": [25, 36, 72],
        "INCART_257_TO_250_V1": [250, 257, 514],
    }[resampler_id]
    return _fill(n, boundaries)


def _run_chunked(spec, x: np.ndarray, chunk_sizes: list[int]):
    resampler = StatefulRationalResampler(spec)
    values_parts = []
    indices_parts = []
    index = 0
    for size in chunk_sizes:
        chunk = resampler.process(x[index : index + size], index)
        values_parts.append(chunk.values)
        indices_parts.append(chunk.output_indices)
        index += size
    return (
        np.concatenate(indices_parts) if indices_parts else np.array([], dtype=np.int64),
        np.concatenate(values_parts) if values_parts else np.array([], dtype=np.float64),
        resampler,
    )


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
@pytest.mark.parametrize("strategy_name", list(CHUNKING_STRATEGIES))
def test_chunking_strategy_matches_single_chunk_baseline(
    resampler_id: str, strategy_name: str
) -> None:
    spec = load_resampler_spec(resampler_id)
    rng = np.random.default_rng(hash((resampler_id, strategy_name)) % (2**32))
    n = 900
    x = rng.standard_normal(n)

    baseline_indices, baseline_values, baseline_resampler = _run_chunked(spec, x, [n])

    chunk_sizes = CHUNKING_STRATEGIES[strategy_name](n)
    assert sum(chunk_sizes) == n
    test_indices, test_values, test_resampler = _run_chunked(spec, x, chunk_sizes)

    assert np.array_equal(test_indices, baseline_indices)
    max_error = np.max(np.abs(test_values - baseline_values)) if len(test_values) else 0.0
    assert max_error <= TOLERANCE_ATOL, f"{strategy_name}: max chunk error {max_error}"
    assert test_resampler.state_metadata() == baseline_resampler.state_metadata()


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_polyphase_boundary_chunk_sizes(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    rng = np.random.default_rng(31)
    n = 3000
    x = rng.standard_normal(n)

    baseline_indices, baseline_values, _ = _run_chunked(spec, x, [n])
    chunk_sizes = _boundary_chunk_sizes(resampler_id, n)
    assert sum(chunk_sizes) == n
    test_indices, test_values, _ = _run_chunked(spec, x, chunk_sizes)

    assert np.array_equal(test_indices, baseline_indices)
    max_error = np.max(np.abs(test_values - baseline_values))
    assert max_error <= TOLERANCE_ATOL


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
@pytest.mark.parametrize("n", [0, 1, 2, 3, 10, 100, 1000, 4999, 10007])
def test_output_length_matches_expected_formula(resampler_id: str, n: int) -> None:
    spec = load_resampler_spec(resampler_id)
    rng = np.random.default_rng(n)
    x = rng.standard_normal(n) if n else np.array([])
    resampler = StatefulRationalResampler(spec)
    chunk = resampler.process(x, 0)
    assert len(chunk.values) == expected_output_count(n, spec.up, spec.down)


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_no_future_zero_padding_by_default(resampler_id: str) -> None:
    """A finite source prefix must not emit output beyond what its causal source requirements
    already permit -- no implicit zero-padded tail."""
    spec = load_resampler_spec(resampler_id)
    x = np.ones(spec.down * 3)
    resampler = StatefulRationalResampler(spec)
    chunk = resampler.process(x, 0)
    assert len(chunk.values) == expected_output_count(len(x), spec.up, spec.down)
    max_valid_source_index = len(x) - 1
    for m in chunk.output_indices:
        n_max = (int(m) * spec.down) // spec.up
        assert n_max <= max_valid_source_index
