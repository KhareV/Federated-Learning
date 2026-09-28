"""Reset behavior, noncontiguous-input rejection, bounded memory, and determinism."""

from __future__ import annotations

import numpy as np
import pytest

from preprocessing.resample import (
    NoncontiguousSourceInputError,
    StatefulRationalResampler,
    load_resampler_spec,
)

RESAMPLER_IDS = ["MITDB_360_TO_250_V1", "INCART_257_TO_250_V1"]
TOLERANCE_ATOL = 1e-9


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_reset_matches_fresh_resampler_on_segment_b(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    rng = np.random.default_rng(123)
    segment_a = rng.standard_normal(400)
    segment_b = rng.standard_normal(500)

    resampler = StatefulRationalResampler(spec)
    resampler.process(segment_a, 0)
    resampler.reset()
    chunk_after_reset = resampler.process(segment_b, 0)

    fresh_resampler = StatefulRationalResampler(spec)
    fresh_chunk = fresh_resampler.process(segment_b, 0)

    assert np.array_equal(chunk_after_reset.output_indices, fresh_chunk.output_indices)
    max_error = np.max(np.abs(chunk_after_reset.values - fresh_chunk.values))
    assert max_error <= TOLERANCE_ATOL
    assert resampler.state_metadata() == fresh_resampler.state_metadata()


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_reset_accepts_new_segment_start_timestamp(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    resampler = StatefulRationalResampler(spec, segment_start_timestamp_us=0)
    resampler.process(np.ones(50), 0)
    resampler.reset(segment_start_timestamp_us=999_000)
    chunk = resampler.process(np.ones(50), 0)
    assert chunk.timestamps_us[0] == 999_000


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_noncontiguous_source_input_is_rejected(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    resampler = StatefulRationalResampler(spec)
    resampler.process(np.ones(100), 0)
    with pytest.raises(NoncontiguousSourceInputError, match="NONCONTIGUOUS_SOURCE_INPUT"):
        resampler.process(np.ones(50), 105)


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_noncontiguous_input_does_not_silently_bridge_the_gap(resampler_id: str) -> None:
    """After a rejected call, state must be unchanged -- the gap is never silently treated as
    present (T012 decides how to repair/reset around it)."""
    spec = load_resampler_spec(resampler_id)
    resampler = StatefulRationalResampler(spec)
    resampler.process(np.ones(100), 0)
    state_before = resampler.state_metadata()
    with pytest.raises(NoncontiguousSourceInputError):
        resampler.process(np.ones(50), 999)
    assert resampler.state_metadata() == state_before


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_first_call_establishes_origin_at_any_nonzero_start(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    resampler = StatefulRationalResampler(spec)
    resampler.process(np.ones(10), 500)
    resampler.process(np.ones(10), 510)  # contiguous with the established origin
    assert resampler.state_metadata()["next_expected_source_index"] == 520


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_retained_history_is_bounded_regardless_of_stream_length(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    resampler = StatefulRationalResampler(spec)
    rng = np.random.default_rng(7)

    max_retained = 0
    chunk_size = 977  # prime, deliberately misaligned with up/down
    num_chunks = 50
    for chunk_index in range(num_chunks):
        block = rng.standard_normal(chunk_size)
        resampler.process(block, chunk_index * chunk_size)
        max_retained = max(max_retained, resampler.state_metadata()["retained_history_length"])

    total_processed = num_chunks * chunk_size
    assert resampler.state_metadata()["input_samples_seen"] == total_processed
    assert max_retained == resampler.state_metadata()["retained_history_length"]
    assert max_retained < 50, f"retained history {max_retained} grew with stream length"


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_retained_history_length_is_fixed_at_construction(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    resampler = StatefulRationalResampler(spec)
    before = resampler.state_metadata()["retained_history_length"]
    resampler.process(np.ones(10_000), 0)
    after = resampler.state_metadata()["retained_history_length"]
    assert before == after


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_determinism_across_fresh_instances(resampler_id: str) -> None:
    spec_a = load_resampler_spec(resampler_id)
    spec_b = load_resampler_spec(resampler_id)
    assert spec_a.coefficient_sha256 == spec_b.coefficient_sha256

    rng_a = np.random.default_rng(2026)
    rng_b = np.random.default_rng(2026)
    x_a = rng_a.standard_normal(700)
    x_b = rng_b.standard_normal(700)
    assert np.array_equal(x_a, x_b)

    resampler_a = StatefulRationalResampler(spec_a, segment_start_timestamp_us=0)
    resampler_b = StatefulRationalResampler(spec_b, segment_start_timestamp_us=0)
    chunk_a = resampler_a.process(x_a, 0)
    chunk_b = resampler_b.process(x_b, 0)

    assert np.array_equal(chunk_a.output_indices, chunk_b.output_indices)
    assert np.array_equal(chunk_a.values, chunk_b.values)
    assert np.array_equal(chunk_a.timestamps_us, chunk_b.timestamps_us)
    assert resampler_a.state_metadata() == resampler_b.state_metadata()


@pytest.mark.parametrize("resampler_id", RESAMPLER_IDS)
def test_state_metadata_contract_fields_present(resampler_id: str) -> None:
    spec = load_resampler_spec(resampler_id)
    resampler = StatefulRationalResampler(spec)
    resampler.process(np.ones(100), 0)
    metadata = resampler.state_metadata()
    required_fields = {
        "resampler_id", "preproc_id", "input_rate_hz", "output_rate_hz", "up", "down",
        "coefficient_sha256", "group_delay_seconds", "group_delay_output_samples",
        "input_samples_seen", "next_expected_source_index", "output_samples_emitted",
        "next_output_index", "retained_history_length", "state_initialization",
        "timestamp_mapping_id",
    }
    assert required_fields <= set(metadata)
    assert "history" not in metadata  # no raw buffer exposed
    assert metadata["state_initialization"] == "ZERO_FIR_HISTORY_AT_SEGMENT_START"
    assert metadata["timestamp_mapping_id"] == "CAUSAL_OUTPUT_GRID_V1"


def test_nonfinite_samples_are_rejected() -> None:
    spec = load_resampler_spec("MITDB_360_TO_250_V1")
    resampler = StatefulRationalResampler(spec)
    with pytest.raises(ValueError, match="NONFINITE_SOURCE_SAMPLE"):
        resampler.process(np.array([1.0, float("nan"), 1.0]), 0)


def test_non_1d_samples_are_rejected() -> None:
    spec = load_resampler_spec("MITDB_360_TO_250_V1")
    resampler = StatefulRationalResampler(spec)
    with pytest.raises(ValueError, match="1-D"):
        resampler.process(np.ones((10, 2)), 0)
