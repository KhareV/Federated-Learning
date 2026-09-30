from __future__ import annotations

import numpy as np

from simulation.quality_perturbations import (
    apply_ecg_perturbation,
    derived_seed,
    experiment_interval,
    perturb_context,
)


def test_seed_derivation_is_stable_and_namespaced() -> None:
    first = derived_seed("BIDMC", "one", "ECG_NOISE_0DB")
    assert first == derived_seed("BIDMC", "one", "ECG_NOISE_0DB")
    assert first != derived_seed("BIDMC", "two", "ECG_NOISE_0DB")


def test_interval_is_predeclared_and_aligned() -> None:
    interval = experiment_interval(600_000_000)
    assert interval.perturb_start_us == 120_000_000
    assert interval.perturb_end_us == 180_000_000
    assert interval.analysis_start_us == 90_000_000
    assert interval.analysis_end_us == 240_000_000


def test_ecg_clipping_has_explicit_mask() -> None:
    source = np.linspace(-1, 1, 250 * 300)
    interval = experiment_interval(300_000_000)
    changed, clipping, gap = apply_ecg_perturbation(
        source, sample_rate_hz=250, interval=interval, scenario_id="ECG_CLIPPING", seed=1
    )
    assert clipping.sum() == 60 * 250
    assert not gap.any()
    assert len(np.unique(changed[clipping])) == 2


def test_ecg_dropout_is_long_gap_not_interpolation() -> None:
    source = np.ones(250 * 300)
    interval = experiment_interval(300_000_000)
    changed, clipping, gap = apply_ecg_perturbation(
        source, sample_rate_hz=250, interval=interval, scenario_id="ECG_DROPOUT", seed=1
    )
    assert gap.sum() == 10 * 250
    assert np.isnan(changed[gap]).all()
    assert not clipping.any()


def test_noise_is_deterministic_zero_db() -> None:
    source = np.ones(250 * 300)
    interval = experiment_interval(300_000_000)
    one, _, _ = apply_ecg_perturbation(
        source, sample_rate_hz=250, interval=interval, scenario_id="ECG_NOISE_0DB", seed=7
    )
    two, _, _ = apply_ecg_perturbation(
        source, sample_rate_hz=250, interval=interval, scenario_id="ECG_NOISE_0DB", seed=7
    )
    assert np.array_equal(one, two)
    start, end = 120 * 250, 180 * 250
    noise = one[start:end] - source[start:end]
    assert np.isclose(np.sqrt(np.mean(noise**2)), 1.0)


def test_context_perturbations_preserve_ecg_fields() -> None:
    interval = experiment_interval(300_000_000)
    base = dict(
        ppg_quality="VALID",
        spo2_pct=98.0,
        spo2_valid=True,
        hr_ecg_bpm=70.0,
        pr_ppg_bpm=70.0,
    )
    clipped = perturb_context("PPG_CLIPPING", 125_000_000, interval, **base)
    assert clipped["ppg_quality"] == "UNUSABLE" and clipped["hr_ecg_bpm"] == 70
    missing = perturb_context("MISSING_PPG", 125_000_000, interval, **base)
    assert missing["ppg_quality"] is None and missing["pr_ppg_bpm"] is None
    spo2 = perturb_context("SPO2_UNAVAILABLE", 125_000_000, interval, **base)
    assert not spo2["spo2_valid"] and spo2["spo2_pct"] is None
    mismatch = perturb_context("CROSS_MODAL_RATE_DISAGREEMENT", 125_000_000, interval, **base)
    assert abs(mismatch["hr_ecg_bpm"] - mismatch["pr_ppg_bpm"]) == 30
