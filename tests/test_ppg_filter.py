"""PPG filter identity, stability, causality, chunk equivalence, reset, and independent
red/IR channel state. Tolerance: atol=1e-12 (same basis as tests/test_ecg_filter.py)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import scipy.signal as sig

from preprocessing.filters import StatefulSOSFilter, load_filter_spec
from preprocessing.ppg import CHANNEL_IR, CHANNEL_RED, DualChannelPPGFilter, StatefulPPGFilter

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE_ATOL = 1e-12


def test_ppg_filter_identity() -> None:
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    assert spec.signal == "PPG"
    assert spec.fs_hz == 100.0
    assert spec.band_hz == (0.5, 8.0)
    assert spec.butterworth_prototype_order == 4
    assert spec.total_order == 8
    assert spec.sos_sections == 4


def test_stateful_ppg_filter_rejects_wrong_filter_id() -> None:
    ecg_spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    try:
        StatefulPPGFilter(ecg_spec)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_ppg_sos_coefficients_finite_and_float64() -> None:
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    assert spec.sos.dtype == np.float64
    assert np.all(np.isfinite(spec.sos))


def test_ppg_filter_poles_are_stable() -> None:
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    _, poles, _ = sig.sos2zpk(np.array(spec.sos))
    assert np.all(np.abs(poles) < 1.0)


def test_ppg_coefficient_hash_matches_manifest() -> None:
    manifest = json.loads(
        (ROOT / "preprocessing/coefficients/manifest.json").read_text(encoding="utf-8")
    )
    entry = manifest["filters"]["entries"]["PREPROC_V1_PPG_FILTER_V1"]
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    assert spec.coefficient_sha256 == entry["coefficient_sha256"]


def test_ppg_filter_matches_one_shot_sosfilt_reference() -> None:
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    rng = np.random.default_rng(11)
    x = rng.standard_normal(1500)
    filt = StatefulSOSFilter(spec)
    y = filt.process(x)
    y_ref, _ = sig.sosfilt(np.array(spec.sos), x, zi=np.zeros((spec.sos_sections, 2)))
    assert np.max(np.abs(y - y_ref)) <= TOLERANCE_ATOL


def test_ppg_filter_future_append_does_not_change_earlier_output() -> None:
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    rng = np.random.default_rng(12)
    prefix = rng.standard_normal(400)
    baseline = StatefulSOSFilter(spec)
    y_prefix = baseline.process(prefix)

    full = np.concatenate([prefix, np.full(300, 1e6)])
    fresh = StatefulSOSFilter(spec)
    y_full = fresh.process(full)
    assert np.max(np.abs(y_full[: len(y_prefix)] - y_prefix)) <= TOLERANCE_ATOL


def test_ppg_filter_chunk_equivalence() -> None:
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    rng = np.random.default_rng(13)
    n = 700
    x = rng.standard_normal(n)

    baseline = StatefulSOSFilter(spec)
    y_baseline = baseline.process(x)

    test_filter = StatefulSOSFilter(spec)
    cycle = [1, 2, 3, 7, 11]
    parts, index, cursor = [], 0, 0
    while index < n:
        size = min(cycle[cursor % len(cycle)], n - index)
        parts.append(test_filter.process(x[index : index + size]))
        index += size
        cursor += 1
    y_test = np.concatenate(parts)

    assert len(y_test) == len(y_baseline)
    assert np.max(np.abs(y_test - y_baseline)) <= TOLERANCE_ATOL


def test_ppg_filter_impulse_causality_no_pre_ringing() -> None:
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    x = np.zeros(200)
    x[80] = 1.0
    filt = StatefulSOSFilter(spec)
    y = filt.process(x)
    assert np.max(np.abs(y[:80])) == 0.0


def test_ppg_filter_reset_matches_fresh_instance() -> None:
    spec = load_filter_spec("PREPROC_V1_PPG_FILTER_V1")
    rng = np.random.default_rng(14)
    filt = StatefulSOSFilter(spec)
    filt.process(rng.standard_normal(300) * 1e6)
    filt.reset()
    quiet = np.full(150, 0.001)
    y_reset = filt.process(quiet)

    fresh = StatefulSOSFilter(spec)
    y_fresh = fresh.process(quiet)
    assert np.max(np.abs(y_reset - y_fresh)) <= TOLERANCE_ATOL


def test_dual_channel_red_and_ir_are_never_mixed() -> None:
    dual = DualChannelPPGFilter()
    red_input = np.full(100, 5.0)
    ir_input = np.full(100, 5.0)
    red_output = dual.process(CHANNEL_RED, red_input)
    ir_output = dual.process(CHANNEL_IR, ir_input)
    # identical inputs through independent filters with identical design -> identical output;
    # the point is that each channel keeps its OWN state, proven by divergence below
    assert np.array_equal(red_output, ir_output)

    dual2 = DualChannelPPGFilter()
    dual2.process(CHANNEL_RED, np.full(50, 1e6))
    dual2.process(CHANNEL_IR, np.full(50, 1e-6))
    red_after = dual2.process(CHANNEL_RED, np.zeros(20))
    ir_after = dual2.process(CHANNEL_IR, np.zeros(20))
    assert not np.array_equal(red_after, ir_after)


def test_dual_channel_reset_resets_both_channels() -> None:
    dual = DualChannelPPGFilter()
    dual.process(CHANNEL_RED, np.full(50, 1e6))
    dual.process(CHANNEL_IR, np.full(50, 1e6))
    dual.reset(segment_id=3)
    metadata = dual.state_metadata()
    assert metadata[CHANNEL_RED]["samples_seen"] == 0
    assert metadata[CHANNEL_IR]["samples_seen"] == 0
    assert metadata[CHANNEL_RED]["segment_id"] == 3
    assert metadata[CHANNEL_IR]["segment_id"] == 3


def test_dual_channel_rejects_unknown_channel() -> None:
    dual = DualChannelPPGFilter()
    try:
        dual.process("GREEN", np.zeros(10))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_ppg_module_does_not_use_zero_phase_or_resample_apis() -> None:
    source = (ROOT / "preprocessing/ppg.py").read_text(encoding="utf-8")
    for forbidden in ("filtfilt(", "sosfiltfilt(", "signal.resample(", "signal.resample_poly("):
        assert forbidden not in source


def test_ppg_module_introduces_no_125_to_100_resampling() -> None:
    """T012 must not silently add BIDMC 125->100 resampling scope: no new resampler
    identifier or resampler import referencing a 125 Hz source rate."""
    source = (ROOT / "preprocessing/ppg.py").read_text(encoding="utf-8")
    assert "125_TO_100" not in source
    assert "StatefulRationalResampler" not in source
    assert "load_resampler_spec" not in source
