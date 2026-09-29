"""ECG filter identity, stability, causality (future-append, chunk-equivalence, impulse,
one-shot causal reference), reset, and the forbidden zero-phase API audit. Tolerance:
atol=1e-12 for streaming-vs-one-shot-sosfilt comparisons (both use the same scipy sosfilt
primitive, so equality is exact in practice -- see observed error below)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import scipy.signal as sig

from preprocessing.filters import StatefulSOSFilter, load_filter_spec

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE_ATOL = 1e-12


def test_ecg_filter_identity() -> None:
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    assert spec.signal == "ECG"
    assert spec.fs_hz == 250.0
    assert spec.band_hz == (0.5, 40.0)
    assert spec.butterworth_prototype_order == 4
    assert spec.total_order == 8
    assert spec.sos_sections == 4


def test_ecg_sos_coefficients_finite_and_float64() -> None:
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    assert spec.sos.dtype == np.float64
    assert np.all(np.isfinite(spec.sos))
    assert spec.sos.shape == (4, 6)


def test_ecg_filter_poles_are_stable() -> None:
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    _, poles, _ = sig.sos2zpk(np.array(spec.sos))
    assert np.all(np.abs(poles) < 1.0)


def test_ecg_coefficient_hash_matches_manifest() -> None:
    import json

    manifest = json.loads(
        (ROOT / "preprocessing/coefficients/manifest.json").read_text(encoding="utf-8")
    )
    entry = manifest["filters"]["entries"]["PREPROC_V1_ECG_FILTER_V1"]
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    assert spec.coefficient_sha256 == entry["coefficient_sha256"]


def test_ecg_filter_matches_one_shot_sosfilt_reference() -> None:
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    rng = np.random.default_rng(1)
    x = rng.standard_normal(2000)
    filt = StatefulSOSFilter(spec)
    y = filt.process(x)
    y_ref, _ = sig.sosfilt(np.array(spec.sos), x, zi=np.zeros((spec.sos_sections, 2)))
    max_error = np.max(np.abs(y - y_ref))
    assert max_error <= TOLERANCE_ATOL


def test_ecg_filter_future_append_does_not_change_earlier_output() -> None:
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    rng = np.random.default_rng(2)
    prefix = rng.standard_normal(500)
    baseline = StatefulSOSFilter(spec)
    y_prefix = baseline.process(prefix)

    for suffix in (np.full(300, 1e6), rng.standard_normal(300) * 1e6):
        full = np.concatenate([prefix, suffix])
        fresh = StatefulSOSFilter(spec)
        y_full = fresh.process(full)
        max_error = np.max(np.abs(y_full[: len(y_prefix)] - y_prefix))
        assert max_error <= TOLERANCE_ATOL


@pytest.mark.parametrize(
    "chunk_sizes_name,chunk_sizes",
    [
        ("single", None),
        ("one_sample", [1] * 900),
        ("small_regular", [4] * 225),
        ("prime", None),
    ],
)
def test_ecg_filter_chunk_equivalence(chunk_sizes_name: str, chunk_sizes) -> None:
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    rng = np.random.default_rng(3)
    n = 900
    x = rng.standard_normal(n)

    baseline = StatefulSOSFilter(spec)
    y_baseline = baseline.process(x)

    if chunk_sizes_name == "single":
        sizes = [n]
    elif chunk_sizes_name == "prime":
        cycle = [7, 11, 13, 17, 19, 23]
        sizes, remaining, i = [], n, 0
        while remaining > 0:
            size = min(cycle[i % len(cycle)], remaining)
            sizes.append(size)
            remaining -= size
            i += 1
    else:
        sizes = chunk_sizes

    test_filter = StatefulSOSFilter(spec)
    parts = []
    index = 0
    for size in sizes:
        parts.append(test_filter.process(x[index : index + size]))
        index += size
    y_test = np.concatenate(parts)

    assert len(y_test) == len(y_baseline)
    max_error = np.max(np.abs(y_test - y_baseline))
    assert max_error <= TOLERANCE_ATOL
    assert test_filter.state_metadata()["samples_seen"] == baseline.state_metadata()["samples_seen"]


def test_ecg_filter_impulse_causality_no_pre_ringing() -> None:
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    x = np.zeros(300)
    x[100] = 1.0
    filt = StatefulSOSFilter(spec)
    y = filt.process(x)
    assert np.max(np.abs(y[:100])) == 0.0


def test_ecg_filter_reset_matches_fresh_instance() -> None:
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    rng = np.random.default_rng(4)
    filt = StatefulSOSFilter(spec)
    filt.process(rng.standard_normal(400) * 1e6)
    filt.reset(segment_id=7)

    quiet = np.full(200, 0.001)
    y_reset = filt.process(quiet)

    fresh = StatefulSOSFilter(spec)
    y_fresh = fresh.process(quiet)

    assert np.max(np.abs(y_reset - y_fresh)) <= TOLERANCE_ATOL
    assert filt.state_metadata()["segment_id"] == 7


def test_ecg_dc_input_is_strongly_attenuated() -> None:
    """Filter-design validation only (0.5 Hz high-pass edge), not a clinical threshold."""
    spec = load_filter_spec("PREPROC_V1_ECG_FILTER_V1")
    x = np.full(5000, 10.0)
    filt = StatefulSOSFilter(spec)
    y = filt.process(x)
    assert abs(y[-1]) < 0.01 * 10.0


def test_ecg_module_does_not_use_zero_phase_or_alternate_resample_apis() -> None:
    for path in ["preprocessing/ecg.py", "preprocessing/filters.py"]:
        source = (ROOT / path).read_text(encoding="utf-8")
        for forbidden in (
            "filtfilt(", "sosfiltfilt(", "signal.resample(", "signal.resample_poly(",
        ):
            assert forbidden not in source, f"{path}: forbidden API {forbidden}"
